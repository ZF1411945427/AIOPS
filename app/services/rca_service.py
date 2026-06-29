from collections import defaultdict

import numpy as np
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation, Alert, Incident, IncidentAlert


def analyze_incident(db: Session, incident_id: int) -> dict:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return {"error": "鏁呴殰鍗曚笉瀛樺湪"}

    alert_ids = [ia.alert_id for ia in db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_id).all()]
    alerts = db.query(Alert).filter(Alert.id.in_(alert_ids)).all() if alert_ids else []
    relations = db.query(AssetRelation).all()

    parent_map = defaultdict(list)
    child_map = defaultdict(list)
    for r in relations:
        parent_map[r.child_id].append(r.parent_id)
        child_map[r.parent_id].append(r.child_id)

    asset_alerts = defaultdict(list)
    for a in alerts:
        aid = a.asset_id or 0
        asset_alerts[aid].append(a)

    severity_score = {"critical": 3, "warning": 2, "info": 1}

    def score_asset(aid: int, depth: int = 0) -> tuple:
        if depth > 10:
            return (0, set())
        total = 0
        for a in asset_alerts.get(aid, []):
            total += severity_score.get(a.severity, 1)
        visited = {aid}
        for child_id in child_map.get(aid, []):
            if child_id not in visited:
                child_score, child_visited = score_asset(child_id, depth + 1)
                total += child_score * 0.5
                visited.update(child_visited)
        return (total, visited)

    scores = {}
    for a in alerts:
        aid = a.asset_id or 0
        if aid not in scores:
            s, _ = score_asset(aid)
            scores[aid] = s

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    root_cause_asset = None
    if ranked:
        top_id = ranked[0][0]
        if top_id > 0:
            root_cause_asset = db.query(Asset).filter(Asset.id == top_id).first()

    involved_assets = []
    for aid in set(a.asset_id or 0 for a in alerts):
        if aid > 0:
            asset = db.query(Asset).filter(Asset.id == aid).first()
            if asset:
                involved_assets.append({
                    "id": asset.id, "name": asset.name, "type": asset.type,
                    "alert_count": len(asset_alerts.get(aid, [])),
                    "rca_score": scores.get(aid, 0),
                })

    involved_assets.sort(key=lambda x: -x["rca_score"])

    paths = []
    if root_cause_asset and len(involved_assets) > 1:
        for ia in involved_assets[:5]:
            if ia["id"] != root_cause_asset.id:
                path = _trace_path(parent_map, root_cause_asset.id, ia["id"])
                if path:
                    paths.append({"from": root_cause_asset.name, "to": ia["name"], "path": path})

    return {
        "root_cause": {
            "id": root_cause_asset.id if root_cause_asset else None,
            "name": root_cause_asset.name if root_cause_asset else "鏈煡",
            "type": root_cause_asset.type if root_cause_asset else "",
            "score": ranked[0][1] if ranked else 0,
        } if root_cause_asset else None,
        "involved_assets": involved_assets,
        "propagation_paths": paths,
        "total_alerts": len(alerts),
        "severity_distribution": {
            sev: len([a for a in alerts if a.severity == sev])
            for sev in ["info", "warning", "critical"]
        },
    }


def analyze_pagerank(db: Session, incident_id: int = None, damping: float = 0.85, max_iter: int = 100) -> dict:
    """PageRank-based root cause ranking on asset dependency graph."""
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
    for j in range(n):
        if col_sums[j] > 0:
            M[:, j] /= col_sums[j]
        else:
            M[:, j] = 1.0 / n

    teleport = np.ones(n) / n
    ranks = teleport.copy()
    for _ in range(max_iter):
        prev = ranks.copy()
        ranks = damping * M.dot(ranks) + (1 - damping) * teleport
        if np.linalg.norm(ranks - prev, 1) < 1e-6:
            break

    alert_scores = {}
    if incident_id:
        alert_ids = [ia.alert_id for ia in db.query(IncidentAlert)
                     .filter(IncidentAlert.incident_id == incident_id).all()]
        for a in db.query(Alert).filter(Alert.id.in_(alert_ids)).all() if alert_ids else []:
            aid = a.asset_id or 0
            if aid in id_to_idx:
                sev = {"critical": 3, "warning": 2, "info": 1}.get(a.severity, 1)
                alert_scores[aid] = alert_scores.get(aid, 0) + sev

    ranked = sorted([
        (idx_to_id[i], asset_map[idx_to_id[i]].name, asset_map[idx_to_id[i]].ci_type,
         float(ranks[i]), alert_scores.get(idx_to_id[i], 0))
        for i in range(n)
    ], key=lambda x: -x[3])

    return {
        "total_assets": n,
        "total_relations": len(relations),
        "damping_factor": damping,
        "iterations": max_iter,
        "ranked_assets": [
            {"id": rid, "name": name, "type": ctype,
             "pagerank": round(pr, 6), "alert_score": asc}
            for rid, name, ctype, pr, asc in ranked[:30]
        ],
    }


def _trace_path(parent_map: dict, from_id: int, to_id: int, visited: set = None) -> list | None:
    if visited is None:
        visited = set()
    if from_id == to_id:
        return [to_id]
    if from_id in visited:
        return None
    visited.add(from_id)

    for parent_id in parent_map.get(from_id, []):
        path = _trace_path(parent_map, parent_id, to_id, visited)
        if path:
            return [from_id] + path

    for parent_id in parent_map.get(to_id, []):
        path = _trace_path(parent_map, from_id, parent_id, visited)
        if path:
            return path + [to_id]
    return None

