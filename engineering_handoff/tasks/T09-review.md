# T09 · Reviewer 审批视图

## 1. 目标
审批人查看待审文档,可以批注、通过、退回(按章节粒度)。
PRD: §5.5 模块 E · 人工编辑与审批,§8.4 关键交互 · 审批流界面

## 2. 路由
- 路径: `/projects/:id/documents/:docId/review`
- 入口: 从工作台待办或 T05 文档列表(状态=reviewing)进入
- 出口: 通过/退回后跳回文档页 T06 或工作台

## 3. 视觉参考
`docs/mockups/T09-review.html` · 左侧文档(只读)+ 右侧批注列表 + 底部操作栏

## 4. API

| 操作 | 端点 |
|---|---|
| 加载文档(review 视角) | `GET /api/v1/assets/{asset_id}`(同 T06 但只读) |
| 章节通过 | `POST /api/v1/assets/{asset_id}/chapters/{chapter_id}/approve` |
| 章节退回 | `POST /api/v1/assets/{asset_id}/chapters/{chapter_id}/reject` body `{reason}` |
| 添加评论 | `POST /api/v1/assets/{asset_id}/comments` body `{chapter_id, span, content}` |

## 5. 组件分解

```
src/features/review/
├── ReviewPage.tsx                  ← 整页,复用 T06 部分组件
├── components/
│   ├── ReviewSidebar.tsx           ← 右侧:章节审批进度 + 批注列表
│   ├── ChapterApprovalRow.tsx      ← 单章节 通过/退回 操作行
│   ├── CommentThread.tsx           ← 批注 + 回复
│   └── BottomActionBar.tsx         ← 底部固定:全部通过 / 退回 / 保存进度
└── hooks/
    ├── useReviewAsset.ts
    └── useApproveChapter.ts
```

shadcn 用: `Button` `Textarea` `Badge` `Card` `Dialog`(退回原因)`Tooltip`

## 6. 状态管理

- 审批草稿(还没提交的批注):useState 本地,提交时统一 POST
- 通过/退回是即时 API 调用(不是草稿模式)

## 7. 必备状态

- [ ] Loading: 三栏骨架
- [ ] Empty: 无章节(异常)→ 错误提示
- [ ] Error: 行级
- [ ] Approved/Rejected: 章节左侧色条变色

## 8. 验收

- [ ] 左侧文档**只读**(不可编辑 TipTap),用 markdown-it 渲染
- [ ] 选中文档片段 → 浮出"批注"按钮 → 弹评论框
- [ ] 右侧批注按章节分组,与左侧滚动联动
- [ ] 章节级"通过"按钮显示绿对勾,"退回"必填原因
- [ ] 底部固定操作栏: "全部通过 + 进入发布(→ T11)" / "退回作者(→ T06 + 通知)" / "保存进度"
- [ ] 已通过的章节折叠显示,可展开
- [ ] 全部通过时,弹 dialog 确认"进入发布"

## 9. 已知陷阱

- Reviewer 角色权限检查:T01 的 useAuth 要拿到角色,非 reviewer 进这页直接 403
- 批注的 span 锚点要稳定(基于章节 ID + 字符偏移),不要基于 DOM 节点
- 退回不删除批注,T06 编辑者要能看到批注列表
- "全部通过"需要所有章节都通过才能点击

## 10. Claude Code 指令
复用 T06 的 DocOutline 和 ChapterBlock(传 readOnly prop),不要重复实现。
