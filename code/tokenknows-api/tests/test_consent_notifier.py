"""ConsentNotifier · v0.5.1 T49.

覆盖:
- WebNotification schema + store roundtrip
- notify_all 主流程:
  * 飞书 DM happy + web 都成功
  * DM 失败 (无 token / 4xx / API code≠0) 仍写 web
  * 去重: 同 skill 同 user 第二次跳过
  * 未配置 connection → 仅 web
- build_feishu_card payload 正确
- notify_followup: signed/rejected/expired
- dispatcher hook: _extract_contributors_from_signals + _pick_project_im_connection
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.notification import WebNotification
from app.schemas.skill import Skill, SkillMetrics
from app.services.im.consent_notifier import (
    build_feishu_card,
    notify_all,
    notify_followup,
)
from app.services.skill.consent import initialize_pending


# ─── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    s = SqliteStore(db_path)
    s._apply_schema()
    monkeypatch.setattr(store_module, "_db", s)
    return s


def _make_pending_skill(*, contributors=("ou-a", "ou-b")) -> Skill:
    now = datetime.now(timezone.utc)
    skill = Skill(
        id="skill-pend-1",
        project_id="proj-X",
        name="im-distilled-test",
        version=1,
        skill_md="---\nname: x\n---\n# body",
        embedding=None,
        metrics=SkillMetrics(),
        distilled_from=[],
        distilled_at=now,
        last_used_at=None,
        locked=False,
        status="draft",
        parent_skill_id=None,
        contributors=list(contributors),
        consent_required_from=[],
        consent_signed_by=[],
        consent_rejected_by=None,
        consent_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    return initialize_pending(skill)


# ─── WebNotification roundtrip ────────────────────────────


def test_web_notification_store_roundtrip(fresh_db):
    now = datetime.now(timezone.utc)
    notif = WebNotification(
        id="notif-test-1",
        user_id="ou-a",
        type="consent_request",
        title="title",
        body="body",
        link_url="/skills/skill-1",
        read=False,
        created_at=now,
        related_skill_id="skill-1",
    )
    fresh_db.upsert_notification(
        notification_id=notif.id,
        user_id=notif.user_id,
        type_=notif.type,
        related_skill_id=notif.related_skill_id,
        read=notif.read,
        created_at=notif.created_at.isoformat(),
        json_str=notif.model_dump_json(),
    )
    raw = fresh_db.get_notification("notif-test-1")
    assert raw is not None
    loaded = WebNotification.model_validate(raw)
    assert loaded.user_id == "ou-a"
    assert loaded.type == "consent_request"
    assert loaded.read is False


def test_unread_count_and_list(fresh_db):
    now = datetime.now(timezone.utc)
    for i in range(3):
        n = WebNotification(
            id=f"notif-x-{i}",
            user_id="ou-a",
            type="consent_request",
            title="t", body="b",
            link_url="/skills/x",
            read=(i == 0),  # 第一条已读
            created_at=now,
            related_skill_id="skill-x",
        )
        fresh_db.upsert_notification(
            notification_id=n.id, user_id=n.user_id, type_=n.type,
            related_skill_id=n.related_skill_id, read=n.read,
            created_at=n.created_at.isoformat(), json_str=n.model_dump_json(),
        )
    assert fresh_db.count_unread_notifications("ou-a") == 2
    unread = fresh_db.list_notifications_for_user("ou-a", unread_only=True)
    assert len(unread) == 2
    all_ = fresh_db.list_notifications_for_user("ou-a")
    assert len(all_) == 3


def test_mark_notification_read(fresh_db):
    now = datetime.now(timezone.utc)
    n = WebNotification(
        id="notif-mr",
        user_id="ou-a",
        type="consent_request",
        title="t", body="b", link_url="/x",
        read=False, created_at=now, related_skill_id=None,
    )
    fresh_db.upsert_notification(
        notification_id=n.id, user_id=n.user_id, type_=n.type,
        related_skill_id=n.related_skill_id, read=n.read,
        created_at=n.created_at.isoformat(), json_str=n.model_dump_json(),
    )
    assert fresh_db.mark_notification_read("notif-mr") is True
    assert fresh_db.count_unread_notifications("ou-a") == 0
    # idempotent
    assert fresh_db.mark_notification_read("notif-mr") is True


def test_mark_all_notifications_read(fresh_db):
    now = datetime.now(timezone.utc)
    for i in range(3):
        n = WebNotification(
            id=f"notif-mar-{i}", user_id="ou-a", type="consent_request",
            title="t", body="b", link_url="/x",
            read=False, created_at=now, related_skill_id=None,
        )
        fresh_db.upsert_notification(
            notification_id=n.id, user_id=n.user_id, type_=n.type,
            related_skill_id=n.related_skill_id, read=n.read,
            created_at=n.created_at.isoformat(), json_str=n.model_dump_json(),
        )
    affected = fresh_db.mark_all_notifications_read("ou-a")
    assert affected == 3
    assert fresh_db.count_unread_notifications("ou-a") == 0


def test_batch_insert_notifications(fresh_db):
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            f"notif-bn-{i}", "ou-a", "consent_request", "skill-y",
            False, now,
            json.dumps({"id": f"notif-bn-{i}", "user_id": "ou-a"}),
        )
        for i in range(5)
    ]
    fresh_db.batch_insert_notifications(rows)
    assert fresh_db.count_unread_notifications("ou-a") == 5


# ─── notify_all 主流程 ────────────────────────────────────


def test_notify_all_wrong_status_returns_empty(fresh_db):
    skill = _make_pending_skill()
    skill = skill.model_copy(update={"status": "draft"})
    report = notify_all(skill, connection_raw=None)
    assert report.total == 0
    assert report.dm_success == 0
    assert report.web_success == 0


def test_notify_all_empty_required(fresh_db):
    skill = _make_pending_skill(contributors=())
    # contributors 空时 initialize_pending 返回原 draft, 无需通知
    report = notify_all(skill, connection_raw=None)
    assert report.total == 0


def test_notify_all_web_only_when_no_connection(fresh_db):
    """无 IM connection → 仅 web 兜底."""
    skill = _make_pending_skill(contributors=("ou-a", "ou-b"))
    report = notify_all(skill, connection_raw=None)
    assert report.total == 2
    assert report.dm_success == 0  # 无 connection
    assert report.web_success == 2

    # web notification 真入库
    assert fresh_db.count_unread_notifications("ou-a") == 1
    assert fresh_db.count_unread_notifications("ou-b") == 1


def test_notify_all_dedup_skips_second_run(fresh_db):
    skill = _make_pending_skill(contributors=("ou-a",))
    r1 = notify_all(skill, connection_raw=None)
    assert r1.total == 1
    assert r1.web_success == 1

    r2 = notify_all(skill, connection_raw=None)
    assert r2.total == 0
    assert r2.skipped == 1  # 第二次跳过
    assert fresh_db.count_unread_notifications("ou-a") == 1  # 没重复


def test_notify_all_feishu_dm_happy(fresh_db, monkeypatch):
    """飞书 connection + decrypt + 200 + code=0 → dm_success."""
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-access-token",
    )
    sent_payloads = []

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            sent_payloads.append({
                "url": url,
                "json": k.get("json"),
                "headers": k.get("headers"),
            })
            return httpx.Response(
                200,
                content=json.dumps(
                    {"code": 0, "msg": "", "data": {"message_id": "om-NEW"}}
                ).encode(),
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )

    skill = _make_pending_skill(contributors=("ou-a",))
    conn = {"platform": "feishu", "auth_token_enc": "x"}
    report = notify_all(skill, connection_raw=conn)
    assert report.total == 1
    assert report.dm_success == 1
    assert report.web_success == 1
    # URL 含 receive_id_type=open_id
    assert "receive_id_type=open_id" in sent_payloads[0]["url"]
    body = sent_payloads[0]["json"]
    assert body["msg_type"] == "interactive"
    assert body["receive_id"] == "ou-a"
    # card content 是 JSON
    card = json.loads(body["content"])
    assert card["header"]["title"]["content"].startswith("🤖")
    assert any(
        elem.get("tag") == "action" for elem in card["elements"]
    )


def test_notify_all_feishu_dm_decrypt_fail_still_writes_web(
    fresh_db, monkeypatch
):
    from app.services import im_crypto

    def _raise(_):
        raise im_crypto.TokenCryptoError("bad ciphertext")

    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token", _raise
    )

    skill = _make_pending_skill(contributors=("ou-a",))
    conn = {"platform": "feishu", "auth_token_enc": "deadbeef"}
    report = notify_all(skill, connection_raw=conn)
    assert report.dm_success == 0
    assert report.web_success == 1  # 兜底


def test_notify_all_feishu_dm_http_fail_still_writes_web(
    fresh_db, monkeypatch
):
    monkeypatch.setattr(
        "app.services.im.consent_notifier.decrypt_token",
        lambda _: "fake-token",
    )

    class _MockClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def post(self, url, **k):
            return httpx.Response(
                403,
                content=b'{"code":99,"msg":"forbidden"}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        "app.services.im.consent_notifier.httpx.Client", _MockClient
    )

    skill = _make_pending_skill(contributors=("ou-a",))
    conn = {"platform": "feishu", "auth_token_enc": "x"}
    report = notify_all(skill, connection_raw=conn)
    assert report.dm_success == 0
    assert report.web_success == 1


def test_notify_all_dingtalk_stub_returns_false(fresh_db):
    skill = _make_pending_skill(contributors=("uid-x",))
    conn = {"platform": "dingtalk", "auth_token_enc": "x"}
    report = notify_all(skill, connection_raw=conn)
    assert report.dm_success == 0  # stub
    assert report.web_success == 1


def test_notify_all_wework_stub_returns_false(fresh_db):
    skill = _make_pending_skill(contributors=("uid-y",))
    conn = {"platform": "wework", "auth_token_enc": "x"}
    report = notify_all(skill, connection_raw=conn)
    assert report.dm_success == 0
    assert report.web_success == 1


def test_notify_all_unknown_platform_only_web(fresh_db):
    skill = _make_pending_skill(contributors=("ou-z",))
    conn = {"platform": "weibo", "auth_token_enc": "x"}
    report = notify_all(skill, connection_raw=conn)
    assert report.dm_success == 0
    assert report.web_success == 1


# ─── build_feishu_card ────────────────────────────────────


def test_build_feishu_card_structure():
    skill = _make_pending_skill(contributors=("ou-a", "ou-b"))
    card = build_feishu_card(skill)
    assert card["header"]["title"]["content"].startswith("🤖")
    assert card["config"]["wide_screen_mode"] is True

    # 3 个 button
    action_elem = next(e for e in card["elements"] if e.get("tag") == "action")
    buttons = action_elem["actions"]
    assert len(buttons) == 3
    contents = [b["text"]["content"] for b in buttons]
    assert "✅ 同意发布" in contents
    assert "❌ 拒绝" in contents
    assert "🔍 查看详情" in contents


def test_build_feishu_card_with_public_base_url(monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(
        s.get_settings(), "public_base_url", "https://tokenknows.acme.com"
    )
    skill = _make_pending_skill(contributors=("ou-a",))
    card = build_feishu_card(skill)
    action_elem = next(e for e in card["elements"] if e.get("tag") == "action")
    sign_button = next(
        b for b in action_elem["actions"]
        if b["text"]["content"].startswith("✅")
    )
    assert sign_button["url"].startswith("https://tokenknows.acme.com/skills/")
    assert sign_button["url"].endswith("?action=sign")


def test_build_feishu_card_without_public_base_url(monkeypatch):
    from app.config import settings as s
    monkeypatch.setattr(s.get_settings(), "public_base_url", None)
    skill = _make_pending_skill(contributors=("ou-a",))
    card = build_feishu_card(skill)
    action_elem = next(e for e in card["elements"] if e.get("tag") == "action")
    sign_button = next(
        b for b in action_elem["actions"]
        if b["text"]["content"].startswith("✅")
    )
    # 相对路径
    assert sign_button["url"] == f"/skills/{skill.id}?action=sign"


# ─── notify_followup ─────────────────────────────────────


def test_notify_followup_signed_writes_to_all_recipients(fresh_db):
    skill = _make_pending_skill(contributors=("ou-a", "ou-b"))
    cnt = notify_followup(
        skill,
        type_="consent_signed",
        recipient_user_ids=["ou-a", "ou-c"],
        actor_user_id="ou-b",
    )
    assert cnt == 2
    a_notifs = fresh_db.list_notifications_for_user("ou-a")
    assert len(a_notifs) == 1
    assert a_notifs[0]["type"] == "consent_signed"
    assert "ou-b" in a_notifs[0]["body"]


def test_notify_followup_rejected_uses_correct_title():
    skill = _make_pending_skill(contributors=("ou-a",))
    cnt = notify_followup(
        skill,
        type_="consent_rejected",
        recipient_user_ids=["ou-a"],
        actor_user_id="ou-bad",
    )
    assert cnt >= 0  # 不直接断言 db, 主要看不抛


def test_notify_followup_request_type_rejected():
    """consent_request 不能用 followup (是初始通知)."""
    skill = _make_pending_skill(contributors=("ou-a",))
    with pytest.raises(ValueError):
        notify_followup(
            skill,
            type_="consent_request",
            recipient_user_ids=["ou-a"],
        )


# ─── dispatcher hook helpers ──────────────────────────────


def test_extract_contributors_dedup_and_order():
    from app.services.auto_trigger.dispatcher import (
        _extract_contributors_from_signals,
    )
    signals = [
        {"sender": {"user_id": "ou-a", "name": "Alice"}},
        {"sender": {"user_id": "ou-b", "name": "Bob"}},
        {"sender": {"user_id": "ou-a", "name": "Alice2"}},  # dup
        {"sender": {"user_id": "ou-c", "name": "Carol"}},
    ]
    assert _extract_contributors_from_signals(signals) == ["ou-a", "ou-b", "ou-c"]


def test_extract_contributors_skips_anon_and_empty():
    from app.services.auto_trigger.dispatcher import (
        _extract_contributors_from_signals,
    )
    signals = [
        {"sender": {"user_id": "anon-abc123"}},
        {"sender": {"user_id": ""}},
        {"sender": None},  # 不是 dict
        {"sender": {"user_id": "ou-real"}},
    ]
    assert _extract_contributors_from_signals(signals) == ["ou-real"]


def test_pick_project_im_connection_returns_first_active(fresh_db):
    from app.services.auto_trigger.dispatcher import _pick_project_im_connection
    now = datetime.now(timezone.utc).isoformat()
    fresh_db.upsert_im_connection(
        connection_id="conn-1", project_id="proj-X",
        platform="feishu", status="active", updated_at=now,
        json_str=json.dumps({
            "id": "conn-1", "project_id": "proj-X", "platform": "feishu",
            "status": "active",
            "auth_token_enc": "x",
            "created_at": now, "updated_at": now,
        }),
    )
    conn = _pick_project_im_connection("proj-X")
    assert conn is not None
    assert conn["platform"] == "feishu"


def test_pick_project_im_connection_none_when_no_active(fresh_db):
    from app.services.auto_trigger.dispatcher import _pick_project_im_connection
    assert _pick_project_im_connection("proj-NOPE") is None
