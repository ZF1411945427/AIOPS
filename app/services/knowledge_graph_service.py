from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation, Alert, KnowledgeBase, AlertKbLink, Runbook


# CI type → color mapping for the dependency graph
CI_COLORS = {
    "server": "#3b82f6",
    "virtual_machine": "#06b6d4",
    "vm": "#06b6d4",
    "container": "#f59e0b",
    "pod": "#f97316",
    "service": "#22c55e",
    "database": "#8b5cf6",
    "middleware": "#ec4899",
    "storage": "#14b8a6",
    "network": "#64748b",
    "cluster": "#6366f1",
    "kubernetes_cluster": "#6366f1",
    "namespace": "#a78bfa",
    "deployment": "#34d399",
    "node": "#94a3b8",
    "application": "#f472b6",
    "runbook": "#14b8a6",
}
DEFAULT_COLOR = "#64748b"


def get_dependency_graph(db: Session):
    assets = db.query(Asset).all()
    relations = db.query(AssetRelation).all()
    runbooks = db.query(Runbook).all()

    # Count active alerts per asset
    active_alerts_count = {}
    for row in db.query(Alert.asset_id, func.count(Alert.id)).filter(
        Alert.status.in_(["triggered", "acknowledged"])
    ).group_by(Alert.asset_id).all():
        active_alerts_count[row[0]] = row[1]

    asset_map = {a.id: a for a in assets}
    node_set = set()
    edge_list = []

    # Collect nodes that have relations + edges
    for rel in relations:
        if rel.parent_id in asset_map and rel.child_id in asset_map:
            edge_list.append({
                "source": f"asset_{rel.parent_id}",
                "target": f"asset_{rel.child_id}",
                "relation": rel.relation_type,
            })
            node_set.update([f"asset_{rel.parent_id}", f"asset_{rel.child_id}"])

    # Also use parent_id field from Asset as edges
    for a in assets:
        if a.parent_id and a.parent_id in asset_map:
            key = f"asset_{a.id}"
            pkey = f"asset_{a.parent_id}"
            edge_list.append({
                "source": pkey,
                "target": key,
                "relation": "parent",
            })
            node_set.update([key, pkey])

    # Include isolated orphans only if total graph is small
    if len(node_set) < 20:
        for a in assets:
            key = f"asset_{a.id}"
            if key not in node_set:
                node_set.add(key)

    nodes = []
    for aid, a in asset_map.items():
        key = f"asset_{a.id}"
        if key in node_set:
            color = CI_COLORS.get(a.ci_type, DEFAULT_COLOR)
            nodes.append({
                "id": key,
                "label": a.name,
                "type": a.ci_type,
                "status": a.status,
                "ip": a.ip,
                "alert_count": active_alerts_count.get(a.id, 0),
                "color": color,
                "asset_id": a.id,
            })

    # Add Runbook nodes and connect to matching assets
    for rb in runbooks:
        rb_key = f"runbook_{rb.id}"
        nodes.append({
            "id": rb_key,
            "label": rb.title,
            "type": "runbook",
            "status": rb.severity or "warning",
            "ip": "",
            "alert_count": 0,
            "color": CI_COLORS["runbook"],
            "category": rb.category or "",
            "asset_type": rb.asset_type or "",
            "tags": rb.tags or "",
        })

        # Connect runbook to matching assets by asset_type
        if rb.asset_type:
            for a in assets:
                if a.ci_type and a.ci_type.lower() == rb.asset_type.lower():
                    a_key = f"asset_{a.id}"
                    edge_list.append({
                        "source": rb_key,
                        "target": a_key,
                        "relation": "covers",
                    })
                    node_set.add(a_key)
                    node_set.add(rb_key)

    return {"nodes": nodes, "edges": edge_list}


def recommend_kb_for_alert(db: Session, alert, limit: int = 5):
    kbs = db.query(KnowledgeBase).all()
    scored = []
    for entry in kbs:
        score = 0
        if alert.metric_name and entry.tags:
            if alert.metric_name in entry.tags:
                score += 3
        if alert.severity == getattr(entry, "severity", None):
            score += 2
        if alert.asset_id and getattr(entry, "asset_type", None):
            asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
            if asset and asset.ci_type == entry.asset_type:
                score += 2
        if entry.symptom and alert.message:
            common = len(set(entry.symptom) & set(alert.message))
            score += common / max(len(entry.symptom), 1) * 5
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:limit]]


def record_rca_result(db: Session, incident_id: int, rca_result: dict, severity: str = "warning") -> int:
    """将 RCA 分析结果自动沉淀为知识库条目，下次同类告警优先推荐."""
    root = rca_result.get("root_cause") or {}
    involved = rca_result.get("involved_assets") or []
    if not root or not root.get("name"):
        return 0

    title = f"【自动沉淀】故障 #{incident_id} 根因: {root['name']}"
    symptom_parts = []
    for a in involved[:3]:
        symptom_parts.append(f"资产 {a['name']} 告警评分 {a['rca_score']}")
    symptom = f"关联 {len(involved)} 个资产；" + "；".join(symptom_parts)
    root_cause = f"根因资产: {root['name']}（类型: {root.get('type', '未知')}，RCA评分: {root.get('score', 0)}）"
    tags = root.get("type", "") or ""

    existing = db.query(KnowledgeBase).filter(
        KnowledgeBase.title == title
    ).first()
    if existing:
        existing.root_cause = root_cause
        existing.updated_at = func.now()
        db.commit()
        return existing.id

    kb = KnowledgeBase(
        title=title,
        symptom=symptom,
        root_cause=root_cause,
        solution="",
        tags=tags,
        severity=severity,
        asset_type=root.get("type", "") or "",
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb.id


def get_similar_rca(db: Session, metric_name: str = "", asset_type: str = "", severity: str = "", limit: int = 5) -> list:
    """查找同类历史 RCA 结果，辅助新告警根因推荐."""
    q = db.query(KnowledgeBase).filter(KnowledgeBase.root_cause != "")
    if metric_name:
        q = q.filter(KnowledgeBase.symptom.ilike(f"%{metric_name}%"))
    if asset_type:
        q = q.filter(KnowledgeBase.asset_type == asset_type)
    if severity:
        q = q.filter(KnowledgeBase.severity == severity)
    items = q.order_by(KnowledgeBase.updated_at.desc()).limit(limit).all()
    return [{
        "id": kb.id,
        "title": kb.title,
        "root_cause": kb.root_cause,
        "symptom": kb.symptom,
        "asset_type": kb.asset_type,
        "updated_at": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S") if kb.updated_at else None,
    } for kb in items]
