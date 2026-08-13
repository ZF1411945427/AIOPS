"""K8s 多集群 data plane 服务(F5) - 集群注册表 + 独立 telemetry 通道。

契约见 CONTRACT.md 第二十章。每个集群关联一个 type='kubernetes' 的 DataSource,
拥有独立 telemetry 通道(按集群过滤 K8sEvent / asset 汇总)。对标 Ongrid
controller/node 双角色多集群 data plane 分离。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Asset, DataSource, K8sCluster, K8sEvent, MetricRecord

CLUSTER_ROLES = ["controller", "node"]


def _cluster_dict(c: K8sCluster) -> Dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "datasource_id": c.datasource_id,
        "data_plane_status": c.data_plane_status,
        "telemetry_channel": c.telemetry_channel,
        "namespace_scope": c.namespace_scope,
        "target_version": c.target_version,
        "agent_version": c.agent_version,
        "last_check_at": c.last_check_at.isoformat() if c.last_check_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


def list_clusters(db: Session) -> List[Dict[str, Any]]:
    return [_cluster_dict(c) for c in db.query(K8sCluster).order_by(K8sCluster.role, K8sCluster.name).all()]


def available_datasources(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return [{"id": d.id, "name": d.name, "endpoint": d.endpoint, "status": d.last_status} for d in rows]


def get_cluster(db: Session, cluster_id: int) -> Optional[K8sCluster]:
    return db.query(K8sCluster).filter(K8sCluster.id == cluster_id).first()


def create_cluster(db: Session, data: Dict[str, Any], created_by: Optional[int] = None) -> K8sCluster:
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("集群名不能为空")
    if db.query(K8sCluster).filter(K8sCluster.name == name).first():
        raise ValueError(f"集群 {name} 已存在")
    c = K8sCluster(
        name=name,
        role=str(data.get("role") or "node"),
        datasource_id=data.get("datasource_id"),
        data_plane_status=str(data.get("data_plane_status") or "active"),
        telemetry_channel=str(data.get("telemetry_channel") or f"{name}.telemetry"),
        namespace_scope=str(data.get("namespace_scope") or ""),
        target_version=str(data.get("target_version") or ""),
        agent_version=str(data.get("agent_version") or "1.0.0"),
        last_check_at=datetime.now(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_cluster(db: Session, cluster_id: int, data: Dict[str, Any]) -> K8sCluster:
    c = get_cluster(db, cluster_id)
    if not c:
        raise ValueError("集群不存在")
    if "name" in data and data["name"]:
        c.name = str(data["name"])
    for field in ("role", "datasource_id", "data_plane_status", "telemetry_channel",
                  "namespace_scope", "target_version", "agent_version"):
        if field in data and data[field] is not None:
            setattr(c, field, data[field])
    c.updated_at = datetime.now()
    db.commit()
    db.refresh(c)
    return c


def delete_cluster(db: Session, cluster_id: int) -> None:
    c = get_cluster(db, cluster_id)
    if not c:
        raise ValueError("集群不存在")
    db.delete(c)
    db.commit()


def check_cluster(db: Session, cluster_id: int) -> Dict[str, Any]:
    """连通性/数据面状态检查: 依赖 DataSource.last_status, 并统计遥测流入量。"""
    c = get_cluster(db, cluster_id)
    if not c:
        raise ValueError("集群不存在")
    ds_status = "unknown"
    endpoint = ""
    if c.datasource_id:
        ds = db.query(DataSource).filter(DataSource.id == c.datasource_id).first()
        if ds:
            ds_status = ds.last_status or "unknown"
            endpoint = ds.endpoint or ""
    events = db.query(K8sEvent).filter(K8sEvent.cluster == c.name).count()
    metrics = db.query(MetricRecord).count()
    c.last_check_at = datetime.now()
    c.data_plane_status = "error" if ds_status == "error" else ("active" if ds_status == "up" else "standby")
    db.commit()
    return {**_cluster_dict(c), "datasource_status": ds_status, "endpoint": endpoint,
            "event_count": events, "metric_count": metrics}


def cluster_telemetry(db: Session, cluster_id: int) -> Dict[str, Any]:
    """单集群独立 telemetry: 集群事件 + 资产汇总 + 数据面状态。"""
    c = get_cluster(db, cluster_id)
    if not c:
        raise ValueError("集群不存在")
    events = [{
        "id": e.id, "kind": e.kind, "reason": e.reason, "severity": e.severity,
        "created_at": e.created_at.isoformat() if e.created_at else "",
    } for e in db.query(K8sEvent).filter(K8sEvent.cluster == c.name).order_by(
        K8sEvent.id.desc()).limit(100).all()]
    assets = db.query(Asset).filter(Asset.k8s_cluster == c.name).all()
    from collections import Counter
    by_type = Counter(a.ci_type or "other" for a in assets)
    return {
        "cluster": _cluster_dict(c),
        "event_total": len(events),
        "events": events,
        "asset_total": len(assets),
        "asset_by_type": dict(by_type),
    }


def cluster_summary(db: Session) -> List[Dict[str, Any]]:
    """所有集群的状态汇总(含每集群遥测计数, 用于列表页)。"""
    out = []
    for c in db.query(K8sCluster).order_by(K8sCluster.name).all():
        check = check_cluster(db, c.id)
        tele = cluster_telemetry(db, c.id)
        out.append({
            **check,
            "event_total": tele["event_total"],
            "asset_total": tele["asset_total"],
            "asset_by_type": tele["asset_by_type"],
        })
    return out
