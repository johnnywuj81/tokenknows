# Changelog

All notable changes to TokenKnows are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

> 平台(api + web)版本走 `v0.x` 主线;分发件各走各的版本线
> (Claude Code 插件 `2.x`,VS Code 扩展 `0.2.x`)—— 内部里程碑名(v1.1 / v1.5 等)是迭代代号,不是制品版本。

## [Unreleased]

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
