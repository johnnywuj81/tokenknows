"""skill_service · 蒸馏 / 注入 / 自进化 (v0.2 Milestone C).

覆盖:
- _parse_skill_md / _sanitize_name 边界
- _compute_trust_score 数值边界
- _build_sources_digest 摘要拼接
- distill_skill 完整路径 (mock LLM + embedding)
- select_skills_for_chapter 排序 / diversity / 探索
- record_skill_application usage_count 累加
- on_chapter_state_changed 4 种反馈 → trust 更新
- should_evolve 触发条件
- evolve_skill_v2 v1→v2 升级
- update_skill / delete_skill / list_skills
- 启动 bootstrap 加载已有 skill
"""

from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.skill import (
    Skill,
    SkillApplicationRecord,
    SkillDistillSource,
    SkillMetrics,
)
from app.services import skill_service


# ─── 测试夹具 ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个测试一个全新的 SQLite + 全新的 _registry."""
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    # 把全局单例换成 fresh store
    monkeypatch.setattr(store_module, "_db", new_store)
    skill_service.reset_registry_for_tests()
    yield new_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_chapter(idx: int) -> dict:
    return {
        "id": f"ch-{idx}",
        "asset_id": f"a-{idx}",
        "asset_version": 1,
        "title": f"章节 {idx}",
        "content": "这里是详细的实现说明..." * 20,
        "regeneration_history": [
            {"instruction": "把数据示例改成真实 PR 链接"},
        ],
    }


def _make_skill(
    skill_id: str = "skill-test",
    project_id: str = "p1",
    usage_count: int = 0,
    acceptance: int = 0,
    rejection: int = 0,
    trust_score: float = 0.5,
    status: str = "draft",
    embedding: list[float] | None = None,
    locked: bool = False,
) -> Skill:
    return Skill(
        id=skill_id,
        project_id=project_id,
        name="test-skill",
        version=1,
        skill_md="---\nname: test-skill\n---\n# body",
        embedding=embedding,
        metrics=SkillMetrics(
            usage_count=usage_count,
            acceptance_count=acceptance,
            rejection_count=rejection,
            avg_acceptance_rate=(
                acceptance / (acceptance + rejection)
                if acceptance + rejection > 0 else 0.0
            ),
            trust_score=trust_score,
        ),
        distilled_at=_now(),
        locked=locked,
        status=status,  # type: ignore[arg-type]
        created_at=_now(),
        updated_at=_now(),
    )


# ─── 辅助函数 ─────────────────────────────────────────────────


def test_sanitize_name_strips_invalid_chars() -> None:
    assert skill_service._sanitize_name("PR Summary!") == "pr-summary"
    assert skill_service._sanitize_name("中文?abc") == "abc"
    assert skill_service._sanitize_name("---") == "unnamed-skill"
    assert skill_service._sanitize_name("good-slug") == "good-slug"


def test_parse_skill_md_extracts_name() -> None:
    md = """---
name: pr-summary
description: short
---

# body
"""
    name, parsed = skill_service._parse_skill_md(md)
    assert name == "pr-summary"
    assert parsed["description"] == "short"


def test_parse_skill_md_falls_back_to_hint() -> None:
    md = "no frontmatter here"
    name, _ = skill_service._parse_skill_md(md, fallback_name="My Skill")
    assert name == "my-skill"


def test_parse_skill_md_raises_without_name() -> None:
    md = "no frontmatter"
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        skill_service._parse_skill_md(md)


def test_parse_skill_md_raises_on_invalid_yaml() -> None:
    md = """---
name: [unclosed
---
body"""
    with pytest.raises(ValueError):
        skill_service._parse_skill_md(md)


def test_parse_skill_md_raises_on_list_frontmatter() -> None:
    md = """---
- this
- is
- a
- list
---
body"""
    with pytest.raises(ValueError, match="must be a YAML dict"):
        skill_service._parse_skill_md(md)


