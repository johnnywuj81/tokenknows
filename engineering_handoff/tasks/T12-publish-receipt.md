# T12 · 发布回执 / 版本对比

## 1. 目标
发布成功后展示回执:版本号、发布渠道链接、本次和上版本的 diff。
PRD: §5.7 模块 G · 导出与发布

## 2. 路由
- 路径: `/projects/:id/documents/:docId/published/:publishId`
- 入口: T11 发布对话框成功后跳过来
- 出口: 回到 T05 文档列表 / T06 文档页 / 撤回发布

## 3. 视觉参考
`docs/mockups/T12-publish-receipt.html`

## 4. API

| 操作 | 端点 |
|---|---|
| 发布详情 | `GET /api/v1/publish-records/{id}` |
| 版本 diff | `GET /api/v1/assets/{asset_id}/versions/{v1}/diff?to={v2}` |
| 撤回 | `POST /api/v1/publish-records/{id}/revoke` |

## 5. 组件分解

```
src/features/publish/
├── PublishReceiptPage.tsx
├── components/
│   ├── ReceiptHeader.tsx           ← 大对勾 + 版本号 + 发布时间
│   ├── DestinationList.tsx         ← 各渠道的发布状态 + 链接 + 复制
│   ├── VersionDiff.tsx             ← 章节级 diff(增/改/删)
│   └── RevokeDialog.tsx
└── hooks/
    └── usePublishRecord.ts
```

shadcn 用: `Card` `Badge` `Button` `Tabs` `Dialog` `Tooltip`
Diff 渲染: 用 `diff` npm 包做 line-by-line,新增绿色 / 删除红色 / 修改 黄色

## 6. 状态管理
单页只读视图,纯 TanStack Query 即可。

## 7. 必备状态

- [ ] Loading: 整页骨架
- [ ] Empty: 不适用
- [ ] Error: 跳回文档页
- [ ] Success: 完整渲染

## 8. 验收

- [ ] 头部大对勾(success 色)+ 版本号 `v1.2.0` (font-mono)
- [ ] 各渠道状态: 成功(绿)/ 失败(红 + 重试)/ 进行中(灰)
- [ ] 每个公开链接旁边有"复制"按钮 + toast
- [ ] 版本 diff 默认展开 1 个章节,其他折叠
- [ ] Diff 视图用 font-mono,行号 + 三栏色(增加/删除/修改)
- [ ] "撤回发布"按钮在 admin / 文档作者可见,二次确认
- [ ] 撤回后页面状态变红"已撤回",链接失效

## 9. 已知陷阱

- 撤回操作不可逆(在用户层面),需要 dialog 强提示
- 多渠道发布是异步的,可能部分成功,要逐项展示
- diff 数据量可能很大(章节内容),用 lazy expand
- 复制按钮用 `navigator.clipboard.writeText`,失败要 fallback toast

## 10. Claude Code 指令
diff 用 `diff` 包,不要自己写。`npm install diff @types/diff`
