# TokenKnows · 代码事件采集

> Capture file-save events from VS Code / Cursor and stream them to your self-hosted TokenKnows workbench.

把 VS Code（及 Cursor 等兼容编辑器）里的文件保存事件实时推到 [TokenKnows](https://github.com/johnnywuj81/tokenknows) 工作台，作为研发知识蒸馏（周报 / 技术方案 / ADR / 知识图谱）的数据源之一。

## 前置条件

本插件是 **TokenKnows 自部署工作台的配套采集端**，需要一个可访问的 TokenKnows API 后端（默认 `http://localhost:8001`）。后端部署方式见 [TokenKnows 主仓库](https://github.com/johnnywuj81/tokenknows)。

没有后端时插件不会报错：事件缓存在内存里，状态栏显示 `TK ⚠ offline`，后端恢复后自动续传。

## 安装

从市场搜索 **TokenKnows** 安装，或手动装 vsix：

```bash
code --install-extension tokenknows-vscode-0.2.1.vsix
```

重启编辑器后，状态栏右下角出现 `TK ✓ N`（N = 已上报事件数）。

## 采集什么 · 不采集什么

仅 `onDidSaveTextDocument`（用户主动 ⌘S），不采：

- keystroke / onDidChangeTextDocument（太频繁、隐私扰）
- `.git/` / `node_modules/` 下的文件
- 不在白名单扩展的文件（`.log` `.lock` `.svg` 等）

入库的 Event：

- `source_type: vscode` · `event_type: code_change`
- `source_ref`: workspace 名
- `content`: 文件路径 + 语言 + 行数 + 字符数（**不传源代码内容**）
- `payload`: file_path + relative_path + language_id + line_count + content_sha256

content_hash 用 `sha256(file_path + sha + 分钟时间桶)`，**同一文件 1 分钟内连续保存只入 1 条**。

## 隐私 / 安全

- **不传源代码内容**，只传文件路径 + 元数据 + sha256
- 数据**只发送到你自己配置的 `backendUrl`**（本机或私有部署），不经过任何第三方服务器
- 文件 sha 用于后端去重 / 关联同一份代码的多版本

## 配置（Settings → 搜索 "tokenknows"）

| 配置项 | 默认 | 说明 |
|---|---|---|
| `tokenknows.backendUrl` | `http://localhost:8001` | TokenKnows API 后端地址 |
| `tokenknows.projectId` | `proj-demo-001` | 事件归属的 project_id |
| `tokenknows.enabled` | `true` | 关闭即停止采集（仍可手动 flush） |
| `tokenknows.batchIntervalSec` | `10` | 批量上报间隔（秒），2–120 |
| `tokenknows.includeFileExtensions` | 20+ 常见源码扩展名 | 白名单外的文件一律跳过 |

## 命令（⌘⇧P → `TokenKnows:`）

- **TokenKnows: 立即上报** — 不等定时器，立刻 POST（点状态栏图标等效）
- **TokenKnows: 启用/禁用采集**
- **TokenKnows: 显示状态** — 弹窗显示当前配置 + 计数

## 状态栏

| 显示 | 含义 |
|---|---|
| `TK ✓ 23` | 已上报 23 条，buffer 空 |
| `TK ⌛ 5 pending` | 5 条在 buffer 等下次 flush |
| `TK ⚠ offline · 3 pending` | 后端不可达，事件已缓存 |
| `TK · 暂停` | 采集已禁用 |

## 数据流

```
用户 ⌘S 保存 file.ts
    ↓
onDidSaveTextDocument(doc)
    ↓ shouldCollect (extension whitelist + skip .git/node_modules)
EventCreate { vscode, code_change, file_path, line_count, sha256 }
    ↓ buffer.push
    ↓ (每 10s 或手动 flush)
POST /api/v1/projects/<id>/events
    ↓ backend content_hash 去重
工作台事件流 (跟 Claude Code / GitHub / Codex 混合显示)
```

## 兼容性

- **VS Code 1.84+**
- **Cursor**（通过 Open VSX 分发，API 兼容）
- 理论上 Windsurf / VSCodium / 其它 VS Code 兼容编辑器也工作

## 从源码开发

```bash
cd plugins/vscode-tokenknows
npm install
npm run compile   # 或 F5 启动 Extension Development Host
npm run package   # 产出 .vsix
```

## License

[MIT](./LICENSE)
