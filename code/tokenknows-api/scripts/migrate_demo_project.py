"""T127 · 把 demo-project 的资产迁到 proj-demo-001.

背景:
    MCP plugin 默认项目 (demo-project) 与 web UI 看的项目 (proj-demo-001)
    是两个独立 project_id, 导致用户通过 plugin 蒸馏的文档在 web UI 看不到.

迁移内容 (假定 backend 已停):
    - assets 表 (column project_id + json blob 内 project_id)
    - events 表 (column project_id)
    - 其它表已确认 demo-project 行数为 0

后置:
    - entity_registry 是 in-memory store, backend 重启时根据 chapter.layout
      自动重建, 不需要手动迁
    - publish_records 通过 asset_id 关联, 自动跟随

幂等: 重复跑无副作用 (只匹配 project_id='demo-project' 的行).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

OLD = "demo-project"
NEW = "proj-demo-001"

DB_PATH = Path(__file__).parent.parent / "data" / "state.sqlite"


def main() -> int:
    if not DB_PATH.exists():
        print(f"!! db not found: {DB_PATH}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── pre-flight ───────────────────────────────────────────────
    pre_assets = cur.execute(
        "SELECT COUNT(*) FROM assets WHERE project_id = ?", (OLD,)
    ).fetchone()[0]
    pre_events = cur.execute(
        "SELECT COUNT(*) FROM events WHERE project_id = ?", (OLD,)
    ).fetchone()[0]
    print(f"pre-flight: {pre_assets} assets · {pre_events} events to migrate")
    if pre_assets == 0 and pre_events == 0:
        print("nothing to do, exit 0")
        return 0

    # ── assets: column + json blob ───────────────────────────────
    rows = cur.execute(
        "SELECT id, json FROM assets WHERE project_id = ?", (OLD,)
    ).fetchall()
    print(f"\n[assets] rewriting {len(rows)} rows (col + json)")
    for r in rows:
        try:
            blob = json.loads(r["json"])
        except json.JSONDecodeError as e:
            print(f"  !! {r['id']} json decode failed: {e}", file=sys.stderr)
            return 3
        if blob.get("project_id") == OLD:
            blob["project_id"] = NEW
        cur.execute(
            "UPDATE assets SET project_id = ?, json = ? WHERE id = ?",
            (NEW, json.dumps(blob, ensure_ascii=False), r["id"]),
        )
        print(f"  ✓ {r['id']} ({blob.get('type'):>20}) {blob.get('title','')[:50]}")

    # ── events: column + json blob; UNIQUE(project_id, content_hash) 撞了就
    # 删 OLD 的副本 (NEW 项目下已有同样 content, 不需要重复) ──
    rows = cur.execute(
        "SELECT id, json, content_hash FROM events WHERE project_id = ?",
        (OLD,),
    ).fetchall()
    print(f"\n[events] rewriting {len(rows)} rows")
    migrated = 0
    deduped = 0
    for r in rows:
        try:
            blob = json.loads(r["json"])
        except json.JSONDecodeError:
            blob = None
        if blob and blob.get("project_id") == OLD:
            blob["project_id"] = NEW
            new_json = json.dumps(blob, ensure_ascii=False)
        else:
            new_json = r["json"]
        try:
            cur.execute(
                "UPDATE events SET project_id = ?, json = ? WHERE id = ?",
                (NEW, new_json, r["id"]),
            )
            migrated += 1
        except sqlite3.IntegrityError:
            # NEW 项目下已有同 content_hash → 删 OLD 副本即可
            cur.execute("DELETE FROM events WHERE id = ?", (r["id"],))
            deduped += 1
        if (migrated + deduped) % 5000 == 0:
            print(f"  · {migrated + deduped}/{len(rows)}  (migrated={migrated} deduped={deduped})")
    print(f"  ✓ done: migrated={migrated}, deduped={deduped}")

    conn.commit()

    # ── post verify ───────────────────────────────────────────────
    leftover_a = cur.execute(
        "SELECT COUNT(*) FROM assets WHERE project_id = ?", (OLD,)
    ).fetchone()[0]
    leftover_e = cur.execute(
        "SELECT COUNT(*) FROM events WHERE project_id = ?", (OLD,)
    ).fetchone()[0]
    new_a = cur.execute(
        "SELECT COUNT(*) FROM assets WHERE project_id = ?", (NEW,)
    ).fetchone()[0]
    new_e = cur.execute(
        "SELECT COUNT(*) FROM events WHERE project_id = ?", (NEW,)
    ).fetchone()[0]
    print()
    print(f"post-verify · {OLD}: assets={leftover_a} events={leftover_e}")
    print(f"post-verify · {NEW}: assets={new_a} events={new_e}")

    if leftover_a or leftover_e:
        print("!! leftover rows found, migration incomplete", file=sys.stderr)
        return 4

    print(f"\n✓ migration done · backend 重启即生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
