"""GitHub Webhook receiver · 可选.

生产部署里用 webhook 替代/补充轮询.

配置:
    1. ngrok / cloudflared 暴露 8001 端口
    2. GitHub repo Settings → Webhooks → Add:
        - Payload URL: https://<tunnel>/api/v1/webhooks/github
        - Content type: application/json
        - Secret: 设一个 strong random, 填到本机 GITHUB_WEBHOOK_SECRET env
        - Events: pull_request / issues / push / issue_comment
    3. 后端启动时自动 verify HMAC-SHA256 签名

如果 GITHUB_WEBHOOK_SECRET 未设, 端点接受任何调用 (仅本地开发用).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.config.logging import logger
from app.schemas.event import EventCreate
from app.services import event_service as svc
from app.services.auto_trigger.evaluator.event_evaluator import (
    GitHubEvent,
    evaluate_github_event,
    normalize_issue_webhook,
    normalize_pr_webhook,
)

router = APIRouter()

WEBHOOK_SECRET_ENV = "GITHUB_WEBHOOK_SECRET"
DEFAULT_PROJECT_ID = "proj-demo-001"


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """X-Hub-Signature-256: sha256=<hex>."""
    secret = os.environ.get(WEBHOOK_SECRET_ENV)
    if not secret:
        # 未配 secret → 接受 (仅本地开发)
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── 事件映射 ──────────────────────────────────────────────


def _pr_event(payload: dict[str, Any], repo: str) -> EventCreate | None:
    """pull_request webhook → EventCreate."""
    action = payload.get("action")
    # 只关心 opened / closed / reopened / synchronize (其它 noise 太多)
    if action not in ("opened", "closed", "reopened", "synchronize", "ready_for_review"):
        return None
    pr = payload.get("pull_request", {})
    is_merged = pr.get("merged_at") is not None
    state_label = "merged" if (action == "closed" and is_merged) else (pr.get("state") or "open")
    title = pr.get("title", "")
    body = pr.get("body") or ""
    occurred = pr.get("updated_at") or _now_iso()
    return EventCreate(
        source_type="github",
        source_ref=repo,
        external_id=f"pr-{pr['number']}",
        version=1,
        event_type="pr_event",
        occurred_at=occurred,  # type: ignore[arg-type]
        author={
            "name": pr.get("user", {}).get("login") or "?",
            "external_id": str(pr.get("user", {}).get("id") or ""),
        },  # type: ignore[arg-type]
        title=f"PR #{pr['number']} · {title}",
        content=f"action={action} state={state_label}\n\n{title}\n\n{body[:1500]}",
        content_hash=_sha256(f"pr-{pr['number']}-{action}-{state_label}-{occurred}"),
        payload={
            "action": action,
            "number": pr["number"],
            "state": state_label,
            "html_url": pr.get("html_url"),
            "head_ref": pr.get("head", {}).get("ref"),
            "base_ref": pr.get("base", {}).get("ref"),
        },
        tags=["github", action, state_label],
    )


def _issue_event(payload: dict[str, Any], repo: str) -> EventCreate | None:
    action = payload.get("action")
    if action not in ("opened", "closed", "reopened", "edited"):
        return None
    iss = payload.get("issue", {})
    if iss.get("pull_request"):  # 跳过 issue 上 PR comment 衍生
        return None
    title = iss.get("title", "")
    body = iss.get("body") or ""
    state = iss.get("state")
    occurred = iss.get("updated_at") or _now_iso()
    return EventCreate(
        source_type="github",
        source_ref=repo,
        external_id=f"issue-{iss['number']}",
        version=1,
        event_type="issue_event",
        occurred_at=occurred,  # type: ignore[arg-type]
        author={
            "name": iss.get("user", {}).get("login") or "?",
            "external_id": str(iss.get("user", {}).get("id") or ""),
        },  # type: ignore[arg-type]
        title=f"Issue #{iss['number']} · {title}",
        content=f"action={action} state={state}\n\n{title}\n\n{body[:1500]}",
        content_hash=_sha256(f"issue-{iss['number']}-{action}-{state}-{occurred}"),
        payload={
            "action": action,
            "number": iss["number"],
            "state": state,
            "html_url": iss.get("html_url"),
            "labels": [lbl.get("name") for lbl in iss.get("labels", [])],
        },
        tags=["github", action, state],
    )


def _push_events(payload: dict[str, Any], repo: str) -> list[EventCreate]:
    """push webhook 可能含多个 commit."""
    out: list[EventCreate] = []
    commits = payload.get("commits") or []
    pusher_login = (payload.get("pusher") or {}).get("name") or "?"
    for c in commits:
        sha = c.get("id")
        if not sha:
            continue
        msg = (c.get("message") or "").strip()
        occurred = c.get("timestamp") or _now_iso()
        title_line = msg.split("\n", 1)[0][:80]
        out.append(
            EventCreate(
                source_type="github",
                source_ref=repo,
                external_id=f"commit-{sha}",
                version=1,
                event_type="commit",
                occurred_at=occurred,  # type: ignore[arg-type]
                author={
                    "name": (c.get("author") or {}).get("name") or pusher_login,
                    "email": (c.get("author") or {}).get("email"),
                },  # type: ignore[arg-type]
                title=f"commit {sha[:7]} · {title_line}",
                content=msg[:2000],
                content_hash=_sha256(f"commit-{sha}"),
                payload={
                    "sha": sha,
                    "html_url": c.get("url"),
                    "added": c.get("added"),
                    "removed": c.get("removed"),
                    "modified": c.get("modified"),
                },
                tags=["github", "commit", payload.get("ref", "").split("/")[-1]],
            )
        )
    return out


# ─── 端点 ─────────────────────────────────────────────────


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, Any]:
    """接收 GitHub webhook. project_id 默认走 demo, 生产应从 URL/payload 解.

    支持事件:
        - pull_request (opened/closed/reopened/synchronize/ready_for_review)
        - issues (opened/closed/reopened/edited)
        - push (commits)
        - ping (健康探测, 回 pong)
    """
    raw = await request.body()
    if not _verify_signature(raw, x_hub_signature_256):
        raise HTTPException(401, detail="invalid signature")

    if x_github_event == "ping":
        return {"ok": True, "pong": True}

    payload = await request.json()
    repo_full = (payload.get("repository") or {}).get("full_name") or "unknown"

    events_to_ingest: list[EventCreate] = []
    auto_trigger_event: GitHubEvent | None = None  # v0.4.1: 喂给 EventEvaluator

    if x_github_event == "pull_request":
        ev = _pr_event(payload, repo_full)
        if ev:
            events_to_ingest.append(ev)
        auto_trigger_event = normalize_pr_webhook(payload)
    elif x_github_event == "issues":
        ev = _issue_event(payload, repo_full)
        if ev:
            events_to_ingest.append(ev)
        auto_trigger_event = normalize_issue_webhook(payload)
    elif x_github_event == "push":
        events_to_ingest.extend(_push_events(payload, repo_full))
    else:
        logger.info("github_webhook_unhandled", gh_event=x_github_event, repo=repo_full)
        return {"ok": True, "skipped": x_github_event}

    if not events_to_ingest and auto_trigger_event is None:
        return {"ok": True, "skipped": "no matching action"}

    result = svc.ingest_events(DEFAULT_PROJECT_ID, events_to_ingest) if events_to_ingest else None

    # v0.4.1 · 把归一化事件喂给 EventEvaluator (mode=event 规则评估)
    # 不阻塞 webhook 响应; evaluator 内部串行评估 + schedule_execution
    auto_trigger_stats: dict[str, int] | None = None
    if auto_trigger_event is not None:
        try:
            auto_trigger_stats = evaluate_github_event(
                auto_trigger_event, DEFAULT_PROJECT_ID
            )
        except Exception as e:
            logger.error(
                "auto_trigger_event_eval_failed",
                gh_event=x_github_event,
                error=str(e),
                exc_info=True,
            )

    logger.info(
        "github_webhook_ingested",
        gh_event=x_github_event,
        repo=repo_full,
        delivery=x_github_delivery,
        ingested=result.ingested if result else 0,
        skipped=result.skipped if result else 0,
        auto_trigger_scheduled=(
            auto_trigger_stats.get("scheduled", 0) if auto_trigger_stats else 0
        ),
    )
    return {
        "ok": True,
        "event": x_github_event,
        "repo": repo_full,
        "ingested": result.ingested if result else 0,
        "skipped": result.skipped if result else 0,
        "auto_trigger": auto_trigger_stats or {"scheduled": 0},
    }
