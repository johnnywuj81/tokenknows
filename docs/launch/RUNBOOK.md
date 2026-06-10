# 开源发布 Runbook(扣扳机指南)

> P0 代码/文档工作已全部落地(见 git log `*(oss)` 提交)。本文是**对外不可逆动作**的
> 执行顺序 —— 全部由维护者亲自执行,严格按序。

## 翻公开日(Flip day)

### 0. 前置确认(全绿才继续)

- [ ] hosted CI 在一个测试 PR 上跑绿(开个临时分支 → PR → `ci.yml` 三 job + status 全绿)
- [ ] 本地全量:`pytest`(api)/ `npm test` + `npm run lint` + `tsc --noEmit`(web)全绿
- [ ] `git status` 干净,`main` 已 push

### 1. 注销自托管 runner(安全关键)

公开仓库 + 自托管 runner = 外部代码可能上你机器。`ci-macos.yml` 已限 main-push-only,
但更稳妥是确认 runner 只接受这条限制,或干脆注销:

```bash
gh api repos/johnnywuj81/tokenknows/actions/runners        # 看现有 runner
# 如决定注销: ./actions-runner/config.sh remove --token <从 settings 取>
```

保留亦可(ci-macos.yml 有 repository guard + 绝不 pull_request),但要确认
Settings → Actions → General → **"Require approval for all outside collaborators"** 开启。

### 2. 翻公开

```bash
gh repo edit johnnywuj81/tokenknows --visibility public --accept-visibility-change-consequences
```

### 3. 元数据

```bash
gh repo edit johnnywuj81/tokenknows \
  --description "Distill AI coding sessions (Claude Code / Codex / Cursor) into weekly reports, ADRs, incident reviews and a knowledge graph — local-first, evidence-linked."

for t in knowledge-management knowledge-graph knowledge-distillation mcp mcp-server \
         claude-code codex cursor llm fastapi developer-tools ai-agents; do
  gh repo edit johnnywuj81/tokenknows --add-topic "$t"
done
```

### 4. Settings 手工项(无 API)

- [ ] **Social preview**:Settings → General → Social preview → 上传 `assets/brand/png/social-preview.png`
- [ ] **Discussions**:Settings → Features 开启;建分类 Q&A / Ideas / Show and tell
- [ ] **Private vulnerability reporting**:Settings → Security 开启
- [ ] **Branch protection**(main):require PR、required check = `CI Status`、禁 force-push
- [ ] Profile → Customize pins → 置顶本仓库

### 5. 公开后立刻重测安装链路(发帖前的硬门禁)

- [ ] Claude Code:`/plugin marketplace add johnnywuj81/tokenknows` → `/plugin install tokenknows@tokenknows`
- [ ] Codex:验证 `codex plugin marketplace add johnnywuj81/tokenknows --sparse codex-plugin`
      是否解析到 `codex-plugin/.agents/plugins/marketplace.json`。
      **成功** → 把 README 安装表 Codex 行升级成这条一行命令;
      **失败** → 维持现在的 clone+local 写法(README 已按保守写法,不用改)
- [ ] 从一个 fork 开测试 PR → hosted CI 绿(证明外部贡献者路径通)
- [ ] 贴 repo URL 到 X/Slack 验证 social preview 卡片渲染

### 6. Tag + Release

```bash
git tag -a v0.1.0 -m "TokenKnows v0.1.0 — first public release"
git push origin v0.1.0
cd plugins/vscode-tokenknows && npx vsce package   # 产 tokenknows-vscode-0.2.1.vsix
gh release create v0.1.0 \
  --title "TokenKnows v0.1.0 — first public release" \
  --notes-file <(sed -n '/## \[0.1.0\]/,/^\[0.1.0\]/p' CHANGELOG.md) \
  tokenknows-vscode-0.2.1.vsix
```

## 宣传节奏(每天一个渠道,中文圈先试错)

| Day | 渠道 | 角度 |
|---|---|---|
| 1 | V2EX /分享创造 + 掘金长文 | 中文首发,收集装机问题(宽容观众) |
| 2 | MCP 目录:mcp.so / PulseMCP / glama.ai;PR 到 awesome-mcp-servers、awesome-claude-code | 安静铺目录。**跳过 Smithery**(它面向 npx 托管型 MCP,本品需本地后端,会引来装不上的报告) |
| 3 | **Show HN**(周二~四 9-11am ET,守评论 ≥3h)+ X 线程 | `Show HN: TokenKnows – Distill AI coding sessions into ADRs and a knowledge graph` |
| 4 | r/LocalLLaMA | 零出域 + Ollama 全本地角度 |
| 6 | r/ClaudeAI | Claude Code 插件角度 |

**红线**:
- fork CI 没绿不发任何帖
- HN 和 Reddit 不同天(cross-post 惩罚 + 精力分散)
- Codex 一行安装命令没在第 5 步验证通过,不写进任何帖子
- 所有帖子里的安装命令从 README 复制,不手敲

## P1/P2 backlog(发布后)

- [ ] 英文短 demo 视频(≤10MB 静音,经 github.com README 网页编辑器上传成 user-attachments → 内嵌播放器)
- [ ] 标签集:`bug` `enhancement` `question` `needs-repro` `good first issue` `install:claude-code` `install:codex` `install:cursor`;pinned "v0.1 feedback" Discussion
- [ ] ROADMAP.md(Now / Next / Later 三段,README 链入)
- [ ] VS Code 扩展发布 Marketplace + Open VSX(`vsce publish`),README 安装行升级
- [ ] `scripts/systemd/` Linux 采集器 user units
- [ ] `scripts/dev-up.sh` 一键起(venv + npm ci + env 拷贝 + demo-seed + 双进程)
- [ ] CI 加严:ruff 强制、pytest `--cov-fail-under`、vitest 覆盖率门槛、dependabot
- [ ] engineering_handoff/ 加历史档前言(解释残留的 /Users/wujun 路径);清一次性修复脚本
- [ ] 技术长文第二波(5-stage pipeline 拆解,dev.to + 掘金)
