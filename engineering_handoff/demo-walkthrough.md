# TokenKnows MVP · 5 分钟离线 Demo Walkthrough

> 演示路径: **数据汇聚 → 真 LLM 生成 → 证据链 → 重生成 → 审批 → 脱敏 → 发布 + diff**
>
> 全程不依赖外网 (Anthropic/OpenAI key 可不配置), 真 LLM 走本机 Ollama Cloud minimax-m2.

---

## 0 · 前置准备 (一次性, ~2 分钟)

### 0.1 Ollama 启动并拉取模型

```bash
# 1. 启动 Ollama daemon (若未启动)
ollama serve &

# 2. 验证可用模型 (需含 minimax-m2:cloud 或 gpt-oss:20b)
ollama list
#   NAME                       ID              SIZE      MODIFIED
#   minimax-m2:cloud           698ab6d56142    -         2 months ago
#   gpt-oss:20b                17052f91a42e    13 GB     2 months ago

# 3. 拉取 (如缺): ollama pull minimax-m2:cloud
```

### 0.2 启动后端 + 前端

```bash
# Terminal A · 后端
cd code/tokenknows-api
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
# 启动日志应见:
#   persistence_initialized       path=.../data/state.sqlite
#   persistence_loaded            assets=N chapters=M evidence=K

# Terminal B · 前端
cd code/tokenknows-web
npm run dev
#   ➜  Local:   http://localhost:5173/
```

### 0.3 (可选) demo 种子脚本

```bash
# 一键生成 demo 文档 (含敏感内容用于 T10 脱敏演示)
./engineering_handoff/demo-seed.sh
```

脚本会:
- 触发 POST /projects/proj-demo-001/assets/generate
- 等 60s 5 阶段流水线完成
- PATCH 章节 1 注入 alice@tokenknows.local + 192.168.10.42 +
  sk-ant-api03-demo-key + Project_OmegaPilot 4 项敏感内容
- 打印 demo asset id

---

## 1 · 工作台 (15s) · `T03 · 数据汇聚`

打开 <http://localhost:5173/projects/proj-demo-001>

**画面**:
- 左栏: 项目卡 "TokenKnows 自身研发" + 4 个数字 (本周事件 23 / 待审 2 / 数据源 3 / 最近活跃 18 小时前)
- 中栏: 实时事件流 (8 条, 按今天分组), 每条左侧色条按 source_type 分色:
  - 绿 = commit
  - 橙 = PR/Issue (GitHub)
  - 蓝 = AI 对话 (Claude Code)
- 右栏: 本周待办 (5 条)

**演示动作**:
1. 鼠标悬停事件卡 → 全局色条高亮
2. 单击"PR #127 · 加入 EgressGate 中间件" → **EventDrawer 抽屉** 滑出, 显示完整元数据 (作者 / 时间 / TRUST 95 / tags / payload 折叠 / 外部链接)
3. 关抽屉, 点 trust_score 那条 → 抽屉切换为 AI 对话内容
4. 注意页脚提示: "polling 每 30 秒自动刷新 · SSE 替换点 W4D17"

**讲点**: 多源数据 (GitHub / Claude Code / Cursor / 本地文档) 通过插件汇聚, trust_score 自动打分, 进入候选 ValueSegment.

---

## 2 · 文档列表 → 生成 (60s) · `T05 + T06 阶段 1`

左侧 nav 点 "文档" → <http://localhost:5173/projects/proj-demo-001/documents>

**画面**: 已有 N 个文档卡 (重启不丢, **P1 SQLite 持久化**生效)

**演示动作**:
1. 点右上 "生成新文档" → **GenerateDocDialog** 弹出
2. 选 "周报" + 时间窗 "本周" + 提交
3. dialog 关闭, 列表新增一条 "周报 · this_week 生成中…"
4. 单击新卡 → 跳文档页

**讲点**: 实时事件 → 主题聚类 → 章节大纲 → 内容生成 → 证据回填 → 自评卡, 5 阶段流水线后台跑.

