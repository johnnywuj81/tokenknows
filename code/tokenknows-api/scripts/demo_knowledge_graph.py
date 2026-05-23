"""端到端 KG demo 数据 seeder.

绕过 LLM (无需 ANTHROPIC_API_KEY), 直接构造一个完整的"故障复盘"知识图谱:
  - 11 个节点 (3 人物 + 3 事件 + 3 概念 + 2 产物)
  - 15 条边 (含 1 个 contradicts 红线 + 2 个 caused_by 黄线)
  - 跑 assess 风格后处理 (entity 注册, SVG + PNG 缩略图)
  - 另 seed 1 个 'weekly_report' asset 让列表对照

用法:
    cd code/tokenknows-api
    .venv/bin/python scripts/demo_knowledge_graph.py

跑完后浏览器:
    http://localhost:5173/projects/demo-project/documents/demo-kg-001
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.persistence import store as store_module
from app.persistence.store import SqliteStore
from app.schemas.asset import Asset, AssetMetrics, Chapter
from app.services import generation_service
from app.services.knowledge_graph import entity_registry
from app.services.knowledge_graph.thumbnail import render_kg_svg
from app.services.knowledge_graph.thumbnail_png import render_kg_png_b64


PROJECT_ID = "demo-project"
ASSET_ID = "demo-kg-001"
CHAPTER_ID = "ch-demo-kg-001"

NODES = [
    # ── 人物 (warning 黄) ──
    {
        "id": "n_alice", "type": "person", "label": "Alice",
        "summary": "前端组长 · 推动响应式重构 · 故障期间值班",
        "properties": {"im_user_id": "alice@example.com"},
        "source_event_ids": ["e_pr127", "e_postmortem_msg"],
        "trust_score": 0.95,
        "span_anchor": {"char_offset": 0},
    },
    {
        "id": "n_bob", "type": "person", "label": "Bob",
        "summary": "后端工程师 · 维护 API gateway · 提了 bug 报告",
        "properties": {"im_user_id": "bob@example.com"},
        "source_event_ids": ["e_bug_report"],
        "trust_score": 0.90,
        "span_anchor": {"char_offset": 120},
    },
    {
        "id": "n_carol", "type": "person", "label": "Carol",
        "summary": "SRE · 处理生产告警 · 主持复盘会",
        "properties": {"im_user_id": "carol@example.com"},
        "source_event_ids": ["e_alert", "e_postmortem_msg"],
        "trust_score": 0.92,
        "span_anchor": {"char_offset": 240},
    },
    # ── 事件 (info 蓝) ──
    {
        "id": "n_outage", "type": "event", "label": "Gateway 504 故障",
        "summary": "2026-05-19 18:42 起持续 23 分钟; 影响 P0 用户登录",
        "properties": {"duration_min": 23, "severity": "P0"},
        "source_event_ids": ["e_alert"],
        "trust_score": 0.99,
        "span_anchor": {"char_offset": 380},
    },
    {
        "id": "n_postmortem", "type": "event", "label": "故障复盘会议",
        "summary": "2026-05-20 上午 · Alice/Bob/Carol 参加 · 输出 ADR-042",
        "properties": {},
        "source_event_ids": ["e_postmortem_msg"],
        "trust_score": 0.93,
        "span_anchor": {"char_offset": 520},
    },
    {
        "id": "n_pr127_merge", "type": "event", "label": "PR #127 修复合并",
        "summary": "2026-05-21 · gateway timeout 提高 + retry 加 jitter",
        "properties": {"pr_id": 127},
        "source_event_ids": ["e_pr127"],
        "trust_score": 0.96,
        "span_anchor": {"char_offset": 680},
    },
    # ── 概念 (success 绿) ──
    {
        "id": "n_timeout_strategy", "type": "concept",
        "label": "Gateway 超时策略",
        "summary": "前端调后端的 fail-fast 阈值 + 重试上限 + jitter 算法",
        "properties": {},
        "source_event_ids": ["e_postmortem_msg", "e_pr127"],
        "trust_score": 0.88,
        "span_anchor": {"char_offset": 820},
    },
    {
        "id": "n_p0_sla", "type": "concept",
        "label": "P0 服务等级 SLA",
        "summary": "可用性 ≥ 99.95% · MTTR ≤ 30min · 触发立即告警",
        "properties": {},
        "source_event_ids": ["e_alert"],
        "trust_score": 0.90,
        "span_anchor": {"char_offset": 960},
    },
    {
        "id": "n_retry_jitter", "type": "concept",
        "label": "重试 + Exponential Jitter",
        "summary": "避免雪崩的标准做法 · base × 2^n × rand(0.5, 1.5)",
        "properties": {},
        "source_event_ids": ["e_pr127"],
        "trust_score": 0.86,
        "span_anchor": {"char_offset": 1100},
    },
    # ── 产物 (danger 红) ──
    {
        "id": "n_adr042", "type": "artifact", "label": "ADR-042",
        "summary": "Gateway 超时策略决策记录 · status=accepted",
        "properties": {"path": "docs/adr/042-gateway-timeout.md"},
        "source_event_ids": ["e_postmortem_msg"],
        "trust_score": 0.94,
        "span_anchor": {"char_offset": 1240},
    },
    {
        "id": "n_runbook", "type": "artifact", "label": "Gateway Runbook",
        "summary": "降级流程 + 告警 owner + 临时止血脚本路径",
        "properties": {"path": "docs/runbooks/gateway.md"},
        "source_event_ids": ["e_postmortem_msg"],
        "trust_score": 0.85,
        "span_anchor": {"char_offset": 1380},
    },
]

# 故事线: outage → caused_by → 超时策略缺失;  postmortem mentions outage;
# Alice authored PR; PR depends_on 重试策略; ADR documents 决策;
# 1 个 contradicts: 旧策略 vs 新策略 (n_timeout_strategy contradicts n_retry_jitter? 简化)
EDGES = [
    # 故障 → 复盘
    {"id": "e_o_pm", "source": "n_outage", "target": "n_postmortem",
     "type": "caused_by", "label": "导致召开",
     "weight": 3, "source_event_ids": ["e_postmortem_msg"]},
    # 复盘 → ADR
    {"id": "e_pm_adr", "source": "n_postmortem", "target": "n_adr042",
     "type": "mentions", "label": "输出",
     "weight": 3, "source_event_ids": ["e_postmortem_msg"]},
    # 复盘 → Runbook
    {"id": "e_pm_rb", "source": "n_postmortem", "target": "n_runbook",
     "type": "mentions", "label": "输出",
     "weight": 2, "source_event_ids": ["e_postmortem_msg"]},
    # Carol 主持复盘
    {"id": "e_carol_pm", "source": "n_postmortem", "target": "n_carol",
     "type": "authored_by", "label": "主持",
     "weight": 3, "source_event_ids": ["e_postmortem_msg"]},
    # 故障原因
    {"id": "e_o_to", "source": "n_outage", "target": "n_timeout_strategy",
     "type": "caused_by", "label": "根因",
     "weight": 4, "source_event_ids": ["e_alert"]},
    # 故障 与 SLA
    {"id": "e_o_sla", "source": "n_outage", "target": "n_p0_sla",
     "type": "mentions", "label": "违反",
     "weight": 2, "source_event_ids": ["e_alert"]},
    # Carol 处理告警
    {"id": "e_c_o", "source": "n_outage", "target": "n_carol",
     "type": "authored_by", "label": "处理",
     "weight": 3, "source_event_ids": ["e_alert"]},
    # Bob 提 bug
    {"id": "e_b_o", "source": "n_outage", "target": "n_bob",
     "type": "mentions", "label": "提报告",
     "weight": 2, "source_event_ids": ["e_bug_report"]},
    # Alice PR
    {"id": "e_alice_pr", "source": "n_pr127_merge", "target": "n_alice",
     "type": "authored_by", "label": "作者",
     "weight": 3, "source_event_ids": ["e_pr127"]},
    # PR depends_on 重试策略
    {"id": "e_pr_retry", "source": "n_pr127_merge", "target": "n_retry_jitter",
     "type": "depends_on", "label": "采用",
     "weight": 3, "source_event_ids": ["e_pr127"]},
    # PR 修了 timeout_strategy
    {"id": "e_pr_to", "source": "n_pr127_merge", "target": "n_timeout_strategy",
     "type": "mentions", "label": "修复",
     "weight": 3, "source_event_ids": ["e_pr127"]},
    # ADR 引用 重试 + 超时
    {"id": "e_adr_retry", "source": "n_adr042", "target": "n_retry_jitter",
     "type": "mentions", "label": "引用",
     "weight": 2, "source_event_ids": ["e_postmortem_msg"]},
    {"id": "e_adr_to", "source": "n_adr042", "target": "n_timeout_strategy",
     "type": "mentions", "label": "决策",
     "weight": 3, "source_event_ids": ["e_postmortem_msg"]},
    # 矛盾红线: 旧 timeout strategy (无 jitter) ↔ 新 retry_jitter (带 jitter)
    {"id": "e_conflict", "source": "n_timeout_strategy", "target": "n_retry_jitter",
     "type": "contradicts", "label": "旧策略 vs 新策略",
     "weight": 4, "source_event_ids": ["e_postmortem_msg", "e_pr127"]},
    # Alice 跟 Bob related (同小组)
    {"id": "e_ab", "source": "n_alice", "target": "n_bob",
     "type": "related_to", "label": "同组",
     "weight": 1, "source_event_ids": []},
]


def main() -> None:
    # 1. Init persistence — 写到 backend 启动时默认加载的 state.sqlite
    # (与 backend 用 SqliteStore.bootstrap() 加载路径一致)
    db_path = Path(__file__).resolve().parent.parent / "data" / "state.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = SqliteStore(db_path)
    db._apply_schema()
    store_module._db = db

    # 清空可能存在的旧数据 (内存 + sqlite 中的同 id)
    generation_service._assets.clear()
    generation_service._chapters.clear()
    entity_registry.clear_for_test()
    # 删旧的 demo asset (如果存在)
    try:
        db.delete_asset(ASSET_ID)
        db.delete_asset("demo-wr-001")
    except Exception:  # noqa: BLE001
        pass

    now = datetime.now(timezone.utc)

    # 2. Seed KG asset
    asset = Asset(
        id=ASSET_ID,
        project_id=PROJECT_ID,
        type="knowledge_graph",
        title="2026 Q2 Gateway 故障复盘 (Demo)",
        status="draft",
        current_version=1,
        template_id=None,
        created_by="alice",
        approval_state="pending",
        redaction_state="all_confirmed",
        metrics=AssetMetrics(
            coverage=0.88,
            citation_density=0.72,
            slop_score=0.05,
            similarity=0.21,
            consistency_score=0.90,
        ),
        created_at=now,
        updated_at=now,
    )
    generation_service._assets[ASSET_ID] = asset

    # 3. 构造 layout + 渲染 SVG/PNG
    layout = {
        "schema_version": "kg.v1",
        "nodes": NODES,
        "edges": EDGES,
        "layout_hints": {"algorithm": "dagre", "rankdir": "LR"},
    }
    layout["thumbnail_svg"] = render_kg_svg(layout)
    png_b64 = render_kg_png_b64(layout)
    if png_b64:
        layout["thumbnail_png_b64"] = png_b64

    content_lines = ["# 实体关系图谱 — 节点索引", ""]
    for n in NODES:
        content_lines.append(f"<!-- node:{n['id']} -->")
        content_lines.append(f"## {n['label']} ({n['type']})")
        if n.get("summary"):
            content_lines.append(n["summary"])
        content_lines.append("")
    content_md = "\n".join(content_lines)

    chapter = Chapter(
        id=CHAPTER_ID,
        asset_id=ASSET_ID,
        order_index=0,
        title="实体关系图谱",
        content=content_md,
        layout=layout,
    )
    generation_service._chapters[ASSET_ID] = [chapter]

    # 4. 注册 entity_registry
    entity_registry.register_asset_nodes(
        project_id=PROJECT_ID,
        asset_id=ASSET_ID,
        chapter_id=CHAPTER_ID,
        nodes=NODES,
    )

    # 5. 写一个 weekly_report 用于对照展示 list page
    wr_id = "demo-wr-001"
    wr = Asset(
        id=wr_id,
        project_id=PROJECT_ID,
        type="weekly_report",
        title="2026 Q2 W21 周报 (Demo)",
        status="draft",
        current_version=1,
        template_id=None,
        created_by="alice",
        approval_state="pending",
        redaction_state="all_confirmed",
        metrics=AssetMetrics(
            coverage=0.82, citation_density=0.61, slop_score=0.12,
            similarity=0.35,
        ),
        created_at=now,
        updated_at=now,
    )
    generation_service._assets[wr_id] = wr

    # 6. 写 SVG 文件到 /tmp 供直接预览
    svg_out = Path("/tmp/kg_demo.svg")
    svg_out.write_text(layout["thumbnail_svg"], encoding="utf-8")

    # 7. 落 sqlite
    generation_service._persist_asset(ASSET_ID)
    generation_service._persist_asset(wr_id)

    print("─" * 60)
    print("✅ KG demo 数据已 seed")
    print("─" * 60)
    print(f"  Project:   {PROJECT_ID}")
    print(f"  KG Asset:  {ASSET_ID}")
    print(f"  Chapter:   {CHAPTER_ID}")
    print(f"  节点数:    {len(NODES)} (3 person + 3 event + 3 concept + 2 artifact)")
    print(f"  边数:      {len(EDGES)} (含 1 contradicts 红线 + 2 caused_by 黄线)")
    print(f"  实体注册:  {len(entity_registry._entities)} (跨 KG asset 可合并)")
    print(f"  SVG 预览:  {svg_out}  (直接浏览器打开)")
    print(f"  SQLite:    {db_path}")
    print()
    print("🚀 启动服务后访问:")
    print(f"  Backend:   uvicorn app.main:app --reload --port 8000")
    print(f"  Frontend:  cd ../tokenknows-web && npm run dev")
    print(f"  浏览器:    http://localhost:5173/projects/{PROJECT_ID}/documents/{ASSET_ID}")
    print(f"  API:       curl http://localhost:8000/api/v1/assets/{ASSET_ID}")
    print("─" * 60)


if __name__ == "__main__":
    main()