def test_normalize_skill_md_strips_markdown_code_fence() -> None:
    """LLM (e.g. MiniMax abab6.5s) 常违反 prompt 约束, 用 ```markdown ... ``` 包整段."""
    polluted = """```markdown
---
name: docker-deploy
description: short
---

# body
```"""
    cleaned = skill_service._normalize_skill_md_text(polluted)
    assert cleaned.startswith("---\nname: docker-deploy")
    # 解析也能跑通
    name, _ = skill_service._parse_skill_md(polluted)
    assert name == "docker-deploy"


def test_normalize_skill_md_strips_plain_code_fence_no_lang() -> None:
    """不带语言标签的 ``` 也要剥."""
    polluted = "```\n---\nname: x\n---\nbody\n```"
    cleaned = skill_service._normalize_skill_md_text(polluted)
    assert cleaned.startswith("---\nname: x")


def test_normalize_skill_md_strips_preamble() -> None:
    """LLM 加 '好的, 下面是您要的 SKILL.md:' 前缀也要丢."""
    polluted = (
        "好的, 以下是您要的 SKILL.md 内容:\n"
        "\n"
        "---\n"
        "name: pr-review\n"
        "description: code review SOP\n"
        "---\n"
        "\n"
        "## 适用场景\n"
        "review PRs\n"
    )
    cleaned = skill_service._normalize_skill_md_text(polluted)
    assert cleaned.startswith("---\nname: pr-review")
    name, _ = skill_service._parse_skill_md(polluted)
    assert name == "pr-review"


def test_normalize_skill_md_preserves_already_clean_input() -> None:
    """正确格式输入应该原样返回 (除了 trim)."""
    clean = "---\nname: x\n---\nbody"
    assert skill_service._normalize_skill_md_text(clean) == clean
    assert skill_service._normalize_skill_md_text(f"  {clean}  \n") == clean


def test_normalize_skill_md_does_not_strip_inline_backticks_in_body() -> None:
    """body 里的单/双反引号 (例: `docker build`) 必须保留, 只剥包裹用的 ```."""
    polluted = (
        "```\n"
        "---\n"
        "name: x\n"
        "---\n"
        "\n"
        "用 `docker build` 命令构建, 然后 `docker run`\n"
        "```"
    )
    cleaned = skill_service._normalize_skill_md_text(polluted)
    assert "`docker build`" in cleaned, "inline backtick 被误剥"
    assert "`docker run`" in cleaned
    assert not cleaned.endswith("```"), "末尾 fence 没剥干净"


def test_normalize_skill_md_gives_up_when_no_frontmatter_in_first_20_lines() -> None:
    """前 20 行内都没 `---` 行 → 不做切片, 让 _parse_skill_md 抛错."""
    polluted = "\n".join(["just some text"] * 30) + "\n---\nname: deep\n---\nbody"
    cleaned = skill_service._normalize_skill_md_text(polluted)
    # 没切, 仍以 "just some text" 开头
    assert cleaned.startswith("just some text")


def test_compute_trust_score_no_data_returns_low() -> None:
    s = skill_service._compute_trust_score(
        acceptance=0, rejection=0, usage=0, last_used_at=None
    )
    # base = 1/2 = 0.5, recency = 1.0, confidence = 0.3 → 0.15
    assert 0.10 < s < 0.20


def test_compute_trust_score_perfect_skill_high() -> None:
    s = skill_service._compute_trust_score(
        acceptance=20, rejection=0, usage=20,
        last_used_at=_now(),
    )
    # base = 21/22 ≈ 0.95, recency ≈ 1.0, confidence = 1.0
    assert s > 0.9


def test_compute_trust_score_rejection_drags_down() -> None:
    s = skill_service._compute_trust_score(
        acceptance=2, rejection=18, usage=20,
        last_used_at=_now(),
    )
    # base = 3/22 ≈ 0.14
    assert s < 0.2


