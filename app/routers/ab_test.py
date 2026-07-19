import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import ab_test_service
from app.models import AIProvider

logger = logging.getLogger(__name__)

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
        "updated_at": t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else None,
    }


@router.get("/configs")
def list_configs(status: str = Query(""), db: Session = Depends(get_db)):
    tests = ab_test_service.list_tests(db, status=status)
    return JSONResponse({"items": [_test_to_dict(t) for t in tests]})


@router.post("/configs")
def create_config(payload: dict, db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "实验名称不能为空"}, status_code=400)
    pa = payload.get("provider_a_id")
    pb = payload.get("provider_b_id")
    if not pa or not pb:
        return JSONResponse({"ok": False, "error": "A 组和 B 组 Provider 都必须选择"}, status_code=400)
    if pa == pb:
        return JSONResponse({"ok": False, "error": "A 组和 B 组不能选择同一个 Provider"}, status_code=400)

    # 校验 provider 存在
    for pid in (pa, pb):
        p = db.query(AIProvider).filter(AIProvider.id == pid).first()
        if not p:
            return JSONResponse({"ok": False, "error": f"Provider #{pid} 不存在"}, status_code=400)

    # 自动填充 model_a / model_b
    pa_obj = db.query(AIProvider).filter(AIProvider.id == pa).first()
    pb_obj = db.query(AIProvider).filter(AIProvider.id == pb).first()
    data = {
        "name": name,
        "provider_a_id": pa,
        "provider_b_id": pb,
        "model_a": pa_obj.default_model or "",
        "model_b": pb_obj.default_model or "",
        "split_ratio": payload.get("split_ratio") or "50/50",
        "metric": payload.get("metric") or "latency",
        "status": payload.get("status") or "active",
    }

    # 创建前若 status=active，先停止其他 active 实验，保证全局只有 1 个 active
    if data["status"] == "active":
        existing_active = ab_test_service.list_tests(db, status="active")
        for o in existing_active:
            ab_test_service.update_test(o.id, {"status": "stopped"}, db)

    try:
        test_id = ab_test_service.create_test(db, data)
        return JSONResponse({"ok": True, "test_id": test_id})
    except Exception as e:
        logger.exception("create_config failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/configs/{test_id}")
def get_config(test_id: int, db: Session = Depends(get_db)):
    t = ab_test_service.get_test(test_id, db)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(_test_to_dict(t))


@router.put("/configs/{test_id}")
def update_config(test_id: int, payload: dict, db: Session = Depends(get_db)):
    t = ab_test_service.get_test(test_id, db)
    if not t:
        return JSONResponse({"error": "Not found"}, status_code=404)

    # 若改动涉及 provider，校验 A≠B
    new_pa = payload.get("provider_a_id", t.provider_a_id)
    new_pb = payload.get("provider_b_id", t.provider_b_id)
    if new_pa and new_pb and new_pa == new_pb:
        return JSONResponse({"ok": False, "error": "A 组和 B 组不能选择同一个 Provider"}, status_code=400)

    try:
        ab_test_service.update_test(test_id, payload, db)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception("update_config failed")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.delete("/configs/{test_id}")
def delete_config(test_id: int, db: Session = Depends(get_db)):
    ok = ab_test_service.delete_test(test_id, db)
    if not ok:
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
