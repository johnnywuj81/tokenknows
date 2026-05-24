# TokenKnows · 本地文档插件

把指定目录下的 `.md` / `.txt` / `.pdf` 文档实时推到工作台,成为可被引用的证据来源。

## 用途场景

- 本地写的 ADR / RFC / 设计稿 (`*.md`)
- 项目内的 README / CHANGELOG
- 随手笔记 / 灵感稿 (`*.txt`)
- 行业研报 / 白皮书 / 书籍章节 (`*.pdf`,按页拆 event)

## 依赖

- 必需: `requests`, `watchdog`
- 可选: `pdfplumber` (若装则启用 `.pdf` 支持; CJK 友好)

```bash
pip install requests watchdog pdfplumber
```

## 快速上手

```bash
# 一次性全量入库
python3 plugins/local-docs/sync.py \
  --backend http://localhost:8001 \
  --project proj-demo-001 \
  --watch-dir ~/Documents/notes \
  --bootstrap

# 持续监听 (前台)
python3 plugins/local-docs/sync.py \
  --backend http://localhost:8001 \
  --project proj-demo-001 \
  --watch-dir ~/Documents/notes \
  --watch
```

后台跑见 `~/Library/LaunchAgents/com.tokenknows.local-docs.plist` (由 `scripts/install-launchd.sh` 安装)。

## 行为说明

| 项 | 值 |
|---|---|
| 监听扩展 | `.md`, `.txt`, `.pdf` (后者需 pdfplumber) |
| 跳过目录 | `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, `.idea`, `.vscode`, `target`, 以及所有 `.` 开头隐藏目录 |
| 跳过文件 | 0 字节 / 二进制 / `.` 开头隐藏文件 / PDF >20MB |
| 大小上限 | 文本类 2 MB(超过截断尾部,`payload.truncated=true`);PDF 20 MB(超过整份跳过) |
| Debounce | 2 秒(连续编辑合并成一次推送) |
| 幂等 | 服务端 `content_hash = sha256(file_path + 前 4KB)`,重复推送会被 `skipped` |

## PDF 处理 (page-level chunking)

依据 2026 业界共识 (NVIDIA RAG benchmark: 0.648 accuracy, 0.107 std, 最稳定):

- **一页一条 event** · `source_ref = "name.pdf#page=N"`, `payload.page=N`, `payload.total_pages=M`
- **空白页跳过** · 单页正文 < 30 字符不入库 (封面/版权页)
- **CJK 友好** · pdfplumber + pdfminer.six 中文不乱码
- **不做 OCR** · 扫描件 PDF (图像非文本) 会被空白页规则跳过; 后续可选 tesseract 扩展

## Event 形状

```json
{
  "source_type": "local_file",
  "source_ref": "notes/architecture/sqlite-switch.md",
  "event_type": "local_document",
  "occurred_at": "2026-05-21T11:30:00Z",
  "author": {"name": "我", "external_id": "local"},
  "title": "sqlite switch",
  "content": "...(全文,最多 2MB)...",
  "trust_score": 0.77,
  "payload": {
    "file_path": "/Users/wujun/Documents/notes/architecture/sqlite-switch.md",
    "size_bytes": 2840,
    "truncated": false,
    "extension": ".md",
    "trust_components": {
      "source_authority": 0.75,
      "extraction_confidence": 0.8
    }
  },
  "tags": ["md", "local"]
}
```

PDF 单页 event 示例:

```json
{
  "source_type": "local_file",
  "source_ref": "playbook.pdf#page=19",
  "event_type": "local_document",
  "title": "playbook · p.19/36",
  "content": "...(第 19 页全部抽出的文本)...",
  "trust_score": 0.85,
  "payload": {
    "file_path": "/Users/wujun/Documents/notes/playbook.pdf",
    "extension": ".pdf",
    "page": 19,
    "total_pages": 36,
    "size_bytes": 476356,
    "truncated": false
  },
  "tags": ["pdf", "local", "pdf-page"]
}
```

## trust_score 公式

```
trust = 0.6 × source_authority + 0.4 × extraction_confidence

source_authority  = 0.75   # 本地文档:用户主动写,但未经发布/同行评审
extraction_confidence:
  ≥500 字符 → 1.0
  100-500   → 0.8
  <100      → 0.5
```

对比其它来源:

| 来源 | authority | 备注 |
|---|---|---|
| GitHub PR (merged) | 0.95 | 经过 review 已合并 |
| GitHub commit | 0.85 | 真上库代码 |
| Claude Code (assistant+tool) | 0.85 | AI 实际"做事" |
| Cursor (assistant) | 0.80 | AI 在 IDE 内的建议 |
| **local_file** | **0.75** | **本插件** |
| Claude Code (user prompt) | 0.70 | 用户意图 |
| GitHub Issue (open) | 0.65 | 未确认问题 |

## 命令行参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--backend` | `http://localhost:8001` | 后端基址 |
| `--project` | `proj-demo-001` | 目标 project_id |
| `--watch-dir` | `~/Documents` | 监听目录(递归) |
| `--watch` | (off) | 持续监听 |
| `--bootstrap` | (off) | 全量扫一次后退出 |
| `--reset` | (off) | 清空 state 重新入库 |

## State 文件

`~/.tokenknows/local_docs_state.json`,记录每个文件的 `mtime`。
**仅作快速跳过参考**——真正的幂等性来自服务端 `content_hash` 去重。

删除 state 文件不会重复入库,只会重新发起请求,服务端会返回 `skipped`。
