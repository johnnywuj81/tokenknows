#!/usr/bin/env python3
"""TokenKnows GitHub 插件 v0 · REST API 轮询.

设计目标:
- 通过 GitHub REST API 拉 PR / Issue / Commit 三类事件
- 增量: 用 ~/.tokenknows/github_state.json 记录 per-repo (kind, last_seen_iso)
- 复用 backend 的 /events 接入端点 + content_hash 去重
- Auth: 优先 env `GH_TOKEN`, fallback `gh auth token`

为什么轮询而非 webhook:
- 不需要公网 / ngrok 隧道, 纯本地
- 速度够用 (5 分钟轮询 ~= 用户看工作台前已经入库)
- 失败重试简单 (下次轮询自动补)
- webhook 端点已在 backend /webhooks/github (生产部署可启)

调用:
    # 一次:
    python3 plugins/github/sync.py --repo johnnywuj81/tokenknows
    # 多 repo:
    python3 plugins/github/sync.py --repo owner/repo1 --repo owner/repo2
    # 持续:
    python3 plugins/github/sync.py --repo johnnywuj81/tokenknows --watch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("✗ 需安装 requests: pip install requests", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("TK_LOG", "INFO"),
)
log = logging.getLogger("tk-gh-sync")

STATE_FILE = Path.home() / ".tokenknows" / "github_state.json"
GH_API = "https://api.github.com"
POLL_INTERVAL_SEC = 300  # 5 分钟 (避免 rate limit)
BATCH_SIZE = 200
PAGE_SIZE = 100          # GitHub REST 单页上限


# ─── Auth ─────────────────────────────────────────────────


def get_token() -> str:
    """优先 GH_TOKEN env, 否则 gh auth token."""
    token = os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True, timeout=5,
        )
        token = out.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    log.error("无 GitHub token. 请设 GH_TOKEN env 或 gh auth login")
    sys.exit(1)


# ─── State ────────────────────────────────────────────────


def load_state() -> dict[str, dict[str, str]]:
    """state[<repo>]<kind> = last_seen_iso  (kind in: prs, issues, commits)."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("state file corrupted, resetting")
        return {}


def save_state(state: dict[str, dict[str, str]]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ─── HTTP helpers ──────────────────────────────────────────


def gh_get(url: str, token: str, **params: Any) -> requests.Response:
    return requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={k: v for k, v in params.items() if v is not None},
        timeout=30,
    )


def gh_paginate(url: str, token: str, **params: Any) -> list[dict[str, Any]]:
    """循环走 GitHub Link header, 拉全部页."""
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = gh_get(url, token, per_page=PAGE_SIZE, page=page, **params)
        if not resp.ok:
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                log.warning("rate limit hit, stop pagination")
                break
            log.warning("GET %s failed: %d %s", url, resp.status_code, resp.text[:200])
            break
        batch = resp.json()
        if not isinstance(batch, list):
            log.warning("unexpected response shape from %s", url)
            break
        out.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        if page > 20:  # 安全阀, 不无限分页
            log.info("page limit 20 hit on %s, stopping", url)
            break
        page += 1
    return out


# ─── 事件映射 ─────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _author(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "name": user.get("login") or "?",
        "email": None,
        "external_id": str(user.get("id") or ""),
    }