---

## 3 · 文档生成 SSE 实时观感 (60s) · `T06 + P4`

文档页 URL: `/documents/asset-XXXXX`

**画面 (生成中)**:
- 顶部状态 badge "生成中" (灰)
- 左侧大纲: 章节逐个浮现 (**P4 SSE chapter_completed 事件触发**, 不再 30s polling)
- 中间正文: 同步增量渲染 (TipTap editor)
- 右侧元数据卡: 自评指标骨架占位

**演示动作**:
1. 开 DevTools → Network → 过滤 `generation/stream` → 看到一条持续连接的 EventSource
2. Console 看 SSE 事件流: `snapshot` → `stage_started:collect` → `stage_completed:collect` → `stage_started:outline` → `stage_completed:outline` (chapters titles in payload) → 5 次 `stage_started:content` + `chapter_completed` × 5 → `stage_started:evidence` → ... → `done`
3. 60s 后所有章节完成. Header 状态变 "草稿" (橙), 自评指标填实数字 (覆盖 71% / 引用 85% / 空话 16%)

**画面 (完成后)**:
- 5 章 markdown 内容由 LLM 真生成 (provider/model 角标显 `ollama · minimax`)
- 每段末尾有 `[1]`/`[2]`/`[3]` 形式的角标 (**P2 EvidenceBadge Node** 渲染, 编辑器内是单元原子, 不会被吞)
- 左侧大纲滚动联动正文

**讲点**: 真 LLM 调用 + 实时 SSE 推进度 + 三层出域门禁审计 (egress_log 落库).

---

## 4 · 证据链抽屉 (30s) · `T07`

**演示动作**:
1. 点章节内 `[1]` 角标, 或章节 footer "查看证据" 按钮 → **EvidenceDrawer** 从右侧滑出
2. Header 显 "证据链 (3 条)"; tab 条数字 [1][2][3]
3. 主体卡片显当前激活的证据:
   - 来源 icon + GITHUB · TOKENKNOWS/API
   - 标题 "PR #127 · 加入 EgressGate 中间件"
   - 作者 Alice / 发生时间 / 原文摘录 (quote 框)
   - TRUST 95 / CITATION 88 badge
   - "在源头打开" 外链
4. 点 tab [2] → 切证据, **不重 query** (TanStack Query staleTime 60s + 同一 queryKey)
5. 关闭, 滚到章节 2, 点其"查看证据" → 抽屉打开但 fetch 不同 chapter 的 evidence list

**讲点**: 每条 LLM 生成结论都有可追溯的原始证据, 用户可一键回到 PR / 对话验证.

---

## 5 · 章节重生成 (60s) · `T08 真 LLM 调用`

**演示动作**:
1. 章节 1 footer 点 "重生成" → **RegenerateDialog** 弹出
2. 目标章节卡显 "§1 本周进展"
3. 填指令 textarea: "用更生动的语气重写, 强调本周完成了 EgressGate 中间件 PR 和证据链抽屉两件大事, 不超过 200 字"
4. 模型选项 (默认 Ollama · minimax-m2:cloud)
5. 点 "提交重生成"
6. 6-8s 后 dialog 关, 章节 1 内容刷新为 LLM 真返回的新文本, 显式提到 EgressGate + 证据链抽屉
7. ChapterBlock header 多出 "已保存" 短暂提示
8. 后端 chapter.regeneration_history 已存上一版内容 (P3 diff 准备)

**画面**: 重生成中, dialog 内 spinner "重生成中…", ChapterBlock 编辑器灰化禁用 (regenerating=true).

**讲点**: 即时反馈, 历史快照保留, 后续可在发布回执看 diff.

---

## 6 · 提交审批 + 章节通过/退回 (45s) · `T09`

