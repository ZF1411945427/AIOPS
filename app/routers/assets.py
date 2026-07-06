import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.template_utils import get_templates
from app.services import asset_service
from app.services.connection_service import ConnectionTester

router = APIRouter(prefix="/assets", tags=["assets"])
templates = get_templates()


@router.get("/api/list")
def asset_api_list(search: str = "", ci_type: str = "", db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db, search, "", ci_type)
    return JSONResponse([{
        "id": a.id, "name": a.name, "type": a.type, "ci_type": getattr(a, 'ci_type', None),
        "ip": a.ip, "status": a.status,
        "connection_type": getattr(a, 'connection_type', None),
        "last_checked": a.last_checked.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, 'last_checked', None) else None,
        "latency_ms": getattr(a, 'latency_ms', None),
        "k8s_cluster": getattr(a, 'k8s_cluster', None) or "",
        "tags": getattr(a, 'tags', None) or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if getattr(a, 'created_at', None) else None,
    } for a in assets])


@router.get("/api/ci-types")
def asset_api_ci_types(db: Session = Depends(get_db)):
    """返回可用 CI 类型列表."""
    ci_types = ["server", "vm", "node", "cluster", "namespace", "deployment", "statefulset", "daemonset", "pod", "container", "service", "ingress", "pvc"]
    return JSONResponse(ci_types)


@router.post("/api/{asset_id}/delete")
def api_asset_delete(asset_id: int, db: Session = Depends(get_db)):
    asset_service.delete_asset(db, asset_id)
    return JSONResponse({"ok": True})


@router.post("/api/create")
def api_asset_create(payload: dict, db: Session = Depends(get_db)):
    """新建资产。payload 字段：name/ci_type/ip/status/tags/k8s_cluster/connection_type/ssh_user/ssh_password/ssh_port/parent_id"""
    import json as _json
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "message": "资产名称不能为空"}, status_code=400)
    ci_type = payload.get("ci_type") or "server"
    connection_type = payload.get("connection_type") or "ssh"
    ssh_user = payload.get("ssh_user") or "root"
    ssh_password = payload.get("ssh_password") or ""
    ssh_port = int(payload.get("ssh_port") or 22)
    config = {"ssh_user": ssh_user, "ssh_password": ssh_password, "ssh_port": ssh_port}
    ip = payload.get("ip") or ""
    status = payload.get("status") or "offline"
    # 保存前探测一次连接，连通则 online
    probe_status = status
    if ip and connection_type:
        try:
            result = ConnectionTester.test(connection_type, ip, config)
            probe_status = "online" if result.get("ok") else "offline"
        except Exception:
            probe_status = status
    data = {
        "name": name,
        "type": ci_type,
        "ci_type": ci_type,
        "ip": ip,
        "status": probe_status,
        "tags": payload.get("tags") or "",
        "k8s_cluster": payload.get("k8s_cluster") or "",
        "connection_type": connection_type,
        "connection_config": _json.dumps(config),
    }
    if payload.get("parent_id"):
        data["parent_id"] = int(payload["parent_id"])
    asset = asset_service.create_asset(db, data)
    return JSONResponse({"ok": True, "id": asset.id, "status": probe_status})


@router.post("/api/{asset_id}/update")
def api_asset_update(asset_id: int, payload: dict, db: Session = Depends(get_db)):
    """更新资产。payload 字段同 create（不含 name 必填校验，但建议传）。"""
    import json as _json
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    data = {}
    for k in ("name", "ci_type", "ip", "status", "tags", "k8s_cluster", "connection_type"):
        if k in payload:
            data[k] = payload[k]
    if "ci_type" in data and "type" not in data:
        data["type"] = data["ci_type"]
    # 连接配置
    if any(k in payload for k in ("ssh_user", "ssh_password", "ssh_port")):
        old_cfg = {}
        try:
            old_cfg = _json.loads(asset.connection_config) if asset.connection_config else {}
        except Exception:
            old_cfg = {}
        config = {
            "ssh_user": payload.get("ssh_user", old_cfg.get("ssh_user", "root")),
            "ssh_password": payload.get("ssh_password", old_cfg.get("ssh_password", "")),
            "ssh_port": int(payload.get("ssh_port", old_cfg.get("ssh_port", 22))),
        }
        data["connection_config"] = _json.dumps(config)
        # 更新连接配置后重新探测
        if data.get("ip", asset.ip) and data.get("connection_type", asset.connection_type):
            try:
                result = ConnectionTester.test(data.get("connection_type", asset.connection_type), data.get("ip", asset.ip), config)
                data["status"] = "online" if result.get("ok") else "offline"
            except Exception:
                pass
    if "parent_id" in payload:
        data["parent_id"] = int(payload["parent_id"]) if payload["parent_id"] else None
    updated = asset_service.update_asset(db, asset_id, data)
    return JSONResponse({"ok": bool(updated), "status": data.get("status", asset.status)})


@router.get("/api/{asset_id}/detail")
def api_asset_detail(asset_id: int, db: Session = Depends(get_db)):
    """获取资产详情（含连接配置解析），供编辑表单回填。"""
    import json as _json
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    config = {}
    try:
        config = _json.loads(asset.connection_config) if asset.connection_config else {}
    except Exception:
        config = {}
    return JSONResponse({
        "id": asset.id, "name": asset.name, "type": asset.type, "ci_type": asset.ci_type,
        "ip": asset.ip, "status": asset.status, "tags": asset.tags or "",
        "k8s_cluster": asset.k8s_cluster or "", "parent_id": asset.parent_id,
        "connection_type": asset.connection_type or "ssh",
        "ssh_user": config.get("ssh_user", "root"),
        "ssh_password": config.get("ssh_password", ""),
        "ssh_port": config.get("ssh_port", 22),
    })


@router.post("/api/test-connection")
def test_connection(
    connection_type: str = Form("ssh"),
    host: str = Form(""),
    connection_config: str = Form("{}")):
    try:
        config = json.loads(connection_config) if connection_config else {}
    except:
        config = {}
    result = ConnectionTester.test(connection_type, host, config)
    return JSONResponse(result)


