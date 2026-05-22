"""飞书 Webhook 处理 (v0.3.1 P2).

覆盖:
- compute_signature 算法
- verify_signature 常量时间比较 + 错签
- decrypt_payload AES-CBC + PKCS#7
- decrypt_payload 错误 (base64 / 太短 / padding / JSON)
- process_event_payload url_verification challenge
- process_event_payload 未知 event_type 静默 ok
- process_event_payload im.message.receive_v1 happy path
- _parse_event_message 跳过 image/empty
- store_message 写库 + 标 is_signal + 计算 retention_until
- store_message 幂等 (重复 webhook 同 msg_id 返 False)
- handle_webhook 完整链路 (含 signature + 加密)
- handle_webhook 缺 timestamp/nonce → SignatureMismatch
- HTTP endpoint 401 (签名错) / 400 (解密错) / 200 (challenge)
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi.testclient import TestClient

from app.config import settings as settings_module
from app.main import app
from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.services import im_crypto, im_service
from app.services.im import feishu_webhook
from app.services.im.feishu_webhook import (
    DecryptError,
    FeishuWebhookError,
    SignatureMismatch,
    compute_signature,
    decrypt_payload,
    handle_webhook,
    process_event_payload,
    store_message,
    verify_signature,
)
from app.services.im.connector_base import IMNormalizedMessage
from app.schemas.im import IMUser


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "state.sqlite"
    new_store = SqliteStore(db_path)
    new_store._apply_schema()
    monkeypatch.setattr(store_module, "_db", new_store)
    im_service.reset_registry_for_tests()
    s = settings_module.get_settings()
    s.im_encryption_key = Fernet.generate_key().decode()
    s.feishu_encrypt_key = "test-encrypt-key-12345"
    s.feishu_app_id = "cli_test"
    s.feishu_app_secret = "secret"
    im_crypto.reset_fernet_cache()
    yield new_store
    im_crypto.reset_fernet_cache()


# ─── 签名 ────────────────────────────────────────────────────


def test_compute_signature_deterministic() -> None:
    sig = compute_signature("1716000000", "n1", "secret", b'{"a":1}')
    again = compute_signature("1716000000", "n1", "secret", b'{"a":1}')
    assert sig == again
    assert len(sig) == 64  # sha256 hex


def test_compute_signature_changes_with_body() -> None:
    a = compute_signature("ts", "n", "k", b'{"a":1}')
    b = compute_signature("ts", "n", "k", b'{"a":2}')
    assert a != b


def test_verify_signature_correct() -> None:
    raw = b'{"hello":"world"}'
    sig = compute_signature("ts", "nonce", "key", raw)
    assert verify_signature("ts", "nonce", sig, "key", raw) is True


def test_verify_signature_wrong_key() -> None:
    raw = b'{"hello":"world"}'
    sig = compute_signature("ts", "nonce", "key-a", raw)
    assert verify_signature("ts", "nonce", sig, "key-b", raw) is False


def test_verify_signature_tampered_body() -> None:
    raw = b'{"hello":"world"}'
    sig = compute_signature("ts", "nonce", "key", raw)
    tampered = b'{"hello":"hijacked"}'
    assert verify_signature("ts", "nonce", sig, "key", tampered) is False


# ─── AES 解密 ────────────────────────────────────────────────


def _encrypt_for_feishu(plaintext: str, encrypt_key: str) -> str:
    """模拟飞书加密: AES-256-CBC, IV=16 字节随机 + PKCS#7."""
    import os
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    iv = os.urandom(16)
    raw = plaintext.encode("utf-8")
    pad_len = 16 - (len(raw) % 16)
    padded = raw + bytes([pad_len]) * pad_len
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode("utf-8")


def test_decrypt_payload_round_trip() -> None:
    plaintext = json.dumps({"hello": "世界", "n": 42}, ensure_ascii=False)
    cipher = _encrypt_for_feishu(plaintext, "my-encrypt-key")
    out = decrypt_payload(cipher, "my-encrypt-key")
    assert out["hello"] == "世界"
    assert out["n"] == 42


def test_decrypt_payload_wrong_key_raises() -> None:
    cipher = _encrypt_for_feishu('{"x":1}', "key-a")
    with pytest.raises(DecryptError):
        decrypt_payload(cipher, "key-b")


def test_decrypt_payload_too_short_raises() -> None:
    short = base64.b64encode(b"abc").decode("utf-8")
    with pytest.raises(DecryptError, match="太短"):
        decrypt_payload(short, "key")


def test_decrypt_payload_bad_base64_raises() -> None:
    with pytest.raises(DecryptError, match="base64"):
        decrypt_payload("!!not-base64!!", "key")


def test_decrypt_payload_bad_json_raises() -> None:
    """解密后的字节不是合法 UTF-8 JSON."""
    junk = "not json at all and quite a long string of plaintext garbage"
    cipher = _encrypt_for_feishu(junk, "key")
    with pytest.raises(DecryptError, match="非合法 JSON"):
        decrypt_payload(cipher, "key")