**演示动作**:
1. 顶部 "提交审批" 按钮 → POST /assets/:id/submit → status: draft → in_review → 自动跳 `/review` 页
2. **ReviewPage** 三栏:
   - 左: 大纲
   - 中: 只读的 5 章 (ChapterBlock readOnly=true, TipTap editable=false, 编辑器灰化)
   - 右: 章节审批进度 (每章 待审批 + 通过/退回 按钮)
   - 底部: 审批进度计数 + 保存进度 / 退回作者 / 全部通过·进入发布
3. 点章节 1 的 "通过" → 卡片变绿 (已通过)
4. 点章节 2 的 "退回" → Dialog 弹出, 填 "缺少具体 Bug 编号引用, 请补 #-link" → 确认退回 → 章节 2 变红
5. 顶部 asset badge 自动变 "已退回" (任一章节退回 → 整体退回)
6. 底部 "退回作者" 按钮变可点

**讲点**: 章节级粒度审批, 状态联动 (chapter↔asset), 退回理由进 regeneration_history 留痕.

---

## 7 · 重新审批通过 → 脱敏 (45s) · `T10`

**演示动作 (准备)**:
```bash
# 把所有章节直接 approve (绕过演示节奏, 真演示时手点 5 次"通过")
for ch in $(curl -s http://localhost:8001/api/v1/assets/asset-XXX/chapters | jq -r '.[].id'); do
  curl -s -X POST "http://localhost:8001/api/v1/assets/asset-XXX/chapters/$ch/approve" > /dev/null
done
```

asset 自动升 status=approved.

**演示动作 (脱敏)**:
1. 返回文档页, 顶部 "发布" 按钮替换原 "提交审批"
2. 旁路 (URL 直跳) <http://localhost:5173/projects/proj-demo-001/documents/asset-XXX/redaction>
3. 进入 **RedactionPage**, 自动触发 POST /redaction/scan
4. 4 类 PII 命中 (若先跑了 demo-seed 脚本):
   - 邮箱地址 · `alice@tokenknows.local`
   - API 密钥 · `sk-ant-api03-demo-key-...`
   - IP 地址 · `192.168.10.42`
   - 内部代号 · `Project_OmegaPilot`
5. 每项有上下文高亮 + 建议替换 ([EMAIL] / [API_KEY] / ...)
6. 点邮箱 "脱敏" → 状态变 "已脱敏" 绿
7. 点 API 密钥 "豁免" → Dialog 弹出, 填 "公开示例代码已失效" → "已豁免" 黄 + 显示理由
8. 处理完所有项 → 底部 "进入发布 (T11)" 启用

**讲点**: 正则 + 黑名单兜底, 用户逐条确认或豁免 (留审计), 替换占位符可在 T13 项目设置自定义.

---

## 8 · 发布对话框 (30s) · `T11`

**演示动作**:
1. 底部点 "进入发布 (T11)" → 自动跳回文档页 + **PublishDialog** 弹出
2. 渠道 radio 卡:
   - 站内文档库 (默认)
   - 公开链接 (展开后多 Team/Public visibility)
   - 导出 Markdown
3. 选 "公开链接" + visibility "团队内"
4. 勾确认清单 (3 项含公开链接风险提示)
5. 点 "确认发布" → POST /assets/:id/publish

**讲点**: 不可猜测 token URL (uuid16), 多渠道独立处理, MVP 内部 / 公开链接 / MD 导出三种.

---

## 9 · 发布回执 + 版本 Diff (45s) · `T12 + P3`

自动跳 `/published/:publishId`

**画面**:
- 大对勾 + "发布成功" + 版本号 v1 + 发布时间 + 发布人
- 本次发布卡:
  - 公开链接 status=成功 (绿)
  - URL `https://share.tokenknows.dev/p/eb27a4bbaaa84f3e`
  - 复制按钮 (navigator.clipboard) + "打开" 外链
  - 团队可见 badge
- 历史发布记录 (若多次发布)
- **章节级 diff** (P3 ChapterDiffView):
  - 列出 5 个章节
  - 章节 1 默认展开 (有 diff): 三色行 (+ 新增绿 / - 删除红)
  - 顶部 stats badge `+5 / -3` (新增 5 行, 删除 3 行)
  - 折叠 footer 显重生成时间 + 模型名
  - 其它 4 章 "未经重生成, 无 diff 历史"