def pr_to_event(pr: dict[str, Any], repo: str) -> dict[str, Any]:
    """Pull Request → Event."""
    title = pr.get("title", "")
    body = pr.get("body") or ""
    state = pr.get("state")
    is_merged = pr.get("merged_at") is not None
    state_label = "merged" if is_merged else state  # open/closed/merged
    full_text = (
        f"PR #{pr['number']} · {title}\n\n"
        f"state: {state_label}\n"
        f"head: {pr.get('head', {}).get('ref')} → base: {pr.get('base', {}).get('ref')}\n\n"
        f"{body[:1500]}"
    )
    occurred = pr.get("merged_at") or pr.get("closed_at") or pr.get("updated_at") or pr.get("created_at")
    # trust_score: merged PR 最权威 (实际合入), open PR 中, closed-unmerged 低
    authority = {"merged": 0.95, "closed": 0.75, "open": 0.70}.get(state_label, 0.70)
    confidence = 1.0 if len(body) >= 50 else (0.7 if body else 0.5)
    trust_score = round(0.7 * authority + 0.3 * confidence, 3)
    return {
        "source_type": "github",
        "source_ref": repo,
        "external_id": f"pr-{pr['number']}",
        "version": 1,
        "event_type": "pr_event",
        "occurred_at": occurred,
        "author": _author(pr.get("user")),
        "title": f"PR #{pr['number']} · {title}",
        "content": full_text,
        "content_hash": _sha256(f"pr-{pr['number']}-{state_label}-{occurred}"),
        "payload": {
            "number": pr["number"],
            "state": state_label,
            "html_url": pr.get("html_url"),
            "head_ref": pr.get("head", {}).get("ref"),
            "base_ref": pr.get("base", {}).get("ref"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": ["github", state_label, pr.get("base", {}).get("ref") or ""],
        "trust_score": trust_score,
    }


def issue_to_event(iss: dict[str, Any], repo: str) -> dict[str, Any] | None:
    """Issue → Event. 注意: GitHub API issues 列表也包含 PR (有 pull_request 字段). 跳过."""
    if iss.get("pull_request"):
        return None
    title = iss.get("title", "")
    body = iss.get("body") or ""
    state = iss.get("state")
    full_text = (
        f"Issue #{iss['number']} · {title}\n\n"
        f"state: {state}\n\n"
        f"{body[:1500]}"
    )
    occurred = iss.get("closed_at") or iss.get("updated_at") or iss.get("created_at")
    # trust_score: closed issue 通常是已确认问题 (有解决方案) 比 open 高
    authority = {"closed": 0.80, "open": 0.65}.get(state or "open", 0.65)
    confidence = 1.0 if len(body) >= 50 else (0.7 if body else 0.4)
    trust_score = round(0.7 * authority + 0.3 * confidence, 3)
    return {
        "source_type": "github",
        "source_ref": repo,
        "external_id": f"issue-{iss['number']}",
        "version": 1,
        "event_type": "issue_event",
        "occurred_at": occurred,
        "author": _author(iss.get("user")),
        "title": f"Issue #{iss['number']} · {title}",
        "content": full_text,
        "content_hash": _sha256(f"issue-{iss['number']}-{state}-{occurred}"),
        "payload": {
            "number": iss["number"],
            "state": state,
            "html_url": iss.get("html_url"),
            "labels": [lbl.get("name") for lbl in iss.get("labels", [])],
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": ["github", state] + [lbl.get("name", "") for lbl in iss.get("labels", [])],
        "trust_score": trust_score,
    }


def commit_to_event(commit: dict[str, Any], repo: str) -> dict[str, Any]:
    """Commit → Event."""
    sha = commit["sha"]
    msg = (commit.get("commit", {}).get("message") or "").strip()
    author_block = commit.get("commit", {}).get("author") or {}
    occurred = author_block.get("date") or datetime.now(timezone.utc).isoformat()
    title_line = msg.split("\n", 1)[0][:80]
    # commit 默认 authority 0.85 (实际入库的代码改动)
    authority = 0.85
    confidence = 1.0 if len(msg) >= 30 else (0.7 if msg else 0.4)
    trust_score = round(0.7 * authority + 0.3 * confidence, 3)
    return {
        "source_type": "github",
        "source_ref": repo,
        "external_id": f"commit-{sha}",
        "version": 1,
        "event_type": "commit",
        "occurred_at": occurred,
        "author": {
            "name": author_block.get("name") or "?",
            "email": author_block.get("email"),
            "external_id": (commit.get("author") or {}).get("login") if commit.get("author") else None,
        },
        "title": f"commit {sha[:7]} · {title_line}",
        "content": msg[:2000],
        "content_hash": _sha256(f"commit-{sha}"),
        "payload": {
            "sha": sha,
            "html_url": commit.get("html_url"),
            "stats": commit.get("stats"),
            "trust_components": {
                "source_authority": authority,
                "extraction_confidence": confidence,
            },
        },
        "tags": ["github", "commit"],
        "trust_score": trust_score,
    }


# ─── 拉取 ─────────────────────────────────────────────────


def fetch_prs(token: str, repo: str, since: str | None) -> list[dict[str, Any]]:
    """拉 PRs. GitHub PR API 不支持 since 过滤, 只能拉 closed/open 全部按 updated 排."""
    url = f"{GH_API}/repos/{repo}/pulls"
    # state=all, sort=updated, direction=desc; 自己 since 截断
    items = gh_paginate(url, token, state="all", sort="updated", direction="desc")
    if since:
        items = [it for it in items if (it.get("updated_at") or "") > since]
    return items


def fetch_issues(token: str, repo: str, since: str | None) -> list[dict[str, Any]]:
    """拉 Issues (GitHub API 把 PR 也算 issue, 我们的 mapper 内部过滤)."""
    url = f"{GH_API}/repos/{repo}/issues"
    items = gh_paginate(url, token, state="all", sort="updated", direction="desc",
                       since=since or None)
    return items


def fetch_commits(token: str, repo: str, since: str | None) -> list[dict[str, Any]]:
    """拉 commits (默认 default branch). since=ISO 8601."""
    url = f"{GH_API}/repos/{repo}/commits"
    return gh_paginate(url, token, since=since or None)


# ─── 投递 ─────────────────────────────────────────────────


def post_events(
    backend_url: str, project_id: str, events: list[dict[str, Any]]
) -> tuple[int, int]:
    if not events:
        return 0, 0
    url = f"{backend_url.rstrip('/')}/api/v1/projects/{project_id}/events"
    ingested = 0
    skipped = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        try:
            resp = requests.post(url, json={"events": batch}, timeout=30)
        except requests.RequestException as e:
            log.error("ingest failed: %s", e)
            continue
        if not resp.ok:
            log.error("ingest failed: %s %s", resp.status_code, resp.text[:200])
            continue
        data = resp.json()
        ingested += data.get("ingested", 0)
        skipped += data.get("skipped", 0)
    return ingested, skipped


# ─── 主循环 ───────────────────────────────────────────────


def run_once(
    token: str, repos: list[str], backend_url: str, project_id: str,
) -> dict[str, int]:
    state = load_state()
    total = {"prs": 0, "issues": 0, "commits": 0, "ingested": 0, "skipped": 0}

    for repo in repos:
        repo_state = state.setdefault(repo, {})

        # PRs
        since_prs = repo_state.get("prs")
        prs = fetch_prs(token, repo, since_prs)
        pr_events = [pr_to_event(pr, repo) for pr in prs]
        max_pr_ts = max([pr.get("updated_at") or "" for pr in prs] + [since_prs or ""]) or None

        # Issues
        since_issues = repo_state.get("issues")
        issues = fetch_issues(token, repo, since_issues)
        issue_events_raw = [issue_to_event(iss, repo) for iss in issues]
        issue_events = [e for e in issue_events_raw if e is not None]
        max_iss_ts = max([iss.get("updated_at") or "" for iss in issues] + [since_issues or ""]) or None

        # Commits
        since_commits = repo_state.get("commits")
        commits = fetch_commits(token, repo, since_commits)
        commit_events = [commit_to_event(c, repo) for c in commits]
        max_commit_ts = (
            max([c.get("commit", {}).get("author", {}).get("date") or "" for c in commits]
                + [since_commits or ""])
            or None
        )

        # 投递
        all_events = pr_events + issue_events + commit_events
        ingested, skipped = post_events(backend_url, project_id, all_events)

        # 更新水位 (用 GitHub 返回的最新 updated_at, 而非现在的时间, 避免漏)
        if max_pr_ts:
            repo_state["prs"] = max_pr_ts
        if max_iss_ts:
            repo_state["issues"] = max_iss_ts
        if max_commit_ts:
            repo_state["commits"] = max_commit_ts

        total["prs"] += len(pr_events)
        total["issues"] += len(issue_events)
        total["commits"] += len(commit_events)
        total["ingested"] += ingested
        total["skipped"] += skipped

        log.info(
            "%s: prs=%d issues=%d commits=%d → ingested=%d skipped=%d",
            repo, len(pr_events), len(issue_events), len(commit_events),
            ingested, skipped,
        )

    save_state(state)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="TokenKnows GitHub sync")
    parser.add_argument("--repo", action="append", required=True,
                        help="owner/repo, 可多次")
    # T141: default 从 env 读 (TOKENKNOWS_API_BASE / TOKENKNOWS_DEFAULT_PROJECT)
    parser.add_argument(
        "--backend",
        default=os.environ.get("TOKENKNOWS_API_BASE", "http://127.0.0.1:8002"),
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("TOKENKNOWS_DEFAULT_PROJECT", "proj-demo-001"),
    )
    parser.add_argument("--watch", action="store_true",
                        help="每 5 分钟轮询")
    parser.add_argument("--reset", action="store_true",
                        help="清空 state, 全量重推")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("state file removed, will re-fetch all")

    token = get_token()
    log.info("backend=%s project=%s repos=%s", args.backend, args.project, args.repo)

    while True:
        try:
            stats = run_once(token, args.repo, args.backend, args.project)
            log.info("scan done: %s", stats)
        except requests.RequestException as e:
            log.error("network err: %s", e)
        if not args.watch:
            break
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
