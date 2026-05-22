"""Auto-Trigger 规则评估器子包 (v0.4 T29).

模块:
- cron_matcher: 判断 cron 表达式是否在 1 分钟窗口内到点
- conditions: ExtraCondition / ThresholdSpec 指标查询 + 比较
- rule_evaluator: 主流程, 遍历 enabled cron 规则 → 检查 → schedule / skip
"""

from app.services.auto_trigger.evaluator.cron_matcher import matches_in_window
from app.services.auto_trigger.evaluator.conditions import evaluate_extra_condition
from app.services.auto_trigger.evaluator.rule_evaluator import (
    evaluate_cron_rules,
    SCAN_WINDOW_SECONDS,
)

__all__ = [
    "matches_in_window",
    "evaluate_extra_condition",
    "evaluate_cron_rules",
    "SCAN_WINDOW_SECONDS",
]
