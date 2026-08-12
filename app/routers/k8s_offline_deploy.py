"""K8S 离线集群部署 API - 对标 Pixiu 一键建集群。

契约见 CONTRACT.md 第十三章。prefix=/k8s-offline/api，WS=/k8s-offline/ws。
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, OfflineRepoBundle, OfflineRegistry, Asset, K8sClusterPlan
from app.services import k8s_offline_deploy_service as svc
from app.logger import logger

router = APIRouter(prefix="/k8s-offline", tags=["k8s-offline"])


def _user_id(request=None) -> int:
    if request is None:
        return 0
    return getattr(request, "session", {}).get("user_id", 0) if hasattr(request, "session") else 0


# ─────────────────── 元数据(离线仓库/资产下拉) ───────────────────

@router.get("/api/meta")
def api_meta(db: Session = Depends(get_db)):
    bundles = db.query(OfflineRepoBundle).filter(
        OfflineRepoBundle.status == "loaded").order_by(OfflineRepoBundle.id.desc()).all()
    registries = db.query(OfflineRegistry).order_by(OfflineRegistry.id.desc()).all()
    assets = db.query(Asset).filter(Asset.connection_type == "ssh").order_by(Asset.id.desc()).all()
    return {
        "bundles": [{"id": b.id, "name": b.name, "version": b.version or "",
                     "os_type": b.os_type or "", "os_version": b.os_version or ""} for b in bundles],
        "registries": [{"id": r.id, "name": r.name, "registry_url": r.registry_url,
                        "is_default": bool(r.is_default)} for r in registries],
        "assets": [{"id": a.id, "name": a.name, "ip": a.ip or "", "ci_type": a.ci_type} for a in assets],
    }


# ─────────────────── 计划 CRUD ───────────────────

@router.get("/api/plans")
def api_list_plans(status: str = "", page: int = 1, per_page: int = 20,
                   db: Session = Depends(get_db)):
    return svc.list_plans(db, status=status, page=page, per_page=per_page)


@router.get("/api/plans/{plan_id}")
def api_get_plan(plan_id: int, include_kubeconfig: bool = False, db: Session = Depends(get_db)):
    plan = svc.get_plan(db, plan_id, include_kubeconfig=include_kubeconfig)
    if not plan:
        return {"ok": False, "message": "计划不存在"}
    return plan


@router.post("/api/plans/create")
def api_create_plan(payload: dict, db: Session = Depends(get_db)):
    try:
        return {"ok": True, "plan": svc.create_plan(db, payload)}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


@router.post("/api/plans/{plan_id}/update")
def api_update_plan(plan_id: int, payload: dict, db: Session = Depends(get_db)):
    try:
        plan = svc.update_plan(db, plan_id, payload)
        if not plan:
            return {"ok": False, "message": "计划不存在"}
        return {"ok": True, "plan": plan}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


@router.post("/api/plans/{plan_id}/delete")
def api_delete_plan(plan_id: int, db: Session = Depends(get_db)):
    try:
        return {"ok": svc.delete_plan(db, plan_id)}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


@router.post("/api/plans/{plan_id}/precheck")
def api_precheck_plan(plan_id: int, db: Session = Depends(get_db)):
    return svc.precheck_plan(db, plan_id)


@router.post("/api/plans/{plan_id}/validate")
def api_validate_plan(plan_id: int, test_ssh: bool = True, db: Session = Depends(get_db)):
    return svc.validate_plan(db, plan_id, test_ssh=test_ssh)


@router.post("/api/plans/{plan_id}/stop")
def api_stop_plan(plan_id: int, db: Session = Depends(get_db)):
    return svc.stop_execution(db, plan_id)


@router.get("/api/plans/{plan_id}/kubeconfig")
def api_get_kubeconfig(plan_id: int, db: Session = Depends(get_db)):
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return {"ok": False, "message": "计划不存在"}
    return {"ok": True, "kubeconfig": p.kubeconfig or ""}


# ─────────────────── WebSocket 流式部署 ───────────────────

@router.websocket("/ws/plans/{plan_id}/deploy")
async def ws_deploy(websocket: WebSocket, plan_id: int):
    await websocket.accept()
    import threading
    from app.database import get_session_for, get_db_mode

    import json as _json

    def producer():
        db = get_session_for(get_db_mode())()
        try:
            for event in svc.run_deploy(db, plan_id):
                try:
                    websocket.send_text(_json.dumps(event, ensure_ascii=False))
                except Exception:
                    return
        except Exception as e:
            try:
                websocket.send_text(_json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False))
            except Exception:
                pass
        finally:
            db.close()

    t = threading.Thread(target=producer, daemon=True)
    t.start()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        db = get_session_for(get_db_mode())()
        try:
            svc.stop_execution(db, plan_id)
        finally:
            db.close()
