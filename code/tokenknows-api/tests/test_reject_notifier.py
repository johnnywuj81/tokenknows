"""T130 MVP · reject_notifier 单测 + 集成验证.

覆盖:
  · 卡片 builder 字段 (header / chapter info / reason / button URL)
  · notify_chapter_rejected 守卫 (anonymous, 非 open_id, 无 active 连接)
  · 主路径 mock httpx.Client 返回 200 → sent=True
  · 主路径 httpx 200 但 API code!=0 → sent=False
  · 网络异常 → sent=False, 不抛
  · 集成: generation_service.reject_chapter 调用 reject_notifier
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.asset import Asset, Chapter
from app.schemas.im import IMConnection
from app.services import generation_service, reject_notifier


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mk_asset(*, author: str = "ou_alice_openid_abc", asset_id: str = "a1") -> Asset:
    return Asset(
        id=asset_id, project_id="p1", type="adr",
        title="ADR · 关键决策", status="in_review", current_version=1,
        template_id="t", created_by=author, approval_state="pending",
        redaction_state="all_confirmed", created_at=_now(), updated_at=_now(),
    )


def _mk_chapter() -> Chapter:
    return Chapter(
        id="c1", asset_id="a1", asset_version=1, order_index=3,
        title="风险与阻塞", content="...", layout={},
        generated_by=None, regeneration_history=[],
        approval_state="pending",
        created_at="", updated_at="",
    )


def _mk_active_feishu_conn(*, token_enc: str = "enc_token_xxx") -> IMConnection:
    return IMConnection(
        id="conn-1", project_id="p1", platform="feishu",
        tenant_name="Acme Corp", auth_token_enc=token_enc,
        status="active",
        created_at=_now(), updated_at=_now(),
    )


# ── card builder ──────────────────────────────────────────────


def test_build_reject_card_includes_asset_chapter_reason() -> None:
    asset = _mk_asset()
    chapter = _mk_chapter()
    card = reject_notifier.build_reject_card_feishu(asset, chapter, "风险评估不够具体")
    # 头部红色 + 退回提示
    assert card["header"]["template"] == "red"
    assert "章节被退回" in card["header"]["title"]["content"]
    # 序列化看是否带必备文本
    blob = str(card)
    assert "ADR · 关键决策" in blob
    assert "§4 风险与阻塞" in blob  # order_index=3 → §4
    assert "风险评估不够具体" in blob
    assert "ADR 架构决策" in blob  # type label


def test_build_reject_card_truncates_long_reason() -> None:
    asset = _mk_asset()
    chapter = _mk_chapter()
    long_reason = "x" * 800
    card = reject_notifier.build_reject_card_feishu(asset, chapter, long_reason)
    blob = str(card)
    # 应该截到 500 + "…"
    assert "…" in blob
    assert "x" * 800 not in blob


def test_build_reject_card_button_uses_relative_url_when_no_base() -> None:
    """settings.public_base_url 缺 → 用相对路径 (飞书客户端按本机域名)."""
    asset = _mk_asset()
    chapter = _mk_chapter()
    with patch("app.services.reject_notifier.get_settings") as gs:
        s = MagicMock()
        s.public_base_url = None
        gs.return_value = s
        card = reject_notifier.build_reject_card_feishu(asset, chapter, "r")
    btn_url = card["elements"][-1]["actions"][0]["url"]
    assert btn_url == "/projects/p1/documents/a1"


def test_build_reject_card_button_uses_absolute_when_base_set() -> None:
    asset = _mk_asset()
    chapter = _mk_chapter()
    with patch("app.services.reject_notifier.get_settings") as gs:
        s = MagicMock()
        s.public_base_url = "https://tk.example.com/"
        gs.return_value = s
        card = reject_notifier.build_reject_card_feishu(asset, chapter, "r")
    btn_url = card["elements"][-1]["actions"][0]["url"]
    assert btn_url == "https://tk.example.com/projects/p1/documents/a1"


# ── notify_chapter_rejected 守卫 ─────────────────────────────


def test_notify_anonymous_author_skipped() -> None:
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="anonymous"), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "anonymous_author"


def test_notify_empty_author_skipped() -> None:
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author=""), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "anonymous_author"


def test_notify_non_openid_author_without_binding_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T130.4 · author 不是 'ou_xxx' AND ProjectMember 没绑 → 跳过."""
    # 没绑定 (get_member 返 None)
    monkeypatch.setattr(
        "app.services.project.membership.get_member",
        lambda project_id, user_id: None,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="alice@example.com"), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "author_no_feishu_openid"


