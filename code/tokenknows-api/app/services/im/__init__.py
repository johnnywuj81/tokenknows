"""IM 集成 (v0.3) · 4 平台统一抽象 + 各 connector + signal gate + value segment.

子模块:
- connector_base: IMConnector ABC + IMNormalizedMessage + Registry
- feishu_connector: 飞书实现 (T18-T19)
- signal_gate: 信号判定 (T20)
- value_segment_service: 段组装 + 蒸馏 (T21)
- retention: 90 天到期清理 + 撤回 (T22)
"""
