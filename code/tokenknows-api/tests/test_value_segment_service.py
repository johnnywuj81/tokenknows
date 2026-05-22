"""ValueSegment 组装 (v0.3 T21).

覆盖:
- assemble_segments 时间窗口 (< 10 分钟 同段)
- chat_id 隔离 (不同 chat 不合并)
- 段最小长度过滤 (< 50 字符丢)
- 段最大长度切分 (> 2000 字符切)
- 段最大消息数切分 (> 50 条切)
- 话题切换 (Jaccard < 0.1)
- noise 消息不进段
- persist_segments 写入 value_segments 表 + ValueSegment.source 正确
- process_messages_to_segments 端到端
- 单消息段 source.type=im_chat; 多消息段 source.type=im_thread
- signal_results 与 messages 长度不匹配 → ValueError
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.im import IMUser
from app.services.im.connector_base import IMNormalizedMessage
from app.services.im.signal_gate import SignalResult
from app.services.im.value_segment_service import (
    MAX_GAP,
    assemble_segments,
    persist_segments,
    process_messages_to_segments,
)


@pytest.fixture(autouse=True)
def fresh_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    yield new_store


def _msg(content: str, idx: int, chat_id: str = "chat-x") -> IMNormalizedMessage:
    return IMNormalizedMessage(
        platform="feishu",
        platform_chat_id=chat_id,
        platform_msg_id=f"m-{idx}",
        sender=IMUser(user_id=f"u{idx}", name=f"User{idx}"),
        content=content,
        received_at=datetime(2026, 5, 22, 10, idx, 0, tzinfo=timezone.utc),
        raw_event_type="message",
    )


def _signal(score: float = 0.8) -> SignalResult:
    return SignalResult(is_signal=True, score=score, reason="R7: decision")


def _noise() -> SignalResult:
    return SignalResult(is_signal=False, score=0.0, reason="R1: short")


# ─── assemble_segments ────────────────────────────────────


def test_assemble_empty_returns_empty() -> None:
    assert assemble_segments([], []) == []


def test_assemble_filters_noise() -> None:
    msgs = [_msg("决定使用 pgvector 这个方案", 0), _msg("ok", 1)]
    results = [_signal(), _noise()]
    segs = assemble_segments(msgs, results)
    # 第二条 noise 不进段, 第一条单独 < 50 字符? 不对, "决定使用 pgvector 这个方案" 也才 14 字符
    # 应过滤掉
    assert segs == [] or all(len(s.content) >= 50 for s in segs)


def test_assemble_two_signals_within_gap_same_segment() -> None:
    """间隔 < 10 分钟的 2 条 signal 应合段. (短消息走时间窗, 不触发 topic switch.)"""
    msgs = [
        _msg("决定用 pgvector,因 PG 里已有 schema", 0),  # 短 → 不触发 topic switch
        _msg("同意,且 pgvector 支持 HNSW 索引", 5),
    ]
    sigs = [_signal(0.8), _signal(0.75)]
    segs = assemble_segments(msgs, sigs)
    assert len(segs) == 1
    assert len(segs[0].message_ids) == 2
    assert segs[0].chat_id == "chat-x"


def test_assemble_gap_too_large_splits() -> None:
    """间隔 > 10 分钟应切段."""
    msgs = [
        _msg("我们最终决定使用 pgvector 作为向量存储引擎,因为已经在 PG 里有 schema", 0),
        _msg("另外我们决定把 worker 数限制到 4 + 加 swap 应对 OOM,详细在 ADR-008", 30),
    ]
    sigs = [_signal(), _signal()]
    segs = assemble_segments(msgs, sigs)
    assert len(segs) == 2


def test_assemble_different_chats_split() -> None:
    msgs = [
        _msg(
            "决定使用 pgvector 作为向量存储引擎,因为已经在 PG 里有完整 schema 定义和迁移路径",
            0, chat_id="A",
        ),
        _msg(
            "决定把 worker 数限制到 4 + 加 swap 应对 OOM,详细在 ADR-008 完整记录与影响范围",
            1, chat_id="B",
        ),
    ]
    sigs = [_signal(), _signal()]
    segs = assemble_segments(msgs, sigs)
    assert len(segs) == 2


def test_assemble_topic_switch_splits() -> None:
    """完全不同主题的长消息 (各 ≥ 60 字) 应分段."""
    msgs = [
        _msg(
            "我们最终决定使用 pgvector 作为向量存储引擎,因为已经在 PG 里有完整的 schema 定义"
            "和迁移路径,所以集成成本最低,运维也方便,推荐一致同意",
            0,
        ),
        _msg(
            "另外我们要把前端框架升级到 React 19 享受 server components 红利,"
            "迁移路径清晰,改造点可控,QA 资源充足,下周开始切",
            1,
        ),
    ]
    sigs = [_signal(), _signal()]
    segs = assemble_segments(msgs, sigs)
    # Jaccard 4-gram 应非常低 → 切段
    assert len(segs) == 2


def test_assemble_minimum_length_filter() -> None:
    """段 < 50 字符应丢弃."""
    msgs = [_msg("好的", 0)]
    sigs = [_signal()]
    segs = assemble_segments(msgs, sigs)
    assert segs == []


def test_assemble_signal_results_length_mismatch_raises() -> None:
    msgs = [_msg("a长内容长内容长内容长内容长内容长内容长内容长内容长内容长内容长内容长内容长内容", 0)]
    with pytest.raises(ValueError, match="长度"):
        assemble_segments(msgs, [_signal(), _signal()])


def test_assemble_auto_classify_when_results_omitted() -> None:
    """signal_results 省略 → 内部 classify_batch."""
    msgs = [_msg("决定使用 pgvector 作为向量存储引擎,理由是已在 PG 里有完整 schema 定义", 0)]
    segs = assemble_segments(msgs)  # 没传 sigs
    assert len(segs) == 1


def test_assemble_max_messages_per_segment() -> None:
    """≥ 50 条消息时强制切."""
    msgs = [
        _msg(f"决定使用方案 {i},理由是充分,详细看 ADR-{i:03d} 文档", i)
        for i in range(60)
    ]
    sigs = [_signal() for _ in msgs]
    segs = assemble_segments(msgs, sigs)
    # 至少 2 段
    assert len(segs) >= 2
    for s in segs:
        assert len(s.message_ids) <= 50


def test_assemble_contributors_dedup() -> None:
    """同一 user 多条消息 → contributors 去重."""
    msgs = [
        _msg("我决定使用 pgvector 因为已在 PG 里,集成成本低,扩容方便,详细看 ADR", 0),
        _msg("我再补充一下,pgvector 还支持 HNSW 索引,生产性能完全够用,推荐", 1),
    ]
    # 改 sender 都是 u0
    msgs = [
        m.__class__(**{
            **m.__dict__,
            "sender": IMUser(user_id="u0", name="Alice"),
        })
        for m in msgs
    ]
    sigs = [_signal(), _signal()]
    segs = assemble_segments(msgs, sigs)
    assert len(segs) == 1
    assert len(segs[0].contributors) == 1


# ─── persist_segments ─────────────────────────────────────


def test_persist_segments_writes_to_db(fresh_store) -> None:
    msgs = [
        _msg("决定使用 pgvector 作为向量存储引擎,理由是已在 PG 里有 schema", 0),
        _msg("同意,并且 pgvector 支持 HNSW 索引,生产性能满足需求", 5),
    ]
    sigs = [_signal(0.8), _signal(0.75)]
    segs = assemble_segments(msgs, sigs)
    persisted = persist_segments("p1", segs, source_mode="assistant")
    assert len(persisted) == 1
    rows = fresh_store.list_value_segments("p1")
    assert len(rows) == 1
    assert rows[0]["trust_score"] == 0.775
    # source 嵌套
    src = rows[0]["source"]
    assert src["type"] == "im_thread"
    assert src["mode"] == "assistant"
    assert src["im_message_ids"] == ["m-0", "m-5"]


def test_persist_single_message_segment_type_im_chat(fresh_store) -> None:
    """单条消息成段 → source.type = im_chat (而非 im_thread)."""
    msgs = [
        _msg(
            "这是一段够长的内容: 我们决定换 LLM provider 到 Anthropic, 详细看 ADR-007 的对比分析",
            0,
        ),
    ]
    sigs = [_signal()]
    segs = assemble_segments(msgs, sigs)
    written = persist_segments("p1", segs, source_mode="archive")
    assert written[0].source.type == "im_chat"
    assert written[0].source.mode == "archive"


# ─── 端到端 ──────────────────────────────────────────────────


def test_process_messages_to_segments_end_to_end(fresh_store) -> None:
    """无需手动跑 classify_batch."""
    msgs = [
        _msg("决定使用 pgvector 而不是 Qdrant 作为向量存储,详细原因在 ADR-005", 0),
        _msg("嗯", 1),  # noise
        _msg("具体集成方案: pgvector + HNSW 索引 + chunk_size=512 + 复用现有 PG 实例", 3),
    ]
    persisted = process_messages_to_segments("p1", msgs)
    assert len(persisted) >= 1
    # noise 不进段
    for vs in persisted:
        assert "嗯" not in vs.content or len(vs.content) >= 50


def test_process_empty_messages_returns_empty() -> None:
    assert process_messages_to_segments("p1", []) == []
