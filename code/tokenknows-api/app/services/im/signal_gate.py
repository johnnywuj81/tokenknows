"""SignalGate · 判定 IM 消息是否"价值信号" (v0.3 T20 + v0.3.1 G).

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
  R10 默认            → LLM 给分 (v0.3.1: 接 Qwen2.5-3B; 失败回退启发式)

v0.3.1 G:
- classify_message(use_llm=True) async wrapper 接 Ollama qwen2.5:3b
- 同步入口 classify_message_sync 保留启发式 (单测 / 性能优先场景用)
- threshold 由调用方传; 默认从 settings 读
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from app.config.logging import logger
from app.config.settings import get_settings
from app.services.im.connector_base import IMNormalizedMessage

DEFAULT_THRESHOLD = 0.5
"""score ≥ threshold → is_signal=True.

新代码应优先用 get_settings().signal_gate_threshold (运行时可调).
"""


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
    """对单条消息判定 is_signal (同步 / 启发式).

    v0.3.1 注: R10 走启发式. 若需要 LLM 兜底, 用 classify_message_async.

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


# ─── 批量处理 (同步) ────────────────────────────────────────


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


# ─── v0.3.1 G · Qwen 异步分类 ──────────────────────────────


_QWEN_TIMEOUT = 30.0
_QWEN_SYSTEM_PROMPT = (
    "你是一个对话价值判断器. 任务: 判断单条 IM 消息是否包含'价值信号'.\n"
    "价值信号包括: 技术决策、复盘教训、问题解决方案、关键事实陈述.\n"
    "不是价值信号: 闲聊、表情、确认词、转发链接无解读、问句无答.\n"
    "严格返回 JSON 一行, 不要 markdown 代码块:\n"
    '{"signal": true|false, "score": 0.0-1.0, "reason": "≤20字"}'
)


async def _qwen_score_message(
    message_text: str, model: str | None = None
) -> tuple[float, str] | None:
    """调本地 Qwen 给 R10 消息打分. 返 (score, reason); 失败返 None.

    复用 settings.ollama_base_url. 不走 LLM Gateway 主路 (不需要 audit / fallback,
    这是单实例本地推理).
    """
    settings = get_settings()
    use_model = model or settings.signal_gate_llm_model
    if not use_model:
        return None
    base = settings.ollama_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/api/chat"
    payload = {
        "model": use_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _QWEN_SYSTEM_PROMPT},
            {"role": "user", "content": message_text[:600]},
        ],
        "options": {"temperature": 0.0},
    }
    try:
        async with httpx.AsyncClient(timeout=_QWEN_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.warning(
                "signal_gate_qwen_http_error",
                status=resp.status_code, body=resp.text[:200],
            )
            return None
        data = resp.json()
        # Ollama /api/chat 返 {"message": {"content": "..."}}
        content = (data.get("message") or {}).get("content") or ""
        return _parse_qwen_output(content)
    except (httpx.RequestError, ValueError) as e:
        logger.warning("signal_gate_qwen_failed", error=str(e))
        return None


def _parse_qwen_output(content: str) -> tuple[float, str] | None:
    """解析 Qwen 返的 JSON. 容错: 找第一个 { 到最后 } 之间的部分."""
    content = content.strip()
    if not content:
        return None
    # JSON 提取 (Qwen 偶尔会加前后多余文字)
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return None
    score = parsed.get("score")
    reason = parsed.get("reason") or "qwen"
    if not isinstance(score, (int, float)):
        # 兜底: 用 signal 布尔值
        sig = parsed.get("signal")
        if isinstance(sig, bool):
            score = 0.8 if sig else 0.2
        else:
            return None
    score = max(0.0, min(1.0, float(score)))
    return score, str(reason)[:30]


async def classify_message_async(
    message: IMNormalizedMessage,
    context_before: Sequence[IMNormalizedMessage] | None = None,
    context_after: Sequence[IMNormalizedMessage] | None = None,
    threshold: float | None = None,
    use_llm: bool = True,
) -> SignalResult:
    """async 版本; R10 默认会调 Qwen, 失败回退启发式.

    Args:
        threshold: 不传走 settings.signal_gate_threshold.
        use_llm: False 时强制走启发式 (与同步 classify_message 等价).
    """
    threshold = (
        threshold if threshold is not None
        else get_settings().signal_gate_threshold
    )
    # 先跑启发式 (R1-R8 优先级强制)
    heuristic = classify_message(message, context_before, context_after, threshold)
    # 仅 R10 (启发式默认) 才走 LLM 兜底
    if not use_llm or heuristic.rule_id != "R10":
        return heuristic
    text = (message.content or "").strip()
    qwen = await _qwen_score_message(text)
    if qwen is None:
        # LLM 不可用 → 保留启发式结果
        return heuristic
    score, reason = qwen
    return SignalResult(
        is_signal=score >= threshold,
        score=score,
        reason=f"R10-llm: {reason}",
    )


async def classify_batch_async(
    messages: list[IMNormalizedMessage],
    context_window_before: int = 5,
    context_window_after: int = 2,
    threshold: float | None = None,
    use_llm: bool = True,
) -> list[SignalResult]:
    """async 批量 (R10 走 Qwen). 比同步 classify_batch 慢但更准."""
    results: list[SignalResult] = []
    for i, msg in enumerate(messages):
        before = messages[max(0, i - context_window_before):i]
        after = messages[i + 1: i + 1 + context_window_after]
        results.append(await classify_message_async(
            msg, before, after, threshold=threshold, use_llm=use_llm,
        ))
    return results
