"""纯函数单测 · generation_service helpers.

覆盖近期新加 / 改的核心算法:
- _normalize_evidence_tags  ([N] 角标重编号)
- _build_outline_text       (asset outline → embedding input)
- _compute_recency          (时间衰减 30 天半衰期)
- _event_to_embed_text      (event → embedding 文本)
- _enforce_source_diversity (top-N 强行换 1 条非主源)

这些函数全是纯函数 (无 DB / 无网络), 跑得快, 不需要 fixture.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.asset import Chapter
from app.services.generation_service import (
    _build_outline_text,
    _compute_recency,
    _enforce_source_diversity,
    _enforce_source_diversity_scored,
    _event_to_embed_text,
    _normalize_evidence_tags,
)


# ─── _normalize_evidence_tags ───────────────────────────────────────


class TestNormalizeEvidenceTags:
    def test_consecutive_within_k_unchanged(self) -> None:
        """[1] [2] [3] 且 k=3: 全保留, 编号不变."""
        content = "段落 [1] 中间 [2] 末尾 [3]"
        new, count = _normalize_evidence_tags(content, k=3)
        assert new == "段落 [1] 中间 [2] 末尾 [3]"
        assert count == 3

    def test_skipped_numbers_get_renumbered(self) -> None:
        """LLM 输出 [1] [3] [5] 跳号 → 重编号为 [1] [2] [3]."""
        content = "A [1] B [3] C [5]"
        new, count = _normalize_evidence_tags(content, k=3)
        assert new == "A [1] B [2] C [3]"
        assert count == 3

    def test_excess_tags_stripped(self) -> None:
        """k=2 但 LLM 写了 4 个 → 留前两个, 后两个删掉避免死链."""
        content = "[1] [2] [3] [4]"
        new, count = _normalize_evidence_tags(content, k=2)
        assert new == "[1] [2]  "
        assert count == 4   # 发现了 4 个, 但只保留了 2 个

    def test_k_zero_strips_all(self) -> None:
        """没 evidence: 全剥光."""
        content = "[1] [2] [3]"
        new, _ = _normalize_evidence_tags(content, k=0)
        assert new == "  "

    def test_markdown_link_not_touched(self) -> None:
        """[text](url) markdown 链接不动."""
        content = "见 [文档](http://a) 第 [1] 节"
        new, count = _normalize_evidence_tags(content, k=1)
        assert new == "见 [文档](http://a) 第 [1] 节"
        assert count == 1

    def test_image_syntax_not_touched(self) -> None:
        """![alt](src) 图片语法不动."""
        content = "![图](img.png) 见 [1]"
        new, _ = _normalize_evidence_tags(content, k=1)
        assert "![图](img.png)" in new
        assert "[1]" in new

    def test_ref_link_not_touched(self) -> None:
        """[text][ref] 引用链接不动."""
        content = "见 [A][ref1] 和 [1]"
        new, _ = _normalize_evidence_tags(content, k=1)
        assert "[A][ref1]" in new
        assert "[1]" in new

    def test_empty_content(self) -> None:
        new, count = _normalize_evidence_tags("", k=3)
        assert new == ""
        assert count == 0


# ─── _build_outline_text ────────────────────────────────────────────


def _make_chapter(idx: int, title: str, content: str) -> Chapter:
    return Chapter(
        id=f"ch-{idx}",
        asset_id="asset-test",
        order_index=idx,
        title=title,
        content=content,
    )


class TestBuildOutlineText:
    def test_minimal(self) -> None:
        chs = [_make_chapter(0, "概述", "本周完成了登录页改造")]
        text = _build_outline_text("周报 W21", chs)
        assert "周报 W21" in text
        assert "概述" in text
        assert "本周完成了登录页改造" in text

    def test_multiple_chapters(self) -> None:
        chs = [
            _make_chapter(0, "概述", "本周亮点"),
            _make_chapter(1, "细节", "做了 A 和 B"),
            _make_chapter(2, "下周", "继续 C"),
        ]
        text = _build_outline_text("周报", chs)
        for needle in ("周报", "概述", "细节", "下周", "本周亮点", "做了 A 和 B", "继续 C"):
            assert needle in text

    def test_capped_at_1500(self) -> None:
        """超长 outline 截到 1500 字."""
        chs = [_make_chapter(0, "标题", "x" * 5000)]
        text = _build_outline_text("title", chs)
        assert len(text) <= 1500

    def test_empty_title_ok(self) -> None:
        chs = [_make_chapter(0, "ch", "content")]
        text = _build_outline_text("", chs)
        assert "ch" in text
        assert "content" in text

    def test_first_paragraph_only(self) -> None:
        """章节首段(\\n 分割的第一段) 截 200 字."""
        chs = [_make_chapter(0, "T", "第一段\n第二段不要")]
        text = _build_outline_text("title", chs)
        assert "第一段" in text
        assert "第二段不要" not in text


# ─── _compute_recency ───────────────────────────────────────────────


class TestComputeRecency:
    def test_zero_days_returns_1(self) -> None:
        now = datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc)
        # 0 天 = 1.0
        assert _compute_recency("2026-05-22T00:00:00+00:00", now) == pytest.approx(1.0, abs=0.01)

    def test_30_days_approx_half(self) -> None:
        """半衰期 30 天 → 30 天前 ≈ 0.5."""
        now = datetime(2026, 5, 22, tzinfo=timezone.utc)
        thirty_days_ago = "2026-04-22T00:00:00+00:00"
        val = _compute_recency(thirty_days_ago, now)
        assert val == pytest.approx(0.5, abs=0.02)

    def test_none_returns_0_5_default(self) -> None:
        now = datetime.now(timezone.utc)
        assert _compute_recency(None, now) == 0.5

    def test_invalid_returns_0_5(self) -> None:
        now = datetime.now(timezone.utc)
        assert _compute_recency("not-a-date", now) == 0.5

    def test_z_suffix_handled(self) -> None:
        """ISO 8601 末尾 Z 是 UTC 的合法表示."""
        now = datetime(2026, 5, 22, tzinfo=timezone.utc)
        val = _compute_recency("2026-05-22T00:00:00Z", now)
        assert val == pytest.approx(1.0, abs=0.01)

    def test_naive_datetime_treated_as_utc(self) -> None:
        now = datetime(2026, 5, 22, tzinfo=timezone.utc)
        val = _compute_recency("2026-05-22T00:00:00", now)
        assert val == pytest.approx(1.0, abs=0.01)

    def test_future_event_clamped_to_1(self) -> None:
        """occurred_at > now 不应该 > 1."""
        now = datetime(2026, 5, 22, tzinfo=timezone.utc)
        # 未来 5 天
        val = _compute_recency("2026-05-27T00:00:00+00:00", now)
        assert val == 1.0


# ─── _event_to_embed_text ───────────────────────────────────────────


class TestEventToEmbedText:
    def test_includes_source_type(self) -> None:
        e = {"source_type": "github", "title": "PR #42", "content": "fixed bug"}
        text = _event_to_embed_text(e)
        assert "[github]" in text
        assert "PR #42" in text
        assert "fixed bug" in text

    def test_caps_content_at_500(self) -> None:
        e = {"source_type": "claude_code", "title": "T", "content": "x" * 2000}
        text = _event_to_embed_text(e)
        # 500 字内容 + 标题 + source 前缀, 整体应 < 600
        assert len(text) < 600

    def test_missing_fields_default_empty(self) -> None:
        e: dict = {}
        text = _event_to_embed_text(e)
        # 不抛, 拼出空壳
        assert isinstance(text, str)


# ─── _enforce_source_diversity ──────────────────────────────────────


class TestEnforceSourceDiversity:
    def test_already_diverse_unchanged(self) -> None:
        """top-3 已有 2 个 source → 直接返回."""
        scored = [
            (0.9, {"source_type": "github"}),
            (0.8, {"source_type": "claude_code"}),
            (0.7, {"source_type": "github"}),
            (0.5, {"source_type": "cursor"}),
        ]
        out = _enforce_source_diversity(scored, num=3, min_sources=2)
        assert len(out) == 3
        types = [e[1]["source_type"] for e in out]
        assert "github" in types and "claude_code" in types

    def test_top_n_all_same_source_swaps_last(self) -> None:
        """top-3 全 github → 最后一名换成 cosine 最高的非 github."""
        scored = [
            (0.9, {"source_type": "github"}),
            (0.8, {"source_type": "github"}),
            (0.7, {"source_type": "github"}),
            (0.5, {"source_type": "cursor"}),   # 这条会顶替第 3 名
            (0.4, {"source_type": "github"}),
        ]
        out = _enforce_source_diversity(scored, num=3, min_sources=2)
        assert len(out) == 3
        types = [e[1]["source_type"] for e in out]
        assert types.count("github") == 2
        assert "cursor" in types

    def test_empty_returns_empty(self) -> None:
        assert _enforce_source_diversity([], num=3) == []

    def test_no_alternative_source_keeps_top_n(self) -> None:
        """没有外族可换 → 接受 top-N 单一源 (不抛错)."""
        scored = [
            (0.9, {"source_type": "github"}),
            (0.8, {"source_type": "github"}),
        ]
        out = _enforce_source_diversity(scored, num=3, min_sources=2)
        assert len(out) <= 2   # 没有第 3 条


class TestEnforceSourceDiversityScored:
    """4 元 tuple 版 (final, cos, trust, event), 用在 _stage_evidence."""

    def test_already_diverse_unchanged(self) -> None:
        scored = [
            (0.9, 0.8, 0.85, {"source_type": "github"}),
            (0.85, 0.75, 0.7, {"source_type": "cursor"}),
            (0.7, 0.6, 0.8, {"source_type": "github"}),
        ]
        out = _enforce_source_diversity_scored(scored, num=3, min_sources=2)
        assert len(out) == 3

    def test_swap_preserves_final_score_field(self) -> None:
        scored = [
            (0.9, 0.8, 0.85, {"source_type": "github"}),
            (0.85, 0.7, 0.85, {"source_type": "github"}),
            (0.8, 0.6, 0.85, {"source_type": "github"}),
            (0.5, 0.4, 0.7, {"source_type": "claude_code"}),
        ]
        out = _enforce_source_diversity_scored(scored, num=3, min_sources=2)
        # 第 3 名应被 claude_code 那条替换, 且 4 元组结构保留
        assert len(out) == 3
        types = [item[3]["source_type"] for item in out]
        assert "claude_code" in types
        # 4 元组结构 (final, cos, trust, event)
        assert len(out[-1]) == 4
