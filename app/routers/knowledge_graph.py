from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import JSONResponse
from typing import List, Optional

from app.database import get_db
from app.services import knowledge_graph_service
from app.services import graph_inference_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/knowledge/graph", tags=["knowledge-graph"])


@router.get("/api/graph")
def api_graph(db: Session = Depends(get_db)):
    try:
        try:
            from app.services.neo4j_graph_service import (
                get_neo4j_config, sync_asset_graph, query_kg,
            )
            cfg = get_neo4j_config()
            if cfg["enabled"]:
                synced = sync_asset_graph(db)
                if synced >= 0:
                    all_nodes = query_kg("", limit=500)
                    nodes = []
                    edges = []
                    for n in all_nodes:
                        nodes.append({
                            "id": n.get("id", ""),
                            "label": n.get("name", ""),
                            "type": n.get("type", ""),
                            "status": n.get("status", ""),
                            "ip": n.get("ip", ""),
                        })
                    from app.services.knowledge_graph_service import get_dependency_graph
                    pg_graph = get_dependency_graph(db)
                    return JSONResponse({
                        "nodes": nodes or pg_graph.get("nodes", []),
                        "edges": edges or pg_graph.get("edges", []),
                        "node_count": len(nodes or pg_graph.get("nodes", [])),
                        "edge_count": len(edges or pg_graph.get("edges", [])),
                        "source": "neo4j" if nodes else "postgresql",
                    })
        except Exception:
            pass
        graph = knowledge_graph_service.get_dependency_graph(db)
        return JSONResponse({
            "nodes": graph.get("nodes", []),
            "edges": graph.get("edges", []),
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
            "source": "postgresql",
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "nodes": [], "edges": []}, status_code=500)


@router.get("/api/subgraph")
def api_subgraph(
    asset_id: str = Query(..., description="资产ID，如 asset_1"),
    depth: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
):
    try:
        from app.services.neo4j_graph_service import get_neo4j_config, get_subgraph
        cfg = get_neo4j_config()
        if not cfg["enabled"]:
            return JSONResponse({"error": "Neo4j未配置"}, status_code=503)
        result = get_subgraph(asset_id, depth=depth)
        return JSONResponse({
            "nodes": result.get("nodes", []),
            "edges": result.get("edges", []),
            "node_count": len(result.get("nodes", [])),
            "edge_count": len(result.get("edges", [])),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/sync")
def api_sync_neo4j(db: Session = Depends(get_db)):
    try:
        from app.services.neo4j_graph_service import get_neo4j_config, sync_asset_graph
        cfg = get_neo4j_config()
        if not cfg["enabled"]:
            return JSONResponse({"error": "Neo4j未配置，请设置环境变量 NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD"}, status_code=503)
        count = sync_asset_graph(db)
        return JSONResponse({"synced": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────────────────
# 知识图谱推理 API
# ─────────────────────────────────────────────────────────

@router.get("/api/impact-analysis")
def api_impact_analysis(
    asset_id: int = Query(..., description="故障源资产 ID"),
    depth: int = Query(3, ge=1, le=5, description="传播深度 1-5"),
    include_alerts: bool = Query(True, description="是否包含告警信息"),
    db: Session = Depends(get_db),
):
    """故障传播分析: 给定故障源资产, 推理所有下游受影响资产."""
    try:
        result = graph_inference_service.analyze_impact(
            db, asset_id=asset_id, depth=depth, include_alerts=include_alerts
        )
        if "error" in result:
            return JSONResponse(result, status_code=404)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/root-cause")
def api_root_cause(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """根因定位推理: 基于拓扑图 + 告警分布融合评分定位根因节点.

    Body:
        alert_ids: List[int]  (可选, 相关告警 ID)
        asset_ids: List[int]  (可选, 相关资产 ID)
        hours: int            (可选, 默认 24, 未指定告警时取最近 N 小时)
    """
    try:
        alert_ids = payload.get("alert_ids") or None
        asset_ids = payload.get("asset_ids") or None
        hours = int(payload.get("hours", 24))
        result = graph_inference_service.infer_root_cause(
            db, alert_ids=alert_ids, asset_ids=asset_ids, hours=hours
        )
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/recommend")
def api_recommend(
    alert_id: Optional[int] = Query(None, description="告警 ID"),
    asset_id: Optional[int] = Query(None, description="资产 ID"),
    limit: int = Query(10, ge=1, le=50, description="返回数量上限"),
    db: Session = Depends(get_db),
):
    """知识推荐推理: 基于图谱多跳关联推理推荐相关知识/Runbook/历史故障."""
    try:
        if not alert_id and not asset_id:
            return JSONResponse({"error": "需要提供 alert_id 或 asset_id"}, status_code=400)
        result = graph_inference_service.recommend_knowledge(
            db, alert_id=alert_id, asset_id=asset_id, limit=limit
        )
        if "error" in result:
            return JSONResponse(result, status_code=404)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
