# T01 · 认证流程(注册 / 登录 / 邮箱验证 / 找回密码)

## 1. 目标
用户首次接触产品的入口。覆盖 4 个子页:注册、登录、邮箱验证、找回密码。
PRD: §4.1 旅程 A · 首次接入与项目空间创建

## 2. 路由

| 子页 | 路径 |
|---|---|
| 登录 | `/login` |
| 注册 | `/register` |
| 邮箱验证 | `/verify-email?token=xxx` |
| 找回密码 | `/forgot-password` |
| 重置密码 | `/reset-password?token=xxx` |

未登录访问受保护路由 → 重定向到 `/login?redirect=/原路径`。
已登录访问 `/login` → 重定向到 `/`(工作台)。

## 3. 视觉参考
- `docs/mockups/T01-auth.html` — 4 个子页都在这一个 HTML 里(用 tab 切换演示),实际是 4 个独立路由
- `docs/figma_handoff/mockups_png/T01-auth.png`

## 4. API

| 操作 | 端点 |
|---|---|
| 注册 | `POST /api/v1/auth/register` body `{email, password, display_name}` |
| 登录 | `POST /api/v1/auth/login` body `{email, password}` → `{access_token, refresh_token}` |
| 邮箱验证 | `POST /api/v1/me/verify-email` body `{token}` |
| 发送找回密码邮件 | `POST /api/v1/auth/forgot-password` body `{email}` |
| 重置密码 | `POST /api/v1/auth/reset-password` body `{token, new_password}` |
| 获取当前用户 | `GET /api/v1/me`(用来判断登录态) |
| 登出 | `POST /api/v1/auth/logout` |

MSW handlers 都要加上,登录 mock 返回固定 token。

## 5. 组件分解

```
src/features/auth/
├── LoginPage.tsx
├── RegisterPage.tsx
├── VerifyEmailPage.tsx
├── ForgotPasswordPage.tsx
├── ResetPasswordPage.tsx
├── components/
│   ├── AuthLayout.tsx        ← 左侧品牌、右侧表单
│   ├── AuthCard.tsx          ← 表单容器
│   └── PasswordInput.tsx     ← 带显示/隐藏切换
└── hooks/
    ├── useLogin.ts
    ├── useRegister.ts
    └── useAuth.ts            ← 当前用户 + token 管理

src/stores/authStore.ts       ← Zustand: { user, token, login(), logout() }
src/lib/api.ts                ← axios 客户端,从 store 读 token 加 header
```

shadcn 用: `Button` `Input` `Label` `Form` `Card` `Separator`
react-hook-form + zod 做表单校验。

## 6. 状态管理

- **Zustand `authStore`**: `{ user, accessToken, isAuthenticated, login(), logout() }`
- token 持久化:存 localStorage (`tokenknows_auth`),refresh 时刷新
- TanStack Query `useUser()`: 包 `GET /me`,登录后自动 fetch

## 7. 必备状态

- [ ] Loading: 提交按钮 → 旋转 + disabled
- [ ] Empty: 不适用
- [ ] Error: 行级红字错误(zod 校验) + 全局 toast(后端错误)
- [ ] Success: 注册成功 → 跳"请验证邮箱"页;登录成功 → 跳工作台

## 8. 验收

- [ ] 4 个子页 UI 对齐 mockup
- [ ] zod schema 写在每个表单旁: email 校验、密码强度(≥8 字符)
- [ ] 输入框 focus 时描边变 `border-medium` + ring `accent-primary`
- [ ] 提交期间按钮 disabled + spinner
- [ ] 错误时表单不清空(用户能看到刚输入的)
- [ ] 未登录访问 `/` → 跳 `/login?redirect=/`
- [ ] 登录后 `/login` → 跳 `/`
- [ ] localStorage 里能看到 `tokenknows_auth`
- [ ] 登出后 localStorage 清掉,跳 `/login`

## 9. 已知陷阱

- 注册成功后**不要**自动登录,要走邮箱验证;mockup 里有"请检查邮箱"中间页
- `/verify-email` 的 token 在 URL query,page mount 时直接 POST,不要等用户点按钮
- 找回密码 token 失效要展示具体错误,不要笼统"失败"
- 不要写 "记住我" checkbox,默认 refresh token 30 天有效就够

## 10. Claude Code 指令

先把 `authStore` 和 `api.ts` 写完,再写 LoginPage,再写其他 3 屏。每写完一屏 commit。
