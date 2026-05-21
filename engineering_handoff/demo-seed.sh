#!/usr/bin/env bash
# Demo 种子脚本 · 一键准备演示状态
#
# 触发 1 份 weekly_report 文档生成 → 等流水线完成 → 注入 4 类 PII 到章节 1
# (为 T10 脱敏页提供命中演示) → 打印 asset_id + 各页 URL
#
# 用法:
#   ./engineering_handoff/demo-seed.sh
#
# 前提:
#   - 后端跑在 localhost:8001
#   - Ollama 跑在 localhost:11434 (用于真 LLM 生成)

set -euo pipefail

API="http://localhost:8001/api/v1"
WEB="http://localhost:5173"
PROJECT="proj-demo-001"

# ─── 检查依赖 ────────────────────────────────────────────────

command -v curl >/dev/null || { echo "需要 curl"; exit 1; }
command -v python3 >/dev/null || { echo "需要 python3"; exit 1; }

# 后端 healthz
curl -sf "${API}/healthz" >/dev/null || {
    echo "✗ 后端未就绪 (${API}/healthz). 请先启动 uvicorn"
    exit 1
}
# Ollama
curl -sf "http://localhost:11434/api/tags" >/dev/null || {
    echo "⚠ Ollama 不可用. LLM 调用会走 fallback 到 placeholder."
    echo "  建议: ollama serve &"
}

# ─── 1. 触发生成 ─────────────────────────────────────────────

echo "▸ POST /projects/${PROJECT}/assets/generate (weekly_report)"
ASSET_ID=$(curl -sf -X POST "${API}/projects/${PROJECT}/assets/generate" \
    -H "Content-Type: application/json" \
    -d '{"type":"weekly_report","time_window":"this_week","scope":{}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo "  asset_id=${ASSET_ID}"
echo "▸ 等待 5 阶段流水线完成 (60s, 真 LLM 调用~每章 5-10s 并发)..."

for i in {1..30}; do
    sleep 3
    STATUS=$(curl -sf "${API}/assets/${ASSET_ID}/generation/status" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["overall_status"])')
    echo "  [${i}] ${STATUS}"
    if [[ "${STATUS}" == "done" ]]; then break; fi
    if [[ "${STATUS}" == "failed" ]]; then
        echo "✗ pipeline failed"
        exit 1
    fi
done

if [[ "${STATUS}" != "done" ]]; then
    echo "⚠ pipeline 未在 90s 内完成 (status=${STATUS}), 继续注入 PII (可能未生成完)"
fi

# ─── 2. 注入 PII 到章节 1 ─────────────────────────────────────

CH1=$(curl -sf "${API}/assets/${ASSET_ID}/chapters" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')

echo "▸ PATCH chapter[0]=${CH1} · 注入 4 类 PII"

curl -sf -X PATCH "${API}/assets/${ASSET_ID}/chapters/${CH1}" \
    -H "Content-Type: application/json" \
    -d '{"content":"## 本周进展\n\n联系 alice@tokenknows.local 推进 EgressGate PR。\n服务部署在 192.168.10.42。\n\n## 待审\n\nAPI 密钥 sk-ant-api03-demo-key-do-not-use-12345678 已合并。\n客户 Project_OmegaPilot 反馈良好 [1].\n\n## 关键决策\n\n- 引入 EgressGate 中间件 [2]\n- 增加 trust_score 加权公式 [3]"}' > /dev/null

echo "  注入完成: alice@... / 192.168.10.42 / sk-ant-api03-... / Project_OmegaPilot"

# ─── 3. 打印 URL ──────────────────────────────────────────────

cat <<EOF

────────────────────────────────────────────
✓ Demo 种子就绪

asset_id: ${ASSET_ID}

跳转 URL:
  工作台              ${WEB}/projects/${PROJECT}
  文档列表            ${WEB}/projects/${PROJECT}/documents
  文档结果页          ${WEB}/projects/${PROJECT}/documents/${ASSET_ID}
  审批页              ${WEB}/projects/${PROJECT}/documents/${ASSET_ID}/review
  脱敏页 (4 项命中)   ${WEB}/projects/${PROJECT}/documents/${ASSET_ID}/redaction
  项目设置 (LLM)      ${WEB}/projects/${PROJECT}/settings?tab=llm
  Admin 控制台        ${WEB}/admin

按 docs/engineering_handoff/demo-walkthrough.md 走完 10 步流程.
────────────────────────────────────────────
EOF
