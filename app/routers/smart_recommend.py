from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, KnowledgeBase, AlertKbLink
from app.services.knowledge_graph_service import recommend_kb_for_alert

router = APIRouter(prefix="/smart-recommend", tags=["smart_recommend"])


def _alert_brief(a):
    return {
        "id": a.id,
        "metric_name": a.metric_name,
        "severity": a.severity,
        "status": a.status,
        "message": a.message or "",
        "asset_id": a.asset_id,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
    }


def _kb_brief(kb):
    return {
        "id": kb.id,
        "title": kb.title,
        "symptom": kb.symptom or "",
        "root_cause": kb.root_cause or "",
        "solution": kb.solution or "",
        "tags": kb.tags or "",
        "severity": kb.severity or "warning",
        "asset_type": kb.asset_type or "",
    }


def _rag_search(alert, top_k=5):
    """用告警特征做 RAG 语义检索"""
    try:
        from app.services.rag_engine_v2 import hybrid_search
        query_parts = []
        if alert.metric_name:
            query_parts.append(alert.metric_name)
        if alert.message:
            query_parts.append(alert.message[:200])
        query = " ".join(query_parts)
        if not query.strip():
            return []
        results = hybrid_search(query, top_k=top_k)
        return results
    except Exception as e:
        print(f"[smart_recommend] RAG search failed: {e}")
        return []


def _merge_results(rule_recs, rag_results, rule_weight=0.6, rag_weight=0.4):
    """融合规则推荐和 RAG 检索结果
    
    rule_recs: KnowledgeBase 对象列表（来自 recommend_kb_for_alert）
    rag_results: dict 列表（来自 hybrid_search）
    """
    merged = []
    seen_titles = set()

    total_rule = len(rule_recs) or 1

    for idx, entry in enumerate(rule_recs):
        norm_score = round((total_rule - idx) / total_rule, 4)
        merged.append({
            "source": "rule",
            "title": entry.title,
            "score": round(norm_score * rule_weight, 4),
            "raw_score": round(norm_score, 2),
            "kb": _kb_brief(entry),
            "linked": False,
            "content": "",
            "doc_title": "",
        })
        seen_titles.add(entry.title)

    for r in rag_results:
        title = r.get("doc_title", "")
        if title in seen_titles:
            for item in merged:
                if item["title"] == title:
                    item["score"] = round(item["score"] + r.get("score", 0) * rag_weight, 4)
                    item["source"] = "both"
                    break
            continue
        seen_titles.add(title)
        merged.append({
            "source": "rag",
            "title": title or "RAG 文档片段",
            "score": round(r.get("score", 0) * rag_weight, 4),
            "raw_score": round(r.get("score", 0), 4),
            "kb": {
                "id": 0,
                "title": title,
                "symptom": "",
                "root_cause": "",
                "solution": "",
                "tags": r.get("tags", ""),
                "severity": r.get("severity", ""),
                "asset_type": r.get("asset_type", ""),
            },
            "linked": False,
            "content": r.get("content", "")[:500],
            "doc_title": title,
        })

    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged


@router.get("/api/recommend")
def api_recommend(alert_id: int = 0, limit: int = 5, db: Session = Depends(get_db)):
    try:
        if not alert_id:
            return JSONResponse({"error": "alert_id is required", "alert_id": 0, "recommendations": []}, status_code=400)
        selected_alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not selected_alert:
            return JSONResponse({"error": "alert not found", "alert_id": alert_id, "recommendations": []}, status_code=404)

        rule_recs = recommend_kb_for_alert(db, selected_alert, limit=min(limit, 20))
        rag_results = _rag_search(selected_alert, top_k=min(limit, 5))

        merged = _merge_results(rule_recs, rag_results)

        for item in merged[:limit]:
            if item["kb"].get("id"):
                linked = db.query(AlertKbLink).filter(
                    AlertKbLink.alert_id == alert_id,
                    AlertKbLink.kb_id == item["kb"]["id"]).first()
                item["linked"] = bool(linked)

        return JSONResponse({
            "alert_id": alert_id,
            "alert": _alert_brief(selected_alert),
            "recommendations": merged[:limit],
            "count": len(merged[:limit]),
            "sources": {
                "rule": len(rule_recs),
                "rag": len(rag_results),
            },
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "alert_id": alert_id, "recommendations": []}, status_code=500)
