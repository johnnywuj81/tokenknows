"""skill_service · 蒸馏 / 注入 / 自进化 (v0.2 升级 Milestone C).

设计来源:
- PRD §5.8 Skill 自进化机制 (H1-H5)
- TDD §7.5 select_skills_for_chapter / §7.6 evolve_skill_v2
- 计划 Milestone C5 反馈循环

核心数据流:
    distill_skill(source_chapter_ids) → Skill(status=draft)
        ↓ 人工 approve 或自动 (auto-active 条件)
    select_skills_for_chapter(query) → top-3 Skill (cosine × trust × recency)
        ↓ 注入 system_prompt → LLM → chapter
    on_chapter_state_changed(chapter_id, action) → 更新 metrics + trust_score
        ↓ 触发条件
    evolve_skill_v2(skill_id) → new Skill (parent_skill_id=old)

线程安全:
- 与 generation_service 一样, asyncio 单进程 + 偶尔后台 task 改 dict
- _write_lock 保护 in-memory dict 与 SQLite 写
"""

from __future__ import annotations

import math
import random
import re
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import yaml

from app.config.logging import logger
from app.llm_gateway import LLMMessage, LLMOptions, get_router
from app.llm_gateway.embedding import EmbeddingError, cosine, embed_batch
from app.persistence import get_db
from app.prompts.base import PromptTemplate
from app.schemas.skill import (
    Skill,
    SkillApplicationRecord,
    SkillDistillSource,
    SkillMetrics,
    SkillStatus,
)

# ─── 配置常量 ────────────────────────────────────────────────

DEFAULT_TOP_K = 3
"""每次 _stage_content 注入的 skill 数量."""

DIVERSITY_COSINE_GATE = 0.7
"""top1 与候选 top2 cosine > 此值时 → 跳过 top2 找下一个 (避免重复)."""

EPSILON_EXPLORE = 0.05
"""5% 概率注入 1 个低分 draft skill (探索 / 防止局部最优)."""

EVOLVE_USAGE_THRESHOLD = 20
"""usage_count ≥ 此值 + acc_rate < 0.5 → 触发 evolve_skill_v2."""

EVOLVE_ACC_RATE_FLOOR = 0.5
"""低于此值认为 skill 有问题."""

AUTO_ACTIVE_USAGE_THRESHOLD = 50
"""usage_count ≥ 此值 + acc_rate ≥ 0.8 → 自动 status=active."""

AUTO_ACTIVE_ACC_RATE = 0.8

MIN_TRUST_FOR_INJECT = 0.3
"""trust_score < 此值的 skill 不参与注入 (避免污染下游)."""

RECENCY_HALF_LIFE_DAYS = 30.0
"""recency_decay 半衰期."""


# ─── 内存 cache ────────────────────────────────────────────