def test_compute_trust_score_recency_decay() -> None:
    """30 天前 last_used → recency ≈ exp(-1) ≈ 0.37."""
    long_ago = _now() - timedelta(days=30)
    s_fresh = skill_service._compute_trust_score(
        acceptance=10, rejection=0, usage=10, last_used_at=_now()
    )
    s_stale = skill_service._compute_trust_score(
        acceptance=10, rejection=0, usage=10, last_used_at=long_ago
    )
    assert s_stale < s_fresh * 0.5


def test_build_sources_digest_truncates_and_includes_regen() -> None:
    chapters = [_make_chapter(1), _make_chapter(2)]
    digest = skill_service._build_sources_digest(chapters)
    assert "Source 1" in digest
    assert "Source 2" in digest
    assert "用户最近的修改指令" in digest


# ─── distill_skill ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_distill_skill_happy_path() -> None:
    """完整 distill: mock LLM + mock embedding → 写入 _registry."""
    mock_response = type("MockResp", (), {
        "text": """---
name: pr-summary-style
description: how to summarize PRs
triggers:
  - PR merge
  - weekly report
scope: project
category: writing
---

## 适用场景
当用户在生成周报时需要总结 PR.

## 核心原则
1. 一句话讲清做了什么
2. 写出 PR number + author""",
        "provider": "anthropic",
        "model_used": "claude-sonnet-4-6",
        "usage": {},
        "fallback_used": False,
    })()

    with patch(
        "app.services.skill_service.get_router",
        new=AsyncMock(return_value=type("R", (), {"generate": AsyncMock(return_value=mock_response)})()),
    ), patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]]),
    ):
        skill = await skill_service.distill_skill(
            project_id="proj-demo",
            source_chapters=[_make_chapter(1), _make_chapter(2)],
            name_hint=None,
        )
    assert skill.name == "pr-summary-style"
    assert skill.project_id == "proj-demo"
    assert skill.version == 1
    assert skill.status == "draft"
    assert skill.embedding == [0.1, 0.2, 0.3, 0.4]
    assert len(skill.distilled_from) == 2
    assert skill_service.get_skill(skill.id) is skill


@pytest.mark.asyncio
async def test_distill_skill_rejects_empty_sources() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        await skill_service.distill_skill(
            project_id="p", source_chapters=[]
        )


@pytest.mark.asyncio
async def test_distill_skill_tolerates_embedding_failure() -> None:
    """embedding 失败应继续返回 skill, embedding=None."""
    mock_response = type("MockResp", (), {
        "text": "---\nname: x\n---\nbody",
        "provider": "anthropic",
        "model_used": "claude",
        "usage": {},
        "fallback_used": False,
    })()

    from app.llm_gateway.embedding import EmbeddingError

    with patch(
        "app.services.skill_service.get_router",
        new=AsyncMock(return_value=type("R", (), {"generate": AsyncMock(return_value=mock_response)})()),
    ), patch(
        "app.services.skill_service.embed_batch",
        side_effect=EmbeddingError("ollama down"),
    ):
        skill = await skill_service.distill_skill(
            project_id="p", source_chapters=[_make_chapter(1)]
        )
    assert skill.embedding is None


# ─── select_skills_for_chapter ──────────────────────────────


@pytest.mark.asyncio
async def test_select_skills_returns_empty_when_no_skills() -> None:
    with patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0]]),
    ):
        out = await skill_service.select_skills_for_chapter(
            project_id="empty-proj", query_text="hello"
        )
    assert out == []


@pytest.mark.asyncio
async def test_select_skills_filters_low_trust() -> None:
    low = _make_skill(
        skill_id="s-low", trust_score=0.1, status="active",
        embedding=[1.0, 0.0],
    )
    high = _make_skill(
        skill_id="s-high", trust_score=0.8, status="active",
        embedding=[1.0, 0.0],
    )
    skill_service.get_registry().add(low)
    skill_service.get_registry().add(high)
    with patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0]]),
    ):
        out = await skill_service.select_skills_for_chapter(
            project_id="p1", query_text="hello"
        )
    assert len(out) == 1
    assert out[0][0].id == "s-high"


