# T21 · IMValueSegment 组装与入库

## 1. 目标
把通过 SignalGate 的零散消息聚合成"段"（ValueSegment），让现有蒸馏管线无差别消费 IM 数据。
Proposal: §7.2 IM-B.2 / §8.5 / §8.6 与 Event Schema 的桥接

## 2. 范围
- **In**: 时间窗口聚合 / 话题切换检测 / 段长度规则 / 入 ValueSegment 表 / 触发下游蒸馏
- **Out**: 蒸馏 LLM 调用本身（复用 MVP §5.8 / C6 已有管线）

## 3. 组装规则

| 规则 | 阈值 |
|---|---|
| 相邻 signal 消息时间间隔 | < 10 分钟 → 同段 |
| 话题切换检测 | LLM 小模型判断"是否换话题"（Yes/No 单 token 输出） |
| 段最小长度 | < 50 字符 → 丢弃 |
| 段最大长度 | > 2000 字符 → 切分 |
| 单段最多消息数 | 50 条（超过强制切） |

## 4. 数据契约

写入 `value_segment` 表（T16 patch 后）：

| 字段 | 值 |
|---|---|
| `source_type` | `'im'` |
| `source_mode` | `'personal'` (v0.3.0) / `'enterprise'` (v0.3.1+) |
| `im_chat_id` | 来源 chat |
| `im_message_ids` | 组成本段的 platform_msg_id 列表 |
| `contributors` | `[{user_id, name, anonymized=false, msg_count, segment_weight}]` |
| `content` | 拼接后的文本（保留发送者前缀 `[用户名]: 内容\n`） |
| `embedding` | 复用 MVP embedding pipeline |

## 5. 组件分解

```
backend/src/im/assembly/
├── assembler.py             ← 主类 IMValueSegmentAssembler
├── topic_detector.py        ← LLM 小模型话题切换判定
├── splitter.py              ← 段太长时切分
└── contributor_calc.py      ← 计算 segment_weight = msg_count / total_msg_count

backend/src/workers/
└── im_assembly_worker.py    ← Celery: 消费 SignalGate 后的消息流 → assembler → 入库
                              ← 触发下游蒸馏（与 MVP Event 流同入口）

backend/tests/im/assembly/
├── test_assembler.py
├── test_topic_detector.py
└── fixtures/conversations.json
```

## 6. 状态管理
- 维护"开放中"段的内存 buffer（每个 chat 1 个）
- 10 分钟无新 signal 消息 → 段关闭 → 入库
- worker 重启时从 redis 持久化的 buffer 恢复（避免段丢失）

## 7. 必备状态（DoD）
- [ ] 50 条 fixture 对话 → 组装出的段在人工评估下"段边界合理"≥ 85%
- [ ] embedding 复用 MVP pipeline，无需新 model
- [ ] 段写入触发下游蒸馏队列（同 MVP Event）
- [ ] worker 重启不丢段

## 8. 验收
- [ ] 一段聊天里 8 条 signal 消息（5 条 K8s + 3 条 Git） → 组装成 2 段
- [ ] 单条 signal 消息（孤立）+ 长度 ≥ 50 字符 → 单独成段
- [ ] 单条 < 50 字符 + 孤立 → 丢弃（不入库）
- [ ] 长段（> 2000 字符）自动切分，元数据指向原始消息列表正确
- [ ] contributors 权重和 = 1.0 (±0.01)
- [ ] 下游 Skill 自进化（MVP §5.8）能消费 IM 来源的 ValueSegment 无差异

## 9. 已知陷阱
- topic_detector 调用频次高（每对相邻消息一次），必须走 LLM Gateway cheap path
- 如果两个 user 几乎同时发消息（< 5 秒），可能是接龙回答，不要切段
- 引用回复（reply_to_msg_id）要并入被引用消息的段
- 段关闭时要再做一次"段内是否有效信号"校验（防止全是 weak signal 凑出来的虚假段）
- buffer 设计要支持每个 chat 独立流水，不能锁全局

## 10. Claude Code 指令
先写 assembler.py + 单测覆盖 fixture → 接 topic_detector（先 stub 后真接）→ splitter → contributor_calc → worker。最后端到端：人工聊一段 → 看入库的段对不对。
