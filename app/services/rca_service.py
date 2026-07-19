"""
RCA 服务 - 根因分析核心算法
输出 Investigation Package（6 部分结构化证据链）
"""
from collections import defaultdict
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation, Alert, Incident, IncidentAlert, AssetChangeLog

SEVERITY_SCORE_MAP = {"critical": 3, "warning": 2, "info": 1}
SEV_CN = {"critical": "严重", "warning": "警告", "info": "提示"}


def analyze_incident(db: Session, incident_id: int) -> dict:
    """主入口：输出 Investigation Package 结构化 RCA 结果（6 部分）."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return {"error": "故障单不存在"}

    alert_ids = [ia.alert_id for ia in
                 db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_id).all()]
    alerts = (db.query(Alert).filter(Alert.id.in_(alert_ids)).all() if alert_ids else [])

    relations = db.query(AssetRelation).all()
    parent_map = defaultdict(list)
    child_map = defaultdict(list)
    for r in relations:
        parent_map[r.child_id].append(r.parent_id)
        child_map[r.parent_id].append(r.child_id)

    asset_alerts_map = defaultdict(list)
    for a in alerts:
        asset_alerts_map[a.asset_id or 0].append(a)

    def score_asset(aid: int, depth: int = 0) -> tuple:
        if depth > 10 or aid == 0:
            return (0.0, set())
        total = sum(SEVERITY_SCORE_MAP.get(a.severity, 1) for a in asset_alerts_map.get(aid, []))
        visited = {aid}
        for child_id in child_map.get(aid, []):
            if child_id not in visited:
                cs, cv = score_asset(child_id, depth + 1)
                total += cs * 0.5
                visited.update(cv)
        return (total, visited)

    scores = {}
    for aid in asset_alerts_map:
        if aid > 0:
            s, _ = score_asset(aid)
            scores[aid] = s

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    root_asset = None
    if ranked:
        top_id = ranked[0][0]
        if top_id > 0:
            root_asset = db.query(Asset).filter(Asset.id == top_id).first()

    involved = []
    for aid in asset_alerts_map:
        if aid > 0:
            a = db.query(Asset).filter(Asset.id == aid).first()
            if a:
                involved.append({
                    "id": a.id, "name": a.name, "ci_type": a.ci_type or "",
                    "alert_count": len(asset_alerts_map.get(aid, [])),
                    "rca_score": scores.get(aid, 0),
                })
    involved.sort(key=lambda x: -x["rca_score"])

    paths = []
    if root_asset and len(involved) > 1:
        for ia in involved[:5]:
            if ia["id"] != root_asset.id:
                path = _trace_path(parent_map, root_asset.id, ia["id"])
                if path:
                    paths.append({"from": root_asset.name, "to": ia["name"], "path": path})

    pkg = _build_investigation_package(
        db, incident, root_asset, involved, ranked, alerts, parent_map, paths
    )
    report_md = _build_markdown_report(incident, root_asset, involved, ranked, alerts, paths, pkg)

    return {
        "incident_id": incident.id,
        "incident_title": incident.title or f"故障 #{incident.id}",
        "incident_severity": incident.severity or "warning",
        "incident_status": incident.status or "open",
        "created_at": incident.created_at.strftime("%Y-%m-%d %H:%M:%S") if incident.created_at else None,
        **pkg,
        "report_md": report_md,
    }


def _build_investigation_package(db, incident, root_asset, involved, ranked, alerts, parent_map, paths=None) -> dict:
    """构建 6 部分 Investigation Package."""
    all_asset_ids = [ia["id"] for ia in involved]

    # ── 1. Facts ──────────────────────────────────────────────
    facts_alerts = [
        {
            "id": a.id,
            "metric": a.metric_name or "",
            "severity": a.severity,
            "severity_cn": SEV_CN.get(a.severity, a.severity or "告警"),
            "asset_id": a.asset_id,
            "message": (a.message or "")[:120],
            "value": a.actual_value,
            "threshold": a.threshold,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
        }
        for a in sorted(alerts, key=lambda x: -SEVERITY_SCORE_MAP.get(x.severity, 0))
    ]
    affected_scope = {a.asset_id for a in alerts if a.asset_id}
    facts = {
        "anomalies": facts_alerts,
        "affected_assets": [ia["name"] for ia in involved],
        "affected_asset_count": len(involved),
        "affected_asset_ids": list(affected_scope),
        "total_alert_count": len(alerts),
        "severity_distribution": {
            "critical": sum(1 for a in alerts if a.severity == "critical"),
            "warning": sum(1 for a in alerts if a.severity == "warning"),
            "info": sum(1 for a in alerts if a.severity == "info"),
        },
    }

    # ── 2. Timeline ─────────────────────────────────────
    try:
        incident_start = min(a.created_at for a in alerts if a.created_at)
    except ValueError:
        incident_start = datetime.now()
    incident_end = incident.created_at or datetime.now()
    duration_min = (incident_end - incident_start).total_seconds() / 60 if incident_start else 0

    change_logs = []
    if all_asset_ids:
        logs = (
            db.query(AssetChangeLog)
            .filter(AssetChangeLog.asset_id.in_(all_asset_ids))
            .filter(AssetChangeLog.created_at >= incident_start)
            .order_by(AssetChangeLog.created_at.desc())
            .limit(10).all()
        )
        change_logs = [
            {
                "asset_name": lg.asset_name or "",
                "field": lg.field or "",
                "old_value": lg.old_value or "",
                "new_value": lg.new_value or "",
                "operator": lg.operator or "system",
                "at": lg.created_at.strftime("%Y-%m-%d %H:%M:%S") if lg.created_at else None,
            }
            for lg in logs
        ]

    timeline = {
        "start": incident_start.strftime("%Y-%m-%d %H:%M:%S"),
        "end": incident_end.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_minutes": round(duration_min, 1),
        "change_events": change_logs,
        "alert_count_at_start": len(alerts),
    }

    # ── 3. Candidate Causes（按置信度排序）────────────────────────────
    candidates = []
    if root_asset and ranked:
        candidates.append({
            "rank": 1,
            "asset_id": root_asset.id,
            "asset_name": root_asset.name,
            "asset_type": root_asset.ci_type or "",
            "confidence": "high",
            "reason": "拓扑传播 RCA 评分最高 + 关联告警数最多",
            "score": round(ranked[0][1], 2),
        })
        for i, ia in enumerate(involved[1:4], start=2):
            candidates.append({
                "rank": i,
                "asset_id": ia["id"],
                "asset_name": ia["name"],
                "asset_type": ia.get("type", ""),
                "confidence": "medium" if i == 2 else "low",
                "reason": "RCA 评分次高，候选验证方向",
                "score": round(ia["rca_score"], 2),
            })
    else:
        candidates.append({
            "rank": 1,
            "asset_name": "未定位到明确根因",
            "confidence": "low",
            "reason": "资产拓扑信息不足或告警分散，建议补充拓扑关系",
            "score": 0,
        })

    # ── 4. Evidence ────────────────────────────────────
    metric_names = defaultdict(lambda: {"name": "", "count": 0, "severity": ""})
    for a in alerts:
        n = a.metric_name or "unknown"
        if n not in metric_names:
            metric_names[n] = {"name": n, "count": 0, "severity": a.severity, "asset_id": a.asset_id}
        metric_names[n]["count"] += 1
    metrics_top = sorted(metric_names.values(), key=lambda x: -x["count"])[:10]

    evidence = {
        "metrics": [{"name": m["name"], "count": m["count"], "severity": m["severity"]} for m in metrics_top],
        "topology_paths": paths,
        "asset_details": [
            {"id": ia["id"], "name": ia["name"], "type": ia.get("type", ""),
             "alert_count": ia["alert_count"], "rca_score": round(ia["rca_score"], 2)}
            for ia in involved[:5]
        ],
    }

    # ── 5. Exclusions（已排除方向）────────────────────────────
    exclusions = []
    for ia in involved[3:]:
        exclusions.append({
            "asset_name": ia["name"],
            "reason": f"RCA 评分 {round(ia['rca_score'], 1)}，传播链末梢，可能性低，建议滞后验证",
        })
    if root_asset and len(involved) <= 2:
        exclusions.append({
            "asset_name": "网络抖动 / Zone 故障",
            "reason": "多点同类告警集中于特定资产，网络泛洪概率低",
        })

    # ── 6. Next Steps ─────────────────────────────────
    next_steps = []
    if root_asset:
        next_steps.append({
            "step": 1, "action": f"检查 {root_asset.name}（IP: {root_asset.ip or '无IP'}）当前指标和告警状态",
            "target": root_asset.name, "tool": "指标监控/SSH", "urgent": True,
        })
        if change_logs:
            next_steps.append({
                "step": 2,
                "action": f"核对变更记录，最近变更: {change_logs[0]['at']} {root_asset.name} {change_logs[0]['field']}",
                "target": "变更记录", "tool": "AssetChangeLog", "urgent": True,
            })
        next_steps.append({
            "step": 3, "action": f"验证 {root_asset.name} 下游依赖服务是否受影响",
            "target": "依赖拓扑", "tool": "拓扑图/CMDB", "urgent": False,
        })
        next_steps.append({
            "step": 4, "action": "若无变更且指标持续异常，触发自动自愈工作流",
            "target": "Remediation Workflow", "tool": "自动化", "urgent": False,
        })
    else:
        next_steps.append({
            "step": 1, "action": "补充资产拓扑关系，关联父子资产",
            "target": "CMDB", "tool": "资产拓扑", "urgent": True,
        })
        next_steps.append({
            "step": 2, "action": "扩大时间窗口重新聚类分析",
            "target": "Incident", "tool": "告警聚类", "urgent": False,
        })

    return {
        "facts": facts,
        "timeline": timeline,
        "candidate_causes": candidates,
        "evidence": evidence,
        "exclusions": exclusions,
        "next_steps": next_steps,
    }


def _build_markdown_report(incident, root_asset, involved, ranked, alerts, paths, pkg: dict) -> str:
    """生成向后兼容的 Markdown 报告摘要（展示用）."""
    lines = ["## 根因分析报告\n"]

    # 故障概况
    lines.append("### 故障概况\n")
    lines.append(f"- **故障级别**: {SEV_CN.get(incident.severity, incident.severity)}")
    lines.append(f"- **关联告警**: {len(alerts)} 条")
    lines.append(f"- **涉事资产**: {len(involved)} 个\n")

    # 候选根因
    for c in pkg["candidate_causes"]:
        tag = "🔴" if c["confidence"] == "high" else "🟡" if c["confidence"] == "medium" else "⚪"
        lines.append(f"{tag} **[候选{c['rank']}] {c['asset_name']}**（置信度: {c['confidence']}）评分: {c['score']}）")
        lines.append(f"   依据: {c['reason']}\n")

    # 时间线
    tl = pkg["timeline"]
    if tl["start"]:
        lines.append("### 故障时间线\n")
        lines.append(f"- 故障窗口: {tl['start']} → {tl['end']}（持续 {tl['duration_minutes']} 分钟）")
        if tl["change_events"]:
            for cl in tl["change_events"][:5]:
                lines.append(
                    f"  - [{cl['at']}] {cl['asset_name']} {cl['field']}: {cl['old_value']} → {cl['new_value']}"
                )
        lines.append("")

    # 证据摘要
    ev = pkg["evidence"]
    if ev["metrics"]:
        top_m = ev["metrics"][0]
        lines.append(f"### 关键指标\n- 最异常指标: **{top_m['name']}**（{top_m['count']} 条告警）\n")

    # 下一步
    if pkg["next_steps"]:
        lines.append("### 建议操作\n")
        for ns in pkg["next_steps"]:
            icon = "🔴" if ns.get("urgent") else "📋"
            lines.append(f"{icon} Step{ns['step']}: {ns['action']}")
        lines.append("")

    # 排除
    if pkg["exclusions"]:
        lines.append("### 已排除方向\n")
        for ex in pkg["exclusions"]:
            lines.append(f"~~{ex['asset_name']}~~  原因: {ex['reason']}")

    return "\n".join(lines)


def _trace_path(parent_map: dict, src: int, dst: int) -> list:
    """BFS 找父子路径."""
    if src == dst:
        return [src]
    from collections import deque
    visited = {src}
    queue = deque([[src]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        for parent in parent_map.get(node, []):
            if parent == dst:
                return path + [dst]
            if parent not in visited:
                visited.add(parent)
                queue.append(path + [parent])
    return None


def analyze_pagerank(db: Session, incident_id: int = None, damping: float = 0.85, max_iter: int = 100) -> dict:
    """PageRank 根因排序（全局拓扑图，不依赖 incident_id."""
    assets = db.query(Asset).all()
    relations = db.query(AssetRelation).all()
    asset_map = {a.id: a for a in assets}
    if not assets:
        return {"error": "No assets found"}

    n = len(assets)
    id_to_idx = {a.id: i for i, a in enumerate(assets)}
    idx_to_id = {i: a.id for i, a in enumerate(assets)}
    M = np.zeros((n, n))
    for r in relations:
        if r.parent_id in id_to_idx and r.child_id in id_to_idx:
            i, j = id_to_idx[r.parent_id], id_to_idx[r.child_id]
            M[j, i] = 1.0

    col_sums = M.sum(axis=0)
    col_sums[col_sums == 0] = 1
    M_norm = M / col_sums

    rank_vec = np.ones(n) / n
    for _ in range(max_iter):
        rank_vec = (1 - damping) / n + damping * M_norm.dot(rank_vec)

    sorted_assets = sorted(
        [(idx_to_id[i], rank_vec[i]) for i in range(n)], key=lambda x: -x[1]
    )
    return {
        "ranks": [
            {"asset_id": aid, "asset_name": asset_map[aid].name,
             "pagerank": round(score, 4)}
            for aid, score in sorted_assets[:10]
        ],
        "damping": damping,
        "iterations": max_iter,
    }
