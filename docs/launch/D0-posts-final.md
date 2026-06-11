# D0 发帖终稿 · V2EX + 即刻

> 状态：待发。V2EX 建议周五 20:00–21:00 发（分享创造节点）；即刻随时可发。
> 发完把帖子链接记回本文件，方便后续盯回复。

---

## V2EX · 分享创造节点

**标题**：

```
写了个工具，把 Claude Code 的编程过程自动蒸馏成周报、ADR 和知识图谱，今天开源了
```

**正文**（Markdown 模式）：

```markdown
和 Claude Code 结对编程大半年，每天四五个小时泡在终端里。慢慢发现一个很烦的事：那些排查 bug 的过程、架构上的取舍、为什么最后选了方案 B 而不是 A——终端一关，全没了。周一写周报的时候只能靠回忆，两周前的决策被人问起来，只记得结论不记得为什么。

这些东西其实都躺在 `~/.claude/projects/` 的 jsonl 里，只是没人去读。所以我写了个工具读它们。

**TokenKnows**：本地采集器盯着 Claude Code / Codex / Cursor / VS Code / GitHub 的活动（全是拉模式，30 秒轮询 jsonl 增量、只读 Cursor 的 state.vscdb，没有 webhook 不用 ngrok），事件进自部署的后端，然后一条 5 阶段 LLM 管线把它们蒸馏成文档：周报、技术方案、ADR、故障复盘，甚至能出整本技术手册和知识图谱。

动图演示（终端敲 /tokenknows:weekly 到周报生成）：
https://raw.githubusercontent.com/johnnywuj81/tokenknows/main/assets/demo/tokenknows-demo.gif

我最在意的一个设计是**证据链**：蒸馏出来的每一段话都能点开看它引用了哪些源事件（哪次对话、哪个 PR、哪条 commit），跨至少两个源交叉排序。LLM 写周报最大的问题是一本正经地编，有了回链至少编没编一眼能看出来。

几个 V 友大概率要问的，先答了：

- **数据去哪**：只去你自己部署的后端（FastAPI + SQLite，单机文件），没有 SaaS、没有遥测，备份就是拷文件。
- **必须用云端大模型吗**：不用。LLM 网关默认指本机 Ollama，不填任何云 key 整条管线全本地跑。配了云 key 也有三层开关门禁，每次出域强制写审计日志（请求 hash + 大小 + 成本）。
- **收费吗**：MIT，自部署，没有付费版，没有公众号，不引流。

一直在用它管自己的开发过程（dogfooding）：八万多条事件，蒸了四十多份文档。中间翻过不少车——发布前一天用全新环境跑 docker compose 验证，注册接口直接 500，查下来是 bcrypt 5.0 和 passlib 1.7 的兼容坑，宿主机上老版本一直没暴露。差点带着这个 bug 上线。

仓库：https://github.com/johnnywuj81/tokenknows

装 Claude Code 插件只要两条命令（市场安装，MCP server 从 PyPI 自动拉）：

    /plugin marketplace add johnnywuj81/tokenknows
    /plugin install tokenknows@tokenknows

最想听大家的意见：你们希望从自己的 AI 编程过程里蒸出什么？现在有周报/技术方案/ADR/复盘/书/Skill/知识图谱七种，但我猜真实需求比我想象的野。
```

**发帖参数**：节点选「分享创造」，语法选 Markdown。发完 24h 内勤回复。

---

## 即刻 · 第一条（AI探索站 或 独立开发的日常）

```
开源了一个攒了半年的东西：TokenKnows。

起因很简单：每天在 Claude Code 里泡四五个小时，关掉终端，那些排坑过程和架构取舍就全蒸发了。周报靠回忆，ADR 靠考古。

于是写了个自部署的工作台，本地采集 Claude Code / Codex / Cursor 的会话，用 5 阶段管线蒸馏成周报、ADR、故障复盘、知识图谱。每段话都能点开看证据（哪次对话/哪个 PR），防 LLM 一本正经地编。

全本地可跑（Ollama），MIT，不收费。

github.com/johnnywuj81/tokenknows

后面会在这里记录它的成长。今天的数据：dogfooding 八万条事件，蒸了 40 份文档，外面用户 0 个，star 1 个（我自己）。
```

**配图**：assets/demo/ 里的 demo GIF（即刻发图用 mp4 转的动图或直接传 GIF）。

---

## 发后跟进清单

- [ ] V2EX 帖子链接：＿＿＿＿＿
- [ ] 即刻动态链接：＿＿＿＿＿
- [ ] 24h 内每条回复都答（隐私问题用 PRIVACY-FAQ 标准答案）
- [ ] star 到 5 → 手填 awesome-claude-code issue 表单
- [ ] 反馈里出现的高频需求 → 记进 PROMOTION.md
