"""
知识图谱推理服务 - 基于拓扑图的智能推理引擎
三大推理能力:
  1. 故障传播分析 (Impact Analysis) - BFS 沿依赖图向下游传播
  2. 根因定位推理 (Root Cause Inference) - PageRank + 度中心性 + 告警传播评分融合
  3. 知识推荐推理 (Knowledge Recommendation) - 图谱多跳关联推理

存储后端:
  - 优先 Neo4j (若配置了 NEO4J_URI/PASSWORD)
  - 降级 networkx 内存图 (从 PostgreSQL Asset/AssetRelation 构建)
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Asset, AssetRelation, Alert, KnowledgeBase, Runbook, AlertKbLink,
)

logger = logging.getLogger("graph_inference")

# 传播衰减因子: 每深一层影响概率衰减
PROPAGATION_DECAY = 0.7
# 根因融合权重
W_PAGERANK = 0.4
W_IN_DEGREE = 0.25
W_ALERT_PROPAGATION = 0.35

SEVERITY_SCORE = {"critical": 3.0, "warning": 2.0, "info": 1.0, "high": 3.0, "medium": 2.0, "low": 1.0}


# ─────────────────────────────────────────────────────────
# 图构建 - 从 PostgreSQL 构建 networkx 有向图
# ─────────────────────────────────────────────────────────
def _build_nx_graph(db: Session) -> Tuple["nx.DiGraph", Dict[int, Asset]]:
    """从 PostgreSQL 构建有向图 (parent -> child 表示依赖方向)."""
    import networkx as nx

    assets = db.query(Asset).all()
    relations = db.query(AssetRelation).all()
    asset_map: Dict[int, Asset] = {a.id: a for a in assets}

    G = nx.DiGraph()
    for a in assets:
        G.add_node(a.id, name=a.name, ci_type=a.ci_type or "unknown",
                   status=a.status or "unknown", ip=a.ip or "")

    for r in relations:
        if r.parent_id in asset_map and r.child_id in asset_map:
            rel_type = r.relation_type or "depends_on"
            G.add_edge(r.parent_id, r.child_id, relation=rel_type)

    for a in assets:
        if a.parent_id and a.parent_id in asset_map:
            G.add_edge(a.parent_id, a.id, relation="parent")

    return G, asset_map


def _get_active_alerts_by_asset(db: Session) -> Dict[int, List[Alert]]:
    """按资产分组活跃告警."""
    result: Dict[int, List[Alert]] = defaultdict(list)
    rows = db.query(Alert).filter(Alert.status.in_(["triggered", "acknowledged"])).all()
    for a in rows:
        if a.asset_id:
            result[a.asset_id].append(a)
    return result


def _get_all_alerts_by_asset(db: Session, hours: int = 24) -> Dict[int, List[Alert]]:
    """按资产分组最近 N 小时的所有告警."""
    result: Dict[int, List[Alert]] = defaultdict(list)
    since = datetime.now() - timedelta(hours=hours)
    rows = db.query(Alert).filter(Alert.created_at >= since).all()
    for a in rows:
        if a.asset_id:
            result[a.asset_id].append(a)
    return result


# ─────────────────────────────────────────────────────────
# 1. 故障传播分析 (Impact Analysis)
# ─────────────────────────────────────────────────────────
def analyze_impact(
    db: Session,
    asset_id: int,
    depth: int = 3,
    include_alerts: bool = True,
) -> Dict[str, Any]:
    """
    故障传播分析: 给定故障源资产, BFS 沿依赖图向下游推理所有受影响资产.

    Args:
        asset_id: 故障源资产 ID
        depth: 最大传播深度 (1-5)
        include_alerts: 是否包含已触发告警信息
    Returns:
        影响范围、传播路径、影响评分、建议操作
    """
    G, asset_map = _build_nx_graph(db)
    if asset_id not in asset_map:
        return {"error": f"资产 ID {asset_id} 不存在"}

    source_asset = asset_map[asset_id]
    depth = max(1, min(5, depth))

    # BFS 向下游传播 (沿出边 parent->child 方向)
    visited: Set[int] = {asset_id}
    impacted: List[Dict[str, Any]] = []
    propagation_paths: List[Dict[str, Any]] = []
    queue: deque = deque([(asset_id, 0, [asset_id])])

    active_alerts = _get_active_alerts_by_asset(db) if include_alerts else {}

    while queue:
        current, d, path = queue.popleft()
        if d >= depth:
            continue
        for neighbor in G.successors(current):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            impact_prob = round(PROPAGATION_DECAY ** (d + 1), 3)
            neighbor_asset = asset_map.get(neighbor)
            if not neighbor_asset:
                continue
            alert_count = len(active_alerts.get(neighbor, []))
            # 影响评分 = 传播概率 * (1 + 告警加成)
            impact_score = round(impact_prob * (1 + alert_count * 0.3), 3)
            impacted.append({
                "asset_id": neighbor,
                "asset_name": neighbor_asset.name,
                "ci_type": neighbor_asset.ci_type or "unknown",
                "ip": neighbor_asset.ip or "",
                "status": neighbor_asset.status or "unknown",
                "depth": d + 1,
                "impact_probability": impact_prob,
                "impact_score": impact_score,
                "active_alert_count": alert_count,
                "has_active_alert": alert_count > 0,
            })
            full_path = path + [neighbor]
            propagation_paths.append({
                "path": [asset_map[n].name if n in asset_map else f"#{n}" for n in full_path],
                "path_ids": full_path,
                "length": d + 1,
            })
            queue.append((neighbor, d + 1, full_path))

    impacted.sort(key=lambda x: (-x["impact_score"], x["depth"]))

    # 影响范围统计
    ci_type_dist: Dict[str, int] = defaultdict(int)
    for imp in impacted:
        ci_type_dist[imp["ci_type"]] += 1

    # 建议操作
    recommendations: List[str] = []
    high_impact = [i for i in impacted if i["impact_score"] >= 0.5]
    if high_impact:
        recommendations.append(
            f"立即检查 {len(high_impact)} 个高影响资产: " +
            ", ".join(i["asset_name"] for i in high_impact[:5])
        )
    alert_impacted = [i for i in impacted if i["has_active_alert"]]
    if alert_impacted:
        recommendations.append(
            f"{len(alert_impacted)} 个下游资产已触发告警, 故障可能已传播, 建议优先处理"
        )
    if not recommendations:
        recommendations.append("当前下游资产无活跃告警, 建议持续监控")

    return {
        "source_asset": {
            "asset_id": asset_id,
            "asset_name": source_asset.name,
            "ci_type": source_asset.ci_type or "unknown",
            "ip": source_asset.ip or "",
            "status": source_asset.status or "unknown",
        },
        "impacted_assets": impacted,
        "propagation_paths": propagation_paths[:20],
        "summary": {
            "total_impacted": len(impacted),
            "max_depth_reached": max((i["depth"] for i in impacted), default=0),
            "high_impact_count": len(high_impact),
            "alert_triggered_count": len(alert_impacted),
            "ci_type_distribution": dict(ci_type_dist),
        },
        "recommendations": recommendations,
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────────────────────────────────────
# 2. 根因定位推理 (Root Cause Inference)
# ─────────────────────────────────────────────────────────
def infer_root_cause(
    db: Session,
    alert_ids: Optional[List[int]] = None,
    asset_ids: Optional[List[int]] = None,
    hours: int = 24,
) -> Dict[str, Any]:
    """
    根因定位推理: 基于拓扑图 + 告警分布, 用图算法融合评分定位根因节点.

    三维评分融合:
      - PageRank (图中心性, 关键节点得分高)
      - 入度中心性 (被依赖越多越可能是根因)
      - 告警传播评分 (子树告警数加权, 根因通常触发最多下游告警)

    Args:
        alert_ids: 相关告警 ID 列表 (可选)
        asset_ids: 相关资产 ID 列表 (可选)
        hours: 若未指定告警, 取最近 N 小时告警分析
    Returns:
        根因候选列表 + 推理依据 + 拓扑路径
    """
    import networkx as nx
    import numpy as np

    G, asset_map = _build_nx_graph(db)
    if len(asset_map) == 0:
        return {"error": "系统中无资产数据"}

    # 收集相关告警
    alerts: List[Alert] = []
    if alert_ids:
        alerts = db.query(Alert).filter(Alert.id.in_(alert_ids)).all()
    relevant_asset_ids: Set[int] = set(asset_ids or [])
    for a in alerts:
        if a.asset_id:
            relevant_asset_ids.add(a.asset_id)

    # 若无指定告警/资产, 取最近 N 小时活跃告警涉及资产
    if not relevant_asset_ids:
        recent_alerts = db.query(Alert).filter(
            Alert.status.in_(["triggered", "acknowledged"]),
            Alert.created_at >= datetime.now() - timedelta(hours=hours),
        ).all()
        alerts = recent_alerts
        for a in recent_alerts:
            if a.asset_id:
                relevant_asset_ids.add(a.asset_id)

    if not relevant_asset_ids:
        return {"error": "未找到相关告警或资产, 无法推理根因"}

    # 活跃告警分组
    alerts_by_asset: Dict[int, List[Alert]] = defaultdict(list)
    for a in alerts:
        if a.asset_id:
            alerts_by_asset[a.asset_id].append(a)

    # ── 评分 1: PageRank ──
    try:
        pagerank = nx.pagerank(G, alpha=0.85, max_iter=200, tol=1e-6)
    except Exception:
        pagerank = {n: 1.0 / len(G) for n in G}

    # ── 评分 2: 入度中心性 ──
    in_degree = dict(G.in_degree())

    # ── 评分 3: 告警传播评分 (子树告警数加权) ──
    alert_prop_score: Dict[int, float] = {}
    for aid in relevant_asset_ids:
        if aid not in asset_map:
            continue
        # 计算该资产子树(下游)的告警总数, 加权衰减
        subtree_alerts = 0.0
        visited: Set[int] = {aid}
        queue2: deque = deque([(aid, 0)])
        while queue2:
            cur, d = queue2.popleft()
            subtree_alerts += len(alerts_by_asset.get(cur, [])) * (PROPAGATION_DECAY ** d)
            for nb in G.successors(cur):
                if nb not in visited:
                    visited.add(nb)
                    queue2.append((nb, d + 1))
        # 自身告警数也计入
        own_alerts = len(alerts_by_asset.get(aid, []))
        alert_prop_score[aid] = own_alerts + subtree_alerts

    # ── 融合评分 ──
    # 归一化
    max_pr = max(pagerank.values()) if pagerank else 1
    max_indeg = max(in_degree.values()) if in_degree else 1
    max_alert = max(alert_prop_score.values()) if alert_prop_score else 1

    candidates: List[Dict[str, Any]] = []
    for aid in relevant_asset_ids:
        if aid not in asset_map:
            continue
        a = asset_map[aid]
        pr_norm = pagerank.get(aid, 0) / max_pr if max_pr > 0 else 0
        indeg_norm = in_degree.get(aid, 0) / max_indeg if max_indeg > 0 else 0
        alert_norm = alert_prop_score.get(aid, 0) / max_alert if max_alert > 0 else 0
        combined = W_PAGERANK * pr_norm + W_IN_DEGREE * indeg_norm + W_ALERT_PROPAGATION * alert_norm
        alert_count = len(alerts_by_asset.get(aid, []))
        candidates.append({
            "asset_id": aid,
            "asset_name": a.name,
            "ci_type": a.ci_type or "unknown",
            "ip": a.ip or "",
            "status": a.status or "unknown",
            "alert_count": alert_count,
            "alert_severity": _dominant_severity(alerts_by_asset.get(aid, [])),
            "pagerank_score": round(pr_norm, 4),
            "in_degree_score": round(indeg_norm, 4),
            "alert_propagation_score": round(alert_norm, 4),
            "combined_score": round(combined, 4),
        })

    candidates.sort(key=lambda x: -x["combined_score"])

    # 置信度分级
    for i, c in enumerate(candidates):
        if i == 0 and c["combined_score"] > 0.5:
            c["confidence"] = "high"
            c["rank"] = 1
        elif i < 3 and c["combined_score"] > 0.2:
            c["confidence"] = "medium"
            c["rank"] = i + 1
        else:
            c["confidence"] = "low"
            c["rank"] = i + 1

    # 推理依据
    top = candidates[0] if candidates else None
    reasoning: List[str] = []
    if top:
        reasoning.append(
            f"根因候选 #{top['asset_name']} 综合评分 {top['combined_score']:.3f} (PageRank={top['pagerank_score']:.3f}, "
            f"入度={top['in_degree_score']:.3f}, 告警传播={top['alert_propagation_score']:.3f})"
        )
        if top["alert_count"] > 0:
            reasoning.append(
                f"该资产当前有 {top['alert_count']} 条活跃告警, 主导级别: {top['alert_severity']}"
            )
        if top["in_degree_score"] > 0.5:
            reasoning.append("该资产被多个上游依赖, 是拓扑关键节点, 故障影响面大")
        if top["alert_propagation_score"] > 0.5:
            reasoning.append("该资产下游告警传播评分高, 可能是故障源头")

    # 拓扑路径: 根因 -> 其他告警资产
    topology_paths: List[Dict[str, Any]] = []
    if top and len(candidates) > 1:
        for c in candidates[1:4]:
            try:
                path = nx.shortest_path(G, top["asset_id"], c["asset_id"])
                topology_paths.append({
                    "from": top["asset_name"],
                    "to": c["asset_name"],
                    "path": [asset_map[n].name if n in asset_map else f"#{n}" for n in path],
                    "path_ids": path,
                    "length": len(path) - 1,
                })
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass

    return {
        "total_alerts_analyzed": len(alerts),
        "total_assets_analyzed": len(relevant_asset_ids),
        "root_cause_candidates": candidates[:10],
        "reasoning": reasoning,
        "topology_paths": topology_paths,
        "algorithm": {
            "pagerank_weight": W_PAGERANK,
            "in_degree_weight": W_IN_DEGREE,
            "alert_propagation_weight": W_ALERT_PROPAGATION,
            "decay_factor": PROPAGATION_DECAY,
        },
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _dominant_severity(alerts: List[Alert]) -> str:
    if not alerts:
        return "none"
    sev_count: Dict[str, int] = defaultdict(int)
    for a in alerts:
        sev_count[a.severity or "info"] += 1
    return max(sev_count, key=sev_count.get)


# ─────────────────────────────────────────────────────────
# 3. 知识推荐推理 (Knowledge Recommendation)
# ─────────────────────────────────────────────────────────
def recommend_knowledge(
    db: Session,
    alert_id: Optional[int] = None,
    asset_id: Optional[int] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    知识推荐推理: 基于图谱多跳关联推理推荐相关知识.

    推理链路:
      1. 告警 -> 资产 -> ci_type -> Runbook(asset_type 匹配)
      2. 告警 -> metric_name -> KnowledgeBase(tags/symptom 匹配)
      3. 资产 -> 依赖链 -> 上下游历史 RCA 知识
      4. 资产 -> 同类型资产历史告警 -> 相似故障知识

    Args:
        alert_id: 告警 ID (可选)
        asset_id: 资产 ID (可选, 若无告警时用)
        limit: 返回数量上限
    Returns:
        推荐知识列表 + Runbook 列表 + 历史故障 + 关联路径
    """
    alert: Optional[Alert] = None
    target_asset: Optional[Asset] = None

    if alert_id:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return {"error": f"告警 ID {alert_id} 不存在"}
        if alert.asset_id:
            target_asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
    elif asset_id:
        target_asset = db.query(Asset).filter(Asset.id == asset_id).first()
    else:
        return {"error": "需要提供 alert_id 或 asset_id"}

    if not target_asset:
        return {"error": "未找到关联资产"}

    ci_type = (target_asset.ci_type or "").lower()
    metric_name = alert.metric_name if alert else ""
    severity = alert.severity if alert else ""
    alert_message = (alert.message or "") if alert else ""

    recommendations: List[Dict[str, Any]] = []

    # ── 推理链 1: 资产 ci_type -> Runbook ──
    runbooks = db.query(Runbook).all()
    for rb in runbooks:
        score = 0
        match_reasons: List[str] = []
        if rb.asset_type and rb.asset_type.lower() == ci_type:
            score += 5
            match_reasons.append(f"Runbook 资产类型 {rb.asset_type} 匹配当前资产 {ci_type}")
        if metric_name and rb.tags and metric_name in (rb.tags or ""):
            score += 3
            match_reasons.append(f"Runbook 标签包含指标 {metric_name}")
        if severity and rb.severity and rb.severity.lower() == (severity or "").lower():
            score += 2
            match_reasons.append(f"严重度 {severity} 匹配")
        if score > 0:
            recommendations.append({
                "type": "runbook",
                "id": rb.id,
                "title": rb.title,
                "score": score,
                "match_reasons": match_reasons,
                "category": rb.category or "",
                "asset_type": rb.asset_type or "",
                "severity": rb.severity or "",
                "steps_count": len((rb.steps or "")) if rb.steps else 0,
            })

    # ── 推理链 2: 告警 metric_name/symptom -> KnowledgeBase ──
    kbs = db.query(KnowledgeBase).all()
    for kb in kbs:
        score = 0
        match_reasons: List[str] = []
        if metric_name and kb.tags and metric_name in (kb.tags or ""):
            score += 4
            match_reasons.append(f"知识标签匹配指标 {metric_name}")
        if alert_message and kb.symptom:
            common = set(alert_message.lower().split()) & set((kb.symptom or "").lower().split())
            if common:
                score += min(len(common) * 2, 6)
                match_reasons.append(f"症状关键词重叠 {len(common)} 个: {', '.join(list(common)[:5])}")
        if ci_type and kb.asset_type and kb.asset_type.lower() == ci_type:
            score += 3
            match_reasons.append(f"知识资产类型 {kb.asset_type} 匹配")
        if severity and kb.severity and kb.severity.lower() == (severity or "").lower():
            score += 2
            match_reasons.append(f"严重度 {severity} 匹配")
        if score > 0:
            recommendations.append({
                "type": "knowledge",
                "id": kb.id,
                "title": kb.title,
                "score": score,
                "match_reasons": match_reasons,
                "root_cause": (kb.root_cause or "")[:200],
                "solution": (kb.solution or "")[:200],
                "asset_type": kb.asset_type or "",
                "severity": kb.severity or "",
                "tags": kb.tags or "",
            })

    # ── 推理链 3: 依赖链 -> 上下游历史 RCA 知识 ──
    G, asset_map = _build_nx_graph(db)
    upstream_assets: Set[int] = set()
    downstream_assets: Set[int] = set()
    import networkx as nx
    for pred in G.predecessors(target_asset.id):
        upstream_assets.add(pred)
    for succ in G.successors(target_asset.id):
        downstream_assets.add(succ)

    related_asset_ids = upstream_assets | downstream_assets
    if related_asset_ids:
        # 查找这些资产的历史 RCA 知识 (有 root_cause 的 KnowledgeBase)
        related_types = {asset_map[aid].ci_type for aid in related_asset_ids if aid in asset_map}
        for kb in kbs:
            if kb.root_cause and kb.asset_type and kb.asset_type.lower() in [t.lower() for t in related_types if t]:
                already = any(r.get("id") == kb.id and r.get("type") == "knowledge" for r in recommendations)
                if not already:
                    recommendations.append({
                        "type": "historical_rca",
                        "id": kb.id,
                        "title": kb.title,
                        "score": 3,
                        "match_reasons": [f"上下游依赖资产类型 {kb.asset_type} 有历史 RCA 记录"],
                        "root_cause": (kb.root_cause or "")[:200],
                        "asset_type": kb.asset_type or "",
                        "tags": kb.tags or "",
                    })

    # ── 推理链 4: 同类型资产历史告警 -> 相似故障知识 ──
    if ci_type:
        similar_assets = [a for a in asset_map.values() if (a.ci_type or "").lower() == ci_type and a.id != target_asset.id]
        similar_asset_ids = [a.id for a in similar_assets[:20]]
        if similar_asset_ids:
            since = datetime.now() - timedelta(days=30)
            similar_alerts = db.query(Alert).filter(
                Alert.asset_id.in_(similar_asset_ids),
                Alert.created_at >= since,
            ).limit(50).all()
            similar_metric_names = {a.metric_name for a in similar_alerts if a.metric_name}
            for kb in kbs:
                if kb.tags and any(m in (kb.tags or "") for m in similar_metric_names):
                    already = any(r.get("id") == kb.id for r in recommendations)
                    if not already:
                        recommendations.append({
                            "type": "similar_fault",
                            "id": kb.id,
                            "title": kb.title,
                            "score": 2,
                            "match_reasons": [f"同类型资产 {ci_type} 近30天出现类似指标告警, 关联知识"],
                            "root_cause": (kb.root_cause or "")[:200],
                            "asset_type": kb.asset_type or "",
                            "tags": kb.tags or "",
                        })

    # 排序 + 截断
    recommendations.sort(key=lambda x: -x["score"])
    top_recommendations = recommendations[:limit]

    # 按类型分组统计
    type_dist: Dict[str, int] = defaultdict(int)
    for r in top_recommendations:
        type_dist[r["type"]] += 1

    # 关联路径可视化
    association_paths: List[Dict[str, Any]] = []
    if alert:
        association_paths.append({"path": [f"告警#{alert.id}", f"资产:{target_asset.name}", f"类型:{ci_type}"], "type": "alert->asset->type"})
    if metric_name:
        association_paths.append({"path": [f"告警#{alert.id}", f"指标:{metric_name}", "知识标签匹配"], "type": "alert->metric->kb"})
    if related_asset_ids:
        association_paths.append({
            "path": [f"资产:{target_asset.name}", f"上下游{len(related_asset_ids)}个资产", "历史RCA知识"],
            "type": "asset->dependency->rca",
        })

    return {
        "target": {
            "alert_id": alert.id if alert else None,
            "alert_message": alert_message[:200] if alert_message else "",
            "alert_metric": metric_name,
            "alert_severity": severity,
            "asset_id": target_asset.id,
            "asset_name": target_asset.name,
            "ci_type": ci_type,
        },
        "recommendations": top_recommendations,
        "recommendation_count": len(top_recommendations),
        "type_distribution": dict(type_dist),
        "association_paths": association_paths,
        "graph_context": {
            "upstream_count": len(upstream_assets),
            "downstream_count": len(downstream_assets),
        },
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
