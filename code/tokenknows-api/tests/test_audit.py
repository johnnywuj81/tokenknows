"""audit · record_egress / list_recent_egress / _estimate_cost / _hash_request.

用 tmp_path + monkeypatch settings.egress_log_path 隔离测试库.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.llm_gateway.audit import (
    PRICING,
    _estimate_cost,
    _hash_request,
    get_db_path,
    list_recent_egress,
    record_egress,
)
from app.llm_gateway.interface import LLMMessage, LLMResponse


@pytest.fixture
def temp_egress_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """每个 test 独立 SQLite 文件, 且重置 _initialized 模块级 flag."""
    import app.llm_gateway.audit as audit_mod
    db_file = str(tmp_path / "egress.sqlite")
    monkeypatch.setattr(audit_mod, "_initialized", False)
    # 让 settings.egress_log_path 指向 tmp
    from app.config.settings import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "egress_log_path", db_file)
    return db_file


def _msg(role: str, content: str) -> LLMMessage:
    return LLMMessage(role=role, content=content)  # type: ignore[arg-type]


def _resp(text: str = "ok", prompt: int = 100, completion: int = 50, ms: int = 1234) -> LLMResponse:
    return LLMResponse(
        text=text,
        usage={"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
        model_used="x",
        provider="anthropic",
        latency_ms=ms,
    )


# ─── _hash_request ──────────────────────────────────────────────────


def test_hash_request_returns_16_chars() -> None:
    """SHA256 截 16 chars."""
    h = _hash_request([_msg("user", "hi")])
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_request_deterministic() -> None:
    """同 messages → 同 hash (重复入库可检测)."""
    msgs = [_msg("user", "hello"), _msg("assistant", "world")]
    assert _hash_request(msgs) == _hash_request(msgs)


def test_hash_request_differs_for_different_content() -> None:
    a = _hash_request([_msg("user", "hello")])
    b = _hash_request([_msg("user", "goodbye")])
    assert a != b


def test_hash_request_role_matters() -> None:
    """user "hi" vs assistant "hi" → 不同 hash (role 是 key 的一部分)."""
    a = _hash_request([_msg("user", "hi")])
    b = _hash_request([_msg("assistant", "hi")])
    assert a != b


# ─── _estimate_cost ─────────────────────────────────────────────────


def test_estimate_cost_anthropic() -> None:
    """Claude $3/M in + $15/M out: 1k in + 1k out = $0.003 + $0.015 = $0.018."""
    cost = _estimate_cost("anthropic", 1000, 1000)
    assert cost == pytest.approx(0.018, abs=1e-6)


def test_estimate_cost_unknown_provider_zero() -> None:
    """未知 provider → 0 (不抛, 不算账)."""
    assert _estimate_cost("nonexistent", 1000, 1000) == 0.0


def test_estimate_cost_zero_tokens() -> None:
    assert _estimate_cost("anthropic", 0, 0) == 0.0


def test_pricing_table_covers_known_providers() -> None:
    """3 个生产 cloud provider 必须有价格 (防 silent zero)."""
    for p in ("anthropic", "openai", "minimax"):
        assert p in PRICING
        in_p, out_p = PRICING[p]
        assert in_p > 0
        assert out_p > 0


# ─── record_egress + list_recent_egress (SQLite 真写) ──────────────


def test_record_and_list(temp_egress_db: str) -> None:
    log_id = record_egress(
        task="weekly_report",
        provider="anthropic",
        model="claude-sonnet-4-6",
        messages=[_msg("user", "test")],
        response=_resp(),
        project_id="proj-1",
        user_id="u-1",
    )
    assert log_id   # uuid
    rows = list_recent_egress(limit=10)
    assert len(rows) >= 1
    last = rows[0]
    assert last["task"] == "weekly_report"
    assert last["provider"] == "anthropic"
    assert last["model"] == "claude-sonnet-4-6"
    assert last["project_id"] == "proj-1"
    assert last["fallback_used"] == 0
    assert last["hash_of_request"]   # 不为空


def test_list_recent_egress_project_filter(temp_egress_db: str) -> None:
    record_egress(task="t1", provider="anthropic", model="m",
                  messages=[_msg("user", "x")], response=_resp(),
                  project_id="proj-A")
    record_egress(task="t2", provider="openai", model="m",
                  messages=[_msg("user", "y")], response=_resp(),
                  project_id="proj-B")
    rows_a = list_recent_egress(project_id="proj-A")
    assert all(r["project_id"] == "proj-A" for r in rows_a)
    assert len(rows_a) >= 1


def test_list_recent_egress_limit(temp_egress_db: str) -> None:
    for i in range(5):
        record_egress(task="t", provider="anthropic", model="m",
                      messages=[_msg("user", f"m{i}")], response=_resp(),
                      project_id="proj-A")
    rows = list_recent_egress(limit=2)
    assert len(rows) == 2


def test_record_with_fallback_flag(temp_egress_db: str) -> None:
    log_id = record_egress(
        task="t", provider="anthropic", model="m",
        messages=[_msg("user", "x")], response=_resp(),
        fallback_used=True,
    )
    rows = list_recent_egress()
    matching = next(r for r in rows if r["id"] == log_id)
    assert matching["fallback_used"] == 1


def test_record_with_metadata(temp_egress_db: str) -> None:
    log_id = record_egress(
        task="t", provider="anthropic", model="m",
        messages=[_msg("user", "x")], response=_resp(),
        metadata={"retry_count": 2, "circuit_breaker_state": "half-open"},
    )
    rows = list_recent_egress()
    matching = next(r for r in rows if r["id"] == log_id)
    assert matching["metadata"]   # 不为空 JSON
    assert "retry_count" in matching["metadata"]


def test_record_without_optional_fields(temp_egress_db: str) -> None:
    """project_id/user_id/metadata 均省略 → 不抛."""
    log_id = record_egress(
        task="t", provider="anthropic", model="m",
        messages=[_msg("user", "x")], response=_resp(),
    )
    assert log_id
    rows = list_recent_egress()
    matching = next(r for r in rows if r["id"] == log_id)
    assert matching["project_id"] is None
    assert matching["user_id"] is None
    assert matching["metadata"] is None


def test_request_size_counts_utf8_bytes(temp_egress_db: str) -> None:
    """中文消息 size > len(text) (UTF-8 编码)."""
    msg = _msg("user", "你好")  # 6 字节 UTF-8
    record_egress(task="t", provider="anthropic", model="m",
                  messages=[msg], response=_resp())
    rows = list_recent_egress()
    assert rows[0]["request_size_bytes"] == 6


# ─── get_db_path ────────────────────────────────────────────────────


def test_get_db_path_returns_absolute() -> None:
    p = get_db_path()
    assert Path(p).is_absolute()
