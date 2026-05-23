"""T128 · todo_service 推导规则测试.

无独立存储, 直接 mock generation_service._assets dict.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.asset import Asset
from app.services import generation_service, todo_service


def _mk_asset(
    *,
    asset_id: str = "a1",
    project_id: str = "p1",
    status: str = "draft",
    approval_state: str = "pending",
    redaction_state: str = "all_confirmed",
    asset_type: str = "weekly_report",
    title: str = "周报 W21",
    updated_at: datetime | None = None,
) -> Asset:
    updated_at = updated_at or datetime.now(timezone.utc)
    return Asset(
        id=asset_id,
        project_id=project_id,
        type=asset_type,  # type: ignore[arg-type]
        title=title,
        status=status,  # type: ignore[arg-type]
        current_version=1,
        template_id="t",
        created_by="anon",
        approval_state=approval_state,  # type: ignore[arg-type]
        redaction_state=redaction_state,  # type: ignore[arg-type]
        created_at=updated_at,
        updated_at=updated_at,
    )


@pytest.fixture(autouse=True)
def _clean_assets():
    """每个 test 跑前后清空 _assets 防互染."""
    saved = dict(generation_service._assets)
    generation_service._assets.clear()
    yield
    generation_service._assets.clear()
    generation_service._assets.update(saved)


def test_rejected_asset_becomes_pending_revision() -> None:
    a = _mk_asset(approval_state="rejected", status="in_review")
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert len(todos) == 1
    assert todos[0].type == "pending_revision"
    assert todos[0].asset_id == "a1"
    assert "修订" in todos[0].title


def test_in_review_pending_review() -> None:
    a = _mk_asset(status="in_review", approval_state="pending")
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos[0].type == "pending_review"


def test_approved_pending_publish() -> None:
    a = _mk_asset(status="approved")
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos[0].type == "pending_publish"


def test_draft_with_unresolved_redaction_pending_redaction() -> None:
    a = _mk_asset(status="draft", redaction_state="any_unresolved")
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos[0].type == "pending_redaction"


def test_draft_clean_no_todo() -> None:
    """draft + all_confirmed + pending approval → 不产生 todo (在编辑中, 没事可做)."""
    a = _mk_asset(status="draft", redaction_state="all_confirmed")
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos == []


def test_stuck_generating_becomes_pending_generate() -> None:
    """generating 状态超过 5 分钟 → 进 pending_generate."""
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    a = _mk_asset(status="generating", updated_at=old_ts)
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos[0].type == "pending_generate"


def test_fresh_generating_no_todo() -> None:
    """generating 状态 < 5 min → 还在跑, 不打扰."""
    a = _mk_asset(status="generating")  # updated_at = now
    generation_service._assets[a.id] = a
    todos = todo_service.list_todos("p1")
    assert todos == []


def test_project_isolation() -> None:
    """只返回 query 项目的 todos."""
    a1 = _mk_asset(asset_id="a1", project_id="p1", approval_state="rejected")
    a2 = _mk_asset(asset_id="a2", project_id="p2", approval_state="rejected")
    generation_service._assets["a1"] = a1
    generation_service._assets["a2"] = a2
    todos = todo_service.list_todos("p1")
    assert len(todos) == 1
    assert todos[0].asset_id == "a1"


def test_priority_sort() -> None:
    """revision > review > publish > redaction · 同时存在时 revision 最前."""
    rev = _mk_asset(asset_id="rev", approval_state="rejected", status="in_review")
    rev_pub = _mk_asset(asset_id="pub", status="approved")
    rev_red = _mk_asset(asset_id="red", status="draft", redaction_state="any_unresolved")
    generation_service._assets["pub"] = rev_pub
    generation_service._assets["red"] = rev_red
    generation_service._assets["rev"] = rev
    todos = todo_service.list_todos("p1")
    types_in_order = [t.type for t in todos]
    assert types_in_order.index("pending_revision") < types_in_order.index("pending_publish")
    assert types_in_order.index("pending_publish") < types_in_order.index("pending_redaction")
