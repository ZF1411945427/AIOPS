from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import ab_test_service

router = APIRouter(prefix="/agent/api/ab-test", tags=["ab_test"])


def _test_to_dict(t):
    return {
        "id": t.id,
        "name": t.name,
        "provider_a_id": t.provider_a_id,
        "provider_b_id": t.provider_b_id,
        "model_a": t.model_a,
        "model_b": t.model_b,
        "split_ratio": t.split_ratio,
        "metric": t.metric,
        "status": t.status,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None,
    }


@router.get("/configs")
def list_configs(status: str = Query(""), db: Session = Depends(get_db)):
    tests = ab_test_service.list_tests(db, status=status)
    return JSONResponse({"items": [_test_to_dict(t) for t in tests]})


@router.post("/configs")
def create_config(payload: dict, db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    test_id = ab_test_service.create_test(db, data)
    return JSONResponse({"ok": True, "test_id": test_id})


@router.get("/configs/{test_id}")
def get_config(test_id: int, db: Session = Depends(get_db)):
    t = ab_test_service.get_test(test_id, db)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(_test_to_dict(t))


@router.put("/configs/{test_id}")
def update_config(test_id: int, payload: dict, db: Session = Depends(get_db)):
    data = {k: v for k, v in payload.items() if k not in ("id", "created_at")}
    t = ab_test_service.update_test(test_id, data, db)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/results/{test_id}")
def get_results(test_id: int, db: Session = Depends(get_db)):
    results = ab_test_service.get_test_results(test_id, db)
    return JSONResponse(results)


@router.get("/provider/{test_id}")
def get_provider_for_session(test_id: int, session_id: int = None, db: Session = Depends(get_db)):
    provider_id, group, cfg = ab_test_service.get_provider_for_request(test_id, session_id, db)
    if provider_id is None:
        return JSONResponse({"error": "No active test found"}, status_code=404)
    return JSONResponse({"provider_id": provider_id, "group": group, "test_name": cfg.name if cfg else ""})