class _SkillRegistry:
    """单进程内存 cache (cache-aside 模式)."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._by_project: dict[str, set[str]] = {}
        self._write_lock = threading.RLock()
        self._bootstrapped = False

    def bootstrap(self) -> None:
        """启动时从 SQLite 全量加载."""
        if self._bootstrapped:
            return
        db = get_db()
        rows = db.load_all_skills()
        for row in rows:
            try:
                skill = Skill.model_validate(row)
            except Exception as e:
                logger.warning("skill_bootstrap_parse_failed", skill=row.get("id"), error=str(e))
                continue
            self._skills[skill.id] = skill
            self._by_project.setdefault(skill.project_id, set()).add(skill.id)
        self._bootstrapped = True
        logger.info("skills_bootstrapped", count=len(self._skills))

    def add(self, skill: Skill) -> None:
        with self._write_lock:
            self._skills[skill.id] = skill
            self._by_project.setdefault(skill.project_id, set()).add(skill.id)
            self._persist(skill)

    def update(self, skill: Skill) -> None:
        with self._write_lock:
            self._skills[skill.id] = skill
            self._persist(skill)

    def delete(self, skill_id: str) -> bool:
        with self._write_lock:
            existing = self._skills.pop(skill_id, None)
            if existing is None:
                return False
            project_set = self._by_project.get(existing.project_id, set())
            project_set.discard(skill_id)
            get_db().delete_skill(skill_id)
            return True

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def all_skills(self) -> list[Skill]:
        """v1.0.1 (review fix): 暴露只读快照供 pool.py 等使用,
        避免私有属性 _skills 被外部访问 (SLF001).
        返回 list 而非 dict.values() 以让调用方安全遍历 (避免遍历中 mutation).
        """
        with self._write_lock:
            return list(self._skills.values())

    def all_skill_items(self) -> list[tuple[str, Skill]]:
        """同 all_skills 但返 (id, skill) 元组列表."""
        with self._write_lock:
            return list(self._skills.items())

    def list_for_project(
        self, project_id: str, status: SkillStatus | None = None
    ) -> list[Skill]:
        ids = self._by_project.get(project_id, set())
        out = [self._skills[i] for i in ids if i in self._skills]
        if status:
            out = [s for s in out if s.status == status]
        # trust_score DESC, updated_at DESC
        out.sort(key=lambda s: (s.metrics.trust_score, s.updated_at), reverse=True)
        return out

    def _persist(self, skill: Skill) -> None:
        db = get_db()
        db.upsert_skill(
            skill_id=skill.id,
            project_id=skill.project_id,
            name=skill.name,
            version=skill.version,
            status=skill.status,
            trust_score=skill.metrics.trust_score,
            updated_at=skill.updated_at.isoformat(),
            json_str=skill.model_dump_json(),
        )


_registry = _SkillRegistry()


def bootstrap() -> None:
    """供 main.py lifespan 调用."""
    _registry.bootstrap()


def get_registry() -> _SkillRegistry:
    """供 HTTP 层 / 测试访问."""
    return _registry


# ─── 核心 API · 蒸馏 ─────────────────────────────────────────


async def distill_skill(
    project_id: str,
    source_chapters: list[dict[str, Any]],
    name_hint: str | None = None,
    project_label: str | None = None,
) -> Skill:
    """从 source chapters 蒸馏出一份 Skill.

    Args:
        project_id: 项目 ID (skill 私有归属)
        source_chapters: chapter dump list (含 id, title, content, regeneration_history)
                         调用方负责筛选 approved + 高 trust chapters.
        name_hint: 可选名称提示 (LLM 兜底用)
        project_label: 可选项目展示名 (写入 prompt 上下文)

    Returns:
        Skill (status=draft, embedding 已生成, 已持久化)

    Raises:
        ValueError: source_chapters 为空, 或 LLM 返回不合 SKILL.md 格式
    """
    if not source_chapters:
        raise ValueError("source_chapters must be non-empty")

    sources_digest = _build_sources_digest(source_chapters)
    distill_sources = [
        SkillDistillSource(
            chapter_id=c["id"],
            asset_id=c["asset_id"],
            asset_version=c.get("asset_version", 1),
            quoted_at=datetime.now(UTC),
        )
        for c in source_chapters
    ]

    tpl = PromptTemplate.load("distill/skill_distill")
    rendered = tpl.render({
        "project_label": project_label or project_id,
        "source_count": len(source_chapters),
        "sources_digest": sources_digest,
        "name_hint": name_hint,
    })

    router = await get_router()
    response = await router.generate(
        task="agent_skill",
        messages=[
            LLMMessage(role="system", content=rendered.system),
            LLMMessage(role="user", content=rendered.user),
        ],
        options=LLMOptions(**rendered.options),
        project_id=project_id,
    )
    skill_md = response.text.strip()
    name, parsed_yaml = _parse_skill_md(skill_md, fallback_name=name_hint)

    # embedding
    try:
        vectors = await embed_batch([skill_md])
        embedding = vectors[0] if vectors else None
    except EmbeddingError as e:
        logger.warning("skill_embedding_failed", error=str(e))
        embedding = None

    now = datetime.now(UTC)
    skill = Skill(
        id=f"skill-{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        name=name,
        version=1,
        skill_md=skill_md,
        embedding=embedding,
        metrics=SkillMetrics(),
        distilled_from=distill_sources,
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status="draft",
        parent_skill_id=None,
        created_at=now,
        updated_at=now,
    )
    _registry.add(skill)
    logger.info(
        "skill_distilled",
        skill_id=skill.id,
        name=name,
        project_id=project_id,
        sources=len(source_chapters),
        provider=response.provider,
        embedding_dim=len(embedding) if embedding else 0,
    )
    return skill


def _build_sources_digest(chapters: list[dict[str, Any]]) -> str:
    """把 chapter list 压缩成 prompt context (≤8K 字).

    优先纳入:
    1. title + 前 1200 字 content
    2. regeneration_history (用户的修正轨迹是金信号)
    3. 截断不超过 1500 字 / chapter
    """
    parts: list[str] = []
    for idx, ch in enumerate(chapters, 1):
        title = ch.get("title", "(untitled)")
        content = (ch.get("content") or "")[:1200]
        regen_hist = ch.get("regeneration_history") or []
        regen_summary = ""
        if regen_hist:
            instructions = [r.get("instruction") or "" for r in regen_hist[-3:]]
            regen_summary = (
                "\n  用户最近的修改指令:\n  - "
                + "\n  - ".join(filter(None, instructions))
            )
        parts.append(f"### Source {idx} · {title}\n{content}{regen_summary}")
    return "\n\n".join(parts)


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_CODE_FENCE_OPEN_RE = re.compile(r"^```(?:[a-zA-Z][a-zA-Z0-9_+-]*)?\s*\n")
_CODE_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


def _normalize_skill_md_text(text: str) -> str:
    """剥 LLM 输出里的常见污染层, 拿到干净 SKILL.md.

    实际 LLM (尤其 MiniMax / GPT-3.5 这类老一代模型) 经常违反 prompt 约束, 输出:
      1. 用 ```markdown ... ``` / ``` ... ``` 把整段 SKILL.md 包起来
      2. 前面加 preamble: "好的, 以下是您要的 SKILL.md:"
      3. 末尾加 epilogue: "希望这对您有帮助!"

    规则:
      - 先 strip 空白
      - 若以 ``` 开头, 剥首尾 fence
      - 若 strip 后 *仍不以 `---\\n` 起头*, 在前 20 行内找首个独占 `---` 行,
        从它开始切 (preamble 丢弃); 找不到原样返回, 让 _parse_skill_md 抛错
    """
    s = (text or "").strip()
    # 1) 剥首尾 ``` 代码 fence (可带语言标签)
    if s.startswith("```"):
        s = _CODE_FENCE_OPEN_RE.sub("", s, count=1)
        s = _CODE_FENCE_CLOSE_RE.sub("", s)
        s = s.strip()
    # 2) 若不是 `---` 开头, 容忍前 ≤20 行的 preamble: 找首个独占 `---` 行
    if not s.startswith("---\n") and not s.startswith("---\r\n"):
        lines = s.split("\n")
        # 限定前 20 行扫描 (preamble 不应该这么长; 超过认为是格式错)
        for i, line in enumerate(lines[:20]):
            if line.strip() == "---":
                s = "\n".join(lines[i:])
                break
    return s


