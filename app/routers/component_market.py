"""组件应用商店 API 路由 (对标 Bitnami Catalog / OOTB 组件目录)

端点:
  GET    /component-market/api/catalog           — 组件目录列表(?category=&keyword=)
  GET    /component-market/api/catalog/{id}      — 组件详情
  GET    /component-market/api/render            — 渲染部署配方(不执行)
  POST   /component-market/api/deploy            — 记录一键部署
  GET    /component-market/api/installs          — 安装记录列表(?asset_id=)
  GET    /component-market/api/installs/{id}     — 安装记录详情
  POST   /component-market/api/installs/{id}/config  — 配置优化检查
  POST   /component-market/api/installs/{id}/health  — 高可用/健康检查
  POST   /component-market/api/installs/{id}/vuln    — 漏洞检查
  POST   /component-market/api/installs/{id}/analyze — AI 综合分析
  DELETE /component-market/api/installs/{id}     — 删除安装记录
  GET    /component-market/api/stats             — 统计
"""
from fastapi import APIRouter, Query, Body

from app.database import get_db
from app.services.component_catalog_service import (
    list_components, get_component, get_deploy_render, seed_builtin_components,
    record_install, list_installs, get_install, delete_install, update_install_status,
    check_config, check_health, check_vuln, ai_analyze, get_stats, full_health_check,
    batch_full_check, deploy_docker,
)

router = APIRouter(prefix="/component-market", tags=["ComponentMarket"])


@router.on_event("startup")
def _on_startup():
    db = next(get_db())
    try:
        seed_builtin_components(db)
    except Exception:
        pass


@router.get("/api/stats")
def api_stats():
    db = next(get_db())
    return get_stats(db)


@router.get("/api/catalog")
def api_catalog(category: str = Query(""), keyword: str = Query("")):
    db = next(get_db())
    return {"items": list_components(db, category=category, keyword=keyword)}


@router.get("/api/catalog/{component_id}")
def api_catalog_detail(component_id: int):
    db = next(get_db())
    item = get_component(db, component_id)
    if not item:
        return {"ok": False, "error": "组件不存在"}
    return {"ok": True, "item": item}


@router.get("/api/render")
def api_render(component_id: int = Query(...), deploy_type: str = Query("docker"),
               host: str = Query(""), namespace: str = Query("default"), release: str = Query("")):
    db = next(get_db())
    comp = get_component(db, component_id)
    if not comp:
        return {"ok": False, "error": "组件不存在"}
    result = get_deploy_render(comp, deploy_type, {
        "host": host, "namespace": namespace, "release": release,
    })
    return result


