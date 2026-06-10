"""Embedding helper · 调 Ollama nomic-embed-text 做 batch 向量化.

为什么不走 LiteLLM:
    LiteLLM 也支持 embeddings 但 ollama embedding 在 LiteLLM 里要 model name
    带 `ollama/` 前缀 + extra_body 兼容差. 直接调 Ollama /api/embed 更简单
    + batch 接口效率高 (单次请求多个文本).

为什么不进 LLM Gateway 主路 (router.generate):
    embedding 不算"出域调用" (因为 Ollama 默认本地), 没 audit_log 必要;
    且 router.generate 是 generation 语义, embedding 不适合复用.
    保持简单, 直接 helper 函数即可.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import httpx

from app.config.logging import logger
from app.config.settings import get_settings


class EmbeddingError(Exception):
    """embed 调用失败. 调用方应捕获并 fallback."""


_DEFAULT_MODEL = "nomic-embed-text:latest"
_TIMEOUT = 60.0


async def embed_batch(
    texts: Sequence[str],
    model: str = _DEFAULT_MODEL,
) -> list[list[float]]:
    """批量 embedding. 空字符串自动占位为 0 向量 (避免后续 cosine 0/0)."""
    if not texts:
        return []

    settings = get_settings()
    # Ollama base_url 形如 http://localhost:11434/v1; embed 在 /api/embed
    base = settings.ollama_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/api/embed"

    # 空字符串 nomic 会返 error, 这里替换成单空格
    safe_texts = [t if t.strip() else " " for t in texts]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={"model": model, "input": list(safe_texts)},
            )
        if resp.status_code != 200:
            raise EmbeddingError(f"ollama {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        vectors = data.get("embeddings") or []
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"返回向量数 {len(vectors)} ≠ 输入数 {len(texts)}"
            )
        logger.info(
            "embedding_batch_done",
            model=model,
            count=len(vectors),
            dim=len(vectors[0]) if vectors else 0,
            load_ms=data.get("load_duration", 0) // 1_000_000,
            total_ms=data.get("total_duration", 0) // 1_000_000,
        )
        return vectors
    except httpx.RequestError as e:
        raise EmbeddingError(f"network: {e}") from e


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度. 任一 0 向量返回 0.0 (避免除零)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