def _parse_skill_md(
    text: str, fallback_name: str | None = None
) -> tuple[str, dict[str, Any]]:
    """从 SKILL.md 抽 YAML frontmatter, 返回 (name, parsed_yaml).

    Raises:
        ValueError: 缺 frontmatter, 或缺 name 字段又无 fallback.
    """
    text = _normalize_skill_md_text(text)
    m = _FRONTMATTER_RE.match(text)
    if not m:
        if fallback_name:
            return _sanitize_name(fallback_name), {}
        raise ValueError("Skill output missing YAML frontmatter")
    try:
        parsed = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Skill frontmatter YAML invalid: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("Skill frontmatter must be a YAML dict")
    name = parsed.get("name") or fallback_name
    if not name:
        raise ValueError("Skill output missing 'name' field; no fallback provided")
    return _sanitize_name(str(name)), parsed


_NAME_RE = re.compile(r"[^a-z0-9-]")


def _sanitize_name(raw: str) -> str:
    """slug 化: lowercase + 替换非 [a-z0-9-] 为 '-' + 去首尾 '-'."""
    s = _NAME_RE.sub("-", raw.lower()).strip("-")
    return s or "unnamed-skill"


# ─── 核心 API · 选择注入 ──────────────────────────────────────


async def select_skills_for_chapter(
    project_id: str,
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
    include_draft: bool = False,
) -> list[tuple[Skill, float]]:
    """挑选要注入下游生成的 top-k skill.

    评分: score = cosine(query, skill_emb) * skill.trust_score
    Diversity: top1 与候选 cosine > DIVERSITY_COSINE_GATE → 跳过
    ε-greedy: 5% 概率在结果末尾追加 1 个 draft skill (探索)

    Args:
        query_text: 通常是 "chapter outline + recent events digest" 拼成
        top_k: 默认 3
        include_draft: 默认仅 active; True 时纳入 draft (探索阶段用)

    Returns:
        [(skill, score), ...] 按 score 降序; 长度 ≤ top_k (+ 可能 1 探索项).
        若 project 无可用 skill 返回 [].
    """
    candidates = _registry.list_for_project(
        project_id,
        status=None if include_draft else "active",
    )
    if not candidates:
        return []

    # 过滤掉无 embedding / trust 太低
    usable = [
        s for s in candidates
        if s.embedding is not None and s.metrics.trust_score >= MIN_TRUST_FOR_INJECT
    ]
    if not usable:
        return []

    # query embedding
    try:
        vectors = await embed_batch([query_text])
    except EmbeddingError as e:
        logger.warning("skill_select_embed_failed", error=str(e))
        return []
    if not vectors:
        return []
    query_emb = vectors[0]

    # 计算分数
    scored: list[tuple[Skill, float, float]] = []  # (skill, cosine, final_score)
    for s in usable:
        cos = cosine(query_emb, s.embedding or [])
        score = cos * s.metrics.trust_score
        scored.append((s, cos, score))
    scored.sort(key=lambda x: x[2], reverse=True)

    # diversity: 跳过与已选项 cosine > gate 的候选
    picked: list[tuple[Skill, float]] = []
    picked_embeddings: list[list[float]] = []
    for skill, _cos_to_query, score in scored:
        if len(picked) >= top_k:
            break
        # 检查与已选 skill 的 embedding 相似度
        if any(
            cosine(skill.embedding or [], emb) > DIVERSITY_COSINE_GATE
            for emb in picked_embeddings
        ):
            continue
        picked.append((skill, score))
        picked_embeddings.append(skill.embedding or [])

    # ε-greedy explore: 5% 概率追加 1 个未被选中的 draft skill
    if random.random() < EPSILON_EXPLORE and not include_draft:
        drafts = [
            s for s in _registry.list_for_project(project_id, status="draft")
            if s.embedding is not None
        ]
        chosen_ids = {s.id for s, _ in picked}
        drafts = [d for d in drafts if d.id not in chosen_ids]
        if drafts:
            explore = random.choice(drafts)
            picked.append((explore, 0.0))  # score=0 标识探索项

    return picked