@pytest.mark.asyncio
async def test_select_skills_skips_draft_by_default() -> None:
    draft = _make_skill(
        skill_id="s-draft", status="draft", trust_score=0.8,
        embedding=[1.0, 0.0],
    )
    active = _make_skill(
        skill_id="s-active", status="active", trust_score=0.8,
        embedding=[1.0, 0.0],
    )
    skill_service.get_registry().add(draft)
    skill_service.get_registry().add(active)
    with patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0]]),
    ), patch(
        "app.services.skill_service.random.random",
        return_value=1.0,  # 关掉 ε-greedy
    ):
        out = await skill_service.select_skills_for_chapter(
            project_id="p1", query_text="hello"
        )
    assert len(out) == 1
    assert out[0][0].id == "s-active"


@pytest.mark.asyncio
async def test_select_skills_diversity_filters_similar() -> None:
    """两个 skill 的 embedding 几乎相同 → 只保留 1 个."""
    s1 = _make_skill(
        skill_id="s1", status="active", trust_score=0.9,
        embedding=[1.0, 0.0],
    )
    s2 = _make_skill(
        skill_id="s2", status="active", trust_score=0.85,
        embedding=[0.99, 0.01],  # 与 s1 cosine ≈ 1.0
    )
    s3 = _make_skill(
        skill_id="s3", status="active", trust_score=0.7,
        embedding=[0.0, 1.0],  # 与 s1 cosine = 0
    )
    skill_service.get_registry().add(s1)
    skill_service.get_registry().add(s2)
    skill_service.get_registry().add(s3)
    with patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[1.0, 0.0]]),
    ), patch(
        "app.services.skill_service.random.random",
        return_value=1.0,
    ):
        out = await skill_service.select_skills_for_chapter(
            project_id="p1", query_text="hello", top_k=3
        )
    ids = [s.id for s, _ in out]
    # s2 与 s1 太像 → 被剔除; s1 + s3 保留
    assert "s1" in ids
    assert "s3" in ids
    assert "s2" not in ids


@pytest.mark.asyncio
async def test_render_skills_for_prompt_concatenates() -> None:
    s = _make_skill(skill_id="s1", status="active", trust_score=0.8,
                    embedding=[1.0, 0.0])
    out = skill_service.render_skills_for_prompt([(s, 0.9)])
    assert "项目专家技能" in out
    assert "test-skill" in out


def test_render_skills_for_prompt_empty_returns_empty_string() -> None:
    assert skill_service.render_skills_for_prompt([]) == ""


# ─── record_skill_application ─────────────────────────────────


def test_record_skill_application_increments_usage() -> None:
    s = _make_skill(skill_id="s1", usage_count=5, status="active",
                    trust_score=0.5, embedding=[1.0])
    skill_service.get_registry().add(s)
    records = skill_service.record_skill_application(
        chapter_id="ch1",
        project_id="p1",
        picked=[(s, 0.8)],
    )
    assert len(records) == 1
    assert records[0].skill_id == "s1"
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.usage_count == 6
    assert updated.last_used_at is not None


# ─── on_chapter_state_changed ─────────────────────────────────


def test_feedback_approved_increments_acceptance() -> None:
    s = _make_skill(skill_id="s1", usage_count=5, acceptance=2,
                    rejection=1, trust_score=0.4)
    skill_service.get_registry().add(s)
    skill_service.on_chapter_state_changed(
        chapter_id="ch1",
        applied_skill_records=[{"skill_id": "s1"}],
        action="approved",
    )
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.acceptance_count == 3
    assert updated.metrics.rejection_count == 1
    assert updated.metrics.avg_acceptance_rate == 0.75