**讲点**: 发布即留痕, 版本对比可视化, 后续撤回 (T13 凭证 + RBAC) 可叠加.

---

## 10 · 设置 / LLM 出域 / Admin (60s) · `T13 + T14 + T15`

### 10.1 项目设置
<http://localhost:5173/projects/proj-demo-001/settings>
- 左 nav: 基本信息 / 成员 / 数据源 / LLM 与出域
- 切到 "LLM 与出域" tab → **LlmEgressPanel** (T14):
  - 三层 toggle (instance / project / task) 全 ENABLED (绿)
  - 4 个 provider 状态: anthropic (本机网络不通黄) / openai (黄) / minimax (Key 无效红) / **ollama (在线绿)**
  - 审计级别 full
  - "dry-run preview" 按钮 → POST /llm/egress/preview → 返回 will_send + provider + estimated_tokens, 不真调云端

### 10.2 Admin 控制台
<http://localhost:5173/admin>
- 深色 header
- 4 数字卡: 用户 12 / 项目 3 / 文档 27 / tokens 248.9K
- 存储进度条 1.71GB / 20GB (8.6%)
- 3 nav cards (用户列表可点, 审计 / LLM 全局 留 v2)

**讲点**: 私有化部署专属, 三层出域门禁 + 全调用审计 + 实例级管理.

---

## 11 · 持久化验证 (15s) · `P1` (可选 bonus)

```bash
# 1. 杀后端
pkill -f "uvicorn app.main:app"

# 2. 重启
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001

# 3. 启动日志:
#   persistence_loaded  assets=N  chapters=M  evidence=K  publish_records=L
```

刷新浏览器 → 所有 asset / chapter / evidence / publish-record 全部还原, 状态保留.

---

## 一句话收尾

> **TokenKnows = 研发事件 → 文档 → 证据链 → 发布的闭环, 全程私有化 + 可审计 + 真 LLM 落地.**

---

## Cheat Sheet (演讲时手卡)

| 屏 | 时长 | 关键句 |
|---|---|---|
| 工作台 | 15s | "多源数据 → trust_score → 候选事件" |
| 列表+生成 | 60s | "5 阶段流水线 + SSE 实时推进度" |
| 文档页 | 60s | "真 Ollama LLM + [N] 证据角标可双击" |
| 证据抽屉 | 30s | "一键回源, 不重 query" |
| 重生成 | 60s | "指令重写, 历史快照保留" |
| 审批 | 45s | "章节级粒度, 退回理由留痕" |
| 脱敏 | 45s | "PII 正则 + 豁免审计" |
| 发布 | 30s | "uuid token, 多渠道独立" |
| 回执+diff | 45s | "三色 line-by-line" |
| 设置/Admin | 60s | "三层出域 + dry-run + 实例审计" |
| 持久化 | 15s | "kill -9 不掉数据" |

**总计 ~7 分钟** (留 1-2 分钟问答缓冲).

---

## 故障排查

| 症状 | 排查 |
|---|---|
| 文档生成卡在"生成中" | 检查 Ollama 是否启动: `curl http://localhost:11434/api/tags` |
| 证据抽屉 4xx | 后端重启 → 旧 asset 已迁 SQLite, 路径 ok |
| `[N]` 角标显示成纯文本 | 看 ChapterBlock 是否引入 EvidenceBadge node 扩展 |
| diff 显示 "未经重生成" | 故意的, 没编辑过的章节就这样, 演示前先重生成一章 |
| SSE 不工作 | DevTools Network → 看 generation/stream 是否连接成功 (状态 200, type=eventsource) |
| Ollama 模型 403 | minimax-m2:cloud 需 Ollama Cloud 订阅. fallback: 用本地 `gpt-oss:20b` (改 .env.local 的 TASK_*_MODEL) |
