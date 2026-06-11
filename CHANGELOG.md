# Changelog

All notable changes to TokenKnows are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

> 平台(api + web)版本走 `v0.x` 主线;分发件各走各的版本线
> (Claude Code 插件 `2.x`,VS Code 扩展 `0.2.x`)—— 内部里程碑名(v1.1 / v1.5 等)是迭代代号,不是制品版本。

## [Unreleased]

打通开源用户闭环:装插件 → 登录 Web → 自助拿 token → 蒸馏结果可点击查看。

### Added · 新增

- **API Token 自助管理**(后端 + Web):`api_tokens` 表 + `pat_service`(`tkk_` 前缀、sha256 存储、可撤销、last_used_at 连接信号);`POST/GET/DELETE /me/tokens` 端点;Web 项目设置新增「MCP 接入」tab(token 创建/列表/撤销 + 一键复制插件环境变量块)
- **AUTH_MODE 开关**(`open`/`required`,默认 `open`):`required` 模式下 events / generation / projects 数据端点强制 Bearer 鉴权(不认可伪造的 `X-User-Id`),公网部署建议开启
- **CORS_ORIGINS 环境变量**:跨域来源可配置(原 localhost:5173 硬编码)
- **JWT secret 启动闸**:非 local 环境使用默认 dev secret 时拒绝启动
- **`tokenknows-watcher` 控制台入口**(tokenknows-mcp 0.3.0):session 守护进程可经 `uvx --from tokenknows-mcp tokenknows-watcher` 调起
- **PyPI 自动发布**:`.github/workflows/publish-pypi.yml`(Trusted Publishing,`mcp-v*` tag 触发)

### Changed · 变更

- **tokenknows-mcp 0.2.1 → 0.3.0**:`view_url` 由相对路径改为绝对 URL(新 env `TOKENKNOWS_WEB_BASE`,默认 `http://127.0.0.1:5173`);MCP 工具错误信息改为可操作的双语单行指引(后端未启动 / 401 缺 token / 404 项目不存在 / 蒸馏超时)
- **Claude Code 插件 2.1.0 → 2.2.0**:`.mcp.json` 改用 `uvx tokenknows-mcp==0.3.0` 从 PyPI 拉起(marketplace 安装零 clone 零 export 可用;`${VAR:-default}` 默认值已获官方文档确认);`TOKENKNOWS_API_ROOT` 降级为本地开发可选项(PYTHONPATH 透传 editable 模式)
- **插件文档重构**:按真实前置链(部署后端 → 启动 Web → 注册登录拿 token → 装 uv → 装插件 → 验证)重写 README;新增 5 分钟跑通脚本、watcher 章节;INSTALL-COWORK / codex-plugin / 根 README 同步;MCP registry server.json 补列 `TOKENKNOWS_DEFAULT_PROJECT` 与 `TOKENKNOWS_WEB_BASE`

## [0.1.0] — 2026-06-10

First public release. 首个公开版本。

### Capture · 采集

- 6 个本地采集器:Claude Code / Codex / Cursor / VS Code 扩展 / GitHub(PR·Issue·Commit)/ 本地文档(md·txt·pdf),全部增量 + 幂等去重,macOS launchd 一键常驻
- 事件级 trust_score(来源权威 × 抽取置信)

### Distill · 蒸馏

- 5 阶段生成流水线(collect → outline → content → evidence → assess)+ SSE 实时进度
- 7 类知识资产:周报 / 技术方案 / ADR / 问题复盘 / 技术书籍(卷-章-节)/ Agent Skill(Anthropic SKILL.md,含 allowed-tools)/ 知识图谱(实体-关系,React Flow 渲染)
- 证据链:`cosine × trust × recency` 排序,强制 ≥2 来源;段落级 [N] 角标回溯原始 PR/对话/Commit
- LLM 输出容错:json-repair 兜底缺逗号/未转义引号/截断;SKILL.md 剥 code-fence/preamble

### Govern · 治理

- 三层 LLM 出域门禁(实例 ∧ 项目 ∧ 任务)+ 完整出域审计(本地 SQLite)
- LLM Gateway 统一 4 家 provider(Anthropic / OpenAI / MiniMax / Ollama),按任务路由 + 故障链回退;Ollama 全离线模式零云端 key
- 审批 / LLM 辅助脱敏 / 发布回执 + 版本 diff;JWT 鉴权

### Integrate · 接入

- Claude Code 插件(marketplace 形态:MCP server + 9 个 slash 命令 + skills)
- Codex 插件(marketplace 形态 + MCP)、Cursor(MCP)、VS Code 扩展(事件采集)
- MCP 工具:submit_session_events / distill_document / list_assets / get_asset / get_asset_chapters / search_entity

[0.1.0]: https://github.com/johnnywuj81/tokenknows/releases/tag/v0.1.0