# ─── process_event_payload ──────────────────────────────────


def test_url_verification_returns_challenge() -> None:
    payload = {"type": "url_verification", "challenge": "abc-123"}
    out = process_event_payload(payload, tenant_key="tenant-x")
    assert out == {"challenge": "abc-123"}


def test_url_verification_missing_challenge_raises() -> None:
    with pytest.raises(FeishuWebhookError, match="challenge"):
        process_event_payload({"type": "url_verification"}, tenant_key="x")


def test_unknown_event_type_silent_ok() -> None:
    payload = {
        "header": {"event_type": "some.unknown.event"},
        "event": {},
    }
    out = process_event_payload(payload, "x")
    assert out["ok"] is True


def test_message_event_no_connection_returns_ok_with_note() -> None:
    """tenant_key 没匹配任何 active 飞书 connection → 跳过."""
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc_a", "message_id": "om_1",
                "message_type": "text",
                "content": json.dumps({"text": "hi all"}),
                "create_time": "1716370800000",
            },
            "sender": {"sender_id": {"open_id": "ou_1"}, "name": "Alice"},
        },
    }
    out = process_event_payload(payload, tenant_key="ghost-tenant")
    assert out["ok"] is False
    assert "no active connection" in out["note"]


def test_message_event_happy_path_stores(fresh_state: SqliteStore) -> None:
    """active 飞书 connection 匹配 → 写 im_messages."""
    # seed active connection 含 tenant_name="my-tenant"
    conn = im_service.create_connection("p1", "feishu")
    from app.services.im.connector_base import OAuthExchangeResult
    im_service.apply_oauth_result(conn.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
        tenant_name="my-tenant", user_id="ou_owner",
    ))

    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc_a",
                "message_id": "om_real",
                "message_type": "text",
                "content": json.dumps({"text": "我们决定使用 pgvector 而不是 Qdrant"}),
                "create_time": "1716370800000",
                "mentions": [],
            },
            "sender": {"sender_id": {"open_id": "ou_alice"}, "name": "Alice"},
        },
    }
    out = process_event_payload(payload, tenant_key="my-tenant")
    assert out["ok"] is True
    assert out["stored"] is True
    # 复查入库
    rows = fresh_state.list_im_messages(conn.id)
    assert len(rows) == 1
    assert rows[0]["platform_msg_id"] == "om_real"
    assert rows[0]["content"] == "我们决定使用 pgvector 而不是 Qdrant"


def test_message_event_idempotent(fresh_state: SqliteStore) -> None:
    """重复推送同 msg_id → 第二次 stored=False."""
    conn = im_service.create_connection("p1", "feishu")
    from app.services.im.connector_base import OAuthExchangeResult
    im_service.apply_oauth_result(conn.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
        tenant_name="t-x",
    ))
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc", "message_id": "om_dup",
                "message_type": "text",
                "content": json.dumps({"text": "重复消息测试 12345"}),
                "create_time": "1716370800000",
            },
            "sender": {"sender_id": {"open_id": "ou_1"}, "name": "U"},
        },
    }
    out1 = process_event_payload(payload, "t-x")
    out2 = process_event_payload(payload, "t-x")
    assert out1["stored"] is True
    assert out2["stored"] is False


def test_message_event_skips_image_type(fresh_state: SqliteStore) -> None:
    """image / file 消息不入库."""
    conn = im_service.create_connection("p1", "feishu")
    from app.services.im.connector_base import OAuthExchangeResult
    im_service.apply_oauth_result(conn.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
        tenant_name="t-x",
    ))
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc", "message_id": "om_img",
                "message_type": "image",
                "content": json.dumps({"image_key": "xxx"}),
            },
            "sender": {"sender_id": {"open_id": "ou_1"}},
        },
    }
    out = process_event_payload(payload, "t-x")
    assert out["ok"] is True
    assert "skipped" in out["note"]


def test_message_event_skips_empty_text(fresh_state: SqliteStore) -> None:
    conn = im_service.create_connection("p1", "feishu")
    from app.services.im.connector_base import OAuthExchangeResult
    im_service.apply_oauth_result(conn.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
        tenant_name="t-x",
    ))
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc", "message_id": "om_empty",
                "message_type": "text",
                "content": json.dumps({"text": "   "}),
            },
            "sender": {"sender_id": {"open_id": "ou_1"}},
        },
    }
    out = process_event_payload(payload, "t-x")
    assert "skipped" in out["note"]


# ─── store_message 单测 ─────────────────────────────────────


def test_store_message_computes_retention(fresh_state: SqliteStore) -> None:
    conn = im_service.create_connection("p1", "feishu")
    msg = IMNormalizedMessage(
        platform="feishu", platform_chat_id="oc",
        platform_msg_id="om-1",
        sender=IMUser(user_id="ou", name="A"),
        content="决定使用 pgvector 因为已经在 PG 里",
        received_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
    )
    ok = store_message(conn.id, msg)
    assert ok is True
    rows = fresh_state.list_im_messages(conn.id)
    assert rows[0]["retention_until"] is not None
    # 90 天后
    assert "2026-08" in rows[0]["retention_until"]


