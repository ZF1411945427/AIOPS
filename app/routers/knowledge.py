from fastapi import APIRouter, Depends, Body, Query
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import knowledge_service, rag_service
from app.models import KnowledgeBase, KbDocument, Runbook
from sqlalchemy.orm import Session
from sqlalchemy import or_

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _kb_to_dict(kb):
    return {
        "id": kb.id,
        "title": kb.title,
        "symptom": kb.symptom or "",
        "root_cause": kb.root_cause or "",
        "solution": kb.solution or "",
        "tags": kb.tags or "",
        "severity": kb.severity or "warning",
        "asset_type": kb.asset_type or "",
        "source_type": kb.source_type or "manual",
        "version_number": kb.version_number or 1,
        "change_log": kb.change_log or "",
        "created_at": kb.created_at.strftime("%Y-%m-%d %H:%M:%S") if kb.created_at else None,
        "updated_at": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S") if kb.updated_at else None,
    }


@router.get("/api/list")
def api_kb_list(
    search: str = "",
    tags: str = "",
    db: Session = Depends(get_db)):
    try:
        items = knowledge_service.list_kb(db, tags)
        if search:
            s = search.lower()
            items = [it for it in items if s in (it.title or "").lower()]
        return JSONResponse({
            "items": [_kb_to_dict(it) for it in items],
            "total": len(items),
            "search": search,
            "tags": tags,
        })
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": []}, status_code=200)


@router.get("/api/unified-search")
def api_unified_search(
    q: str = Query("", description="搜索关键词"),
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """跨知识库/文档/Runbook 统一搜索"""
    try:
        query = q.strip()
        if not query:
            return JSONResponse({"items": [], "total": 0})

        results = {"kb": [], "documents": [], "runbooks": []}

        kb_items = db.query(KnowledgeBase).filter(
            or_(
                KnowledgeBase.title.ilike(f"%{query}%"),
                KnowledgeBase.symptom.ilike(f"%{query}%"),
                KnowledgeBase.root_cause.ilike(f"%{query}%"),
                KnowledgeBase.solution.ilike(f"%{query}%"),
                KnowledgeBase.tags.ilike(f"%{query}%"),
            )
        ).limit(top_k).all()
        for kb in kb_items:
            results["kb"].append({
                "id": kb.id, "title": kb.title,
                "symptom": (kb.symptom or "")[:200],
                "root_cause": (kb.root_cause or "")[:200],
                "type": "knowledge_base",
            })

        doc_items = db.query(KbDocument).filter(
            or_(
                KbDocument.title.ilike(f"%{query}%"),
                KbDocument.content.ilike(f"%{query}%"),
                KbDocument.tags.ilike(f"%{query}%"),
            )
        ).limit(top_k).all()
        for d in doc_items:
            results["documents"].append({
                "id": d.id, "title": d.title,
                "content": (d.content or "")[:300],
                "type": "document",
            })

        rb_items = db.query(Runbook).filter(
            or_(
                Runbook.title.ilike(f"%{query}%"),
                Runbook.symptom.ilike(f"%{query}%"),
                Runbook.diagnosis.ilike(f"%{query}%"),
                Runbook.tags.ilike(f"%{query}%"),
            )
        ).limit(top_k).all()
        for rb in rb_items:
            results["runbooks"].append({
                "id": rb.id, "title": rb.title,
                "symptom": (rb.symptom or "")[:200],
                "type": "runbook",
            })

        total = sum(len(v) for v in results.values())
        return JSONResponse({"items": results, "total": total, "query": query})
    except Exception as e:
        return JSONResponse({"warning": str(e), "items": [], "total": 0}, status_code=200)


@router.get("/api/{kb_id}")
def api_kb_detail(kb_id: int, db: Session = Depends(get_db)):
    try:
        item = knowledge_service.get_kb(db, kb_id)
        if not item:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(_kb_to_dict(item))
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/create")
def api_kb_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        kb = knowledge_service.create_kb(db, {
            "title": payload.get("title", ""),
            "symptom": payload.get("symptom", ""),
            "root_cause": payload.get("root_cause", ""),
            "solution": payload.get("solution", ""),
            "tags": payload.get("tags", ""),
            "severity": payload.get("severity", "warning"),
            "asset_type": payload.get("asset_type", ""),
            "change_log": payload.get("change_log", "初始版本"),
        })
        return JSONResponse({"ok": True, "id": kb.id, "item": _kb_to_dict(kb)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/{kb_id}/update")
def api_kb_update(kb_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        old_kb = knowledge_service.get_kb(db, kb_id)
        if not old_kb:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        data = {
            "title": payload.get("title", old_kb.title),
            "symptom": payload.get("symptom", old_kb.symptom or ""),
            "root_cause": payload.get("root_cause", old_kb.root_cause or ""),
            "solution": payload.get("solution", old_kb.solution or ""),
            "tags": payload.get("tags", old_kb.tags or ""),
            "severity": payload.get("severity", old_kb.severity or "warning"),
            "asset_type": payload.get("asset_type", old_kb.asset_type or ""),
        }
        change_log = payload.get("change_log", "")
        if change_log:
            data["change_log"] = change_log
            data["version_number"] = (old_kb.version_number or 1) + 1
        kb = knowledge_service.update_kb(db, kb_id, data)
        if not kb:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "id": kb.id, "item": _kb_to_dict(kb)})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/{kb_id}/delete")
def api_kb_delete(kb_id: int, db: Session = Depends(get_db)):
    try:
        knowledge_service.delete_kb(db, kb_id)
        return JSONResponse({"ok": True, "id": kb_id})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)

