from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Runbook

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


def _rb_to_dict(rb):
    return {
        "id": rb.id,
        "title": rb.title,
        "category": rb.category or "general",
        "symptom": rb.symptom or "",
        "diagnosis": rb.diagnosis or "",
        "steps": rb.steps or "",
        "tags": rb.tags or "",
        "severity": rb.severity or "warning",
        "asset_type": rb.asset_type or "",
        "created_at": rb.created_at.strftime("%Y-%m-%d %H:%M:%S") if rb.created_at else None,
        "updated_at": rb.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rb.updated_at else None,
    }


@router.get("/api/list")
def api_list_runbooks(category: str = "", db: Session = Depends(get_db)):
    try:
        q = db.query(Runbook)
        if category:
            q = q.filter(Runbook.category == category)
        runbooks = q.order_by(Runbook.updated_at.desc()).all()
        cats = [r[0] for r in db.query(Runbook.category).distinct().all() if r[0]]
        return JSONResponse({
            "items": [_rb_to_dict(rb) for rb in runbooks],
            "total": len(runbooks),
            "category": category,
            "categories": cats,
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=500)


@router.get("/api/{rb_id}")
def api_runbook_detail(rb_id: int, db: Session = Depends(get_db)):
    try:
        rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
        if not rb:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(_rb_to_dict(rb))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/create")
def api_create_runbook(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        rb = Runbook(
            title=payload.get("title", ""),
            category=payload.get("category", "general"),
            symptom=payload.get("symptom", ""),
            diagnosis=payload.get("diagnosis", ""),
            steps=payload.get("steps", ""),
            tags=payload.get("tags", ""),
            severity=payload.get("severity", "warning"),
            asset_type=payload.get("asset_type", ""))
        db.add(rb)
        db.commit()
        db.refresh(rb)
        return JSONResponse({"ok": True, "id": rb.id, "item": _rb_to_dict(rb)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/{rb_id}/update")
def api_update_runbook(rb_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
        if not rb:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        rb.title = payload.get("title", rb.title)
        rb.category = payload.get("category", rb.category)
        rb.symptom = payload.get("symptom", rb.symptom)
        rb.diagnosis = payload.get("diagnosis", rb.diagnosis)
        rb.steps = payload.get("steps", rb.steps)
        rb.tags = payload.get("tags", rb.tags)
        rb.severity = payload.get("severity", rb.severity)
        rb.asset_type = payload.get("asset_type", rb.asset_type)
        db.commit()
        db.refresh(rb)
        return JSONResponse({"ok": True, "id": rb.id, "item": _rb_to_dict(rb)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/{rb_id}/delete")
def api_delete_runbook(rb_id: int, db: Session = Depends(get_db)):
    try:
        rb = db.query(Runbook).filter(Runbook.id == rb_id).first()
        if rb:
            db.delete(rb)
            db.commit()
        return JSONResponse({"ok": True, "id": rb_id})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
