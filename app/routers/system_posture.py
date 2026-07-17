from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, text
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Asset, Alert, Incident

router = APIRouter(prefix="/api/system/posture", tags=["system_posture"])


def _build_systems(db):
    systems = []
    clusters = [c[0] for c in db.query(distinct(Asset.k8s_cluster)).filter(
        Asset.k8s_cluster != "", Asset.k8s_cluster != None).all() if c[0]]
    for cluster in clusters:
        systems.append({
            "system_key": "k8s_" + cluster,
            "system_name": cluster,
            "domain": "Kubernetes",
            "environment": "prod",
            "type": "k8s_cluster",
            "filter": {"k8s_cluster": cluster},
        })
    types = db.query(Asset.ci_type, func.count(Asset.id).label("cnt")).filter(
        (Asset.k8s_cluster == "") | (Asset.k8s_cluster == None)
    ).group_by(Asset.ci_type).having(func.count(Asset.id) >= 2).order_by(text("cnt desc")).all()
    domain_map = {
        "server": "基础设施", "virtual_machine": "基础设施", "vm": "基础设施",
        "database": "数据库", "middleware": "中间件",
        "network": "网络", "storage": "存储",
        "container": "容器", "docker": "容器",
        "loadbalancer": "负载均衡",
    }
    for t, cnt in types:
        systems.append({
            "system_key": "type_" + t,
            "system_name": t + " (" + str(cnt) + ")",
            "domain": domain_map.get(t, "其他"),
            "environment": "prod",
            "type": "asset_type",
            "filter": {"type": t},
        })
    return systems


def _collect_asset_ids(db, systems):
    """为每个 system 收集 asset_ids，返回 dict[system_key, list[asset_id]]"""
    result = {}
    for sys in systems:
        filt = sys.get("filter")
        if "k8s_cluster" in filt:
            ids = [r[0] for r in db.query(Asset.id).filter(
                Asset.k8s_cluster == filt["k8s_cluster"]).all()]
        elif "type" in filt:
            ids = [r[0] for r in db.query(Asset.id).filter(
                Asset.ci_type == filt["type"]).all()]
        else:
            ids = []
        result[sys["system_key"]] = ids
    return result


def _batch_alert_incident_counts(db, all_asset_ids, day_start, day_end):
    """批量查询所有 asset 在时间范围内的每日告警/故障数"""
    alert_by_day_asset = {}
    incident_by_day_asset = {}
    if not all_asset_ids:
        return alert_by_day_asset, incident_by_day_asset

    rows = db.query(
        func.date(Alert.created_at).label("day"),
        Alert.asset_id,
        func.count(Alert.id).label("cnt")
    ).filter(
        Alert.asset_id.in_(all_asset_ids),
        Alert.created_at >= day_start,
        Alert.created_at < day_end
    ).group_by(func.date(Alert.created_at), Alert.asset_id).all()
    for day_str, asset_id, cnt in rows:
        alert_by_day_asset[(day_str, asset_id)] = cnt

    rows = db.query(
        func.date(Incident.created_at).label("day"),
        Incident.asset_id,
        func.count(Incident.id).label("cnt")
    ).filter(
        Incident.asset_id.in_(all_asset_ids),
        Incident.created_at >= day_start,
        Incident.created_at < day_end
    ).group_by(func.date(Incident.created_at), Incident.asset_id).all()
    for day_str, asset_id, cnt in rows:
        incident_by_day_asset[(day_str, asset_id)] = cnt

    return alert_by_day_asset, incident_by_day_asset


def _sla_result(online_count, total, day_alerts, day_incidents):
    uptime_rate = online_count / total * 100 if total > 0 else 0
    sla_value = max(0, min(100, uptime_rate - day_alerts * 0.5 - day_incidents * 5))
    health_score = int(sla_value)
    status = "healthy" if sla_value >= 99 else "warning" if sla_value >= 95 else "critical"
    return {
        "sla_value": round(sla_value, 3),
        "health_score": health_score,
        "status": status,
        "alerts": day_alerts,
        "incidents": day_incidents,
    }


