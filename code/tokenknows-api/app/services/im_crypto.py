"""Fernet 加解密 OAuth tokens (v0.3 T16).

设计:
- 主密钥从 settings.im_encryption_key 读 (base64-encoded 32 字节)
- 加密结果以 hex 字符串存数据库 (避免 BYTEA 在 SQLite 的兼容问题)
- 失败抛 TokenCryptoError (调用方 fall back 重新授权)

生产路径:
- 生成新密钥: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- 私有化部署: 通过 KMS (AWS KMS / GCP KMS) 包装 Fernet key, 启动时解出
- 密钥轮换: MultiFernet([new_key, old_key]) — 留 v0.3 后期
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings


class TokenCryptoError(Exception):
    """加密 / 解密失败. 通常需要用户重新授权."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """单例 Fernet (settings 不可变, 安全 cache)."""
    key = get_settings().im_encryption_key
    if not key:
        raise TokenCryptoError(
            "IM_ENCRYPTION_KEY 未配置; 生成方法见 settings.im_encryption_key docstring"
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    """加密 OAuth token (access_token / refresh_token).

    Returns:
        hex 字符串 (双倍长度, 比 base64 更易在 JSON 里传).
    """
    if not plaintext:
        raise TokenCryptoError("encrypt_token: plaintext empty")
    cipher = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return cipher.hex()


def decrypt_token(ciphertext_hex: str) -> str:
    """解密 OAuth token.

    Raises:
        TokenCryptoError: 密文损坏 / 密钥不对 / 密钥未配置.
    """
    if not ciphertext_hex:
        raise TokenCryptoError("decrypt_token: ciphertext_hex empty")
    try:
        cipher_bytes = bytes.fromhex(ciphertext_hex)
    except ValueError as e:
        raise TokenCryptoError(f"密文不是合法 hex: {e}") from e
    try:
        plain = _get_fernet().decrypt(cipher_bytes)
    except InvalidToken as e:
        raise TokenCryptoError("Fernet 解密失败 (密钥已更换或密文损坏)") from e
    return plain.decode("utf-8")


def reset_fernet_cache() -> None:
    """测试用: settings 变更后强制重建 Fernet."""
    _get_fernet.cache_clear()