# ── T130.4 · ProjectMember 反查 ───────────────────────────────


def _mk_member_with_binding(
    user_id: str = "alice@example.com",
    bound: str | None = "ou_alice_bound_xyz",
):
    """构造一个 ProjectMember dict (membership.get_member 返 ProjectMember)."""
    from app.schemas.project_member import ProjectMember
    return ProjectMember(
        id="member-abc",
        project_id="p1",
        user_id=user_id,
        role="contributor",
        added_by="owner1",
        added_at=_now(),
        im_feishu_open_id=bound,
    )


def test_notify_resolves_openid_via_projectmember_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T130.4 · author 是邮箱, 但 ProjectMember 有 im_feishu_open_id 绑定
    → reject_notifier 用绑定的 open_id 当 receive_id."""
    monkeypatch.setattr(
        "app.services.project.membership.get_member",
        lambda project_id, user_id: _mk_member_with_binding(
            user_id="alice@example.com", bound="ou_bound_via_member"
        ),
    )
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(
        _FakeResp(200, {"code": 0, "data": {"message_id": "m_xxx"}})
    )
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="alice@example.com"), _mk_chapter(), "r"
    )
    assert result.sent is True
    # receive_id 应是绑定的 open_id, 不是原 author
    assert fake_client.last_body is not None
    assert fake_client.last_body["receive_id"] == "ou_bound_via_member"


def test_notify_member_lookup_exception_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProjectMember 查询抛异常 → 安全降级到 skip, 不让 reject 流程崩."""
    def _raise(*a, **kw):
        raise RuntimeError("db down")
    monkeypatch.setattr(
        "app.services.project.membership.get_member", _raise
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="alice@example.com"), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "author_no_feishu_openid"


def test_notify_member_empty_binding_treated_as_unbound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProjectMember 存在但 im_feishu_open_id 为空字符串 → 仍当未绑定."""
    monkeypatch.setattr(
        "app.services.project.membership.get_member",
        lambda project_id, user_id: _mk_member_with_binding(
            user_id="alice@example.com", bound="   "  # 全空格
        ),
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="alice@example.com"), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "author_no_feishu_openid"


def test_notify_openid_author_skips_member_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T130.4 · author 已经是 ou_xxx → 不走 ProjectMember 反查 (优化路径)."""
    member_called = {"n": 0}
    def _spy(project_id, user_id):
        member_called["n"] += 1
        return None
    monkeypatch.setattr(
        "app.services.project.membership.get_member", _spy
    )
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(
        _FakeResp(200, {"code": 0, "data": {"message_id": "m_xxx"}})
    )
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(author="ou_alice_already_openid"), _mk_chapter(), "r"
    )
    assert result.sent is True
    assert member_called["n"] == 0  # 直接走快路径不查 member


def test_notify_skipped_when_no_active_feishu_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # author 是 ou_xxx, 跳过 member 查询直接到 connection 检查
    monkeypatch.setattr(
        "app.services.reject_notifier.im_service.list_connections",
        lambda project_id, status=None: [],
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "no_active_feishu_connection"


# ── 主路径 mock httpx ─────────────────────────────────────────


def _stub_decrypt_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.reject_notifier.decrypt_token",
        lambda enc: "fake_access_token",
    )


def _stub_conns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _mk_active_feishu_conn()
    monkeypatch.setattr(
        "app.services.reject_notifier.im_service.list_connections",
        lambda project_id, status=None: [conn] if status == "active" else [],
    )


class _FakeResp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeHttpxClient:
    def __init__(self, resp: _FakeResp, *, raise_on_post: Exception | None = None) -> None:
        self._resp = resp
        self._raise = raise_on_post
        self.last_url: str | None = None
        self.last_body: dict | None = None
        self.last_headers: dict | None = None

    def __enter__(self) -> "_FakeHttpxClient":
        return self

    def __exit__(self, *a, **kw) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict) -> _FakeResp:
        self.last_url = url
        self.last_body = json
        self.last_headers = headers
        if self._raise is not None:
            raise self._raise
        return self._resp


