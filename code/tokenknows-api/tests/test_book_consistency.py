"""Book consistency_score (v0.2 · _stage_assess 跨章连贯度).

覆盖:
- _compute_book_consistency: 同卷相邻章 cosine 均值
- 不同卷的章不混算
- 单章卷不参与计算
- embedding 失败 → None + method=embedding_unavailable
- 无相邻对 → None + method=no_pairs
- AssetMetrics.consistency_score 可选 (None / 非 None)
- _stage_assess 在 type=book 时填充 consistency_score
- _stage_assess 在 type=weekly_report 时跳过 (consistency=None)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset, AssetMetrics, Chapter
from app.schemas.generation import GenerateAssetRequest
from app.services import generation_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._progress.clear()
    generation_service._evidence_by_chapter.clear()
    yield new_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_ch(
    id: str, asset_id: str = "a1", depth: int = 1,
    parent_id: str | None = None, order_index: int = 0,
    content: str = "内容 " * 50,
) -> Chapter:
    return Chapter(
        id=id, asset_id=asset_id, asset_version=1,
        order_index=order_index, depth=depth, parent_id=parent_id,
        title=f"标题 {id}", content=content,
    )


# ─── AssetMetrics schema ────────────────────────────────────


def test_asset_metrics_consistency_optional() -> None:
    m = AssetMetrics(
        coverage=0.5, citation_density=0.5,
        slop_score=0.1, similarity=0.0,
    )
    assert m.consistency_score is None


def test_asset_metrics_consistency_clamped() -> None:
    """0-1 边界."""
    with pytest.raises(Exception):
        AssetMetrics(
            coverage=0.5, citation_density=0.5,
            slop_score=0.1, similarity=0.0,
            consistency_score=1.5,
        )


# ─── _compute_book_consistency ───────────────────────────────


@pytest.mark.asyncio
async def test_consistency_no_chapters_returns_none() -> None:
    score, method = await generation_service._compute_book_consistency([])
    assert score is None
    assert method == "no_pairs"


@pytest.mark.asyncio
async def test_consistency_single_chapter_per_volume_no_pairs() -> None:
    """每卷只有 1 章 → 无相邻对."""
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1),
        _make_ch("v2", depth=0, parent_id=None, order_index=2),
        _make_ch("v2-c1", depth=1, parent_id="v2", order_index=3),
    ]
    score, method = await generation_service._compute_book_consistency(chapters)
    assert score is None
    assert method == "no_pairs"


@pytest.mark.asyncio
async def test_consistency_happy_path_two_adjacent_chapters() -> None:
    """2 章相邻 → embed_batch 返 2*2 向量, 计算 cosine 均值."""
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1, content="A " * 100),
        _make_ch("v1-c2", depth=1, parent_id="v1", order_index=2, content="B " * 100),
    ]
    # 模拟相邻章 cosine = 0.8 (向量近似)
    with patch(
        "app.llm_gateway.embedding.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0], [0.8, 0.6]]),  # cos ≈ 0.8
    ):
        score, method = await generation_service._compute_book_consistency(chapters)
    assert score is not None
    assert 0.79 < score < 0.81
    assert method == "adjacent_chapter_cosine"


@pytest.mark.asyncio
async def test_consistency_isolates_by_volume() -> None:
    """v1 的章和 v2 的章不参与同一对."""
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1, content="同卷 1"),
        _make_ch("v1-c2", depth=1, parent_id="v1", order_index=2, content="同卷 2"),
        _make_ch("v2", depth=0, parent_id=None, order_index=3),
        _make_ch("v2-c1", depth=1, parent_id="v2", order_index=4, content="另卷 1"),
        _make_ch("v2-c2", depth=1, parent_id="v2", order_index=5, content="另卷 2"),
    ]
    # 4 个章节 = 2 对 = 4 个 embedding (a,b,a,b)
    calls = {"texts": None}

    async def fake_embed(texts):
        calls["texts"] = list(texts)
        # 每对返回 cos=1.0 (相同向量)
        return [[1.0, 0.0]] * len(texts)

    with patch("app.llm_gateway.embedding.embed_batch", new=fake_embed):
        score, _ = await generation_service._compute_book_consistency(chapters)
    # 验证只有 4 段被 embed (2 对 × 2 段), 没有 v1-c2 vs v2-c1
    assert len(calls["texts"]) == 4
    assert score == 1.0


@pytest.mark.asyncio
async def test_consistency_embedding_failure_returns_none() -> None:
    from app.llm_gateway.embedding import EmbeddingError
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1, content="A"),
        _make_ch("v1-c2", depth=1, parent_id="v1", order_index=2, content="B"),
    ]
    with patch(
        "app.llm_gateway.embedding.embed_batch",
        side_effect=EmbeddingError("ollama down"),
    ):
        score, method = await generation_service._compute_book_consistency(chapters)
    assert score is None
    assert method == "embedding_unavailable"


@pytest.mark.asyncio
async def test_consistency_embedding_length_mismatch_returns_none() -> None:
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1, content="A"),
        _make_ch("v1-c2", depth=1, parent_id="v1", order_index=2, content="B"),
    ]
    # 返回 1 个向量 ≠ 2
    with patch(
        "app.llm_gateway.embedding.embed_batch",
        new=AsyncMock(return_value=[[1.0]]),
    ):
        score, method = await generation_service._compute_book_consistency(chapters)
    assert score is None
    assert method == "embedding_unavailable"


@pytest.mark.asyncio
async def test_consistency_skips_volume_chapters() -> None:
    """depth=0 的卷本身不进入计算."""
    chapters = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0, content="卷正文"),
        _make_ch("v2", depth=0, parent_id=None, order_index=1, content="另一卷"),
    ]
    score, method = await generation_service._compute_book_consistency(chapters)
    # 卷自身不算 → no_pairs
    assert score is None
    assert method == "no_pairs"


# ─── _stage_assess 集成 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_assess_book_includes_consistency() -> None:
    asset = Asset(
        id="a1", project_id="p1", type="book", title="书",
        status="generating", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets["a1"] = asset
    generation_service._progress["a1"] = generation_service._initial_progress("a1")
    generation_service._chapters["a1"] = [
        _make_ch("v1", depth=0, parent_id=None, order_index=0),
        _make_ch("v1-c1", depth=1, parent_id="v1", order_index=1),
        _make_ch("v1-c2", depth=1, parent_id="v1", order_index=2),
    ]
    # mock slop LLM + similarity embed + book consistency embed
    with patch(
        "app.services.generation_service._assess_slop_via_llm",
        new=AsyncMock(return_value=(0.15, "llm", "low slop")),
    ), patch(
        "app.services.generation_service._compute_similarity_to_history",
        new=AsyncMock(return_value=(0.0, "no_history", None)),
    ), patch(
        "app.llm_gateway.embedding.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0], [0.6, 0.8]]),
    ):
        result = await generation_service._stage_assess(
            "a1", GenerateAssetRequest(type="book", time_window="last_30_days"),
        )
    assert "consistency_score" in result
    assert result["consistency_score"] is not None
    assert result["_method"]["consistency_score"] == "adjacent_chapter_cosine"


@pytest.mark.asyncio
async def test_stage_assess_weekly_report_skips_consistency() -> None:
    asset = Asset(
        id="a2", project_id="p1", type="weekly_report", title="周报",
        status="generating", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets["a2"] = asset
    generation_service._progress["a2"] = generation_service._initial_progress("a2")
    generation_service._chapters["a2"] = [
        _make_ch("c1", asset_id="a2", depth=0, parent_id=None, order_index=0),
        _make_ch("c2", asset_id="a2", depth=0, parent_id=None, order_index=1),
    ]
    with patch(
        "app.services.generation_service._assess_slop_via_llm",
        new=AsyncMock(return_value=(0.1, "llm", "")),
    ), patch(
        "app.services.generation_service._compute_similarity_to_history",
        new=AsyncMock(return_value=(0.0, "no_history", None)),
    ):
        result = await generation_service._stage_assess(
            "a2",
            GenerateAssetRequest(type="weekly_report", time_window="last_7_days"),
        )
    # 非 book → consistency_score=None, _method 不含 consistency_score
    assert result["consistency_score"] is None
    assert "consistency_score" not in result["_method"]