# ─── handle_webhook 完整链路 ────────────────────────────────


def test_handle_webhook_unencrypted_challenge() -> None:
    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    out = handle_webhook(
        raw_body=body, tenant_key="x",
        timestamp=None, nonce=None, signature=None,
    )
    assert out == {"challenge": "abc"}


def test_handle_webhook_signature_required(monkeypatch) -> None:
    """encrypt_key 配置 + 提供了 signature → 必须验证."""
    body = b'{"type":"url_verification","challenge":"x"}'
    wrong_sig = "deadbeef" * 8
    with pytest.raises(SignatureMismatch):
        handle_webhook(
            raw_body=body, tenant_key="x",
            timestamp="1716000000", nonce="n1", signature=wrong_sig,
        )


def test_handle_webhook_signature_missing_timestamp(monkeypatch) -> None:
    body = b'{"type":"url_verification","challenge":"x"}'
    with pytest.raises(SignatureMismatch, match="缺 timestamp"):
        handle_webhook(
            raw_body=body, tenant_key="x",
            timestamp=None, nonce="n1", signature="abcd",
        )


def test_handle_webhook_signature_ok_with_decryption() -> None:
    """完整加密链路."""
    inner = json.dumps({"type": "url_verification", "challenge": "secret-token"})
    cipher = _encrypt_for_feishu(inner, "test-encrypt-key-12345")
    outer = json.dumps({"encrypt": cipher}).encode()
    sig = compute_signature("ts", "n", "test-encrypt-key-12345", outer)
    out = handle_webhook(
        raw_body=outer, tenant_key="x",
        timestamp="ts", nonce="n", signature=sig,
    )
    assert out["challenge"] == "secret-token"


def test_handle_webhook_encrypted_without_key_raises(monkeypatch) -> None:
    monkeypatch.setattr(settings_module.get_settings(), "feishu_encrypt_key", None)
    outer = json.dumps({"encrypt": "anything"}).encode()
    with pytest.raises(DecryptError, match="未配置"):
        handle_webhook(
            raw_body=outer, tenant_key="x",
            timestamp=None, nonce=None, signature=None,
        )


def test_handle_webhook_bad_json_raises() -> None:
    with pytest.raises(FeishuWebhookError, match="JSON"):
        handle_webhook(
            raw_body=b"not json {",
            tenant_key="x",
            timestamp=None, nonce=None, signature=None,
        )


# ─── HTTP endpoint ──────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_http_unencrypted_challenge(client: TestClient) -> None:
    r = client.post(
        "/api/v1/webhooks/feishu/events/x",
        content=json.dumps({"type": "url_verification", "challenge": "ch-1"}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json() == {"challenge": "ch-1"}


def test_http_bad_signature_returns_401(client: TestClient) -> None:
    body = json.dumps({"type": "url_verification", "challenge": "x"})
    r = client.post(
        "/api/v1/webhooks/feishu/events/t-x",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": "ts",
            "X-Lark-Request-Nonce": "n",
            "X-Lark-Signature": "wrong" * 12,
        },
    )
    assert r.status_code == 401


def test_http_encrypted_message_stored(
    client: TestClient, fresh_state: SqliteStore
) -> None:
    """加密的 message event 经 HTTP 进入 → 入库."""
    conn = im_service.create_connection("p1", "feishu")
    from app.services.im.connector_base import OAuthExchangeResult
    im_service.apply_oauth_result(conn.id, OAuthExchangeResult(
        access_token="t", refresh_token=None, expires_at=None,
        tenant_name="my-tenant",
    ))
    inner = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "chat_id": "oc_a",
                "message_id": "om_http",
                "message_type": "text",
                "content": json.dumps({"text": "我们决定切换前端框架到 React 19"}),
                "create_time": "1716370800000",
            },
            "sender": {"sender_id": {"open_id": "ou_alice"}, "name": "Alice"},
        },
    }
    inner_json = json.dumps(inner, ensure_ascii=False)
    cipher = _encrypt_for_feishu(inner_json, "test-encrypt-key-12345")
    outer = json.dumps({"encrypt": cipher})
    body_bytes = outer.encode("utf-8")
    sig = compute_signature("ts", "n", "test-encrypt-key-12345", body_bytes)

    r = client.post(
        "/api/v1/webhooks/feishu/events/my-tenant",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": "ts",
            "X-Lark-Request-Nonce": "n",
            "X-Lark-Signature": sig,
        },
    )
    assert r.status_code == 200
    assert r.json()["stored"] is True
    rows = fresh_state.list_im_messages(conn.id)
    assert len(rows) == 1
    assert rows[0]["platform_msg_id"] == "om_http"
