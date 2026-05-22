# T18 · 飞书 OAuth 接入（个人助理模式）

## 1. 目标
实现飞书个人助理模式的授权全链路：用户点"添加 IM" → 跳飞书 OAuth → 回调换 token → 落 IMConnection。
Proposal: §6.1 旅程 A · 步骤 1-6 / §9.3 飞书适配器

## 2. 范围
- **In**: `FeishuConnector` 的 OAuth 四方法、callback 路由、token 刷新定时任务
- **Out**: 消息读取（T19）、bot 入群（T19）

## 3. 接口契约

实现 `IMConnector` 的 4 个 OAuth 方法：

| 方法 | 飞书 endpoint | 备注 |
|---|---|---|
| `get_authorize_url` | `GET /open-apis/authen/v1/authorize` | scopes: `im:message im:chat:readonly im:chat contact:user.id:readonly` |
| `exchange_code` | `POST /open-apis/authen/v1/access_token` | grant_type=authorization_code |
| `refresh_token` | `POST /open-apis/authen/v1/refresh_access_token` | 过期前 5 分钟自动刷 |
| `revoke` | 本地清除 token，飞书无 revoke API | 标记 connection.status='revoked' |

POST `/api/projects/{pid}/im/connections` 创建记录、返回 `{ connection_id, authorize_url }`。
GET `/api/webhooks/feishu/auth-callback?code=...&state=...` 处理回调，state=connection_id。

## 4. 配置

`.env`:
```
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_ENCRYPT_KEY=xxx       # 事件订阅加密 key (T19 用)
FEISHU_VERIFICATION_TOKEN=xxx # 事件订阅 token (T19 用)
FEISHU_REDIRECT_URI=https://your-domain.com/api/webhooks/feishu/auth-callback
```

## 5. 组件分解

```
backend/src/im/feishu/
├── __init__.py
├── adapter.py               ← @register_connector("feishu") class FeishuConnector
├── oauth.py                 ← 4 个 OAuth 方法的实现
├── client.py                ← httpx async client + token 自动注入 + 错误重试
├── errors.py                ← FeishuAPIError / TokenExpired 等
└── const.py                 ← scopes / base_url / endpoints

backend/src/api/routes/
├── im_connections.py        ← POST/GET/PATCH/DELETE /api/projects/{pid}/im/connections
└── feishu_callback.py       ← GET /api/webhooks/feishu/auth-callback

backend/src/workers/
└── im_token_refresher.py    ← 定时任务：扫即将过期的 token，调 refresh

backend/tests/im/feishu/
├── test_oauth.py            ← 用 respx mock 飞书 endpoint
└── test_callback.py
```

## 6. 状态管理
- access_token 过期前 5 分钟由 worker 自动刷新
- refresh_token 失效时（28 天后）→ connection.status='error'，前端显示"请重新授权"

## 7. 必备状态（DoD）
- [ ] OAuth URL 包含正确的 scopes 和 state
- [ ] callback 校验 state 防 CSRF（state 必须在数据库里能找到对应未完成的 connection）
- [ ] token 用 T16 的 crypto.py 加密落库
- [ ] refresh worker 跑得通；token 离过期 < 5 min 触发刷新
- [ ] revoke 后 connection.status='revoked'，启动数据清理 task（T22）

## 8. 验收
- [ ] 在测试环境用真实飞书账号能完成一遍 OAuth
- [ ] 重复点 "添加 IM" 不会创建多个 pending connection（应复用最近 10min 内未完成的）
- [ ] token 自动刷新生效，无需用户手动重新授权
- [ ] 错误码完整覆盖：app_id 错、code 过期、redirect_uri 不匹配
- [ ] 单测用 respx 模拟，离线可跑

## 9. 已知陷阱
- 飞书的 `tenant_access_token` 和 `user_access_token` 不同；个人助理模式用 `user_access_token`
- redirect_uri 必须**精确匹配**应用后台配置（含 query string），本地开发要用 ngrok
- code 只能用一次，重试会失败；要做幂等（同一 code 第二次直接返回已存在的 connection）
- 飞书 `state` 长度有限（≤ 1024），不要塞太多东西，只放 connection_id（UUID）
- 离线开发：respx mock 必须 mock 完整 token 响应（含 `expires_in / refresh_expires_in`）

## 10. Claude Code 指令
先把 client.py 写完（httpx + 错误处理），再实现 4 个 OAuth 方法，最后接 API 路由。callback 路由的逻辑写完后用 curl 模拟一遍再写测试。