def render_skills_for_prompt(picked: list[tuple[Skill, float]]) -> str:
    """把 select_skills_for_chapter 的结果拼成可塞 system_prompt 的字符串.

    格式:
        ## 项目专家技能 (可参考)
        ---
        <skill1.skill_md>
        ---
        <skill2.skill_md>
        ...
    """
    if not picked:
        return ""
    bodies = [s.skill_md for s, _ in picked]
    return "## 项目专家技能 (可参考)\n\n" + "\n\n---\n\n".join(bodies)


def record_skill_application(
    chapter_id: str,
    project_id: str,
    picked: list[tuple[Skill, float]],
) -> list[SkillApplicationRecord]:
    """把 picked skills 写入 chapter.applied_skills + 更新 skill.usage_count.

    Returns:
        SkillApplicationRecord 列表 (供 generation_service 写入 chapter dump)
    """
    now = datetime.now(UTC)
    records: list[SkillApplicationRecord] = []
    for skill, score in picked:
        records.append(SkillApplicationRecord(
            skill_id=skill.id,
            version=skill.version,
            applied_at=now,
            cosine_similarity=score if score > 0 else None,
        ))
        # 更新 usage_count + last_used_at, 重算 trust_score
        new_metrics = SkillMetrics(
            usage_count=skill.metrics.usage_count + 1,
            acceptance_count=skill.metrics.acceptance_count,
            rejection_count=skill.metrics.rejection_count,
            avg_acceptance_rate=skill.metrics.avg_acceptance_rate,
            trust_score=skill.metrics.trust_score,  # 暂不变, on_chapter_state_changed 再改
        )
        updated = skill.model_copy(update={
            "metrics": new_metrics,
            "last_used_at": now,
            "updated_at": now,
        })
        _registry.update(updated)
    return records


