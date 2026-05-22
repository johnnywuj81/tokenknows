"""ValueSegment 组装 (v0.3 T21).

来源:
- engineering_handoff/tasks/T21-value-segment-assembly.md
- Proposal §7.2 IM-B.2

把通过 SignalGate 的零散消息聚合成"段", 让现有蒸馏管线 (MVP §C6 Skill) 无差别消费.

组装规则:
- 相邻 signal 消息时间间隔 < 10 分钟 → 同段
- 段最小长度 < 50 字符 → 丢弃
- 段最大长度 > 2000 字符 / 50 条 → 切分
- 话题切换: MVP 用关键词差异 (Jaccard < 0.1); v0.3.1 接 LLM 小模型

写入 value_segments 表 (T16 已就绪).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config.logging import logger
from app.persistence import get_db
from app.schemas.im import (
    IMSourceMode,
    IMUser,
    ValueSegment,
    ValueSegmentSource,
)
from app.services.im.connector_base import IMNormalizedMessage
from app.services.im.signal_gate import SignalResult, classify_batch

# ─── 配置 ────────────────────────────────────────────────────

MAX_GAP = timedelta(minutes=10)
"""相邻 signal 消息间隔 > 此值则切段."""

MIN_SEGMENT_CHARS = 50
"""段太短直接丢弃."""

MAX_SEGMENT_CHARS = 2000
MAX_SEGMENT_MESSAGES = 50

JACCARD_TOPIC_GATE = 0.1
"""相邻消息 Jaccard 相似度 < 此值视为话题切换."""


@dataclass(frozen=True)
class AssembledSegment:
    """组装阶段产出 (含 metadata, 未写库)."""

    content: str
    message_ids: list[str]
    contributors: list[IMUser]
    chat_id: str
    trust_score: float
    first_received_at: datetime
    last_received_at: datetime


# ─── 组装入口 ────────────────────────────────────────────────


def assemble_segments(
    messages: list[IMNormalizedMessage],
    signal_results: list[SignalResult] | None = None,
) -> list[AssembledSegment]:
    """从一批消息组装段. messages 应已按 received_at 升序.

    Args:
        messages: 候选消息 (混 signal + noise)
        signal_results: 与 messages 对应的判定结果; 省略则内部跑 classify_batch

    Returns:
        AssembledSegment 列表 (各段 trust_score = 内部 signal score 均值)
    """
    if not messages:
        return []
    if signal_results is None:
        signal_results = classify_batch(messages)
    if len(signal_results) != len(messages):
        raise ValueError("signal_results 长度与 messages 不匹配")

    # 只保留 signal=True 的消息
    pairs = [
        (msg, sr) for msg, sr in zip(messages, signal_results) if sr.is_signal
    ]
    if not pairs:
        return []

    segments: list[AssembledSegment] = []
    current: list[tuple[IMNormalizedMessage, SignalResult]] = []

    for msg, sr in pairs:
        if not current:
            current = [(msg, sr)]
            continue
        prev_msg, prev_sr = current[-1]
        gap = msg.received_at - prev_msg.received_at
        same_chat = msg.platform_chat_id == prev_msg.platform_chat_id
        if not same_chat or gap > MAX_GAP or _topic_switched(prev_msg, msg):
            segments.append(_close_segment(current))
            current = [(msg, sr)]
            continue
        # 累加; 超过 max → flush
        if (
            len(current) >= MAX_SEGMENT_MESSAGES
            or _total_chars(current) + len(msg.content) > MAX_SEGMENT_CHARS
        ):
            segments.append(_close_segment(current))
            current = [(msg, sr)]
        else:
            current.append((msg, sr))

    if current:
        segments.append(_close_segment(current))

    # 过滤太短的
    return [s for s in segments if len(s.content) >= MIN_SEGMENT_CHARS]


def _close_segment(
    pairs: list[tuple[IMNormalizedMessage, SignalResult]],
) -> AssembledSegment:
    """把累积的 messages + signals 合成一个 AssembledSegment."""
    lines: list[str] = []
    contributors_by_id: dict[str, IMUser] = {}
    message_ids: list[str] = []
    scores: list[float] = []
    for msg, sr in pairs:
        prefix = msg.sender.name if msg.sender and msg.sender.name else "anonymous"
        lines.append(f"{prefix}: {msg.content.strip()}")
        message_ids.append(msg.platform_msg_id)
        scores.append(sr.score)
        if msg.sender and msg.sender.user_id:
            contributors_by_id.setdefault(msg.sender.user_id, msg.sender)
    first = pairs[0][0]
    last = pairs[-1][0]
    return AssembledSegment(
        content="\n".join(lines),
        message_ids=message_ids,
        contributors=list(contributors_by_id.values()),
        chat_id=first.platform_chat_id,
        trust_score=round(sum(scores) / len(scores), 3),
        first_received_at=first.received_at,
        last_received_at=last.received_at,
    )


def _total_chars(pairs: list[tuple[IMNormalizedMessage, SignalResult]]) -> int:
    return sum(len(p[0].content) for p in pairs)


# ─── 话题切换 (Jaccard) ──────────────────────────────────────


def _topic_switched(
    prev: IMNormalizedMessage, cur: IMNormalizedMessage
) -> bool:
    """Jaccard 相似度 < gate 视为切换. 简化: 字符 4-gram 集合.

    短文本 (任一 < 60 字) 不可靠, 直接返回 False 让时间窗主导.
    """
    prev_text = (prev.content or "").lower()
    cur_text = (cur.content or "").lower()
    if len(prev_text) < 60 or len(cur_text) < 60:
        return False
    set_prev = _ngrams(prev_text, 4)
    set_cur = _ngrams(cur_text, 4)
    if not set_prev or not set_cur:
        return False
    inter = len(set_prev & set_cur)
    union = len(set_prev | set_cur)
    sim = inter / union if union else 0.0
    return sim < JACCARD_TOPIC_GATE


def _ngrams(text: str, n: int) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


# ─── 持久化 ──────────────────────────────────────────────────


def persist_segments(
    project_id: str,
    segments: list[AssembledSegment],
    source_mode: IMSourceMode,
) -> list[ValueSegment]:
    """写入 value_segments 表; 返回构造好的 ValueSegment 列表."""
    db = get_db()
    written: list[ValueSegment] = []
    now = datetime.now(timezone.utc)
    for seg in segments:
        vs = ValueSegment(
            id=f"seg-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            source=ValueSegmentSource(
                type="im_thread" if len(seg.message_ids) > 1 else "im_chat",
                mode=source_mode,
                im_chat_id=seg.chat_id,
                im_message_ids=seg.message_ids,
                contributors=seg.contributors,
            ),
            content=seg.content,
            trust_score=seg.trust_score,
            extracted_at=now,
        )
        db.upsert_value_segment(
            segment_id=vs.id,
            project_id=project_id,
            source_type=vs.source.type,
            trust_score=vs.trust_score,
            extracted_at=now.isoformat(),
            json_str=vs.model_dump_json(),
        )
        written.append(vs)
    if written:
        logger.info(
            "value_segments_persisted",
            project=project_id,
            count=len(written),
            source_mode=source_mode,
        )
    return written


def process_messages_to_segments(
    project_id: str,
    messages: list[IMNormalizedMessage],
    source_mode: IMSourceMode = "assistant",
) -> list[ValueSegment]:
    """一站式: SignalGate → assemble → persist. 返回已写入的 ValueSegment."""
    if not messages:
        return []
    signals = classify_batch(messages)
    segments = assemble_segments(messages, signals)
    if not segments:
        return []
    return persist_segments(project_id, segments, source_mode)
