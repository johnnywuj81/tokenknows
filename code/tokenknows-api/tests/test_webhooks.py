"""GitHub webhook 端点单测 · FastAPI TestClient + payload fixtures.

覆盖:
- _verify_signature (HMAC-SHA256, secret unset 接受任意)
- _pr_event / _issue_event / _push_events 三种映射
- 端点路由 + 各 event_type 分支
- ping → pong
- 非支持事件 → skipped
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.gateway.http_api.webhooks import (
    WEBHOOK_SECRET_ENV,
    _issue_event,
    _pr_event,
    _push_events,
    _verify_signature,
)
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ─── _verify_signature ──────────────────────────────────────────────


def test_verify_signature_accepts_when_secret_unset() -> None:
    """secret 未配 → 任何签名都接受 (本地开发模式)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(WEBHOOK_SECRET_ENV, None)
        assert _verify_signature(b"payload", "sha256=anything") is True
        assert _verify_signature(b"payload", None) is True


def test_verify_signature_rejects_bad_sig_when_secret_set() -> None:
    with patch.dict(os.environ, {WEBHOOK_SECRET_ENV: "my-secret"}):
        assert _verify_signature(b"payload", "sha256=wrong") is False


def test_verify_signature_rejects_missing_when_secret_set() -> None:
    with patch.dict(os.environ, {WEBHOOK_SECRET_ENV: "my-secret"}):
        assert _verify_signature(b"payload", None) is False


def test_verify_signature_rejects_wrong_prefix() -> None:
    with patch.dict(os.environ, {WEBHOOK_SECRET_ENV: "s"}):
        assert _verify_signature(b"p", "md5=x") is False


def test_verify_signature_accepts_correct_hmac() -> None:
    secret = "test-secret-123"
    body = b'{"action":"opened"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch.dict(os.environ, {WEBHOOK_SECRET_ENV: secret}):
        assert _verify_signature(body, sig) is True


# ─── _pr_event ──────────────────────────────────────────────────────


def _pr_payload(
    number: int = 42,
    action: str = "opened",
    merged_at: str | None = None,
    state: str = "open",
    **kw: Any,
) -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": number,
            "title": "Fix login bug",
            "body": "Fixes #100",
            "state": state,
            "merged_at": merged_at,
            "updated_at": "2026-05-21T10:00:00Z",
            "user": {"login": "alice", "id": 1},
            "html_url": f"https://github.com/o/r/pull/{number}",
            "head": {"ref": "feature/login"},
            "base": {"ref": "main"},
            **kw,
        },
    }


def test_pr_event_opened_mapped() -> None:
    ev = _pr_event(_pr_payload(), "o/r")
    assert ev is not None
    assert ev.source_type == "github"
    assert ev.event_type == "pr_event"
    assert ev.external_id == "pr-42"
    assert ev.title.startswith("PR #42")
    assert "opened" in ev.tags
    assert ev.payload["number"] == 42


def test_pr_event_merged_state_label() -> None:
    """closed + merged_at → state_label='merged'."""
    ev = _pr_event(
        _pr_payload(action="closed", merged_at="2026-05-21T11:00:00Z", state="closed"),
        "o/r",
    )
    assert ev is not None
    assert ev.payload["state"] == "merged"


def test_pr_event_skipped_action_returns_none() -> None:
    """labeled / unlabeled 等 noise action 跳过."""
    ev = _pr_event(_pr_payload(action="labeled"), "o/r")
    assert ev is None


def test_pr_event_unknown_action_skipped() -> None:
    ev = _pr_event(_pr_payload(action="assigned"), "o/r")
    assert ev is None


# ─── _issue_event ──────────────────────────────────────────────────


def _issue_payload(number: int = 7, action: str = "opened", **kw: Any) -> dict:
    return {
        "action": action,
        "issue": {
            "number": number,
            "title": "Bug: login fails",
            "body": "Stack trace here",
            "state": "open",
            "updated_at": "2026-05-21T10:00:00Z",
            "user": {"login": "bob", "id": 2},
            "html_url": f"https://github.com/o/r/issues/{number}",
            "labels": [{"name": "bug"}, {"name": "p0"}],
            **kw,
        },
    }


def test_issue_event_mapped() -> None:
    ev = _issue_event(_issue_payload(), "o/r")
    assert ev is not None
    assert ev.event_type == "issue_event"
    assert ev.external_id == "issue-7"
    assert ev.payload["labels"] == ["bug", "p0"]


