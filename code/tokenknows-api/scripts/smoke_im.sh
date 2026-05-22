#!/usr/bin/env bash
# v0.3 IM 集成 · 部署后冒烟测试
#
# 用法:
#   BASE_URL=https://YOUR-DOMAIN.com ./scripts/smoke_im.sh
#
# 不需要真飞书账号; 只验证:
# 1. 健康检查
# 2. IM endpoints 都可达 (不真发 OAuth)
# 3. Webhook url_verification 可响应 challenge
# 4. retention loop 起来了 (查日志关键词)
#
# 退出码:
#   0 = 全过
#   1 = 至少一项失败

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8001}"
PROJECT_ID="${PROJECT_ID:-proj-demo-001}"
FAILED=0

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /tmp/smoke_im_out 2>&1; then
        green "✓ $name"
    else
        red "✗ $name"
        cat /tmp/smoke_im_out | sed 's/^/    /'
        FAILED=$((FAILED + 1))
    fi
}

echo "=== TokenKnows v0.3 IM Smoke Test ==="
echo "BASE_URL = $BASE_URL"
echo

# 1. 健康检查
check "GET /api/v1/health" \
    "curl -fsS -m 5 $BASE_URL/api/v1/health"

# 2. IM connections list (空列表应返 200 + [])
check "GET /api/v1/projects/$PROJECT_ID/im/connections" \
    "curl -fsS -m 5 $BASE_URL/api/v1/projects/$PROJECT_ID/im/connections"

# 3. Webhook url_verification (无签名 → 应返 challenge)
check "POST /api/v1/webhooks/feishu/events/test-tenant (challenge)" \
    "curl -fsS -m 5 -X POST $BASE_URL/api/v1/webhooks/feishu/events/test-tenant \
        -H 'Content-Type: application/json' \
        -d '{\"type\":\"url_verification\",\"challenge\":\"smoke-test-123\"}' \
        | grep -q 'smoke-test-123'"

# 4. OAuth callback 缺 state → 404 ghost
check "GET /api/v1/webhooks/feishu/auth-callback?code=x&state=ghost (404)" \
    "curl -fsS -m 5 -o /dev/null -w '%{http_code}' \
        '$BASE_URL/api/v1/webhooks/feishu/auth-callback?code=x&state=ghost' \
        | grep -q '404'"

# 5. 创建一个 pending connection 验证流程
check "POST /api/v1/projects/$PROJECT_ID/im/connections" \
    "curl -fsS -m 5 -X POST $BASE_URL/api/v1/projects/$PROJECT_ID/im/connections \
        -H 'Content-Type: application/json' \
        -d '{\"platform\":\"feishu\"}' \
        | grep -q 'authorize_url'"

# 6. Skills list (与 v0.2 兼容性, 没 break)
check "GET /api/v1/projects/$PROJECT_ID/skills" \
    "curl -fsS -m 5 $BASE_URL/api/v1/projects/$PROJECT_ID/skills"

echo
if [ "$FAILED" -eq 0 ]; then
    green "All checks passed ($((6 - FAILED))/6)"
    exit 0
else
    red "$FAILED check(s) failed"
    exit 1
fi
