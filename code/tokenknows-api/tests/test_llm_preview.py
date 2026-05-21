"""LLMRouter.preview() 单测 · T14 dry-run 架构红线.

测试焦点: 不发起真 LLM 调用, 仅展示"如果开启会发哪些字段去哪 provider".
通过 mock get_settings 控制三层开关状态.

架构红线: 永不应出现 '用户以为没出域, 其实出了' 的状态.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.llm_gateway.interface import LLMMessage
from app.llm_gateway.router import LLMRouter
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)  # type: ignore[arg-type]


# ─── LLMRouter.preview() 直接调用 ─────────────────────────────────


def test_preview_when_all_gates_open() -> None:
    """三层全开 → will_send=True + 返回 provider/model."""
    router = LLMRouter()
    # 用 patch 强制 instance + project 都开
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    result = router.preview(
        task="weekly_report",
        messages=[_msg("user", "测试内容 hello world")],
    )

    assert result["will_send"] is True
    assert result["egress_check"]["all_pass"] is True
    assert result["egress_check"]["instance"] is True
    assert result["egress_check"]["project"] is True
    assert result["blocking_reason"] is None
    assert result["provider"]   # 不为空
    assert result["model"]
    assert result["estimated_input_tokens"] > 0
    assert result["estimated_output_tokens"] > 0


def test_preview_instance_gate_closed_blocks() -> None:
    """instance 关 → will_send=False, blocking_reason 提及 instance."""
    router = LLMRouter()
    router.settings.instance_egress_enabled = False
    router.settings.default_project_egress_enabled = True

    result = router.preview(
        task="weekly_report",
        messages=[_msg("user", "x")],
    )
    assert result["will_send"] is False
    assert result["egress_check"]["all_pass"] is False
    assert result["egress_check"]["instance"] is False
    assert "instance" in result["blocking_reason"]


def test_preview_project_gate_closed_blocks() -> None:
    """instance 开 + project 关 → blocking_layer=project."""
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = False

    result = router.preview(
        task="weekly_report",
        messages=[_msg("user", "x")],
    )
    assert result["will_send"] is False
    assert result["egress_check"]["instance"] is True
    assert result["egress_check"]["project"] is False
    assert "project" in result["blocking_reason"]


def test_preview_estimated_tokens_proportional() -> None:
    """input_tokens 随 messages 内容长度增长 (粗略 1 token ≈ 3 字符)."""
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    short = router.preview(
        task="weekly_report",
        messages=[_msg("user", "abc")],
    )
    long = router.preview(
        task="weekly_report",
        messages=[_msg("user", "a" * 900)],
    )
    assert long["estimated_input_tokens"] > short["estimated_input_tokens"]
    # 900 字符 ≈ 300 tokens
    assert 250 <= long["estimated_input_tokens"] <= 350


def test_preview_provider_override_respected() -> None:
    """显式 provider_override → 反映在响应里."""
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    result = router.preview(
        task="weekly_report",
        messages=[_msg("user", "x")],
        provider_override="anthropic",
        model_override="claude-sonnet-4-6",
    )
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-sonnet-4-6"


def test_preview_multiple_messages_summed() -> None:
    """input_tokens 是所有 messages content 长度之和 / 3."""
    router = LLMRouter()
    router.settings.instance_egress_enabled = True
    router.settings.default_project_egress_enabled = True

    result = router.preview(
        task="weekly_report",
        messages=[
            _msg("system", "system prompt 30 chars padding here xx"),
            _msg("user", "user question 30 chars padding too zz"),
        ],
    )
    # 总字符 ≈ 75 → tokens ≈ 25
    assert 20 <= result["estimated_input_tokens"] <= 30


# ─── HTTP 端点 ─────────────────────────────────────────────────────


def test_preview_endpoint_returns_200(client: TestClient) -> None:
    """POST /api/v1/llm/egress/preview · 端点响应 200 + shape."""
    body = {
        "task": "weekly_report",
        "messages": [{"role": "user", "content": "测试"}],
    }
    r = client.post("/api/v1/llm/egress/preview", json=body)
    assert r.status_code == 200
    data = r.json()
    for key in (
        "will_send", "provider", "model",
        "estimated_input_tokens", "estimated_output_tokens",
        "egress_check", "blocking_reason",
    ):
        assert key in data


def test_preview_endpoint_unknown_task_422(client: TestClient) -> None:
    """unknown task → pydantic 拦截, 返 422 (不是 500)."""
    body = {
        "task": "not_a_real_task",
        "messages": [{"role": "user", "content": "x"}],
    }
    r = client.post("/api/v1/llm/egress/preview", json=body)
    assert r.status_code == 422


def test_preview_endpoint_empty_messages_handled(client: TestClient) -> None:
    """空 messages 数组也不 500 (est_input_tokens=0)."""
    body = {
        "task": "weekly_report",
        "messages": [],
    }
    r = client.post("/api/v1/llm/egress/preview", json=body)
    assert r.status_code == 200
    assert r.json()["estimated_input_tokens"] == 0
