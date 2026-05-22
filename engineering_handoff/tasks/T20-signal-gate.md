# T20 · SignalGate（规则 + Qwen2.5-3B 本地分类器）

## 1. 目标
在消息进入蒸馏管线之前过滤噪声。规则强判（R1-R8）+ 本地小模型兜底（R10）。
Proposal: §7.2 模块 IM-B / §9.6 SignalGate 实现 / 决策 IM-13

## 2. 范围
- **In**: 规则引擎、Qwen2.5-3B 集成、阈值配置、可观测性指标、阈值变更后重算
- **Out**: ValueSegment 组装（T21）

## 3. 决策契约

输入 `IMNormalizedMessage` + 上下文（前 5 + 后 2 条）→ 输出 `SignalResult { is_signal, score, reason }`。

| 规则 | 判定 | 优先级 |
|---|---|---|
| R1 长度 < 5 字符 | noise | 1（强制） |
| R2 全表情 / 全标点 | noise | 1 |
| R3 系统消息 | noise | 1 |
| R4 纯转发/链接（< 30 字补充） | noise | 1 |
| R5 问句无回答 | weak (score=0.3) | 2 |
| R6 问答配对 | signal (score≥0.7) | 1（强制） |
| R7 决策表述 | signal (score≥0.7) | 1 |
| R8 复盘/总结 | signal (score≥0.7) | 1 |
| R9 链接 + 长解读 | maybe → 给 LLM | 3 |
| R10 默认 | LLM 小模型给分 | 3 |

合成：`if R1-R4: 0.0; elif R6-R8: max(0.7, llm); else: llm`

## 4. 本地模型集成

| 维度 | 选型 |
|---|---|
| 模型 | Qwen2.5-3B-Instruct (4-bit 量化 GGUF) |
| 部署 | Ollama (`ollama pull qwen2.5:3b`) |
| 调用 | LLM Gateway `model_hint="cheap"` → 路由到 ollama:11434 |
| 输入 | 中文 prompt "判断以下消息是否是工作中有沉淀价值的信息（问答/决策/复盘），输出 JSON {score: 0-1}" |
| 性能目标 | 单条 < 200ms（CPU），< 50ms（GPU） |
| 兜底 | 模型超时（500ms） → 走 R5 弱信号路径，不阻塞流程 |

## 5. 组件分解

```
backend/src/im/signal/
├── gate.py                  ← SignalGate 主类
├── rules.py                 ← R1-R9 规则函数
├── llm_classifier.py        ← R10：调 LLM Gateway
├── prompt.py                ← prompt 模板
└── metrics.py               ← 指标：signal_rate / dropped_by_rule / llm_calls

backend/src/workers/
└── im_signal_worker.py      ← Celery worker：消费消息 → SignalGate → 写回 im_message.signal_*

backend/src/api/routes/
└── im_signal.py             ← GET/PATCH /api/.../im/signal/config
                              ← POST /api/.../im/signal/recompute

backend/tests/im/signal/
├── test_rules.py            ← 每条规则 5+ 用例
├── test_gate.py             ← 端到端：注入 FakeLLM
└── fixtures/messages.json   ← 100 条标注样本（手工 + 后续真实数据）
```

## 6. 状态管理
- 阈值存 `im_connection.config.signal_threshold`，默认 0.4
- 阈值变更 → POST `/im/signal/recompute` 触发重算（按 chat + 时间区间）

## 7. 必备状态（DoD）
- [ ] 100 条 fixture 样本上：规则准确率 ≥ 90%（vs 人工标注）
- [ ] LLM 兜底准确率 ≥ 75%
- [ ] 整体 signal 召回率 ≥ 85%（不要漏掉真信号）
- [ ] 单条处理延迟 P95 < 300ms
- [ ] 指标暴露到 Prometheus

## 8. 验收
- [ ] 阈值调到 0.6（节流）后，signal_rate 显著下降；调到 0.2（激进）显著上升
- [ ] LLM Gateway 关闭出域 → 必须走本地 Ollama，不抛错
- [ ] recompute 任务支持断点续跑（chat × 月分片 checkpoint）
- [ ] metrics 暴露：`im_signal_rate` / `im_signal_llm_calls_total` / `im_signal_rule_hit_total{rule="R1"}`

## 9. 已知陷阱
- Ollama 在 macOS / Linux 表现不同；私有化部署清单写明硬件要求（最低 8GB RAM CPU / 推荐 16GB + GPU）
- Qwen2.5-3B 的 4-bit 量化（q4_K_M）vs 8-bit：4-bit 速度 1.5x，准确率掉 ~3%；v0.3.0 用 q4_K_M
- prompt 不要让模型自由生成，强制 JSON 输出 + 失败时 fallback 到 weak signal
- 表情判定要 unicode 范围扫描，不要用第三方包（可能 GPL）
- R7 "决策表述" 关键词列表要可配置（不同团队语言习惯不同）；存 `signal/keywords.json`
- recompute 别在生产白天跑，凌晨触发；任务期间 SignalGate 仍按新阈值处理新消息

## 10. Claude Code 指令
先写 rules.py（纯函数易测）→ test_rules.py → 跑过 100 条 fixture → 写 llm_classifier.py（先用 FakeLLM）→ 真实接 Ollama → metrics → worker → API。最后用真实飞书测试群跑 1000+ 条消息看整体准确率。
