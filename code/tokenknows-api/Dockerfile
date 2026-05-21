# TokenKnows API · 多阶段构建
# 用法:
#   docker build -t tokenknows/api:dev .
#   docker run --env-file .env.local -p 8001:8001 \
#     -v $(pwd)/data:/app/data \
#     -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
#     tokenknows/api:dev
# 或:
#   docker compose up -d

FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

FROM python:3.11-slim
WORKDIR /app

# curl 用于 healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app/ ./app/
RUN mkdir -p ./data && chmod 750 ./data

# data/ 作为 volume 持久化 SQLite (state.sqlite + egress.sqlite)
VOLUME ["/app/data"]

# 容器默认走 host.docker.internal 连 host 上的 Ollama
ENV API_HOST=0.0.0.0 \
    API_PORT=8001 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
    EGRESS_LOG_PATH=/app/data/egress.sqlite

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/v1/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
