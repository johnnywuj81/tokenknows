"""embedding helper · embed_batch (mock httpx) + cosine 数学.

cosine 是纯函数, 跑得快; embed_batch 用 httpx.AsyncClient + mock 替换.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm_gateway.embedding import EmbeddingError, cosine, embed_batch


# ─── cosine ────────────────────────────────────────────────────────


def test_cosine_identical_vectors_is_one() -> None:
    assert cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero() -> None:
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_is_negative_one() -> None:
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_zero() -> None:
    """除零保护."""
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine([1.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_empty_input_returns_zero() -> None:
    assert cosine([], []) == 0.0
    assert cosine([1.0], []) == 0.0


def test_cosine_mismatched_lengths_returns_zero() -> None:
    """768d vs 384d 等差错保护."""
    assert cosine([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_scaling_invariant() -> None:
    """cos(v, 2v) = 1 (尺度无关)."""
    assert cosine([3.0, 4.0], [6.0, 8.0]) == pytest.approx(1.0)


def test_cosine_45_degrees() -> None:
    """[1,0] 与 [1,1] 夹角 45° → cos=√2/2 ≈ 0.707."""
    val = cosine([1.0, 0.0], [1.0, 1.0])
    assert val == pytest.approx(math.sqrt(2) / 2, abs=1e-6)


# ─── embed_batch ───────────────────────────────────────────────────


def _make_response(
    status_code: int = 200,
    embeddings: list[list[float]] | None = None,
    text: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value={
        "embeddings": embeddings or [],
        "load_duration": 1_000_000,
        "total_duration": 2_000_000,
    })
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_embed_batch_empty_returns_empty() -> None:
    """空输入立即返 [] 不调网络."""
    result = await embed_batch([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_batch_returns_vectors() -> None:
    fake_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_resp = _make_response(embeddings=fake_vectors)
    mock_post = AsyncMock(return_value=mock_resp)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        result = await embed_batch(["hello", "world"])
    assert result == fake_vectors


@pytest.mark.asyncio
async def test_embed_batch_http_error_raises() -> None:
    mock_resp = _make_response(status_code=500, text="internal error")
    mock_post = AsyncMock(return_value=mock_resp)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(EmbeddingError) as exc:
            await embed_batch(["x"])
    assert "500" in str(exc.value)


@pytest.mark.asyncio
async def test_embed_batch_count_mismatch_raises() -> None:
    """返回 1 个 vector 但请求 2 个 → 抛."""
    mock_resp = _make_response(embeddings=[[0.1, 0.2]])
    mock_post = AsyncMock(return_value=mock_resp)
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=mock_post))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(EmbeddingError) as exc:
            await embed_batch(["x", "y"])
    assert "≠" in str(exc.value)


@pytest.mark.asyncio
async def test_embed_batch_network_error_raises() -> None:
    """httpx.RequestError → 包装成 EmbeddingError."""
    import httpx

    async def _raise(*args, **kw):
        raise httpx.RequestError("connection refused")
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(side_effect=_raise)))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(EmbeddingError) as exc:
            await embed_batch(["x"])
    assert "network" in str(exc.value)


@pytest.mark.asyncio
async def test_embed_batch_empty_string_replaced_with_space() -> None:
    """空字符串送 nomic 会报错 → 替成单空格 (验证未拒)."""
    sent_payload = {}

    async def capture(url, json):
        sent_payload["json"] = json
        return _make_response(embeddings=[[0.1]])

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(side_effect=capture)))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        await embed_batch([""])
    # 空字符串被替换成空格
    assert sent_payload["json"]["input"] == [" "]


@pytest.mark.asyncio
async def test_embed_batch_strips_v1_suffix_from_base_url() -> None:
    """ollama_base_url 形如 http://x:11434/v1 → /v1 要去掉, 因 /api/embed 不带."""
    sent_url = {}

    async def capture(url, json):
        sent_url["url"] = url
        return _make_response(embeddings=[[0.1]])

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=MagicMock(post=AsyncMock(side_effect=capture)))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("app.llm_gateway.embedding.httpx.AsyncClient", return_value=mock_client):
        await embed_batch(["x"])
    # URL 末尾应该是 /api/embed 不含 /v1
    assert sent_url["url"].endswith("/api/embed")
    assert "/v1/api" not in sent_url["url"]