@router.post("/api/deploy")
def api_deploy(body: dict = Body(...)):
    """一键部署组件到目标机。
    - docker/native: 真实执行(docker compose up -d / 脚本), 支持代理注入
    - helm/ha: 落记录并回显配方(依赖 K8s/helm 引擎)
    body: {component_id, asset_id, deploy_type, namespace?, release?, deploy_path?, port?,
           http_proxy?, https_proxy?, no_proxy?}"""
    from app.database import get_db
    from app.models import Asset
    db = next(get_db())
    comp = get_component(db, body.get("component_id"))
    if not comp:
        return {"ok": False, "error": "组件不存在"}
    asset_id = body.get("asset_id")
    deploy_type = body.get("deploy_type", "docker")
    if deploy_type not in (comp.get("deploy_types") or []):
        return {"ok": False, "error": f"组件不支持部署方式 {deploy_type}"}
    if not asset_id:
        return {"ok": False, "error": "缺少目标机 asset_id"}

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"ok": False, "error": "目标机资产不存在"}

    deploy_path = body.get("deploy_path", "").strip()
    if not deploy_path:
        deploy_path = f"/data/aiops-components/{comp['name']}"
    port = body.get("port") or comp.get("default_port") or 0
    http_proxy = body.get("http_proxy") or ""
    https_proxy = body.get("https_proxy") or ""
    no_proxy = body.get("no_proxy") or "127.0.0.1,localhost,.local"

    # 先落记录(状态 deploying), 真部署成功后置 running, 失败置 failed
    inst = record_install(
        db, comp["id"], comp["name"], asset_id, deploy_type=deploy_type,
        deploy_path=deploy_path, release_name=body.get("release", ""),
        name_space=body.get("namespace", ""), port=port,
    )
    update_install_status(db, inst["id"], "deploying", "开始部署, 目标机: %s" % (asset.ip or asset.name))

    if deploy_type == "docker":
        ok, log = deploy_docker(asset, comp, port, deploy_path,
                                http_proxy=http_proxy, https_proxy=https_proxy, no_proxy=no_proxy,
                                compose=body.get("compose") or "")
        update_install_status(db, inst["id"], "running" if ok else "failed", log)
        return {"ok": ok, "install": get_install(db, inst["id"]), "component": comp["display_name"],
                "deploy_type": deploy_type, "deploy_log": log}
    elif deploy_type == "native":
        ok, out = _exec_native(asset, comp.get("native_script") or "")
        update_install_status(db, inst["id"], "running" if ok else "failed", out)
        return {"ok": ok, "install": get_install(db, inst["id"]), "component": comp["display_name"],
                "deploy_type": deploy_type, "deploy_log": out}
    else:
        # helm / ha: 仅落记录并回显配方(依赖 K8s/helm 引擎)
        update_install_status(db, inst["id"], "deploying", "helm/ha 部署依赖 K8s/helm 引擎, 已建记录待执行")
        return {"ok": True, "install": get_install(db, inst["id"]), "component": comp["display_name"],
                "deploy_type": deploy_type, "message": "helm/ha 部署需通过 K8s/helm 引擎执行"}


def _exec_native(asset, script: str) -> tuple:
    """目标机执行传统部署脚本(yum/apt)。"""
    from app.services.component_catalog_service import _exec_ssh
    if not script:
        return (False, "组件未提供原生安装脚本")
    cmd = f"set -e; {script} 2>&1 | tail -20; echo __RC__=$?"
    return _exec_ssh(asset, cmd, timeout=300)


@router.get("/api/installs")
def api_installs(asset_id: int = Query(None)):
    db = next(get_db())
    return {"items": list_installs(db, asset_id=asset_id)}


@router.get("/api/installs/{install_id}")
def api_install_detail(install_id: int):
    db = next(get_db())
    item = get_install(db, install_id)
    if not item:
        return {"ok": False, "error": "安装记录不存在"}
    return {"ok": True, "item": item}


@router.post("/api/installs/{install_id}/config")
def api_config_check(install_id: int):
    db = next(get_db())
    try:
        result = check_config(db, install_id)
        return {"ok": True, "result": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/installs/{install_id}/health")
def api_health_check(install_id: int):
    db = next(get_db())
    try:
        result = check_health(db, install_id)
        return {"ok": True, "result": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/installs/{install_id}/vuln")
def api_vuln_check(install_id: int):
    db = next(get_db())
    result = check_vuln(db, install_id)
    if result is None:
        return {"ok": False, "error": "安装记录不存在"}
    return {"ok": True, "result": result}


@router.post("/api/installs/{install_id}/analyze")
def api_ai_analyze(install_id: int):
    db = next(get_db())
    try:
        result = ai_analyze(db, install_id)
        return {"ok": True, "result": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.delete("/api/installs/{install_id}")
def api_delete_install(install_id: int):
    db = next(get_db())
    if delete_install(db, install_id):
        return {"ok": True}
    return {"ok": False, "error": "安装记录不存在"}


@router.post("/api/installs/{install_id}/full-check")
def api_full_check(install_id: int):
    """四合一体检闭环: 一键同时执行 健康+配置+漏洞+AI 分析"""
    db = next(get_db())
    try:
        result = full_health_check(db, install_id)
        return {"ok": True, "result": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/batch-full-check")
def api_batch_full_check(limit: int = Query(50)):
    """批量四合一体检: 对所有 running 实例一键全面体检"""
    db = next(get_db())
    result = batch_full_check(db, limit=limit)
    return {"ok": True, "result": result}
