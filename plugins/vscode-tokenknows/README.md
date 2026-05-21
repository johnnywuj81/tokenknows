# TokenKnows · VS Code 扩展 v0

把 VS Code(及 Cursor 等 fork)里的文件保存事件实时推到 TokenKnows 工作台。

## 安装

```bash
# 1. 装到本机 VS Code / Cursor (同 .vsix 兼容)
code --install-extension plugins/vscode-tokenknows/tokenknows-vscode-0.1.0.vsix

# 2. 重启 VS Code 后, 状态栏右下角出现 "TK ✓ N"
```

或从源码起:

```bash
cd plugins/vscode-tokenknows
npm install
npm run compile
# F5 在 VS Code 里 launch Extension Development Host
```

## 配置(VS Code Settings → Tokenknows)

| 配置项 | 默认 | 说明 |
|---|---|---|
| `tokenknows.backendUrl` | `http://localhost:8001` | TokenKnows API 后端地址 |
| `tokenknows.projectId` | `proj-demo-001` | 事件投递的 project_id |
| `tokenknows.enabled` | `true` | 关闭即不采集 |
| `tokenknows.batchIntervalSec` | `10` | 批量上报间隔(秒) |
| `tokenknows.includeFileExtensions` | 20+ 常见扩展名 | 只采这些文件类型 |

## 采集什么

仅 `onDidSaveTextDocument`(用户主动 ⌘S),不采:
- keystroke / onDidChangeTextDocument(太频繁、隐私扰)
- `.git/` / `node_modules/` 下的文件
- 不在白名单扩展的文件(`.log` `.lock` `.svg` 等)

入库的 Event:
- `source_type: vscode`
- `source_ref`: workspace 名
- `event_type: code_change`
- `content`: 文件路径 + 语言 + 行数 + 字符数(不传源代码内容!)
- `payload`: file_path + relative_path + language_id + line_count + content_sha256

content_hash 用 `sha256(file_path + sha + 分钟时间桶)`,**同一文件 1 分钟内连续保存只入 1 条**。

## 状态栏

| 显示 | 含义 |
|---|---|
| `TK ✓ 23` | 已上报 23 条,buffer 空 |
| `TK ⌛ 5 pending` | 5 条在 buffer 等下次 flush |
| `TK ⚠ offline · 3 pending` | 后端不可达,事件已缓存 |
| `TK · 暂停` | enabled=false |

点状态栏 = 立即 flush。

## 命令(`⌘P` → `>TokenKnows:`)

- **TokenKnows: 立即上报** — 不等定时器, 立刻 POST
- **TokenKnows: 启用/禁用采集**
- **TokenKnows: 显示状态** — 弹窗显示当前配置 + 计数

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
工作台事件流 (跟 Claude Code / GitHub / Cursor 混合显示)
```

## 隐私 / 安全

- **不传源代码内容**, 只传文件路径 + 元数据 + sha256
- backend 是本机或私有部署 (HTTPS / 局域网)
- 没有 secret / token 配置, 走纯 HTTP (本地端口)
- 文件 sha 用于后端将来去重 / 关联同一份代码的多版本

## 兼容性

- **VS Code 1.84+**
- **Cursor**(VS Code fork, API 兼容)
- 理论上 Windsurf / Codeium / 其它 VS Code fork 也工作