def test_feedback_rejected_increments_rejection() -> None:
    s = _make_skill(skill_id="s1", acceptance=5, rejection=0)
    skill_service.get_registry().add(s)
    skill_service.on_chapter_state_changed(
        chapter_id="ch1",
        applied_skill_records=[{"skill_id": "s1"}],
        action="rejected",
    )
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.rejection_count == 1


def test_feedback_skips_locked_skill() -> None:
    s = _make_skill(skill_id="s1", acceptance=3, locked=True)
    skill_service.get_registry().add(s)
    skill_service.on_chapter_state_changed(
        chapter_id="ch1",
        applied_skill_records=[{"skill_id": "s1"}],
        action="rejected",
    )
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.rejection_count == 0
    assert updated.locked is True


def test_feedback_unknown_action_is_noop() -> None:
    s = _make_skill(skill_id="s1", acceptance=2)
    skill_service.get_registry().add(s)
    skill_service.on_chapter_state_changed(
        chapter_id="ch1",
        applied_skill_records=[{"skill_id": "s1"}],
        action="bogus_action",
    )
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.metrics.acceptance_count == 2


def test_feedback_auto_promote_to_active() -> None:
    """draft skill 达到 usage>=50 且 acc>=0.8 时自动 active."""
    s = _make_skill(
        skill_id="s1", status="draft",
        usage_count=51, acceptance=45, rejection=4,
    )
    skill_service.get_registry().add(s)
    skill_service.on_chapter_state_changed(
        chapter_id="ch1",
        applied_skill_records=[{"skill_id": "s1"}],
        action="approved",
    )
    updated = skill_service.get_skill("s1")
    assert updated is not None
    assert updated.status == "active"


# ─── should_evolve / evolve_skill_v2 ──────────────────────────


def test_should_evolve_triggered_when_low_acceptance() -> None:
    s = _make_skill(
        skill_id="s1",
        usage_count=25,
    )
    s = s.model_copy(update={
        "metrics": SkillMetrics(
            usage_count=25, acceptance_count=8, rejection_count=17,
            avg_acceptance_rate=0.32, trust_score=0.4,
        ),
    })
    assert skill_service.should_evolve(s) is True


def test_should_evolve_skips_locked() -> None:
    s = _make_skill(skill_id="s1", locked=True)
    s = s.model_copy(update={
        "metrics": SkillMetrics(
            usage_count=25, acceptance_count=8, rejection_count=17,
            avg_acceptance_rate=0.32, trust_score=0.4,
        ),
    })
    assert skill_service.should_evolve(s) is False


def test_should_evolve_skips_low_usage() -> None:
    s = _make_skill(skill_id="s1")
    s = s.model_copy(update={
        "metrics": SkillMetrics(
            usage_count=5, acceptance_count=1, rejection_count=4,
            avg_acceptance_rate=0.2, trust_score=0.3,
        ),
    })
    assert skill_service.should_evolve(s) is False


@pytest.mark.asyncio
async def test_evolve_skill_v2_creates_new_version() -> None:
    """旧 skill 表现差 → 新 v2 skill, 旧 skill 标 deprecated."""
    old = _make_skill(skill_id="s-old", status="active")
    old = old.model_copy(update={
        "metrics": SkillMetrics(
            usage_count=25, acceptance_count=8, rejection_count=17,
            avg_acceptance_rate=0.32, trust_score=0.4,
        ),
    })
    skill_service.get_registry().add(old)

    mock_response = type("MockResp", (), {
        "text": "---\nname: pr-summary-v2\n---\n# improved",
        "provider": "anthropic",
        "model_used": "claude",
        "usage": {},
        "fallback_used": False,
    })()
    with patch(
        "app.services.skill_service.get_router",
        new=AsyncMock(return_value=type("R", (), {"generate": AsyncMock(return_value=mock_response)})()),
    ), patch(
        "app.services.skill_service.embed_batch",
        new=AsyncMock(return_value=[[0.5, 0.5]]),
    ):
        new_skill = await skill_service.evolve_skill_v2(
            skill_id="s-old",
            failing_chapters=[_make_chapter(1)],
        )
    assert new_skill is not None
    assert new_skill.version == 2
    assert new_skill.parent_skill_id == "s-old"
    # 旧 skill 标 deprecated
    old_after = skill_service.get_skill("s-old")
    assert old_after is not None
    assert old_after.status == "deprecated"