@router.get("")
def get_posture(days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db)):
    now = datetime.now()
    start = now - timedelta(days=days)
    systems = _build_systems(db)
    sys_asset_map = _collect_asset_ids(db, systems)

    all_ids = list(set(aid for ids in sys_asset_map.values() for aid in ids))
    alert_batch, incident_batch = _batch_alert_incident_counts(db, all_ids, start, now)

    online_set = set()
    if all_ids:
        online_set = set(r[0] for r in db.query(Asset.id).filter(
            Asset.id.in_(all_ids), Asset.status == "online").all())
    online_map = {sk: sum(1 for aid in aids if aid in online_set)
                  for sk, aids in sys_asset_map.items()}

    result_systems = []
    for sys in systems:
        sk = sys["system_key"]
        asset_ids = sys_asset_map.get(sk, [])
        total = len(asset_ids)
        online = online_map.get(sk, 0)

        total_alerts = sum(v for (d, aid), v in alert_batch.items() if aid in asset_ids)
        total_incidents = sum(v for (d, aid), v in incident_batch.items() if aid in asset_ids)

        r = _sla_result(online, total, total_alerts, total_incidents)
        entry = {
            "system_key": sk,
            "system_name": sys["system_name"],
            "domain": sys["domain"],
            "environment": sys["environment"],
            "status": r["status"],
            "sla_value": r["sla_value"],
            "health_score": r["health_score"],
            "alerts_count": r["alerts"],
            "incidents_count": r["incidents"],
        }
        result_systems.append(entry)

    return JSONResponse({
        "days": days,
        "start": start.strftime("%Y-%m-%d"),
        "end": now.strftime("%Y-%m-%d"),
        "summary": {
            "healthy": sum(1 for s in result_systems if s["status"] == "healthy"),
            "warning": sum(1 for s in result_systems if s["status"] == "warning"),
            "critical": sum(1 for s in result_systems if s["status"] == "critical"),
            "unknown": sum(1 for s in result_systems if s["status"] == "unknown"),
        },
        "systems": result_systems,
    })


@router.get("/heatmap")
def get_heatmap(days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db)):
    now = datetime.now()
    start = now - timedelta(days=days)
    systems = _build_systems(db)
    sys_asset_map = _collect_asset_ids(db, systems)

    all_ids = list(set(aid for ids in sys_asset_map.values() for aid in ids))
    alert_batch, incident_batch = _batch_alert_incident_counts(db, all_ids, start, now)

    online_set = set()
    if all_ids:
        online_set = set(r[0] for r in db.query(Asset.id).filter(
            Asset.id.in_(all_ids), Asset.status == "online").all())
    online_map = {sk: sum(1 for aid in aids if aid in online_set)
                  for sk, aids in sys_asset_map.items()}

    date_labels = []
    for i in range(days - 1, -1, -1):
        date_labels.append((now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0))

    result = []
    for sys in systems:
        sk = sys["system_key"]
        asset_ids = sys_asset_map.get(sk, [])
        total = len(asset_ids)
        online = online_map.get(sk, 0)
        cells = []
        for ds in date_labels:
            day_str = ds.strftime("%Y-%m-%d")
            day_alerts = sum(alert_batch.get((day_str, aid), 0) for aid in asset_ids)
            day_incidents = sum(incident_batch.get((day_str, aid), 0) for aid in asset_ids)
            r = _sla_result(online, total, day_alerts, day_incidents)
            cells.append({
                "day": day_str,
                "sla_value": r["sla_value"],
                "health_score": r["health_score"],
                "status": r["status"],
                "alerts": r["alerts"],
                "incidents": r["incidents"],
            })
        result.append({
            "system_key": sk,
            "system_name": sys["system_name"],
            "cells": cells,
        })
    return JSONResponse(result)
