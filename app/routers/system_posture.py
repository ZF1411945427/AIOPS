from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, text
from datetime import datetime, timedelta
from app.database import get_db
from app.models import Asset, Alert, Incident

router = APIRouter(prefix="/api/system/posture", tags=["system_posture"])


def _get_asset_ids_and_total(base_q):
    rows = base_q.with_entities(Asset.id).all()
    ids = [r[0] for r in rows]
    return ids, len(ids)


def _compute_day_sla(db, cluster, day_start, day_end):
    base_q = db.query(Asset).filter(Asset.k8s_cluster == cluster)
    asset_ids, total = _get_asset_ids_and_total(base_q)
    if total == 0:
        return None
    online = base_q.filter(Asset.status == "online").count()
    alerts = _count_alerts(db, asset_ids, day_start, day_end)
    incidents = _count_incidents(db, asset_ids, day_start, day_end)
    return _sla_result(online, total, alerts, incidents)


def _compute_day_sla_by_filter(db, base_q, day_start, day_end):
    asset_ids, total = _get_asset_ids_and_total(base_q)
    if total == 0:
        return None
    online = base_q.filter(Asset.status == "online").count()
    alerts = _count_alerts(db, asset_ids, day_start, day_end)
    incidents = _count_incidents(db, asset_ids, day_start, day_end)
    return _sla_result(online, total, alerts, incidents)


def _count_alerts(db, asset_ids, day_start, day_end):
    if not asset_ids:
        return 0
    return db.query(func.count(Alert.id)).filter(
        Alert.asset_id.in_(asset_ids),
        Alert.created_at >= day_start,
        Alert.created_at < day_end
    ).scalar() or 0


def _count_incidents(db, asset_ids, day_start, day_end):
    if not asset_ids:
        return 0
    return db.query(func.count(Incident.id)).filter(
        Incident.asset_id.in_(asset_ids),
        Incident.created_at >= day_start,
        Incident.created_at < day_end
    ).scalar() or 0


def _sla_result(online, total, alerts, incidents):
    uptime_rate = online / total * 100
    sla_value = max(0, min(100, uptime_rate - alerts * 0.5 - incidents * 5))
    health_score = int(sla_value)
    status = "healthy" if sla_value >= 99 else "warning" if sla_value >= 95 else "critical"
    return {
        "sla_value": round(sla_value, 3),
        "health_score": health_score,
        "status": status,
        "alerts": alerts,
        "incidents": incidents,
    }


def _build_systems(db):
    now = datetime.now()
    systems = []

    # 1. Group by k8s_cluster
    clusters = [c[0] for c in db.query(distinct(Asset.k8s_cluster)).filter(
        Asset.k8s_cluster != "", Asset.k8s_cluster != None).all() if c[0]]
    for cluster in clusters:
        base_q = db.query(Asset).filter(Asset.k8s_cluster == cluster)
        systems.append({
            "system_key": "k8s_" + cluster,
            "system_name": cluster,
            "domain": "Kubernetes",
            "environment": "prod",
            "type": "k8s_cluster",
            "filter": {"k8s_cluster": cluster},
        })

    # 2. Group by Asset.type for non-K8s assets (those without k8s_cluster)
    types = db.query(Asset.type, func.count(Asset.id).label("cnt")).filter(
        (Asset.k8s_cluster == "") | (Asset.k8s_cluster == None)
    ).group_by(Asset.type).having(func.count(Asset.id) >= 2).order_by(text("cnt desc")).all()
    for t, cnt in types:
        domain_map = {
            "server": "基础设施", "virtual_machine": "基础设施", "vm": "基础设施",
            "database": "数据库", "middleware": "中间件",
            "network": "网络", "storage": "存储",
            "container": "容器", "docker": "容器",
            "loadbalancer": "负载均衡",
        }
        domain = domain_map.get(t, "其他")
        systems.append({
            "system_key": "type_" + t,
            "system_name": t + " (" + str(cnt) + ")",
            "domain": domain,
            "environment": "prod",
            "type": "asset_type",
            "filter": {"type": t},
        })

    # 3. 虚拟 demo 系统已移除 — REAL 模式只展示真实资产数据
    # 原来硬编码的"核心支付系统""CDN加速网络""旧版监控平台"用 random 生成假 SLA，已删除

    return systems


def _process_system(sys, db, day_start, day_end):
    # 虚拟系统的 random 假数据已移除 — 只查真实数据
    filt = sys.get("filter")
    if not filt:
        return None
    if "k8s_cluster" in filt:
        return _compute_day_sla(db, filt["k8s_cluster"], day_start, day_end)
    if "type" in filt:
        base_q = db.query(Asset).filter(Asset.type == filt["type"])
        return _compute_day_sla_by_filter(db, base_q, day_start, day_end)
    return None


@router.get("")
def get_posture(days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db)):
    now = datetime.now()
    start = now - timedelta(days=days)
    systems = _build_systems(db)
    result_systems = []
    for sys in systems:
        entry = {
            "system_key": sys["system_key"],
            "system_name": sys["system_name"],
            "domain": sys["domain"],
            "environment": sys["environment"],
            "status": "unknown",
            "sla_value": 0,
            "health_score": 0,
            "alerts_count": 0,
            "incidents_count": 0,
        }
        result = _process_system(sys, db, start, now)
        if result:
            entry.update(result)
            entry["alerts_count"] = result["alerts"]
            entry["incidents_count"] = result["incidents"]
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
    systems = _build_systems(db)
    result = []
    for sys in systems:
        cells = []
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            r = _process_system(sys, db, day_start, day_end)
            if r:
                cells.append({
                    "day": day_start.strftime("%Y-%m-%d"),
                    "sla_value": r["sla_value"],
                    "health_score": r["health_score"],
                    "status": r["status"],
                    "alerts": r["alerts"],
                    "incidents": r["incidents"],
                })
            else:
                cells.append({
                    "day": day_start.strftime("%Y-%m-%d"),
                    "sla_value": None, "health_score": None, "status": "unknown", "alerts": 0, "incidents": 0,
                })
        result.append({
            "system_key": sys["system_key"],
            "system_name": sys["system_name"],
            "cells": cells,
        })
    return JSONResponse(result)
