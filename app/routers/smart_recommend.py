from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, KnowledgeBase, AlertKbLink, Asset
import json
import re

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


def _parse_tags(tags):
    if not tags:
        return []
    if isinstance(tags, list):
        return tags
    try:
        return json.loads(tags)
    except Exception:
        return [t.strip().strip('"') for t in tags.strip('[]').split(',') if t.strip()]


def _score_rule(alert, entry, db):
    score = 0
    reasons = []

    alert_tags = _parse_tags(entry.tags)
    metric = (alert.metric_name or "").lower()
    if metric:
        for tag in alert_tags:
            tag_lower = tag.lower()
            if metric == tag_lower or metric in tag_lower or tag_lower in metric:
                score += 5
                reasons.append("metric_tag:%s" % tag)
                break
        title_lower = (entry.title or "").lower()
        if metric.replace("_", "") in title_lower.replace("_", "") or metric in title_lower:
            score += 3
            reasons.append("metric_in_title")

    if alert.severity and entry.severity:
        sev_order = {"critical": 4, "high": 3, "warning": 2, "info": 1}
        a_sev = sev_order.get(alert.severity, 0)
        e_sev = sev_order.get(entry.severity, 0)
        if a_sev == e_sev:
            score += 2
            reasons.append("severity_exact")
        elif abs(a_sev - e_sev) == 1:
            score += 1
            reasons.append("severity_adjacent")

    if alert.asset_id and entry.asset_type:
        asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
        if asset and asset.type and asset.type.lower() == entry.asset_type.lower():
            score += 3
            reasons.append("asset_type_match")

    alert_msg = (alert.message or "").lower()
    symptom = (entry.symptom or "").lower()
    if symptom and alert_msg:
        symptom_words = set(re.findall(r'[\u4e00-\u9fa5]{2,}|[a-z]+', symptom))
        msg_words = set(re.findall(r'[\u4e00-\u9fa5]{2,}|[a-z]+', alert_msg))
        overlap = symptom_words & msg_words
        if overlap:
            ratio = len(overlap) / max(len(symptom_words), 1)
            score += round(ratio * 4, 2)
            reasons.append("text_overlap:%s" % ",".join(list(overlap)[:3]))

    return score, reasons


def _rule_recommend(db, alert, limit=10):
    kbs = db.query(KnowledgeBase).all()
    scored = []
    for entry in kbs:
        score, reasons = _score_rule(alert, entry, db)
        if score > 0:
            scored.append((score, entry, reasons))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def _rag_search(alert, top_k=5):
    try:
        from app.services.rag_engine_v2 import hybrid_search
        query_parts = []
        if alert.metric_name:
            query_parts.append(alert.metric_name.replace("_", " "))
        if alert.message:
            query_parts.append(alert.message[:200])
        query = " ".join(query_parts)
        if not query.strip():
            return []
        return hybrid_search(query, top_k=top_k)
    except Exception as e:
        print("[smart_recommend] RAG search failed: %s" % e)
        return []


def _merge_results(rule_recs, rag_results, rule_weight=0.5, rag_weight=0.5):
    merged = []
    seen = {}

    max_rule = max((r[0] for r in rule_recs), default=1) or 1

    for score, entry, reasons in rule_recs:
        norm = round(score / max_rule, 4)
        item = {
            "source": "rule",
            "title": entry.title,
            "score": min(round(norm * rule_weight, 4), 1.0),
            "raw_score": round(score, 2),
            "kb": _kb_brief(entry),
            "linked": False,
            "content": "",
            "doc_title": "",
            "reasons": reasons,
        }
        merged.append(item)
        seen[entry.title] = item

    rag_only = []
    rule_seen = set(seen.keys())
    for r in rag_results:
        title = r.get("doc_title", "")
        rag_s = min(r.get("score", 0), 1.0)
        if title and title in rule_seen:
            old = seen[title]
            old["score"] = min(round(old["score"] + rag_s * rag_weight, 4), 1.0)
            old["source"] = "both"
            if not old["content"] and r.get("content"):
                old["content"] = r["content"][:500]
            continue
        item = {
            "source": "rag",
            "title": title or "RAG 文档片段",
            "score": min(round(rag_s * rag_weight, 4), 1.0),
            "raw_score": round(rag_s, 4),
            "kb": {
                "id": 0, "title": title,
                "symptom": "", "root_cause": "", "solution": "",
                "tags": r.get("tags", ""), "severity": r.get("severity", ""),
                "asset_type": r.get("asset_type", ""),
            },
            "linked": False,
            "content": r.get("content", "")[:500],
            "doc_title": title,
            "reasons": ["rag_semantic"],
        }
        rag_only.append(item)

    rule_only = [m for m in merged if m["source"] != "both"]
    both_items = [m for m in merged if m["source"] == "both"]

    rule_only.sort(key=lambda x: x["score"], reverse=True)

    rag_dedup = {}
    for item in rag_only:
        t = item["doc_title"] or item["title"]
        if t not in rag_dedup or item["score"] > rag_dedup[t]["score"]:
            rag_dedup[t] = item
    rag_only = sorted(rag_dedup.values(), key=lambda x: x["score"], reverse=True)

    both_items.sort(key=lambda x: x["score"], reverse=True)

    return both_items + rule_only + rag_only


@router.get("/api/recommend")
def api_recommend(alert_id: int = 0, limit: int = 5, db: Session = Depends(get_db)):
    try:
        if not alert_id:
            return JSONResponse({"error": "alert_id is required", "alert_id": 0, "recommendations": []}, status_code=400)
        selected_alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not selected_alert:
            return JSONResponse({"error": "alert not found", "alert_id": alert_id, "recommendations": []}, status_code=404)

        rule_recs = _rule_recommend(db, selected_alert, limit=min(limit, 20))
        rag_results = _rag_search(selected_alert, top_k=min(limit, 5))

        merged = _merge_results(rule_recs, rag_results)

        for item in merged[:limit]:
            kb_id = item["kb"].get("id")
            if kb_id:
                linked = db.query(AlertKbLink).filter(
                    AlertKbLink.alert_id == alert_id,
                    AlertKbLink.kb_id == kb_id).first()
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
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e), "alert_id": alert_id, "recommendations": []}, status_code=500)