@pytest.mark.asyncio
async def test_evolve_skill_v2_skips_missing_skill() -> None:
    out = await skill_service.evolve_skill_v2(
        skill_id="nonexistent", failing_chapters=[_make_chapter(1)]
    )
    assert out is None


@pytest.mark.asyncio
async def test_evolve_skill_v2_skips_locked() -> None:
    old = _make_skill(skill_id="s-locked", locked=True)
    skill_service.get_registry().add(old)
    out = await skill_service.evolve_skill_v2(
        skill_id="s-locked", failing_chapters=[_make_chapter(1)]
    )
    assert out is None


# ─── 业务操作 ────────────────────────────────────────────────


def test_update_skill_partial() -> None:
    s = _make_skill(skill_id="s1")
    skill_service.get_registry().add(s)
    updated = skill_service.update_skill(
        skill_id="s1", locked=True, status="active"
    )
    assert updated is not None
    assert updated.locked is True
    assert updated.status == "active"
    # 不应改变 name
    assert updated.name == "test-skill"


def test_update_skill_missing_returns_none() -> None:
    assert skill_service.update_skill(skill_id="ghost", locked=True) is None


def test_delete_skill() -> None:
    s = _make_skill(skill_id="s1")
    skill_service.get_registry().add(s)
    assert skill_service.delete_skill("s1") is True
    assert skill_service.get_skill("s1") is None


def test_delete_skill_missing_returns_false() -> None:
    assert skill_service.delete_skill("ghost") is False


def test_list_skills_sorted_by_trust() -> None:
    skill_service.get_registry().add(_make_skill(
        skill_id="s-low", trust_score=0.2, status="active",
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-high", trust_score=0.9, status="active",
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-mid", trust_score=0.5, status="active",
    ))
    out = skill_service.list_skills("p1")
    assert [s.id for s in out] == ["s-high", "s-mid", "s-low"]


def test_list_skills_filter_by_status() -> None:
    skill_service.get_registry().add(_make_skill(
        skill_id="s1", status="draft", trust_score=0.5,
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s2", status="active", trust_score=0.5,
    ))
    actives = skill_service.list_skills("p1", status="active")
    assert [s.id for s in actives] == ["s2"]


def test_list_skills_isolated_by_project() -> None:
    skill_service.get_registry().add(_make_skill(
        skill_id="s-a", project_id="proj-A",
    ))
    skill_service.get_registry().add(_make_skill(
        skill_id="s-b", project_id="proj-B",
    ))
    a = skill_service.list_skills("proj-A")
    b = skill_service.list_skills("proj-B")
    assert {s.id for s in a} == {"s-a"}
    assert {s.id for s in b} == {"s-b"}


# ─── bootstrap 加载 ───────────────────────────────────────────


def test_bootstrap_loads_from_db(fresh_store: SqliteStore) -> None:
    """新 registry 启动应从 SQLite 还原 skills."""
    s = _make_skill(skill_id="s-persisted", trust_score=0.6, status="active")
    skill_service.get_registry().add(s)
    # 模拟应用重启: 重置 registry, 再 bootstrap
    skill_service.reset_registry_for_tests()
    skill_service.bootstrap()
    loaded = skill_service.get_skill("s-persisted")
    assert loaded is not None
    assert loaded.metrics.trust_score == 0.6


def test_bootstrap_is_idempotent() -> None:
    s = _make_skill(skill_id="s1")
    skill_service.get_registry().add(s)
    skill_service.bootstrap()
    skill_service.bootstrap()  # 二次调用应短路
    assert skill_service.get_skill("s1") is not None