# ─── 核心 API · 反馈循环 ──────────────────────────────────────


def on_chapter_state_changed(
    chapter_id: str,
    applied_skill_records: list[dict[str, Any]],
    action: str,
) -> None:
    """当 chapter 被 approve / reject / regenerate 时回调.

    Args:
        chapter_id: 章节 id (仅日志用)
        applied_skill_records: chapter.applied_skills 列表
            (每项含 skill_id, version, applied_at, cosine_similarity)
        action: 'approved' / 'rejected' / 'regen_big_diff' / 'regen_small_diff'
    """
    delta_map = {
        "approved": (1, 0, +1.0),         # acceptance +1
        "rejected": (0, 1, -1.0),         # rejection +1
        "regen_big_diff": (0, 1, -0.3),   # 隐式负反馈 (用户大幅改写)
        "regen_small_diff": (1, 0, +0.1), # 隐式正反馈 (微调通过)
    }
    if action not in delta_map:
        logger.warning("skill_feedback_unknown_action", action=action)
        return
    acc_d, rej_d, _signal = delta_map[action]

    for rec in applied_skill_records:
        skill_id = rec.get("skill_id")
        if not skill_id:
            continue
        skill = _registry.get(skill_id)
        if skill is None or skill.locked:
            continue

        new_acc = skill.metrics.acceptance_count + acc_d
        new_rej = skill.metrics.rejection_count + rej_d
        total = new_acc + new_rej
        acc_rate = new_acc / total if total > 0 else 0.0
        new_trust = _compute_trust_score(
            acceptance=new_acc,
            rejection=new_rej,
            usage=skill.metrics.usage_count,
            last_used_at=skill.last_used_at,
        )
        new_metrics = SkillMetrics(
            usage_count=skill.metrics.usage_count,
            acceptance_count=new_acc,
            rejection_count=new_rej,
            avg_acceptance_rate=acc_rate,
            trust_score=new_trust,
        )
        now = datetime.now(UTC)
        # 自动 active 条件
        new_status: SkillStatus = skill.status
        if (
            skill.status == "draft"
            and skill.metrics.usage_count >= AUTO_ACTIVE_USAGE_THRESHOLD
            and acc_rate >= AUTO_ACTIVE_ACC_RATE
        ):
            new_status = "active"
            logger.info("skill_auto_promoted", skill_id=skill_id, acc_rate=acc_rate)

        updated = skill.model_copy(update={
            "metrics": new_metrics,
            "status": new_status,
            "updated_at": now,
        })
        _registry.update(updated)
        logger.info(
            "skill_feedback_applied",
            chapter_id=chapter_id,
            skill_id=skill_id,
            action=action,
            new_acc=new_acc,
            new_rej=new_rej,
            new_trust=new_trust,
        )


