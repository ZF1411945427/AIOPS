"""K8S 离线集群部署 API - 对标 Pixiu 一键建集群。

契约见 CONTRACT.md 第十三章。prefix=/k8s-offline/api，WS=/k8s-offline/ws。
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OfflineRepoBundle, OfflineRegistry, Asset, K8sClusterPlan
from app.services import k8s_offline_deploy_service as svc

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
def api_precheck_plan(plan_id: int, test_ssh: bool = True, db: Session = Depends(get_db)):
    return svc.precheck_plan(db, plan_id, test_ssh=test_ssh)


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


@router.post("/api/plans/{plan_id}/to-assets")
def api_plan_to_assets(plan_id: int, db: Session = Depends(get_db)):
    """部署成功后，将集群注册为资产管理中的 K8s 资产（DataSource type=kubernetes）。
    幂等：已存在同名数据源则更新其 endpoint/auth_config，否则新建。"""
    from app.models import K8sClusterNode
    p = db.query(K8sClusterPlan).filter(K8sClusterPlan.id == plan_id).first()
    if not p:
        return {"ok": False, "message": "计划不存在"}
    if p.status != "succeeded":
        return {"ok": False, "message": "仅部署成功的集群可注册为 K8s 资产，当前状态: " + (p.status or "unknown")}
    nodes = db.query(K8sClusterNode).filter(K8sClusterNode.plan_id == plan_id).all()
    masters = [n for n in nodes if n.host_role == "master"]
    if not masters:
        return {"ok": False, "message": "未找到 master 节点，无法确定 API Server 地址"}
    conn = svc._resolve_node_conn(db, masters[0])
    api_ip = conn.get("ip")
    ds = svc._create_platform_datasource(db, p, api_ip)
    if not ds:
        return {"ok": False, "message": "缺少 kubeconfig，无法注册 K8s 资产"}
    return {
        "ok": True,
        "message": "已注册为 K8s 资产(数据源)",
        "datasource": {"id": ds.id, "name": ds.name, "type": ds.type,
                       "endpoint": ds.endpoint or "", "enabled": bool(ds.enabled)},
    }


# ─────────────────── WebSocket 流式部署 ───────────────────

@router.websocket("/ws/plans/{plan_id}/deploy")
async def ws_deploy(websocket: WebSocket, plan_id: int):
    await websocket.accept()
    import asyncio
    import threading
    from app.database import get_session_for, get_db_mode

    import json as _json

    loop = asyncio.get_running_loop()
    disconnected = threading.Event()

    def send_event(evt: str):
        if disconnected.is_set():
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(websocket.send_text(evt), loop)
            fut.result(timeout=5)
        except Exception:
            disconnected.set()

    def producer():
        db = get_session_for(get_db_mode())()
        try:
            # 即使 WS 断开也持续跑完部署(写入 DB 日志)，只是不再推送
            for event in svc.run_deploy(db, plan_id):
                try:
                    send_event(_json.dumps(event, ensure_ascii=False))
                except Exception:
                    pass
        except Exception as e:
            try:
                send_event(_json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False))
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
    # 注意：断开 WS 只结束推送连接，不停止部署任务。
    # 部署由后台线程持续执行，除非显式调用 /stop 停止。
