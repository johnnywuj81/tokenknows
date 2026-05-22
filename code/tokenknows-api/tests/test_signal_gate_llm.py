"""SignalGate R10 LLM 兜底 + 阈值 UI (v0.3.1 G).

覆盖:
- _parse_qwen_output 解析 JSON + 容错
- _qwen_score_message 调 Ollama (mock httpx)
- _qwen_score_message HTTP 错误 → None
- classify_message_async R10 走 LLM
- classify_message_async R7 强规则不调 LLM (短路)
- classify_message_async use_llm=False 完全启发式
- classify_batch_async 批量
- HTTP GET/PATCH /im/signal/config
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.schemas.im import IMUser
from app.services.im import signal_gate
from app.services.im.connector_base import IMNormalizedMessage


def _msg(content: str, raw_type: str = "message") -> IMNormalizedMessage:
    return IMNormalizedMessage(
        platform="feishu", platform_chat_id="ch", platform_msg_id="m",
        sender=IMUser(user_id="u"), content=content,
        received_at=datetime.now(timezone.utc),
        raw_event_type=raw_type,
    )


# ─── _parse_qwen_output ─────────────────────────────────────


def test_parse_qwen_output_clean_json() -> None:
    raw = '{"signal": true, "score": 0.8, "reason": "技术决策"}'
    out = signal_gate._parse_qwen_output(raw)
    assert out == (0.8, "技术决策")


def test_parse_qwen_output_strips_surrounding_text() -> None:
    raw = '这条消息分析结果 {"score": 0.6, "reason": "qa"} 完结'
    out = signal_gate._parse_qwen_output(raw)
    assert out == (0.6, "qa")


def test_parse_qwen_output_fallback_to_signal_bool() -> None:
    raw = '{"signal": true, "reason": "x"}'
    out = signal_gate._parse_qwen_output(raw)
    assert out == (0.8, "x")


def test_parse_qwen_output_signal_false_score_low() -> None:
    raw = '{"signal": false, "reason": "noise"}'
    out = signal_gate._parse_qwen_output(raw)
    assert out == (0.2, "noise")


def test_parse_qwen_output_score_clamped_to_unit() -> None:
    raw = '{"score": 1.5, "reason": "x"}'
    out = signal_gate._parse_qwen_output(raw)
    assert out is not None
    assert out[0] == 1.0


def test_parse_qwen_output_invalid_returns_none() -> None:
    assert signal_gate._parse_qwen_output("") is None
    assert signal_gate._parse_qwen_output("not json at all") is None
    assert signal_gate._parse_qwen_output("{invalid") is None
    # 缺 score 和 signal → None
    assert signal_gate._parse_qwen_output('{"reason": "x"}') is None
    # score 非数字
    assert signal_gate._parse_qwen_output('{"score": "high", "reason": "x"}') is None


# ─── _qwen_score_message ────────────────────────────────────


@pytest.mark.asyncio
async def test_qwen_score_empty_model_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(
        settings_module.get_settings(), "signal_gate_llm_model", ""
    )
    out = await signal_gate._qwen_score_message("hello")
    assert out is None


@pytest.mark.asyncio
async def test_qwen_score_http_200_returns_score() -> None:
    fake_resp = httpx.Response(
        200,
        json={"message": {"content": '{"score": 0.75, "reason": "决策"}'}},
        request=httpx.Request("POST", "http://x"),
    )
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=fake_resp)):
        out = await signal_gate._qwen_score_message("text")
    assert out == (0.75, "决策")


@pytest.mark.asyncio
async def test_qwen_score_http_5xx_returns_none() -> None:
    fake_resp = httpx.Response(
        503, text="busy", request=httpx.Request("POST", "http://x")
    )
    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=fake_resp)):
        out = await signal_gate._qwen_score_message("text")
    assert out is None


@pytest.mark.asyncio
async def test_qwen_score_network_error_returns_none() -> None:
    with patch.object(
        httpx.AsyncClient, "post",
        side_effect=httpx.ConnectError("refused"),
    ):
        out = await signal_gate._qwen_score_message("text")
    assert out is None


# ─── classify_message_async ─────────────────────────────────


@pytest.mark.asyncio
async def test_classify_async_r7_short_circuit_no_llm_call() -> None:
    """R7 决策关键词命中, 不应调 LLM."""
    called = {"n": 0}

    async def fake_score(text):
        called["n"] += 1
        return (0.5, "x")

    with patch.object(signal_gate, "_qwen_score_message", new=fake_score):
        r = await signal_gate.classify_message_async(
            _msg("我们决定使用 pgvector 而不是 Qdrant")
        )
    assert r.is_signal is True
    assert r.rule_id == "R7"
    assert called["n"] == 0


_R10_NEUTRAL_TEXT = "今天我把上周的事务理了一下 内容已经放在共享盘 大家空的时候看一眼就好"
"""中性文本: 不含 R5-R8 关键词 (没有 ? 没有 决定 复盘 总结 如何 怎么),
长度 < 100 字 → 启发式落 R10 noise."""


@pytest.mark.asyncio
async def test_classify_async_r10_calls_llm() -> None:
    """R10 默认分支应调 LLM."""

    async def fake_score(text):
        return (0.7, "qwen-reason")

    with patch.object(signal_gate, "_qwen_score_message", new=fake_score):
        r = await signal_gate.classify_message_async(_msg(_R10_NEUTRAL_TEXT))
    assert r.is_signal is True
    assert r.score == 0.7
    assert "R10-llm" in r.reason


@pytest.mark.asyncio
async def test_classify_async_llm_failed_fallback_to_heuristic() -> None:
    """Qwen 返 None → 用启发式结果."""

    async def fake_score(text):
        return None

    with patch.object(signal_gate, "_qwen_score_message", new=fake_score):
        r = await signal_gate.classify_message_async(_msg(_R10_NEUTRAL_TEXT))
    # 启发式 R10 - 短文 → noise
    assert r.rule_id == "R10"


@pytest.mark.asyncio
async def test_classify_async_use_llm_false_forces_heuristic() -> None:
    """use_llm=False 时即使 R10 也不调 LLM."""
    called = {"n": 0}

    async def fake_score(text):
        called["n"] += 1
        return (0.9, "should-not-be-called")

    with patch.object(signal_gate, "_qwen_score_message", new=fake_score):
        r = await signal_gate.classify_message_async(
            _msg(_R10_NEUTRAL_TEXT), use_llm=False,
        )
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_classify_async_threshold_overrides_settings() -> None:
    """传 threshold=0.9 时, LLM 返 0.7 → is_signal=False."""

    async def fake_score(text):
        return (0.7, "mid")

    with patch.object(signal_gate, "_qwen_score_message", new=fake_score):
        r = await signal_gate.classify_message_async(
            _msg(_R10_NEUTRAL_TEXT),
            threshold=0.9,
        )
    assert r.score == 0.7
    assert r.is_signal is False


@pytest.mark.asyncio
async def test_classify_batch_async_uses_context() -> None:
    msgs = [
        _msg("如何处理 OOM 问题呢"),
        _msg("把 worker pool 限制到 4 + 加 swap 应对 OOM 即可解决问题完整记录"),
    ]
    results = await signal_gate.classify_batch_async(msgs, use_llm=False)
    # 第 2 条 R6 命中
    assert results[1].rule_id == "R6"


# ─── HTTP signal/config ─────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_signal_config_returns_current(client: TestClient, monkeypatch) -> None:
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "signal_gate_threshold", 0.5)
    monkeypatch.setattr(s, "signal_gate_llm_model", "qwen2.5:3b")
    r = client.get("/api/v1/projects/p1/im/signal/config")
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] == 0.5
    assert body["llm_model"] == "qwen2.5:3b"


def test_patch_signal_config_updates_threshold(client: TestClient) -> None:
    r = client.patch(
        "/api/v1/projects/p1/im/signal/config",
        json={"threshold": 0.7},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] == 0.7
    # 复查二次 GET
    r2 = client.get("/api/v1/projects/p1/im/signal/config")
    assert r2.json()["threshold"] == 0.7


def test_patch_signal_config_rejects_out_of_range(client: TestClient) -> None:
    r = client.patch(
        "/api/v1/projects/p1/im/signal/config",
        json={"threshold": 1.5},
    )
    assert r.status_code == 422


def test_patch_signal_config_change_model(client: TestClient) -> None:
    r = client.patch(
        "/api/v1/projects/p1/im/signal/config",
        json={"llm_model": "qwen2.5:7b"},
    )
    assert r.status_code == 200
    assert r.json()["llm_model"] == "qwen2.5:7b"
