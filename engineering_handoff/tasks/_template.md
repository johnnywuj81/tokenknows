# T0X · [屏幕名]

## 1. 目标 & 用户旅程位置

[1-2 句话:这屏在哪个用户旅程的哪一步,解决用户什么诉求]

PRD 参考: `docs/PRD.md` §X.Y

## 2. 路由

- 路径: `/path/here`
- 入口: 从 X 屏点击 Y 进来
- 出口: 提交后跳到 Z 屏

## 3. 视觉参考

- Mockup HTML: `docs/mockups/T0X-name.html`(浏览器打开看像素 + 交互态)
- 高清截图: `docs/figma_handoff/mockups_png/T0X-name.png`

## 4. API & 数据

| 操作 | 端点 | TanStack Query Key |
|---|---|---|
| 加载列表 | `GET /api/v1/...` | `['...']` |
| 提交 | `POST /api/v1/...` | (mutation) |

MSW handler:加到 `src/mocks/handlers.ts`

## 5. 组件分解

```
src/features/X/
├── XPage.tsx                ← 路由组件
├── components/
│   ├── SubComponentA.tsx
│   └── SubComponentB.tsx
└── hooks/
    └── useX.ts              ← TanStack Query
```

shadcn 组件用: `Button` `Card` `Input` `...`
自定义组件: `SubComponentA`(理由:...)

## 6. 状态管理

- Server state: TanStack Query(query key 见上)
- Client state: useState(描述每个)
- Zustand:[是否要塞全局 store,通常不要]

## 7. 必备状态(Definition of Done)

- [ ] Loading: 骨架屏/spinner 已渲染
- [ ] Empty: 用 `EmptyState` 组件 + 主操作
- [ ] Error: 用 `ErrorState` 组件 + 重试按钮
- [ ] Success: 数据正常展示
- [ ] 表单(如有): 字段校验 + 错误提示 + disabled 状态
- [ ] 键盘可达: Tab 顺序合理,主操作 Enter 可触发
- [ ] 响应式: 1280px 桌面端为主,无横向滚动

## 8. 验收清单

- [ ] 视觉对齐 mockup(截图比对无明显偏差)
- [ ] 颜色用 token,无原生 stone/gray
- [ ] 字体: 标题 font-content / UI font-ui / ID font-mono
- [ ] TypeScript 零错误(`npx tsc --noEmit`)
- [ ] ESLint 零警告
- [ ] 路由 push/back 正常
- [ ] MSW mock 接通,真实场景下不会留 mock 调用

## 9. 已知陷阱

- [陷阱描述]
- [比如 SSE/WebSocket 在 vite dev 的代理配置]

## 10. 给 Claude Code 的额外指令(可选)

[如果有特殊提示,例如"先写组件,再写 hook;数据 fetching 放最后"]