def test_notify_happy_path_sends_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(
        _FakeResp(200, {"code": 0, "data": {"message_id": "om_msgid_xxx"}})
    )
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(), _mk_chapter(), "需更具体"
    )
    assert result.sent is True
    assert result.platform == "feishu"
    assert result.skipped_reason is None
    # 验证 URL + body 关键字段
    assert "/open-apis/im/v1/messages" in (fake_client.last_url or "")
    assert "receive_id_type=open_id" in (fake_client.last_url or "")
    assert fake_client.last_body is not None
    assert fake_client.last_body["receive_id"] == "ou_alice_openid_abc"
    assert fake_client.last_body["msg_type"] == "interactive"
    assert "需更具体" in fake_client.last_body["content"]
    assert fake_client.last_headers is not None
    assert "Bearer fake_access_token" in fake_client.last_headers["Authorization"]


def test_notify_feishu_api_error_returns_sent_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 200 但 API code != 0 → sent=False."""
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(
        _FakeResp(200, {"code": 230005, "msg": "user not in chat"})
    )
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "feishu_http_error"


def test_notify_http_error_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 5xx → sent=False, 不抛."""
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(_FakeResp(503, {"error": "down"}))
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "feishu_http_error"


def test_notify_network_exception_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """httpx.HTTPError → sent=False, 不抛."""
    import httpx
    _stub_conns_ok(monkeypatch)
    _stub_decrypt_ok(monkeypatch)
    fake_client = _FakeHttpxClient(
        _FakeResp(200, {"code": 0}),
        raise_on_post=httpx.ConnectError("connection refused"),
    )
    monkeypatch.setattr(
        "app.services.reject_notifier.httpx.Client",
        lambda timeout: fake_client,
    )
    result = reject_notifier.notify_chapter_rejected(
        _mk_asset(), _mk_chapter(), "r"
    )
    assert result.sent is False
    assert result.skipped_reason == "feishu_http_error"


# ── 集成: reject_chapter → reject_notifier ────────────────────


def test_reject_chapter_invokes_im_notifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reject_chapter 主路径调 reject_notifier.notify_chapter_rejected 一次."""
    asset = _mk_asset(author="ou_carol_openid")
    chapter = _mk_chapter()
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._assets[asset.id] = asset
    generation_service._chapters[asset.id] = [chapter]
    monkeypatch.setattr(generation_service, "_persist_asset", lambda _: None)

    called = {"count": 0, "asset_id": None, "reason": None}

    def fake_notify(a: Asset, c: Chapter, reason: str) -> reject_notifier.NotifyResult:
        called["count"] += 1
        called["asset_id"] = a.id
        called["reason"] = reason
        return reject_notifier.NotifyResult(sent=True, platform="feishu")

    monkeypatch.setattr(reject_notifier, "notify_chapter_rejected", fake_notify)
    result = generation_service.reject_chapter(asset.id, chapter.id, "测试 IM")
    assert result is not None
    assert called["count"] == 1
    assert called["asset_id"] == asset.id
    assert called["reason"] == "测试 IM"
    generation_service._assets.clear()
    generation_service._chapters.clear()


def test_reject_chapter_swallows_notifier_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """notifier 抛异常 → reject_chapter 主流程仍成功返回 chapter."""
    asset = _mk_asset(author="ou_dave_openid")
    chapter = _mk_chapter()
    generation_service._assets.clear()
    generation_service._chapters.clear()
    generation_service._assets[asset.id] = asset
    generation_service._chapters[asset.id] = [chapter]
    monkeypatch.setattr(generation_service, "_persist_asset", lambda _: None)

    def fake_notify_raise(a, c, r):
        raise RuntimeError("notifier boom")

    monkeypatch.setattr(reject_notifier, "notify_chapter_rejected", fake_notify_raise)
    result = generation_service.reject_chapter(asset.id, chapter.id, "r")
    assert result is not None  # 主流程不抛
    assert result.approval_state == "rejected"
    generation_service._assets.clear()
    generation_service._chapters.clear()
