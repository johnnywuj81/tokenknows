"""_compute_similarity_to_history (async) 单测 · mock embed_batch.

覆盖 5 个关键路径:
  1. no_history    项目内无其它 asset → 返回 0.0
  2. self_excluded 当前 asset 不参与对比 (避免自相似 1.0 假阳性)
  3. max_cosine    多个 prior 取最相似那个 + 返回其 id
  4. embedding_fail embed_batch 抛错 → 优雅返回 0.0 + method="embedding_unavailable"
  5. no_chapters_prior 历史 asset 没 chapter → 跳过 (不参与对比)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from app.schemas.asset import Asset, Chapter
from app.services.generation_service import (
    _assets,
    _chapters,
    _compute_similarity_to_history,
)


# ─── Fixtures ────────────────────────────────────────────────────────


def _make_asset(asset_id: str, project_id: str, title: str = "title") -> Asset:
    return Asset(
        id=asset_id,
        project_id=project_id,
        type="weekly_report",
        title=title,
        status="draft",
        current_version=1,
        template_id="tpl-test",
        created_by="anon",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_chapter(asset_id: str, idx: int, title: str, content: str) -> Chapter:
    return Chapter(
        id=f"ch-{asset_id}-{idx}",
        asset_id=asset_id,
        order_index=idx,
        title=title,
        content=content,
    )


@pytest.fixture(autouse=True)
def _clean_global_state() -> Any:
    """每个 test 用完清空全局 _assets / _chapters 防污染."""
    snapshot_assets = dict(_assets)
    snapshot_chapters = dict(_chapters)
    _assets.clear()
    _chapters.clear()
    yield
    _assets.clear()
    _chapters.clear()
    _assets.update(snapshot_assets)
    _chapters.update(snapshot_chapters)


def _register(asset: Asset, chapters: list[Chapter]) -> None:
    _assets[asset.id] = asset
    _chapters[asset.id] = chapters


# ─── 测试用例 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_history_returns_zero() -> None:
    """项目内只有当前 asset → similarity = 0.0, method=no_history."""
    a = _make_asset("a1", "proj-1")
    chs = [_make_chapter("a1", 0, "T", "C")]
    _register(a, chs)

    sim, method, most = await _compute_similarity_to_history(a, chs)
    assert sim == 0.0
    assert method == "no_history"
    assert most is None


@pytest.mark.asyncio
async def test_cross_project_assets_ignored() -> None:
    """同一 instance 别的 project 的 asset 不参与对比."""
    a = _make_asset("a1", "proj-1")
    _register(a, [_make_chapter("a1", 0, "T", "C")])
    other = _make_asset("a2", "proj-OTHER")
    _register(other, [_make_chapter("a2", 0, "T", "C")])

    sim, method, _ = await _compute_similarity_to_history(a, _chapters["a1"])
    assert sim == 0.0
    assert method == "no_history"


@pytest.mark.asyncio
async def test_self_excluded_from_comparison() -> None:
    """当前 asset.id 不会被拿来跟自己 cos (否则 sim=1.0 假阳性)."""
    a = _make_asset("a1", "proj-1")
    _register(a, [_make_chapter("a1", 0, "T", "C")])
    # 没有其它 asset → 直接 no_history
    sim, method, _ = await _compute_similarity_to_history(a, _chapters["a1"])
    assert sim == 0.0
    assert method == "no_history"


@pytest.mark.asyncio
async def test_max_cosine_picks_most_similar() -> None:
    """3 个 prior, 返回 cosine 最高那个 id."""
    a_current = _make_asset("a-cur", "proj-1")
    _register(a_current, [_make_chapter("a-cur", 0, "T", "C")])

    a_close = _make_asset("a-close", "proj-1")
    _register(a_close, [_make_chapter("a-close", 0, "T", "C")])

    a_mid = _make_asset("a-mid", "proj-1")
    _register(a_mid, [_make_chapter("a-mid", 0, "T", "C")])

    a_far = _make_asset("a-far", "proj-1")
    _register(a_far, [_make_chapter("a-far", 0, "T", "C")])

    # Mock embed_batch 返回固定 vectors
    #   current ≈ a-close (cos~0.99) > a-mid (cos~0.6) > a-far (cos~0.1)
    async def fake_embed(texts: list[str], model: str | None = None) -> list[list[float]]:
        return [
            [1.0, 0.0, 0.0],   # current
            [0.99, 0.14, 0.0],   # a-close (high cos)
            [0.6, 0.8, 0.0],     # a-mid
            [0.1, 0.99, 0.0],    # a-far
        ]

    with patch(
        "app.llm_gateway.embedding.embed_batch",
        side_effect=fake_embed,
    ):
        sim, method, most = await _compute_similarity_to_history(
            a_current, _chapters["a-cur"],
        )

    assert method == "max_cosine_to_history"
    assert most == "a-close"
    assert sim > 0.9    # cos(current, a-close) very high


@pytest.mark.asyncio
async def test_embedding_failure_returns_unavailable() -> None:
    """embed_batch 抛任何异常 → 优雅 fallback."""
    a = _make_asset("a-cur", "proj-1")
    _register(a, [_make_chapter("a-cur", 0, "T", "C")])
    prior = _make_asset("a-prior", "proj-1")
    _register(prior, [_make_chapter("a-prior", 0, "T", "C")])

    async def boom(texts: list[str], model: str | None = None) -> list[list[float]]:
        raise RuntimeError("ollama unreachable")

    with patch(
        "app.llm_gateway.embedding.embed_batch",
        side_effect=boom,
    ):
        sim, method, most = await _compute_similarity_to_history(
            a, _chapters["a-cur"],
        )

    assert sim == 0.0
    assert method == "embedding_unavailable"
    assert most is None


@pytest.mark.asyncio
async def test_prior_without_chapters_skipped() -> None:
    """历史 asset 没 chapter (extreme corner case) → 跳过对比."""
    a = _make_asset("a-cur", "proj-1")
    _register(a, [_make_chapter("a-cur", 0, "T", "C")])
    prior = _make_asset("a-empty", "proj-1")
    _chapters[prior.id] = []   # 没章节
    _assets[prior.id] = prior

    # 没有其它有效 prior → no_history (即使 _assets 字典里有)
    sim, method, _ = await _compute_similarity_to_history(a, _chapters["a-cur"])
    assert sim == 0.0
    assert method == "no_history"


@pytest.mark.asyncio
async def test_embed_batch_called_with_current_first() -> None:
    """embed_batch 第一条 text 必须是 current asset (索引依赖)."""
    a_cur = _make_asset("a-cur", "proj-1", title="独特标题甲乙丙")
    _register(a_cur, [_make_chapter("a-cur", 0, "cur_chapter", "cur_content")])
    a_prior = _make_asset("a-prior", "proj-1", title="历史标题")
    _register(a_prior, [_make_chapter("a-prior", 0, "prior_ch", "prior_content")])

    captured: dict[str, list[str]] = {}

    async def capture_embed(texts: list[str], model: str | None = None) -> list[list[float]]:
        captured["texts"] = list(texts)
        return [[1.0, 0.0], [0.5, 0.5]]

    with patch(
        "app.llm_gateway.embedding.embed_batch",
        side_effect=capture_embed,
    ):
        await _compute_similarity_to_history(a_cur, _chapters["a-cur"])

    assert len(captured["texts"]) == 2
    # 第 1 条是 current outline
    assert "独特标题甲乙丙" in captured["texts"][0]
    assert "cur_chapter" in captured["texts"][0]
    # 第 2 条是 prior
    assert "历史标题" in captured["texts"][1]


@pytest.mark.asyncio
async def test_empty_vectors_returns_unavailable() -> None:
    """embed_batch 返回空 list 或 < 2 条 → 视为不可用."""
    a = _make_asset("a-cur", "proj-1")
    _register(a, [_make_chapter("a-cur", 0, "T", "C")])
    prior = _make_asset("a-prior", "proj-1")
    _register(prior, [_make_chapter("a-prior", 0, "T", "C")])

    async def empty_embed(texts: list[str], model: str | None = None) -> list[list[float]]:
        return []

    with patch(
        "app.llm_gateway.embedding.embed_batch",
        side_effect=empty_embed,
    ):
        sim, method, _ = await _compute_similarity_to_history(a, _chapters["a-cur"])

    assert sim == 0.0
    assert method == "embedding_unavailable"
