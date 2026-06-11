# TokenKnows 推广计划 · 三波打法

> 制定于 2026-06-11，基于 36 个渠道的实地调研（14 个高价值渠道二次核实过提交方式与门槛规则）。
> 状态图例：☐ 未开始 · ▶ 进行中 · ✅ 完成 · ⏳ 等待解锁

## 总策略

渠道分三类，按依赖顺序推进：

1. **结构性收录**（目录/列表，提交一次长期有效）→ 先铺满"被搜到"的基础设施
2. **一次性发布**（Show HN / V2EX 等大场子，每个只有一发）→ 攒齐弹药再打
3. **时间门槛渠道**（解锁条件明确）→ 设日历，到点就交

核心原则：**先小圈子收反馈打磨，再上一次性大场子**。所有英文社区帖主动披露"我是作者"+"数据只发你自部署的后端"。

---

## 第一波 · 结构性收录（零门槛，立即执行）

| 状态 | 渠道 | 方式 | 备注 |
|---|---|---|---|
| ✅ | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)（88.8k⭐） | 直接 PR，Knowledge & Memory 类目 | 明文欢迎 agent PR；已提 [PR #7816](https://github.com/punkpeye/awesome-mcp-servers/pull/7816)（🤖 fast-track）；收录后自动进 Glama |
| ☐ | [appcypher/awesome-mcp-servers](https://github.com/appcypher/awesome-mcp-servers)（5.6k⭐） | PR，字母序，一条一个 PR | |
| ✅ | [jamesmurdza/awesome-ai-devtools](https://github.com/jamesmurdza/awesome-ai-devtools)（3.8k⭐） | PR，按 PR 模板 checklist | 已提 [PR #637](https://github.com/jamesmurdza/awesome-ai-devtools/pull/637)，Agent Infrastructure → Configuration & Context Management |
| ✅ | [ComposioHQ/awesome-claude-plugins](https://github.com/ComposioHQ/awesome-claude-plugins)（1.7k⭐） | PR，README 链接条目 | 已提 [PR #287](https://github.com/ComposioHQ/awesome-claude-plugins/pull/287)，外链条目 |
| ✅ | [mcp.so](https://mcp.so/) | 给 [chatmcp/mcpso](https://github.com/chatmcp/mcpso) 开 issue | 已提 [issue #2715](https://github.com/chatmcp/mcpso/issues/2715)；积压多，慢 |
| ✅ | Glama 认领 | 仓库根放 `glama.json`（maintainers: johnnywuj81） | glama.json 已入库（commit a2b0e39）；等收录自动建档后走 Claim ownership |
| ⏳ | [PulseMCP](https://www.pulsemcp.com/submit) | 网页表单（一个 URL 字段） | 2026 改制：server 不收直接提交，只从官方 MCP Registry 每日同步 → 并入下面 Registry 任务 |
| ✅ | [mcpservers.org/submit](https://mcpservers.org/submit) | 网页表单 | 2026-06-11 表单已提交，12h 内审核，结果发 john.wuj@outlook.com |
| ✅ | GitHub topics 补全 | `gh repo edit --add-topic` | 已补 claude / self-hosted / vscode-extension（现 15 个） |
| ✅ | Release v0.2.1 | `gh release create` 挂 vsix | [已发布](https://github.com/johnnywuj81/tokenknows/releases/tag/v0.2.1)，挂 vsix |
| ▶ | Anthropic 社区插件市场 | [platform.claude.com/plugins/submit](https://platform.claude.com/plugins/submit) 表单 | `claude plugin validate` 已通过（修了 adr/design/incident 三处 frontmatter YAML）；**待本人**登录 [platform.claude.com/plugins/submit](https://platform.claude.com/plugins/submit) 提交表单 |
| ☐ | 官方 MCP Registry | `mcp-publisher` CLI | **工程前置**：MCP server 需先发 PyPI 包（需要 PyPI 账号）→ `mcp-publisher` 发布；完成后 PulseMCP 等自动同步 |

## 第二波 · 一次性发布（弹药齐了再打）

**弹药清单（发布前必须就位）：**

- ☐ README 首屏 demo GIF（采集 → 蒸馏 → 周报/KG 的 30 秒闭环演示）
- ☐ `docker-compose up` 一键起（HN / r/selfhosted 评论区必问）
- ☐ 隐私答辩词：支持哪些 LLM 后端、能否全本地跑、token 流向

**发布顺序（中文圈先打收反馈，HN 压轴）：**

| 状态 | 渠道 | 要点 |
|---|---|---|
| ☐ | V2EX [分享创造](https://www.v2ex.com/go/create) | 中文、第一人称建造故事、明示开源/MIT/自部署/不收费；**不要**发推广节点 |
| ☐ | [Linux.do 开发调优](https://linux.do/c/develop/4) | `[开源项目]` 前缀；2026 中文 Claude Code 浓度最高社区；**禁 AI 生成内容，必须本人写**；需 TL1（读 30 帖 ×10 分钟即达） |
| ☐ | Reddit r/ClaudeAI（~91.6 万成员） | Built with Claude flair；角度 = "把你的 Claude Code session 蒸馏成周报/ADR/KG" |
| ☐ | Show HN | 周二–四 7–10am PT；标题平实：`Show HN: TokenKnows – Self-hosted workbench that distills AI coding sessions into docs`；发完立刻顶楼讲架构与求反馈；**严禁拉票**；回复每条评论 |
| ☐ | Reddit r/ChatGPTCoding | 跨工具（Claude Code/Codex/Cursor）角度；与其它 sub 分天发 |
| ☐ | Product Hunt | Show HN 后 1–2 周再上，定位社会证明而非获客 |

## 第三波 · 时间门槛渠道（日历驱动）

| 状态 | 渠道 | 解锁条件 | 预计日期 |
|---|---|---|---|
| ⏳ | [awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)（46k⭐，fit 最高） | 仓库 ≥5 stars；**只能本人手填 [issue 表单](https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml)**（AI 代发/PR/gh CLI = 直接 ban）；需披露网络调用与遥测；同仓库同时只能有一个 open issue | star≥5 即可 |
| ⏳ | r/selfhosted 独立帖 | 2026-04 新规：项目满 3 个月（按首次公开计）才可发独立帖，此前只能进周五 New Project Megathread；发帖会被 bot 拦截要求声明 AI 参与度 | ~2026-08-20 |
| ⏳ | [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted-data)（29.8 万⭐，最大渠道） | 首个 release 满 4 个月；PR = 新增 `software/tokenknows.yml`（描述 <250 字符、禁用 "open-source/self-hosted" 字眼、围绕 FastAPI 后端而非编辑器插件框定）；期间保持打 tag | ~2026-10-10 |
| ⏳ | r/LocalLLaMA | 蒸馏管线能跑本地模型（Ollama/vLLM）并有演示后，价值升为 high | 本地后端 ready 后 |
| ☐ | lobste.rs | 邀请制；最佳路径 = 别人转发了你的项目后去官方 chat 自认作者领邀请 | 随缘 |

## 持续渠道（第二波后长期经营）

- ☐ 掘金：深度技术文（5-stage pipeline 架构、MCP server 设计），AI Coding 是 2026 平台三大热点之一
- ☐ 即刻：AI探索站/独立开发的日常 圈子，build-in-public 周更，不发硬广
- ☐ 少数派 Matrix：申请作者权限（说明自荐产品），投"开发者说"栏目，写造物故事不写通稿
- ☐ W2solo 新品发布：CN 独立开发社区，零成本
- ☐ bilibili：5–10 分钟安装+蒸馏演示视频（高成本可选；被中型 up 主翻牌 > 自己投十期）

## 分工

- **可由 AI 代办**：全部 awesome-list PR（punkpeye 明文允许）、MCP Registry 发布、topics、Release、glama.json、mcp.so issue、各平台文案草稿、demo GIF 脚本
- **必须本人**：awesome-claude-code issue 表单、Linux.do/V2EX 中文帖、HN/Reddit 发帖与互动、少数派 Matrix 申请

## 避坑备忘

1. Reddit 多 sub 分天发，同日多发触发反垃圾
2. HN/PH 严禁任何形式拉票，检测到判流量作弊
3. awesome-claude-code 与 Linux.do 对 AI 代写零容忍
4. r/selfhosted 必拷问数据隐私 —— 答辩词常备
5. awesome-selfhosted 条目描述禁带 "open-source / self-hosted / free" 字样（他们的行文规范）
