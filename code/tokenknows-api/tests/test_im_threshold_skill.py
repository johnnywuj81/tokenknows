"""IM Signal threshold → Skill 自动蒸馏 (v0.4.2 T42).

覆盖:
- store: count_im_signals_in_project / list_top_im_signals_in_project
  (含 connection 隔离 / redacted 过滤 / since 窗口)
- threshold_evaluator: im_signal_count_30d / im_signal_count_7d metrics
- dispatcher: agent_skill 类型分支 → 调 skill_service.distill_skill (mocked)
- _build_fake_chapter_from_signals 拼装格式正确
- 端到端: 阈值规则 → schedule → dispatcher.fire → skill draft 入库
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.auto_trigger import ThresholdSpec, TriggerSignal
from app.services import auto_trigger_service as svc
from app.services import skill_service
from app.services.auto_trigger import dispatcher
from app.services.auto_trigger.dispatcher import _build_fake_chapter_from_signals
from app.services.auto_trigger.evaluator.threshold_evaluator import (
    _count_im_signals,
    _resolve_metric,
    evaluate_threshold_rules,
)


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.services import generation_service
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    monkeypatch.setattr(generation_service, "_assets", {})
    monkeypatch.setattr(generation_service, "_chapters", {})
    monkeypatch.setattr(generation_service, "_progress", {})
    return s


def _insert_im_connection(store: SqliteStore, project_id: str, conn_id: str = "conn-1"):
    """插入一条 IM 连接 (供 messages FK)."""
    now = datetime.now(timezone.utc)
    store.upsert_im_connection(
        connection_id=conn_id,
        project_id=project_id,
        platform="feishu",
        status="active",
        updated_at=now.isoformat(),
        json_str=json.dumps({
            "id": conn_id, "project_id": project_id,
            "platform": "feishu", "status": "active",
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }),
    )
    return conn_id


def _insert_im_signal(
    store: SqliteStore, conn_id: str = "conn-1",
    msg_id: str | None = None,
    days_ago: int = 0, is_signal: bool = True,
    sender_name: str = "alice", text: str = "K8s tip",
    redacted: bool = False,
):
    """插入一条 IM message (默认 signal=True)."""
    from uuid import uuid4
    msg_id = msg_id or f"msg-{uuid4().hex[:8]}"
    received_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    retention_until = received_at + timedelta(days=90)
    payload = {
        "id": msg_id, "connection_id": conn_id,
        "platform_chat_id": "chat-1",
        "platform_msg_id": msg_id,
        "received_at": received_at.isoformat(),
        "is_signal": is_signal,
        "redacted": redacted,
        "sender": {"user_id": f"u-{sender_name}", "name": sender_name},
        "text": text,
    }
    store.insert_im_message(
        message_id=msg_id, connection_id=conn_id,
        platform_chat_id="chat-1", platform_msg_id=msg_id,
        received_at=received_at.isoformat(),
        retention_until=retention_until.isoformat(),
        is_signal=is_signal, redacted=redacted,
        json_str=json.dumps(payload),
    )
    return msg_id


# ─── store: count_im_signals_in_project ──────────────────


def test_count_im_signals_in_project(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    for i in range(15):
        _insert_im_signal(fresh_db, days_ago=i, text=f"signal {i}")
    # 5 个 non-signal (噪声不计)
    for i in range(5):
        _insert_im_signal(fresh_db, days_ago=i, text="noise", is_signal=False)
    # 1 个 redacted (不计)
    _insert_im_signal(fresh_db, days_ago=1, text="hidden", redacted=True)

    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    n = fresh_db.count_im_signals_in_project("proj-1", since)
    assert n == 15


def test_count_im_signals_project_isolation(fresh_db):
    _insert_im_connection(fresh_db, "proj-1", conn_id="c1")
    _insert_im_connection(fresh_db, "proj-other", conn_id="c2")
    for _ in range(10):
        _insert_im_signal(fresh_db, conn_id="c1")
    for _ in range(5):
        _insert_im_signal(fresh_db, conn_id="c2")

    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert fresh_db.count_im_signals_in_project("proj-1", since) == 10
    assert fresh_db.count_im_signals_in_project("proj-other", since) == 5


def test_count_im_signals_window(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    _insert_im_signal(fresh_db, days_ago=2)
    _insert_im_signal(fresh_db, days_ago=10)
    _insert_im_signal(fresh_db, days_ago=40)  # 30 天窗口外

    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert fresh_db.count_im_signals_in_project("proj-1", since) == 2


# ─── store: list_top_im_signals_in_project ───────────────


def test_list_top_signals_orders_by_recent(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    _insert_im_signal(fresh_db, days_ago=1, text="newer", msg_id="m-new")
    _insert_im_signal(fresh_db, days_ago=10, text="older", msg_id="m-old")
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    sigs = fresh_db.list_top_im_signals_in_project("proj-1", since, limit=10)
    assert len(sigs) == 2
    assert sigs[0]["text"] == "newer"  # 最新优先


def test_list_top_signals_limit(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    for i in range(25):
        _insert_im_signal(fresh_db, days_ago=i, text=f"s{i}")
    since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    sigs = fresh_db.list_top_im_signals_in_project("proj-1", since, limit=10)
    assert len(sigs) == 10


# ─── threshold evaluator: im_signal_count_30d ────────────


def test_metric_im_signal_count_30d(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    for _ in range(20):
        _insert_im_signal(fresh_db, days_ago=2)
    val = _resolve_metric("im_signal_count_30d", "proj-1", datetime.now(timezone.utc))
    assert val == 20


def test_metric_im_signal_count_7d(fresh_db):
    _insert_im_connection(fresh_db, "proj-1")
    _insert_im_signal(fresh_db, days_ago=1)
    _insert_im_signal(fresh_db, days_ago=8)  # 7 天窗口外
    val = _resolve_metric("im_signal_count_7d", "proj-1", datetime.now(timezone.utc))
    assert val == 1


# ─── _build_fake_chapter_from_signals ────────────────────


def test_fake_chapter_format():
    signals = [
        {
            "id": "m1", "received_at": "2026-05-22T09:00:00+00:00",
            "sender": {"user_id": "u1", "name": "alice"},
            "text": "K8s Pod pending: check nodeSelector",
        },
        {
            "id": "m2", "received_at": "2026-05-22T09:05:00+00:00",
            "sender": {"user_id": "u2", "name": "bob"},
            "text": "Use kubectl describe to debug",
        },
    ]
    ch = _build_fake_chapter_from_signals("proj-1", signals)
    assert ch["title"] == "IM 信号汇编 · proj-1"
    assert ch["approval_state"] == "approved"
    assert "alice" in ch["content"]
    assert "K8s Pod pending" in ch["content"]
    assert "§1" in ch["content"]
    assert "§2" in ch["content"]


def test_fake_chapter_handles_missing_text():
    """text 字段缺失时不抛 (兼容不同 IM 平台 message schema)."""
    signals = [{"id": "m1", "sender": {"name": "x"}}]  # 无 text
    ch = _build_fake_chapter_from_signals("p", signals)
    assert ch["id"]  # 不抛即可


# ─── 端到端: 阈值规则 → schedule → skill 蒸馏 ────────────


def _create_im_skill_rule(**overrides):
    defaults = dict(
        project_id=None,
        name="20 IM signals → 自动 Skill",
        mode="threshold",
        asset_type="agent_skill",
        threshold_spec=ThresholdSpec(
            metric="im_signal_count_30d", comparator=">=", value=20,
        ),
        priority=60, created_by="system",
        cooldown_seconds=86400, daily_cap=2,
    )
    defaults.update(overrides)
    return svc.create_rule(**defaults)


def test_evaluate_im_threshold_schedules(fresh_db):
    _create_im_skill_rule()
    _insert_im_connection(fresh_db, "proj-1")
    # 20 个 signal
    for _ in range(20):
        _insert_im_signal(fresh_db, days_ago=1)
    # 加一个 event 让 list_active_project_ids 命中 proj-1
    fresh_db.upsert_event(
        event_id="e1", project_id="proj-1", source_type="github",
        event_type="commit", occurred_at=datetime.now(timezone.utc).isoformat(),
        ingested_at=datetime.now(timezone.utc).isoformat(),
        content_hash="h1", json_str="{}",
    )
    stats = evaluate_threshold_rules()
    assert stats["scheduled"] == 1


@pytest.mark.asyncio
async def test_dispatcher_agent_skill_routes_to_distill(fresh_db, monkeypatch):
    """rule.asset_type='agent_skill' → dispatcher 走 skill_service.distill_skill 路径."""
    from app.schemas.skill import Skill, SkillMetrics

    # mock skill_service.distill_skill 避免真调 LLM
    _now = datetime.now(timezone.utc)
    mock_distill = AsyncMock(return_value=Skill(
        id="skill-mock-99",
        project_id="proj-1",
        name="mock-skill",
        version=1,
        status="draft",
        skill_md="---\nname: mock-skill\n---\nbody",
        embedding=[0.1] * 8,
        metrics=SkillMetrics(),
        distilled_at=_now,
        created_at=_now,
        updated_at=_now,
    ))
    monkeypatch.setattr(skill_service, "distill_skill", mock_distill)

    rule = _create_im_skill_rule()
    _insert_im_connection(fresh_db, "proj-1")
    for _ in range(5):
        _insert_im_signal(fresh_db, days_ago=1, text="K8s tip from alice")

    # 手动 schedule 一条 execution (fire_at = now-1s 已可 fire)
    exe = svc.schedule_execution(
        rule, "proj-1", TriggerSignal(type="threshold_scan", summary="20 signals reached"),
        withdraw_window_min=0,  # 立即可 fire
    )
    # 把 fire_at 设为过去
    from app.services.auto_trigger_service import _to_iso, _now
    raw = exe.model_dump()
    raw["fire_at"] = _to_iso(_now() - timedelta(seconds=1))
    store_module.get_db().update_trigger_execution(
        execution_id=exe.id, status=exe.status,
        fired_at=None, asset_id=None,
        json_str=json.dumps(raw, default=str),
    )

    artifact_id = await dispatcher.fire(exe.id)
    assert artifact_id == "skill-mock-99"
    assert mock_distill.call_count == 1

    # 检查 distill 接收的 fake chapter
    call_args = mock_distill.call_args
    fake_chapters = call_args.kwargs["source_chapters"]
    assert len(fake_chapters) == 1
    assert "IM 信号汇编" in fake_chapters[0]["content"]
    assert "alice" in fake_chapters[0]["content"]

    # execution 状态机
    again = svc.get_execution(exe.id)
    assert again.status == "fired"
    assert again.asset_id == "skill-mock-99"


@pytest.mark.asyncio
async def test_dispatcher_skill_no_signals_marks_failed(fresh_db, monkeypatch):
    """没 IM signal source → mark_failed 不调 LLM."""
    mock_distill = AsyncMock()
    monkeypatch.setattr(skill_service, "distill_skill", mock_distill)

    rule = _create_im_skill_rule()
    exe = svc.schedule_execution(
        rule, "proj-1", TriggerSignal(type="threshold_scan", summary="x"),
        withdraw_window_min=0,
    )
    from app.services.auto_trigger_service import _to_iso, _now
    raw = exe.model_dump()
    raw["fire_at"] = _to_iso(_now() - timedelta(seconds=1))
    store_module.get_db().update_trigger_execution(
        execution_id=exe.id, status=exe.status,
        fired_at=None, asset_id=None,
        json_str=json.dumps(raw, default=str),
    )

    result = await dispatcher.fire(exe.id)
    assert result is None
    assert mock_distill.call_count == 0
    again = svc.get_execution(exe.id)
    assert again.status == "failed"
    assert "无可用 IM signal" in (again.error_message or "")