def test_issue_event_pull_request_subtype_skipped() -> None:
    """issue 上包含 pull_request 字段 → 跳过 (是 PR 评论, 不是真 issue)."""
    payload = _issue_payload()
    payload["issue"]["pull_request"] = {"url": "..."}
    ev = _issue_event(payload, "o/r")
    assert ev is None


def test_issue_event_skipped_action() -> None:
    ev = _issue_event(_issue_payload(action="labeled"), "o/r")
    assert ev is None


# ─── _push_events ──────────────────────────────────────────────────


def test_push_events_multiple_commits() -> None:
    payload = {
        "pusher": {"name": "carol"},
        "ref": "refs/heads/main",
        "commits": [
            {
                "id": "abc1234567",
                "message": "feat: add login\n\nBody...",
                "timestamp": "2026-05-21T10:00:00Z",
                "author": {"name": "carol", "email": "c@e.com"},
                "url": "https://gh/c/abc1234567",
                "added": ["a.py"],
                "removed": [],
                "modified": ["b.py"],
            },
            {
                "id": "def9876543",
                "message": "fix typo",
                "timestamp": "2026-05-21T11:00:00Z",
                "author": {"name": "dave", "email": "d@e.com"},
            },
        ],
    }
    events = _push_events(payload, "o/r")
    assert len(events) == 2
    assert events[0].external_id == "commit-abc1234567"
    assert events[0].event_type == "commit"
    assert "commit" in events[0].tags
    assert "main" in events[0].tags


def test_push_events_empty_commits_returns_empty() -> None:
    assert _push_events({"commits": []}, "o/r") == []


def test_push_events_skips_commit_without_id() -> None:
    payload = {"commits": [{"message": "x"}]}
    assert _push_events(payload, "o/r") == []


# ─── HTTP 端点 ─────────────────────────────────────────────────────


def test_webhook_ping_returns_pong(client: TestClient) -> None:
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "ping"},
        content=b"{}",
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("pong") is True


def test_webhook_signature_rejection_401(client: TestClient) -> None:
    with patch.dict(os.environ, {WEBHOOK_SECRET_ENV: "test-secret"}):
        r = client.post(
            "/api/v1/webhooks/github",
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=wrong",
            },
            content=b"{}",
        )
        assert r.status_code == 401


def test_webhook_unhandled_event_skipped(client: TestClient) -> None:
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "fork"},
        json={"repository": {"full_name": "o/r"}},
    )
    assert r.status_code == 200
    assert r.json()["skipped"] == "fork"


def test_webhook_pr_opened_ingests(client: TestClient) -> None:
    payload = _pr_payload(number=99001, action="opened")
    payload["repository"] = {"full_name": "test/repo"}
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "pull_request"},
        json=payload,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["event"] == "pull_request"
    assert body["repo"] == "test/repo"
    # ingested >= 1 (新 PR) 或 skipped=1 (content_hash 已存在)
    assert body["ingested"] + body["skipped"] >= 1


def test_webhook_pr_noisy_action_returns_no_match(client: TestClient) -> None:
    payload = _pr_payload(action="labeled")
    payload["repository"] = {"full_name": "test/repo"}
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "pull_request"},
        json=payload,
    )
    assert r.status_code == 200
    assert "no matching action" in r.json()["skipped"]


def test_webhook_issues_opened(client: TestClient) -> None:
    payload = _issue_payload(number=88001)
    payload["repository"] = {"full_name": "test/repo"}
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "issues"},
        json=payload,
    )
    assert r.status_code == 200
    assert r.json()["event"] == "issues"


def test_webhook_push_with_one_commit(client: TestClient) -> None:
    payload = {
        "repository": {"full_name": "test/repo"},
        "pusher": {"name": "x"},
        "ref": "refs/heads/main",
        "commits": [{
            "id": "deadbeef1234",
            "message": "test commit",
            "timestamp": "2026-05-21T12:00:00Z",
            "author": {"name": "x", "email": "x@y"},
        }],
    }
    r = client.post(
        "/api/v1/webhooks/github",
        headers={"X-GitHub-Event": "push"},
        json=payload,
    )
    assert r.status_code == 200
    assert r.json()["event"] == "push"
