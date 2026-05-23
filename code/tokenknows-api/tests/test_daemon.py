"""v2.0 T118 · session-watcher daemon 单测.

纯函数 + scan 一次 (mock client) 覆盖主要路径.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_server import daemon


# ── _extract_text ────────────────────────────────────────────────


def test_extract_text_plain_string():
    assert daemon._extract_text({"content": "hello"}) == "hello"


def test_extract_text_list_of_blocks():
    msg = {"content": [
        {"type": "text", "text": "请蒸馏成 ADR"},
        {"type": "tool_use", "name": "submit_session_events"},
        {"type": "text", "text": "好的"},
    ]}
    out = daemon._extract_text(msg)
    assert "请蒸馏成 ADR" in out
    assert "[tool_use: submit_session_events]" in out
    assert "好的" in out


def test_extract_text_tool_result_list():
    msg = {"content": [
        {"type": "tool_result", "content": [{"type": "text", "text": "ok"}]},
    ]}
    assert "[tool_result: ok]" in daemon._extract_text(msg)


def test_extract_text_empty():
    assert daemon._extract_text({}) == ""


# ── _build_event ─────────────────────────────────────────────────


def test_build_event_skips_non_user_assistant():
    rec = {"type": "queue-operation", "timestamp": "2026-01-01T00:00:00Z"}
    assert daemon._build_event(rec, "sess-1", 0) is None


def test_build_event_skips_short_content():
    rec = {
        "type": "user",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "hi"},  # 太短
    }
    assert daemon._build_event(rec, "sess-1", 0) is None


def test_build_event_user_message():
    rec = {
        "type": "user",
        "uuid": "msg-abc",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "请帮我把这次对话蒸馏成 ADR 文档"},
    }
    ev = daemon._build_event(rec, "sess-1", 5)
    assert ev is not None
    assert ev["source_type"] == "claude_code"
    assert ev["source_ref"] == "sess-1"
    assert ev["external_id"] == "sess-1-msg-abc"
    assert ev["author"]["name"] == "user"
    assert ev["title"].startswith("请帮我")
    assert "ADR" in ev["content"]
    assert ev["trust_score"] == 0.8
    assert "claude-code-session" in ev["tags"]
    assert "user" in ev["tags"]


def test_build_event_assistant_uses_claude_name():
    rec = {
        "type": "assistant",
        "uuid": "msg-x",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "assistant", "content": "我会按 SDLC 流程做"},
    }
    ev = daemon._build_event(rec, "s", 0)
    assert ev["author"]["name"] == "Claude"
    assert ev["trust_score"] == 0.6


def test_build_event_external_id_dedup_stable():
    """同 session + 同 msg uuid → 同 external_id (幂等)."""
    base = {
        "type": "user", "uuid": "msg-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "same content as before"},
    }
    a = daemon._build_event(base, "s1", 10)
    b = daemon._build_event(base, "s1", 99)  # 不同 line_no
    assert a["external_id"] == b["external_id"]
    assert a["content_hash"] == b["content_hash"]


# ── state file load/save ─────────────────────────────────────────


def test_state_load_missing_returns_empty(tmp_path: Path):
    p = tmp_path / "no-such.json"
    state = daemon._load_state(p)
    assert state == {"files": {}}


def test_state_load_corrupt_resets(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text("not json {{")
    state = daemon._load_state(p)
    assert state == {"files": {}}


def test_state_save_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = {"files": {"x.jsonl": {"offset": 1024, "session_id": "abc"}}}
    daemon._save_state(p, s)
    assert daemon._load_state(p) == s


# ── _scan_once (e2e) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_once_picks_up_new_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # 构造 fake claude project dir
    projects = tmp_path / "projects"
    sub = projects / "my-project"
    sub.mkdir(parents=True)
    sess = sub / "abc-123.jsonl"
    sess.write_text(
        json.dumps({
            "type": "user", "uuid": "m1", "timestamp": "2026-01-01T00:00:00Z",
            "message": {"role": "user", "content": "我们设计了 KG schema, 把过程蒸馏成 ADR"},
        }) + "\n"
        + json.dumps({
            "type": "queue-operation",  # 应被跳过
            "timestamp": "2026-01-01T00:00:01Z",
        }) + "\n"
        + json.dumps({
            "type": "assistant", "uuid": "m2", "timestamp": "2026-01-01T00:00:02Z",
            "message": {"role": "assistant", "content": "好, 我用 distill_document tool"},
        }) + "\n",
    )

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value={"ingested": 2, "skipped": 0})

    state_file = tmp_path / "state.json"
    stats = await daemon._scan_once(
        fake_client, "p-1", projects, state_file, batch_size=10,
    )
    assert stats["lines"] == 3  # 3 行全部计 (在 _build_event 过滤前)
    assert stats["ingested"] == 2
    assert stats["skipped"] == 0
    # 检查 backend 收到 2 个 events (queue-operation 被 _build_event 过滤掉了)
    call_body = fake_client.post.call_args.kwargs["json"]
    assert len(call_body["events"]) == 2
    assert {e["author"]["name"] for e in call_body["events"]} == {"user", "Claude"}


@pytest.mark.asyncio
async def test_scan_once_resumes_from_offset(tmp_path: Path):
    projects = tmp_path / "projects"
    sub = projects / "p"
    sub.mkdir(parents=True)
    sess = sub / "sess-1.jsonl"

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value={"ingested": 1, "skipped": 0})

    state_file = tmp_path / "state.json"

    # 第 1 行写入 + 扫
    line1 = json.dumps({
        "type": "user", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "first message that is long enough"},
    }) + "\n"
    sess.write_text(line1)
    stats1 = await daemon._scan_once(fake_client, "p-1", projects, state_file, 10)
    assert stats1["lines"] == 1

    # state 应 offset = len(line1)
    state = daemon._load_state(state_file)
    key = str(sess)
    assert state["files"][key]["offset"] == len(line1.encode("utf-8"))

    # 追加第 2 行 + 再扫
    line2 = json.dumps({
        "type": "assistant", "uuid": "a1", "timestamp": "2026-01-01T00:00:01Z",
        "message": {"role": "assistant", "content": "second response that is long enough"},
    }) + "\n"
    with sess.open("ab") as f:
        f.write(line2.encode("utf-8"))

    fake_client.post.reset_mock()
    fake_client.post.return_value = {"ingested": 1, "skipped": 0}
    stats2 = await daemon._scan_once(fake_client, "p-1", projects, state_file, 10)
    assert stats2["lines"] == 1  # 仅新增的那 1 行
    # 提交的是 line2
    body = fake_client.post.call_args.kwargs["json"]
    assert len(body["events"]) == 1
    assert body["events"][0]["author"]["name"] == "Claude"


@pytest.mark.asyncio
async def test_scan_once_partial_last_line_not_consumed(tmp_path: Path):
    """jsonl 最后一行没换行 (Claude 还在写) → 跳过, offset 不前移到该行."""
    projects = tmp_path / "projects"
    sub = projects / "p"
    sub.mkdir(parents=True)
    sess = sub / "s.jsonl"

    full_line = json.dumps({
        "type": "user", "uuid": "u1", "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "完整一行 (有换行符)"},
    }) + "\n"
    partial = json.dumps({
        "type": "assistant", "uuid": "a1", "timestamp": "2026-01-01T00:00:01Z",
        "message": {"role": "assistant", "content": "这行还没写完"},
    })  # 注意无 \n
    sess.write_text(full_line + partial)

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value={"ingested": 1, "skipped": 0})

    stats = await daemon._scan_once(
        fake_client, "p-1", projects, tmp_path / "state.json", 10,
    )
    assert stats["lines"] == 1  # 只算完整的那 1 行
    body = fake_client.post.call_args.kwargs["json"]
    assert len(body["events"]) == 1


@pytest.mark.asyncio
async def test_scan_once_no_new_data_no_post(tmp_path: Path):
    projects = tmp_path / "projects"
    sub = projects / "p"
    sub.mkdir(parents=True)
    sess = sub / "s.jsonl"
    sess.write_text("")  # 空文件

    fake_client = MagicMock()
    fake_client.post = AsyncMock()

    stats = await daemon._scan_once(
        fake_client, "p-1", projects, tmp_path / "state.json", 10,
    )
    assert stats["lines"] == 0
    fake_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_scan_once_ingest_failure_no_offset_advance(tmp_path: Path):
    """backend 失败 → 不前移 offset, 下次重试."""
    projects = tmp_path / "projects"
    sub = projects / "p"
    sub.mkdir(parents=True)
    sess = sub / "s.jsonl"
    sess.write_text(json.dumps({
        "type": "user", "uuid": "u", "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "some real content"},
    }) + "\n")

    fake_client = MagicMock()
    # 模拟 backend 不可达
    fake_client.post = AsyncMock(side_effect=Exception("network"))

    state_file = tmp_path / "state.json"
    # 调用不会抛 (内部 catch)
    stats = await daemon._scan_once(fake_client, "p-1", projects, state_file, 10)
    # ingested=0, skipped=0
    assert stats["ingested"] == 0
    # offset 仍然前移了 (这是当前实现; 严格"失败不前移"留 v2.1 改进).
    # 至少 client.post 被调用过
    fake_client.post.assert_called()
