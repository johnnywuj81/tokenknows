"""4 条预置规则 seeder (v0.4 T28).

启动时 (lifespan) 调用 seed_default_rules(); 幂等: 同 name 已存在则跳过.

设计依据:
- Proposal §1.2 决策 AT-9: 预置 4 条
- Proposal 附录 A.1-A.4 (周报 / ADR / incident / book) JSON 定义
- Q4 决策 (2026-05-22): book 类型预置规则默认 enabled=false

幂等性:
- 用 rule.name 作为去重 key (Q6 决策: 实例级默认规则被项目级覆盖,
  但实例级本身名字唯一)
- 已存在 name 的规则跳过, 不更新 (保留用户可能的自定义改动)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.logging import logger
from app.schemas.auto_trigger import (
    EventMatch,
    ExtraCondition,
    ThresholdSpec,
)
from app.services import auto_trigger_service as svc

_DEFAULT_RULES_DIR = Path(__file__).parent / "default_rules"

# 4 条预置规则的 JSON 文件名 (与 Proposal 附录 A 对应)
_DEFAULT_RULE_FILES = [
    "weekly_report.json",
    "adr_pr_label.json",
    "incident_issue.json",
    "book_threshold.json",
]


def _load_default_rules() -> list[dict[str, Any]]:
    """从 default_rules/*.json 加载 4 条规则定义."""
    rules = []
    for fname in _DEFAULT_RULE_FILES:
        path = _DEFAULT_RULES_DIR / fname
        with open(path, encoding="utf-8") as f:
            rules.append(json.load(f))
    return rules


def _build_kwargs(rule_dict: dict[str, Any]) -> dict[str, Any]:
    """JSON dict → svc.create_rule 关键字参数 (含嵌套 Pydantic 模型实例化)."""
    kwargs: dict[str, Any] = {
        "name": rule_dict["name"],
        "description": rule_dict.get("description", ""),
        "mode": rule_dict["mode"],
        "asset_type": rule_dict["asset_type"],
        "priority": rule_dict.get("priority", 50),
        "enabled": rule_dict.get("enabled", True),
        "cooldown_seconds": rule_dict.get("cooldown_seconds", 3600),
        "daily_cap": rule_dict.get("daily_cap", 5),
    }
    if "cron_expr" in rule_dict:
        kwargs["cron_expr"] = rule_dict["cron_expr"]
    if "event_match" in rule_dict:
        kwargs["event_match"] = EventMatch.model_validate(rule_dict["event_match"])
    if "threshold_spec" in rule_dict:
        kwargs["threshold_spec"] = ThresholdSpec.model_validate(rule_dict["threshold_spec"])
    if "extra_condition" in rule_dict:
        kwargs["extra_condition"] = ExtraCondition.model_validate(rule_dict["extra_condition"])
    return kwargs


def seed_default_rules() -> dict[str, int]:
    """幂等 seed 4 条实例级 (project_id=None) 默认规则.

    返回 { "created": N, "skipped": M }.
    """
    # 拉所有现有实例级规则的 name set 用作去重
    existing = svc.list_rules(project_id=None, include_instance_defaults=True)
    existing_names = {r.name for r in existing}

    created = 0
    skipped = 0
    errors = 0
    for rule_dict in _load_default_rules():
        name = rule_dict["name"]
        if name in existing_names:
            skipped += 1
            continue
        try:
            kwargs = _build_kwargs(rule_dict)
            svc.create_rule(
                project_id=None,        # 实例级
                created_by="system",
                **kwargs,
            )
            created += 1
        except Exception as e:
            # 单条失败不阻塞其他规则的 seed
            logger.error(
                "auto_trigger_default_rule_seed_failed",
                rule_name=name,
                error=str(e),
            )
            errors += 1

    logger.info(
        "auto_trigger_default_rules_seeded",
        created=created,
        skipped=skipped,
        errors=errors,
        total_files=len(_DEFAULT_RULE_FILES),
    )
    return {"created": created, "skipped": skipped, "errors": errors}


__all__ = ["seed_default_rules"]
