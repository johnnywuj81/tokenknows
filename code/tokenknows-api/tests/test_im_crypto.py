"""Fernet token 加解密 (v0.3 T16).

覆盖:
- 主密钥未配置 → TokenCryptoError
- round-trip: encrypt → decrypt 还原明文
- 空字符串 → 报错
- 错密钥 → TokenCryptoError
- 损坏密文 → TokenCryptoError
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.config import settings as settings_module
from app.services import im_crypto
from app.services.im_crypto import (
    TokenCryptoError,
    decrypt_token,
    encrypt_token,
    reset_fernet_cache,
)


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch):
    """注入一个有效 Fernet 主密钥."""
    key = Fernet.generate_key().decode("utf-8")
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "im_encryption_key", key)
    reset_fernet_cache()
    yield key
    reset_fernet_cache()


@pytest.fixture
def no_key(monkeypatch: pytest.MonkeyPatch):
    s = settings_module.get_settings()
    monkeypatch.setattr(s, "im_encryption_key", None)
    reset_fernet_cache()
    yield
    reset_fernet_cache()


def test_encrypt_without_key_raises(no_key) -> None:
    with pytest.raises(TokenCryptoError, match="IM_ENCRYPTION_KEY"):
        encrypt_token("hello")


def test_decrypt_without_key_raises(no_key) -> None:
    with pytest.raises(TokenCryptoError, match="IM_ENCRYPTION_KEY"):
        decrypt_token("deadbeef")


def test_round_trip_roundtrips_plaintext(with_key) -> None:
    plain = "feishu-access-token-abc-123"
    cipher = encrypt_token(plain)
    assert cipher != plain  # 已加密
    assert len(cipher) > 0
    # hex
    assert all(c in "0123456789abcdef" for c in cipher)
    # 解密还原
    assert decrypt_token(cipher) == plain


def test_round_trip_chinese(with_key) -> None:
    plain = "中文 token 试 unicode 边界"
    cipher = encrypt_token(plain)
    assert decrypt_token(cipher) == plain


def test_empty_plaintext_raises(with_key) -> None:
    with pytest.raises(TokenCryptoError, match="empty"):
        encrypt_token("")


def test_empty_ciphertext_raises(with_key) -> None:
    with pytest.raises(TokenCryptoError, match="empty"):
        decrypt_token("")


def test_corrupted_ciphertext_raises(with_key) -> None:
    # 合法 hex 但不是有效 Fernet 密文
    with pytest.raises(TokenCryptoError, match="Fernet"):
        decrypt_token("00" * 64)


def test_invalid_hex_raises(with_key) -> None:
    with pytest.raises(TokenCryptoError, match="hex"):
        decrypt_token("not-hex-format-ZZZZ")


def test_wrong_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    s = settings_module.get_settings()
    # 用 key A 加密
    key_a = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(s, "im_encryption_key", key_a)
    reset_fernet_cache()
    cipher = encrypt_token("secret")
    # 换 key B 解密 → 失败
    key_b = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(s, "im_encryption_key", key_b)
    reset_fernet_cache()
    with pytest.raises(TokenCryptoError, match="Fernet"):
        decrypt_token(cipher)
    reset_fernet_cache()
