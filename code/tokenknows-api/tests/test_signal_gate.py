"""SignalGate 规则引擎 (v0.3 T20).

覆盖 R1-R10:
- R1 长度 < 5 → noise
- R2 全表情/全标点 → noise
- R3 system → noise
- R4 纯链接(< 30 字补充) → noise
- R5 问句无回答 → weak (score=0.3)
- R6 问答配对 → signal (>=0.7)
- R7 决策表述 → signal
- R8 复盘/总结 → signal
- R10 默认 长文 → signal; 短文 → noise
- classify_batch 上下文窗口正确
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.im import IMUser
from app.services.im.connector_base import IMNormalizedMessage
from app.services.im.signal_gate import (
    SignalResult,
    classify_batch,
    classify_message,
)


def _msg(content: str, raw_type: str = "message") -> IMNormalizedMessage:
    return IMNormalizedMessage(
        platform="feishu",
        platform_chat_id="ch",
        platform_msg_id="m",
        sender=IMUser(user_id="u", name="A"),
        content=content,
        received_at=datetime.now(timezone.utc),
        raw_event_type=raw_type,
    )


# ─── R1 ─────────────────────────────────────────────────────


def test_r1_short_message_is_noise() -> None:
    r = classify_message(_msg("hi"))
    assert r.is_signal is False
    assert r.score == 0.0
    assert r.rule_id == "R1"


def test_r1_empty_after_strip_is_noise() -> None:
    r = classify_message(_msg("   "))
    assert r.is_signal is False
    assert "R1" in r.reason


# ─── R2 ─────────────────────────────────────────────────────


def test_r2_emoji_only_is_noise() -> None:
    r = classify_message(_msg("😀😀😀😀😀"))
    assert r.is_signal is False
    assert "R2" in r.reason


def test_r2_punctuation_only_is_noise() -> None:
    r = classify_message(_msg("......????"))
    assert r.is_signal is False
    assert r.score == 0.0


# ─── R3 ─────────────────────────────────────────────────────


def test_r3_system_message_is_noise() -> None:
    r = classify_message(_msg("用户加入了群聊", raw_type="system"))
    assert r.is_signal is False
    assert r.rule_id == "R3"


# ─── R4 ─────────────────────────────────────────────────────


def test_r4_pure_link_is_noise() -> None:
    r = classify_message(_msg("https://example.com/abc"))
    assert r.is_signal is False
    assert "R4" in r.reason


def test_r4_link_with_long_commentary_passes_through() -> None:
    """链接 + 30+ 字解读 → 不是 R4, 继续走 R10/其它."""
    text = "看这个 https://example.com/abc 它讲了如何在生产环境下优化数据库索引选择和分区策略"
    r = classify_message(_msg(text))
    # 不被 R4 标 noise; 走 R10 长文 → signal
    assert r.rule_id != "R4"


# ─── R7 决策 ────────────────────────────────────────────────


def test_r7_decision_detected() -> None:
    r = classify_message(_msg("我们决定使用 pgvector 而不是 Qdrant, 因为 schema 已经在 PG 里"))
    assert r.is_signal is True
    assert r.score >= 0.7
    assert "R7" in r.reason


def test_r7_english_decision() -> None:
    r = classify_message(_msg("Decision: we'll use pgvector for the embeddings store"))
    assert r.is_signal is True
    assert r.rule_id == "R7"


# ─── R8 复盘/总结 ───────────────────────────────────────────


def test_r8_retro_detected() -> None:
    r = classify_message(_msg("本周复盘: 上线 PR-127 后引发 OOM, 教训是没做 load test"))
    assert r.is_signal is True
    assert r.rule_id == "R8"


def test_r8_summary_keyword() -> None:
    r = classify_message(_msg("总结一下今天讨论的几个关键点和决议执行细节"))
    assert r.is_signal is True


# ─── R6 问答配对 ────────────────────────────────────────────


def test_r6_qa_pair_signal() -> None:
    """前面有问句, 当前 ≥ 30 字 → R6 signal."""
    question = _msg("如何处理 OOM?")
    answer = _msg("把 worker pool 限制到 4 + 加 swap, 同时升级到 minimax-m2:cloud 试试")
    r = classify_message(answer, context_before=[question])
    assert r.is_signal is True
    assert r.rule_id == "R6"


def test_r6_skipped_if_answer_too_short() -> None:
    """回复太短 → 不算 R6."""
    question = _msg("如何处理?")
    short_answer = _msg("不知道")
    r = classify_message(short_answer, context_before=[question])
    # 不应是 R6 signal
    assert r.rule_id != "R6"


# ─── R5 问句无答 ───────────────────────────────────────────


def test_r5_question_without_followup_is_weak() -> None:
    q = _msg("为什么这里要这么处理? 有没有更好的实现方法呢")
    r = classify_message(q, context_after=[])
    assert r.is_signal is False
    assert r.score == 0.3
    assert r.rule_id == "R5"


def test_r5_question_with_long_answer_after_not_r5() -> None:
    q = _msg("为什么要这么处理? 有什么权衡吗")
    long_answer = _msg("因为我们需要保证强一致性 + 跨节点同步, 详细看 ADR-005")
    r = classify_message(q, context_after=[long_answer])
    # 不应是 R5
    assert r.rule_id != "R5"


# ─── R10 默认 ──────────────────────────────────────────────


def test_r10_long_text_default_signal() -> None:
    text = "x" * 120  # ≥ 100 字 → R10 signal
    r = classify_message(_msg(text))
    assert r.is_signal is True
    assert r.score == 0.6
    assert "R10" in r.reason


def test_r10_short_text_default_noise() -> None:
    r = classify_message(_msg("还行吧, 看着办"))
    assert r.is_signal is False
    assert r.score == 0.4


# ─── classify_batch ────────────────────────────────────────


def test_classify_batch_uses_context_window() -> None:
    msgs = [
        _msg("如何处理 OOM?"),
        _msg("你试过了吗"),
        _msg("把 worker pool 限制到 4 + 加 swap, 同时升级到 minimax-m2:cloud 试试看"),
    ]
    results = classify_batch(msgs)
    assert len(results) == 3
    # 第 3 条应能命中 R6 (上文有问句)
    assert results[2].rule_id == "R6"


def test_classify_batch_window_size_bounded() -> None:
    """大量消息时, 上下文窗口只取最近 N 条."""
    msgs = [_msg(f"消息 {i}") for i in range(20)] + [_msg("如何处理?")]
    msgs.append(_msg("可以试试这个方案, 详细看 ADR-005, 这是个完整的回答内容"))
    results = classify_batch(msgs)
    # 最后一条应能命中 R6
    assert results[-1].rule_id == "R6"


# ─── SignalResult ──────────────────────────────────────────


def test_signal_result_rule_id_property() -> None:
    r = SignalResult(is_signal=True, score=0.8, reason="R7: decision detected")
    assert r.rule_id == "R7"
