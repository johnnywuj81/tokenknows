"""SignalGate · 判定 IM 消息是否"价值信号" (v0.3 T20).

来源:
- engineering_handoff/tasks/T20-signal-gate.md
- Proposal §7.2 模块 IM-B

规则:
  R1 长度 < 5         → noise (强制)
  R2 全表情/全标点    → noise (强制)
  R3 系统消息标签     → noise (强制)
  R4 纯转发/链接     → noise (强制)
  R5 问句无回答       → weak (score=0.3)
  R6 问答配对         → signal (>=0.7) 强制
  R7 决策表述         → signal (>=0.7) 强制
  R8 复盘/总结        → signal (>=0.7) 强制
  R9 链接 + 长解读   → maybe → LLM
  R10 默认            → LLM 给分

合成: if R1-R4: 0.0; elif R6-R8: max(0.7, llm); else: llm

MVP 简化: R10 不调 LLM, 直接给中性分 0.5. v0.3.1 接 Qwen2.5-3B 本地分类器.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.services.im.connector_base import IMNormalizedMessage

DEFAULT_THRESHOLD = 0.5
"""score ≥ threshold → is_signal=True."""


@dataclass(frozen=True)
class SignalResult:
    """单条消息的判定结果."""

    is_signal: bool
    score: float        # 0.0 - 1.0
    reason: str         # R1 / R2-rule-name / llm 等

    @property
    def rule_id(self) -> str:
        """R1 / R2 / ... 取第一段."""
        return self.reason.split(":", 1)[0].strip()


# ─── 规则字典 (中英关键词) ──────────────────────────────────


_DECISION_KEYWORDS = (
    "决定", "决策", "已通过", "通过决议", "确认要做", "已敲定", "结论是",
    "敲定", "选了", "选择", "决定使用", "我们用", "let's use", "we'll use",
    "decision:",
)

_RETRO_KEYWORDS = (
    "复盘", "回顾", "总结", "教训", "经验", "改进", "下次", "下一步",
    "retro", "lessons learned", "summary",
)

_QUESTION_HINTS = ("?", "？", "如何", "怎么", "为何", "为什么", "可以吗", "能不能", "what", "how", "why", "should we", "do we")

_URL_RE = re.compile(r"https?://\S+")
_PUNCT_ONLY_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)
_EMOJI_RE = re.compile(
    r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]+"
)


# ─── 主入口 ─────────────────────────────────────────────────


def classify_message(
    message: IMNormalizedMessage,
    context_before: Sequence[IMNormalizedMessage] | None = None,
    context_after: Sequence[IMNormalizedMessage] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> SignalResult:
    """对单条消息判定 is_signal.

    Args:
        message: 当前消息
        context_before: 前 N 条 (默认 5; 用于问答配对判断)
        context_after: 后 N 条 (默认 2)
        threshold: 评分阈值

    Returns:
        SignalResult: 含 score / reason
    """
    text = (message.content or "").strip()

    # R1: 长度太短
    if len(text) < 5:
        return SignalResult(is_signal=False, score=0.0, reason="R1: length < 5")

    # R2: 全表情/全标点
    text_no_emoji = _EMOJI_RE.sub("", text).strip()
    if not text_no_emoji or _PUNCT_ONLY_RE.match(text_no_emoji):
        return SignalResult(is_signal=False, score=0.0, reason="R2: emoji/punctuation only")

    # R3: 系统消息标签
    if message.raw_event_type == "system":
        return SignalResult(is_signal=False, score=0.0, reason="R3: system message")

    # R4: 纯转发/链接 (短文本含 URL 且其它内容 < 30 字)
    urls = _URL_RE.findall(text)
    if urls:
        text_no_url = _URL_RE.sub("", text).strip()
        if len(text_no_url) < 30:
            return SignalResult(is_signal=False, score=0.0, reason="R4: link only")

    # R7: 决策表述
    if _contains_keyword(text, _DECISION_KEYWORDS):
        return SignalResult(is_signal=True, score=0.85, reason="R7: decision")

    # R8: 复盘/总结
    if _contains_keyword(text, _RETRO_KEYWORDS):
        return SignalResult(is_signal=True, score=0.8, reason="R8: retro/summary")

    # R6: 问答配对 (前面有问句, 当前消息长度 ≥ 30)
    if context_before and _is_answer_to_recent_question(
        text, list(context_before)
    ):
        return SignalResult(is_signal=True, score=0.75, reason="R6: Q&A pair")

    # R5: 问句无回答
    if _contains_keyword(text, _QUESTION_HINTS) and not _has_followup_answer(
        context_after or ()
    ):
        return SignalResult(is_signal=False, score=0.3, reason="R5: unanswered question")

    # R9 / R10: 兜底 - MVP 给中性分; 后续 v0.3.1 接 Qwen2.5-3B
    # 启发: 长文 (≥ 100 字) 倾向 signal; 短文倾向 weak
    if len(text) >= 100:
        return SignalResult(
            is_signal=True, score=0.6, reason="R10: default (long text)"
        )
    return SignalResult(
        is_signal=False, score=0.4, reason="R10: default (short text)"
    )


# ─── 辅助 ───────────────────────────────────────────────────


def _contains_keyword(text: str, keywords: Sequence[str]) -> bool:
    """大小写不敏感关键词命中."""
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _is_answer_to_recent_question(
    text: str, context_before: list[IMNormalizedMessage]
) -> bool:
    """当前文本 ≥ 30 字 + 前 N 条内有问句."""
    if len(text) < 30:
        return False
    for prev in context_before[-5:]:
        if _contains_keyword(prev.content or "", _QUESTION_HINTS):
            return True
    return False


def _has_followup_answer(
    context_after: Sequence[IMNormalizedMessage], min_len: int = 30
) -> bool:
    """后 N 条是否有 >= min_len 字符的回复 (问题被回答)."""
    return any(len((m.content or "").strip()) >= min_len for m in context_after)


# ─── 批量处理 ───────────────────────────────────────────────


def classify_batch(
    messages: list[IMNormalizedMessage],
    context_window_before: int = 5,
    context_window_after: int = 2,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[SignalResult]:
    """对一批消息逐条判定. 复用上下文减少重复扫描."""
    results: list[SignalResult] = []
    for i, msg in enumerate(messages):
        before = messages[max(0, i - context_window_before):i]
        after = messages[i + 1: i + 1 + context_window_after]
        results.append(
            classify_message(msg, before, after, threshold=threshold)
        )
    return results
