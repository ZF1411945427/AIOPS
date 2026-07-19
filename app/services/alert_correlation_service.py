"""告警收敛服务（P2 任务#9）

AIOps 核心闭环：告警聚类 → 关联拓扑 → 根因推荐 → 单一工单。

聚类维度:
1. 同服务（asset_id 相同）
2. 同时间窗（默认 5 分钟）
3. 同拓扑路径（共享拓扑祖先，由 graph_inference_service 推断）

设计:
- 临时计算 + 进程内缓存（TTL=30s），不持久化（避免脏数据）
- 每个 cluster 计算根因候选（复用 graph_inference_service.infer_root_cause）
- 输出影响路径 + 推荐处置建议
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import Alert, Asset, AssetRelation


# ── 缓存 ──
_CLUSTER_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CLUSTER_TTL = 30.0  # 30 秒缓存


def _serialize_alert(a: Alert, asset: Optional[Asset] = None) -> Dict[str, Any]:
    return {
        "id": a.id,
        "rule_id": a.rule_id,
        "asset_id": a.asset_id,
        "asset_name": asset.name if asset else None,
        "ci_type": asset.ci_type if asset else None,
        "metric_name": a.metric_name,
        "actual_value": a.actual_value,
        "threshold": a.threshold,
        "severity": a.severity,
        "status": a.status,
        "message": a.message or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


def _get_active_alerts(db: Session) -> List[Alert]:
    """获取所有活跃告警（triggered / acknowledged）"""
    return db.query(Alert).filter(Alert.status.in_(["triggered", "acknowledged"])).all()


def _build_asset_index(db: Session) -> Tuple[Dict[int, Asset], Dict[int, List[int]]]:
    """构建资产索引: id→Asset, parent_id→[child_ids]"""
    assets = db.query(Asset).all()
    id_map = {a.id: a for a in assets}
    children_map: Dict[int, List[int]] = defaultdict(list)
    for a in assets:
        if a.parent_id and a.parent_id in id_map:
            children_map[a.parent_id].append(a.id)
    # 加上 AssetRelation
    relations = db.query(AssetRelation).all()
    for r in relations:
        if r.parent_id in id_map and r.child_id in id_map:
            children_map[r.parent_id].append(r.child_id)
    return id_map, children_map


def _ancestors(asset_id: Optional[int], id_map: Dict[int, Asset]) -> List[int]:
    """获取资产的所有祖先链（含自身）"""
    if not asset_id or asset_id not in id_map:
        return []
    chain = [asset_id]
    cur = asset_id
    seen = {cur}
    while True:
        parent_id = id_map[cur].parent_id
        if not parent_id or parent_id not in id_map or parent_id in seen:
            break
        chain.append(parent_id)
        seen.add(parent_id)
        cur = parent_id
    return chain


def _cluster_by_service(alerts: List[Alert]) -> Dict[int, List[Alert]]:
    """按 asset_id 聚类"""
    clusters: Dict[int, List[Alert]] = defaultdict(list)
    for a in alerts:
        if a.asset_id:
            clusters[a.asset_id].append(a)
    return clusters


def _cluster_by_time_window(alerts: List[Alert], window_minutes: int = 5) -> List[List[Alert]]:
    """按时间窗聚类（同 metric_name + 同 asset_id + 时间窗内）"""
    if not alerts:
        return []
    sorted_alerts = sorted(alerts, key=lambda a: a.created_at or datetime.min)
    clusters: List[List[Alert]] = []
    current: List[Alert] = [sorted_alerts[0]]
    for a in sorted_alerts[1:]:
        prev = current[-1]
        same_key = (a.metric_name == prev.metric_name and a.asset_id == prev.asset_id)
        within_window = (
            a.created_at and prev.created_at
            and (a.created_at - prev.created_at) <= timedelta(minutes=window_minutes)
        )
        if same_key and within_window:
            current.append(a)
        else:
            clusters.append(current)
            current = [a]
    if current:
        clusters.append(current)
    return clusters


def _cluster_by_topology(
    alerts: List[Alert],
    id_map: Dict[int, Asset],
) -> Dict[int, List[Alert]]:
    """按拓扑祖先聚类：共享同一祖先（含自身）的告警归一类。
    选取祖先链中最深的"分叉点"作为 cluster key。
    """
    # 简化版: 用顶层祖先（链尾）作为 cluster key
    clusters: Dict[int, List[Alert]] = defaultdict(list)
    for a in alerts:
        if not a.asset_id or a.asset_id not in id_map:
            continue
        chain = _ancestors(a.asset_id, id_map)
        if not chain:
            continue
        # 用链尾（最顶层祖先）作为 cluster key
        top_ancestor = chain[-1]
        clusters[top_ancestor].append(a)
    return clusters


def _severity_weight(s: str) -> int:
    return {"critical": 4, "high": 3, "warning": 2, "medium": 2, "info": 1, "low": 1}.get(s or "", 0)


def _build_cluster_summary(
    cluster_id: str,
    cluster_type: str,
    alerts: List[Alert],
    id_map: Dict[int, Asset],
    key_asset_id: Optional[int] = None,
) -> Dict[str, Any]:
    """构造 cluster 摘要 dict"""
    if not alerts:
        return {}
    sev_counts: Dict[str, int] = defaultdict(int)
    asset_ids: set = set()
    metric_names: set = set()
    services: set = set()
    for a in alerts:
        sev_counts[a.severity or "info"] += 1
        if a.asset_id:
            asset_ids.add(a.asset_id)
            asset = id_map.get(a.asset_id)
            if asset:
                services.add(asset.ci_type or "unknown")
        metric_names.add(a.metric_name or "")
    latest = max((a.created_at for a in alerts if a.created_at), default=None)
    earliest = min((a.created_at for a in alerts if a.created_at), default=None)
    dominant_sev = max(sev_counts.items(), key=lambda x: x[1])[0] if sev_counts else "info"
    return {
        "cluster_id": cluster_id,
        "cluster_type": cluster_type,
        "alert_count": len(alerts),
        "asset_count": len(asset_ids),
        "dominant_severity": dominant_sev,
        "severity_distribution": dict(sev_counts),
        "services": sorted(services),
        "metric_names": sorted(m for m in metric_names if m),
        "earliest_at": earliest.strftime("%Y-%m-%d %H:%M:%S") if earliest else None,
        "latest_at": latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None,
        "key_asset_id": key_asset_id,
        "key_asset_name": id_map[key_asset_id].name if key_asset_id and key_asset_id in id_map else None,
        "alert_ids": [a.id for a in alerts],
        "alerts": [_serialize_alert(a, id_map.get(a.asset_id)) for a in alerts[:20]],
    }


def cluster_alerts(db: Session, window_minutes: int = 5) -> Dict[str, Any]:
    """告警聚类主函数: 三维度聚类 + 统计摘要"""
    t0 = time.time()
    alerts = _get_active_alerts(db)
    id_map, _children = _build_asset_index(db)

    # 维度 1: 按服务（asset_id）
    by_service = _cluster_by_service(alerts)
    service_clusters = [
        _build_cluster_summary(f"svc-{aid}", "service", al, id_map, key_asset_id=aid)
        for aid, al in by_service.items() if al
    ]
    service_clusters.sort(key=lambda x: (-x["alert_count"], x["cluster_id"]))

    # 维度 2: 按时间窗
    time_clusters_raw = _cluster_by_time_window(alerts, window_minutes)
    time_clusters: List[Dict[str, Any]] = []
    for i, al in enumerate(time_clusters_raw):
        if len(al) < 2:
            continue  # 只展示聚合了 ≥2 条告警的窗口
        first = al[0]
        time_clusters.append(_build_cluster_summary(
            f"time-{i}", "time_window", al, id_map, key_asset_id=first.asset_id
        ))
    time_clusters.sort(key=lambda x: (-x["alert_count"], x["cluster_id"]))

    # 维度 3: 按拓扑
    by_topo = _cluster_by_topology(alerts, id_map)
    topo_clusters = [
        _build_cluster_summary(f"topo-{aid}", "topology", al, id_map, key_asset_id=aid)
        for aid, al in by_topo.items() if al
    ]
    topo_clusters.sort(key=lambda x: (-x["alert_count"], x["cluster_id"]))

    # 汇总
    total_alerts = len(alerts)
    total_assets = len({a.asset_id for a in alerts if a.asset_id})
    severity_dist: Dict[str, int] = defaultdict(int)
    for a in alerts:
        severity_dist[a.severity or "info"] += 1

    elapsed_ms = int((time.time() - t0) * 1000)
    return {
        "summary": {
            "total_alerts": total_alerts,
            "total_assets": total_assets,
            "service_cluster_count": len(service_clusters),
            "time_cluster_count": len(time_clusters),
            "topology_cluster_count": len(topo_clusters),
            "severity_distribution": dict(severity_dist),
            "window_minutes": window_minutes,
            "elapsed_ms": elapsed_ms,
            "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "service_clusters": service_clusters[:50],
        "time_clusters": time_clusters[:50],
        "topology_clusters": topo_clusters[:50],
    }


def cluster_detail(db: Session, cluster_id: str) -> Dict[str, Any]:
    """获取单个 cluster 详情：含根因推荐 + 拓扑影响路径"""
    # 重新计算聚类以找到对应 cluster
    data = cluster_alerts(db)
    target: Optional[Dict[str, Any]] = None
    cluster_type = ""
    for group_key in ("service_clusters", "time_clusters", "topology_clusters"):
        for c in data.get(group_key, []):
            if c["cluster_id"] == cluster_id:
                target = c
                cluster_type = c["cluster_type"]
                break
        if target:
            break

    if not target:
        return {"warning": f"cluster {cluster_id} 不存在或已过期", "cluster": None}

    # 根因推荐: 调用 graph_inference_service
    root_cause: Dict[str, Any] = {}
    try:
        from app.services.graph_inference_service import infer_root_cause
        alert_ids = target.get("alert_ids", [])[:50]
        if alert_ids:
            root_cause = infer_root_cause(db, alert_ids=alert_ids)
    except Exception as e:
        logger.warning(f"cluster_detail infer_root_cause 异常: {e}")
        root_cause = {"warning": f"根因推理失败: {e}"}

    # 影响路径: 调用 graph_inference_service.analyze_impact
    impact: Dict[str, Any] = {}
    try:
        from app.services.graph_inference_service import analyze_impact
        key_asset_id = target.get("key_asset_id")
        if key_asset_id:
            impact = analyze_impact(db, key_asset_id, depth=3)
    except Exception as e:
        logger.warning(f"cluster_detail analyze_impact 异常: {e}")
        impact = {"warning": f"影响分析失败: {e}"}

    return {
        "cluster": target,
        "cluster_type": cluster_type,
        "root_cause": root_cause,
        "impact_analysis": impact,
    }


def get_clusters_cached(db: Session, force_refresh: bool = False) -> Dict[str, Any]:
    """获取聚类结果（带 30s 缓存）"""
    now = time.time()
    if (not force_refresh
            and _CLUSTER_CACHE["data"] is not None
            and now - _CLUSTER_CACHE["ts"] < _CLUSTER_TTL):
        return _CLUSTER_CACHE["data"]
    data = cluster_alerts(db)
    _CLUSTER_CACHE["ts"] = now
    _CLUSTER_CACHE["data"] = data
    return data
