from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse

from app.database import get_db
from app.services import knowledge_service
from sqlalchemy.orm import Session

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
        return JSONResponse({"error": str(e), "items": []}, status_code=500)


@router.get("/api/{kb_id}")
def api_kb_detail(kb_id: int, db: Session = Depends(get_db)):
    try:
        item = knowledge_service.get_kb(db, kb_id)
        if not item:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(_kb_to_dict(item))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
        })
        return JSONResponse({"ok": True, "id": kb.id, "item": _kb_to_dict(kb)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/{kb_id}/update")
def api_kb_update(kb_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        kb = knowledge_service.update_kb(db, kb_id, {
            "title": payload.get("title", ""),
            "symptom": payload.get("symptom", ""),
            "root_cause": payload.get("root_cause", ""),
            "solution": payload.get("solution", ""),
            "tags": payload.get("tags", ""),
            "severity": payload.get("severity", "warning"),
            "asset_type": payload.get("asset_type", ""),
        })
        if not kb:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "id": kb.id, "item": _kb_to_dict(kb)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/{kb_id}/delete")
def api_kb_delete(kb_id: int, db: Session = Depends(get_db)):
    try:
        knowledge_service.delete_kb(db, kb_id)
        return JSONResponse({"ok": True, "id": kb_id})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
