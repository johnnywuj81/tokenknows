"""skill 注入 + 反馈循环 集成 (v0.2 Milestone C).

覆盖 generation_service ↔ skill_service 跨边界:
- _call_chapter_llm 接受 skill_suffix
- _stage_content 注入 + record_skill_application
- approve_chapter → on_chapter_state_changed("approved")
- reject_chapter → on_chapter_state_changed("rejected")
- regenerate_chapter (big diff) → "regen_big_diff"
- regenerate_chapter (small diff) → "regen_small_diff"
- _common_prefix_len / _common_suffix_len 字符 diff 估算
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Chapter
from app.schemas.skill import Skill, SkillApplicationRecord, SkillMetrics
from app.services import generation_service, skill_service


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    skill_service.reset_registry_for_tests()
    # 清理 generation_service 内存
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._progress.clear()
    generation_service._evidence_by_chapter.clear()
    yield new_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_skill(skill_id: str, project_id: str = "p1", **overrides) -> Skill:
    defaults = dict(
        id=skill_id,
        project_id=project_id,
        name="formatter",
        version=1,
        skill_md="---\nname: formatter\n---\n# body",
        embedding=[1.0, 0.0],
        metrics=SkillMetrics(
            usage_count=0, acceptance_count=0, rejection_count=0,
            avg_acceptance_rate=0.0, trust_score=0.7,
        ),
        distilled_at=_now(),
        status="active",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(overrides)
    return Skill(**defaults)


def _make_chapter(applied_skills=None) -> Chapter:
    return Chapter(
        id="ch-test",
        asset_id="a-test",
        asset_version=1,
        order_index=0,
        title="测试章节",
        content="原文 " * 30,
        applied_skills=applied_skills or [],
    )


# ─── _call_chapter_llm 注入 ──────────────────────────────────


class _FakeRouter:
    """简单测试 router. seen_prompts 累积每次 generate 的 system_prompt."""

    def __init__(self) -> None:
        self.seen_prompts: list[str] = []
        self.text: str = "生成的章节内容,详细地讨论了如何实现这个功能" * 5

    async def generate(self, **kwargs):
        msgs = kwargs.get("messages", [])
        self.seen_prompts.append(msgs[0].content)
        return type("R", (), {
            "text": self.text,
            "usage": {},
            "fallback_used": False,
            "latency_ms": 100,
        })()


@pytest.mark.asyncio
async def test_call_chapter_llm_accepts_skill_suffix() -> None:
    """skill_suffix 应拼到 system_prompt 末尾."""
    fake = _FakeRouter()
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        result = await generation_service._call_chapter_llm(
            asset_type="weekly_report",
            title="本周进展",
            time_window="last_7_days",
            project_id="p1",
            provider="anthropic",
            model="claude",
            skill_suffix="## 项目专家技能\n\n规则1: 写清 PR 编号",
        )
    assert len(fake.seen_prompts) == 1
    assert "项目专家技能" in fake.seen_prompts[0]
    assert "PR 编号" in fake.seen_prompts[0]
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_call_chapter_llm_without_skill_suffix() -> None:
    """空 skill_suffix 时 system_prompt 不变."""
    fake = _FakeRouter()
    with patch(
        "app.services.generation_service.get_router",
        new=AsyncMock(return_value=fake),
    ):
        await generation_service._call_chapter_llm(
            asset_type="weekly_report",
            title="本周",
            time_window="last_7_days",
            project_id="p1",
            provider="anthropic",
            model="claude",
        )
    assert len(fake.seen_prompts) == 1
    assert "项目专家技能" not in fake.seen_prompts[0]


# ─── approve/reject 反馈 ────────────────────────────────────


def test_approve_chapter_no_applied_skills_is_noop() -> None:
    """老 chapter 没有 applied_skills, 不应崩."""
    # 设置 asset + chapter
    from app.schemas.asset import Asset, AssetMetrics
    asset = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="in_review", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets["a1"] = asset
    ch = _make_chapter(applied_skills=[])
    ch.id = "ch-1"
    ch.asset_id = "a1"
    generation_service._chapters["a1"] = [ch]

    # 不应抛
    result = generation_service.approve_chapter("a1", "ch-1")
    assert result is not None
    assert result.approval_state == "approved"


def test_approve_chapter_triggers_skill_feedback() -> None:
    skill = _make_skill("s1", acceptance=0, rejection=0)
    skill = skill.model_copy(update={
        "metrics": skill.metrics.model_copy(update={"acceptance_count": 0}),
    })
    skill_service.get_registry().add(skill)

    from app.schemas.asset import Asset
    asset = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="in_review", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets["a1"] = asset

    applied = [{"skill_id": "s1", "version": 1, "applied_at": _now().isoformat()}]
    ch = _make_chapter(applied_skills=applied)
    ch.id = "ch-1"
    ch.asset_id = "a1"
    generation_service._chapters["a1"] = [ch]

    generation_service.approve_chapter("a1", "ch-1")
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.acceptance_count == 1


def test_reject_chapter_triggers_skill_feedback() -> None:
    skill = _make_skill("s1")
    skill_service.get_registry().add(skill)

    from app.schemas.asset import Asset
    asset = Asset(
        id="a1", project_id="p1", type="weekly_report", title="t",
        status="in_review", current_version=1, template_id=None,
        created_by="u", created_at=_now(), updated_at=_now(),
    )
    generation_service._assets["a1"] = asset

    applied = [{"skill_id": "s1", "version": 1, "applied_at": _now().isoformat()}]
    ch = _make_chapter(applied_skills=applied)
    ch.id = "ch-1"
    ch.asset_id = "a1"
    generation_service._chapters["a1"] = [ch]

    generation_service.reject_chapter("a1", "ch-1", reason="不准确")
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.rejection_count == 1


def test_notify_skill_feedback_handles_service_exception(monkeypatch) -> None:
    """skill_service 抛异常时, 反馈不应破坏 chapter 状态."""
    def boom(**kwargs):
        raise RuntimeError("registry corrupted")
    monkeypatch.setattr(skill_service, "on_chapter_state_changed", boom)

    applied = [{"skill_id": "s1"}]
    ch = _make_chapter(applied_skills=applied)
    # 不抛即可
    generation_service._notify_skill_feedback(ch, action="approved")


# ─── diff 比例估算 ──────────────────────────────────────────


def test_common_prefix_len() -> None:
    assert generation_service._common_prefix_len("hello world", "hello there") == 6
    assert generation_service._common_prefix_len("", "abc") == 0
    assert generation_service._common_prefix_len("xyz", "abc") == 0
    assert generation_service._common_prefix_len("same", "same") == 4


def test_common_suffix_len() -> None:
    assert generation_service._common_suffix_len("abc world", "xyz world") == 6
    assert generation_service._common_suffix_len("", "abc") == 0
    assert generation_service._common_suffix_len("hello", "hello") == 5


def test_notify_regen_big_diff() -> None:
    """完全改写 → regen_big_diff."""
    skill = _make_skill("s1")
    skill_service.get_registry().add(skill)
    applied = [{"skill_id": "s1"}]
    ch = _make_chapter(applied_skills=applied)
    old = "abcde" * 20  # 100 chars
    new = "xyzpq" * 20  # 100 chars 完全不同
    generation_service._notify_skill_feedback_regen(ch, old, new)
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.rejection_count == 1  # big_diff → reject 信号


def test_notify_regen_small_diff() -> None:
    """小幅修改 → regen_small_diff (正向)."""
    skill = _make_skill("s1")
    skill_service.get_registry().add(skill)
    applied = [{"skill_id": "s1"}]
    ch = _make_chapter(applied_skills=applied)
    old = "原文内容 " * 50
    new = "原文内容 " * 49 + "改了一点 "
    generation_service._notify_skill_feedback_regen(ch, old, new)
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.acceptance_count == 1  # small_diff → accept 信号


def test_notify_regen_empty_old_content_is_noop() -> None:
    """空旧内容时不发反馈."""
    skill = _make_skill("s1")
    skill_service.get_registry().add(skill)
    applied = [{"skill_id": "s1"}]
    ch = _make_chapter(applied_skills=applied)
    generation_service._notify_skill_feedback_regen(ch, "", "新内容")
    updated = skill_service.get_skill("s1")
    assert updated is not None
    # 无更新
    assert updated.metrics.acceptance_count == 0
    assert updated.metrics.rejection_count == 0