def _compute_trust_score(
    acceptance: int,
    rejection: int,
    usage: int,
    last_used_at: datetime | None,
) -> float:
    """trust = base_acceptance * recency_decay * usage_confidence.

    base_acceptance = (acc + 1) / (acc + rej + 2)   # Laplace smoothing
    recency_decay   = exp(-days / 30)
    usage_confidence= min(1.0, usage / 10)
    """
    total = acceptance + rejection + 2
    base = (acceptance + 1) / total
    if last_used_at is None:
        recency = 1.0
    else:
        days = (datetime.now(UTC) - last_used_at).total_seconds() / 86400
        recency = math.exp(-days / RECENCY_HALF_LIFE_DAYS)
    confidence = min(1.0, usage / 10.0) if usage > 0 else 0.3  # 0 use → 0.3 默认
    score = base * recency * confidence
    return max(0.0, min(1.0, score))


# ─── 核心 API · 进化 ─────────────────────────────────────────


def should_evolve(skill: Skill) -> bool:
    """检查是否应触发 evolve_skill_v2."""
    if skill.locked:
        return False
    return (
        skill.metrics.usage_count >= EVOLVE_USAGE_THRESHOLD
        and skill.metrics.avg_acceptance_rate < EVOLVE_ACC_RATE_FLOOR
    )


async def evolve_skill_v2(
    skill_id: str,
    failing_chapters: list[dict[str, Any]],
    project_label: str | None = None,
) -> Skill | None:
    """触发 skill v2 蒸馏: 当 skill 表现差时, 用应用过它但被 reject 的 chapter 重新蒸馏.

    Args:
        skill_id: 旧 skill id
        failing_chapters: 应用了该 skill 但 reject 的 chapter dumps
        project_label: 可选项目展示名

    Returns:
        新 skill (parent_skill_id=skill_id, version=old.version+1)
        若旧 skill 不存在 / 被锁 / failing_chapters 空, 返回 None
    """
    old = _registry.get(skill_id)
    if old is None or old.locked or not failing_chapters:
        return None

    new_skill = await distill_skill(
        project_id=old.project_id,
        source_chapters=failing_chapters,
        name_hint=old.name,
        project_label=project_label,
    )
    # 升级 metadata: version 递增, 标识 parent
    promoted = new_skill.model_copy(update={
        "version": old.version + 1,
        "parent_skill_id": old.id,
    })
    _registry.update(promoted)

    # 旧 skill 标 deprecated
    old_deprecated = old.model_copy(update={
        "status": "deprecated",
        "updated_at": datetime.now(UTC),
    })
    _registry.update(old_deprecated)

    logger.info(
        "skill_evolved",
        old_skill_id=skill_id,
        new_skill_id=promoted.id,
        new_version=promoted.version,
    )
    return promoted


# ─── 业务操作 (HTTP 层用) ─────────────────────────────────────


def get_skill(skill_id: str) -> Skill | None:
    return _registry.get(skill_id)


def list_skills(project_id: str, status: SkillStatus | None = None) -> list[Skill]:
    return _registry.list_for_project(project_id, status)


def update_skill(
    skill_id: str,
    skill_md: str | None = None,
    name: str | None = None,
    locked: bool | None = None,
    status: SkillStatus | None = None,
) -> Skill | None:
    skill = _registry.get(skill_id)
    if skill is None:
        return None
    update: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if skill_md is not None:
        update["skill_md"] = skill_md
    if name is not None:
        update["name"] = _sanitize_name(name)
    if locked is not None:
        update["locked"] = locked
    if status is not None:
        update["status"] = status
    updated = skill.model_copy(update=update)
    _registry.update(updated)
    return updated


def delete_skill(skill_id: str) -> bool:
    return _registry.delete(skill_id)


def reset_registry_for_tests() -> None:
    """测试用: 清空 in-memory cache (SQLite 不动)."""
    global _registry
    _registry = _SkillRegistry()
