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
from fastapi import APIRouter, Query, Body, WebSocket, WebSocketDisconnect
import json

from app.database import get_db
from app.services.component_catalog_service import (
    list_components, get_component, get_deploy_render, seed_builtin_components,
    record_install, list_installs, get_install, delete_install, update_install_status,
    check_config, check_health, check_vuln, ai_analyze, get_stats, full_health_check,
    batch_full_check, deploy_docker, component_to_asset,
    deploy_stream, register_deploy_stop, cancel_deploy, precheck_deploy,
    resolve_decision, _append_install_event, get_install_events,
    generate_install_report, generate_ai_health_report,
)
from app.services.component_catalog_service import submit_install_decision, _set_pending_decision_install

router = APIRouter(prefix="/component-market", tags=["ComponentMarket"])


@router.on_event("startup")
def _on_startup():
    db = next(get_db())
    try:
        seed_builtin_components(db)
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)


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
               host: str = Query(""), namespace: str = Query("default"), release: str = Query(""),
               params: str = Query(""), use_offline: str = Query("")):
    db = next(get_db())
    comp = get_component(db, component_id)
    if not comp:
        return {"ok": False, "error": "组件不存在"}
    custom = {}
    if params:
        try:
            p = json.loads(params)
            if isinstance(p, dict):
                custom = p
        except Exception:
            custom = {}
    custom["use_offline"] = (use_offline or "").lower() in ("1", "true", "yes", "on")
    result = get_deploy_render(comp, deploy_type, {
        "host": host, "namespace": namespace, "release": release, **custom,
    }, db=db)
    return result


@router.post("/api/precheck")
def api_precheck(body: dict = Body(...)):
    """逻辑预检(对标 K8s 集群部署 precheck): 部署前检查目标机/环境/端口/资源。
    body: {component_id, asset_id, deploy_type?, port?, params?, http_proxy?, https_proxy?, no_proxy?}
    返回: {ok, issues, checks:[{name, ok, message}]}"""
    from app.models import Asset
    db = next(get_db())
    comp = get_component(db, body.get("component_id"))
    if not comp:
        return {"ok": False, "issues": ["组件不存在"], "checks": [{"name": "组件", "ok": False, "message": "组件不存在"}]}
    asset = db.query(Asset).filter(Asset.id == body.get("asset_id")).first()
    result = precheck_deploy(
        db, asset, comp,
        deploy_type=body.get("deploy_type", "docker"),
        port=body.get("port"),
        http_proxy=body.get("http_proxy") or "",
        https_proxy=body.get("https_proxy") or "",
        no_proxy=body.get("no_proxy") or "",
        deploy_path=body.get("deploy_path") or "",
        params=body.get("params") or {},
    )
    return result


@router.post("/api/plan")
def api_gen_plan(body: dict = Body(...)):
    """按目标机系统类型生成部署方案(先预检探测系统, 再 AI 生成可执行方案)。
    body: {component_id, asset_id, deploy_type?, port?, deploy_path?}
    返回: {ok, system, plan} 或 {ok:false, error}"""
    from app.models import Asset
    from app.services.component_catalog_service import _ai_generate_plan, _plan_to_visual_steps
    db = next(get_db())
    comp = get_component(db, body.get("component_id"))
    if not comp:
        return {"ok": False, "error": "组件不存在"}
    asset = db.query(Asset).filter(Asset.id == body.get("asset_id")).first()
    deploy_type = body.get("deploy_type", "docker")
    # 先预检拿系统类型
    pc = precheck_deploy(
        db, asset, comp, deploy_type=deploy_type,
        port=body.get("port"),
        deploy_path=body.get("deploy_path") or "",
        params=body.get("params") or {},
    )
    system = (pc or {}).get("system") or ""
    params = body.get("params") or {}
    _gen_port = int(params.get("db_port") or params.get("amqp_port")
                    or body.get("port") or comp.get("default_port") or 0)
    plan = _ai_generate_plan(db, comp, deploy_type, system,
                             target=asset.ip if asset else "",
                             port=_gen_port,
                             deploy_path=body.get("deploy_path") or "",
                             params=params)
    # 附加结构化步骤(前端渲染步骤卡片) + 预检摘要信息, 便于方案顶部展示环境
    plan_text = plan.get("plan") or ""
    steps = _plan_to_visual_steps(plan_text, deploy_type)
    # 从预检里挑出「系统/工具链/端口/磁盘」等关键环境信息给方案头
    _env = {}
    if pc:
        chk = pc.get("checks") or []
        for c in chk:
            n = c.get("name", "")
            if c.get("level") == "error":
                _env.setdefault("errors", []).append(f"{n}: {c.get('message','')}")
        try:
            _env["system"] = next((c["message"] for c in chk if c["name"] == "目标机系统"), "") or ""
            _env["port"] = next((c["message"] for c in chk if c["name"].startswith("端口")), "") or ""
            _env["disk"] = next((c["message"] for c in chk if c["name"].startswith("磁盘空间")), "") or ""
        except Exception:
            pass
    return {"ok": True, "system": system, "steps": steps, "env": _env, **plan}


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
        # ▼ 使用 _inject_native_params 保证参数真正注入部署脚本
        from app.services.component_catalog_service import _inject_native_params, _native_proxy_prefix
        params = body.get("params") or {}
        deploy_path = body.get("deploy_path", "").strip() or f"/data/aiops-components/{comp['name']}"
        native_script = comp.get("native_script") or ""
        if params:
            injected = _inject_native_params(native_script, comp, params, deploy_path=deploy_path)
            http_proxy = body.get("http_proxy") or ""
            https_proxy = body.get("https_proxy") or ""
            if http_proxy:
                injected = f"{_native_proxy_prefix(http_proxy, https_proxy or http_proxy, body.get('no_proxy') or '')}\n{injected}"
            ok, out = _exec_native(asset, injected)
        else:
            ok, out = _exec_native(asset, native_script)
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
    cmd = f"export AIOPS_DEPLOY=1; {script} 2>&1 | tail -20; echo __RC__=$?"
    # ▼ 大型包(ES/Mongo 数百MB)+ 冷启动重试可能超过5分钟, 放宽到10分钟
    return _exec_ssh(asset, cmd, timeout=600)


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


@router.post("/api/installs/{install_id}/report")
def api_install_report(install_id: int, body: dict = Body({})):
    """AI 生成该安装记录的**可直接交付**完整部署报告(对标 AI 自动部署页报告版式)。
    body: {template_id?: 知识库报告模板ID, 可选}"""
    db = next(get_db())
    try:
        result = generate_install_report(db, install_id, template_id=body.get("template_id") or 0)
        return {"ok": True, "report": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/installs/{install_id}/health-report")
def api_install_health_report(install_id: int):
    """AI 全面体检: 运行四合一检查并生成**可读**的体检报告(对标部署报告版式)"""
    db = next(get_db())
    try:
        result = generate_ai_health_report(db, install_id)
        return {"ok": True, "report": result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/batch-full-check")
def api_batch_full_check(limit: int = Query(50)):
    """批量四合一体检: 对所有 running 实例一键全面体检"""
    db = next(get_db())
    result = batch_full_check(db, limit=limit)
    return {"ok": True, "result": result}


@router.post("/api/installs/{install_id}/to-asset")
def api_install_to_asset(install_id: int):
    """把部署成功的组件实例自动登记为一条子资产(挂在目标机下)。"""
    db = next(get_db())
    try:
        result = component_to_asset(db, install_id)
        return {"ok": True, **result}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


# ─────────────────── WebSocket 流式部署(AI 辅助, 对标 K8s) ───────────────────

@router.websocket("/ws/deploy")
async def ws_deploy(websocket: WebSocket):
    """实时部署组件(Query 传参, 对标 k8s/deploy 的 WS 模式)。
    逐步推送 phase/log/ai/complete/error 事件; 断开 WS 不停止后台部署。
    query: component_id, asset_id, deploy_type, deploy_path, namespace, release,
           http_proxy, https_proxy, no_proxy
    """
    import asyncio
    import threading
    import json as _json
    from app.database import get_session_for, get_db_mode
    from app.models import Asset

    await websocket.accept()
    qp = dict(websocket.query_params)
    do_resume = qp.get("resume") in ("1", "true", "yes")
    resume_id = 0
    try:
        resume_id = int(qp.get("install_id", 0) or 0)
    except (TypeError, ValueError):
        resume_id = 0
    try:
        component_id = int(qp.get("component_id", 0))
        asset_id = int(qp.get("asset_id", 0))
    except (TypeError, ValueError):
        component_id, asset_id = 0, 0
    deploy_type = qp.get("deploy_type", "docker")
    if (not do_resume) and (not component_id or not asset_id):
        try:
            await websocket.send_text(_json.dumps(
                {"type": "error", "message": "缺少 component_id / asset_id"}, ensure_ascii=False))
        except Exception as _exc1:
            logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
        await websocket.close()
        return

    loop = asyncio.get_running_loop()
    disconnected = threading.Event()
    event_buf = []

    def send_event(evt: dict):
        event_buf.append(evt)
        if disconnected.is_set():
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(
                websocket.send_text(_json.dumps(evt, ensure_ascii=False)), loop)
            fut.result(timeout=10)
        except Exception:
            disconnected.set()

    def producer():
        db = get_session_for(get_db_mode())()
        try:
            # ── resume: 回放历史事件(含续 pending decision) ──
            if do_resume and resume_id:
                hist = get_install_events(db, resume_id)
                for ev in hist:
                    if ev.get("type") == "phase":
                        ev["resume_phase"] = True
                    ev["install_id"] = ev.get("install_id") or resume_id
                    ev["resumed"] = True
                    send_event(ev)
                # 若该部署仍有未决的 AI 决策(后台等待中或已持久化到 DB), 推送最新 decision 供续对话
                from app.services import component_catalog_service as _cc
                pending = _cc._DECISION_REG.get(resume_id)
                # 尝试从 DB 恢复持久化的待决策卡片
                pending_decision = None
                try:
                    from app.models import ComponentInstall as _CI
                    _inst = db.query(_CI).filter(_CI.id == resume_id).first()
                    if _inst and _inst.pending_decision_json:
                        _db_dec = json.loads(_inst.pending_decision_json)
                        if isinstance(_db_dec, dict):
                            pending_decision = _db_dec
                except Exception:
                    pending_decision = None
                if pending and not pending.get("event").is_set():
                    latest_decision = None
                    for ev in hist:
                        if ev.get("type") == "decide":
                            latest_decision = ev
                    if latest_decision:
                        latest_decision["install_id"] = resume_id
                        latest_decision["resumed_decision"] = True
                        send_event(latest_decision)
                elif pending_decision:
                    pending_decision["install_id"] = resume_id
                    pending_decision["resumed_decision"] = True
                    pending_decision["resumed"] = True
                    send_event(pending_decision)
                else:
                    send_event({"type": "resume_done", "install_id": resume_id})
                return
            # ── 新建部署 ──
            comp = get_component(db, component_id)
            asset = db.query(Asset).filter(Asset.id == asset_id).first()
            if not comp or not asset:
                send_event({"type": "error", "message": "组件或目标机不存在"})
                return
            deploy_path = (qp.get("deploy_path") or "").strip() or f"/data/aiops-components/{comp['name']}"
            release = qp.get("release") or ""
            namespace = qp.get("namespace") or "default"
            params = {}
            if qp.get("params"):
                try:
                    params = _json.loads(qp.get("params"))
                    if not isinstance(params, dict):
                        params = {}
                except Exception:
                    params = {}
            # ▼ 修复: 端口优先取 params 里的端口类参数(db_port/amqp_port/mq_port 等),
            # 因为前端把用户配置端口放在 params 而非顶层的 port query;
            # 否则 port 回退到 default_port(如 redis 6379), 导致 AI 决策拿不到用户配置的真实端口(如 16379)。
            _p_for_port = int(params.get("db_port") or params.get("amqp_port")
                             or params.get("mq_port") or params.get("port") or 0)
            port = int(qp.get("port") or _p_for_port or comp.get("default_port") or 0)
            use_offline = (qp.get("use_offline") or "").lower() in ("1", "true", "yes", "on")
            plan = qp.get("plan") or ""
            inst = record_install(
                db, comp["id"], comp["name"], asset_id, deploy_type=deploy_type,
                deploy_path=deploy_path, release_name=release,
                name_space=namespace, port=port, deploy_params=params,
            )
            install_id = inst["id"]
            update_install_status(db, install_id, "deploying",
                                  "开始部署(实时流), 目标机: %s" % (asset.ip or asset.name))
            register_deploy_stop(install_id)
            for event in deploy_stream(
                db, asset, comp, port, deploy_path, deploy_type,
                http_proxy=qp.get("http_proxy") or "",
                https_proxy=qp.get("https_proxy") or "",
                no_proxy=qp.get("no_proxy") or "127.0.0.1,localhost,.local",
                namespace=namespace, release=release, install_id=install_id,
                params=params, use_offline=use_offline, plan=plan,
            ):
                event["install_id"] = install_id
                _append_install_event(db, install_id, event)
                send_event(event)
                if event.get("type") == "complete":
                    _set_pending_decision_install(db, install_id, None)
                    status = event.get("status")
                    logtext = "\n".join(e.get("message", "") for e in event_buf if e.get("message"))
                    if status == "succeeded":
                        update_install_status(db, install_id, "running", logtext or "部署成功")
                    elif status == "failed":
                        update_install_status(db, install_id, "failed", event.get("message", "部署失败"))
                    elif status == "stopped":
                        update_install_status(db, install_id, "stopped", "部署已停止")
                    elif status == "deployed":
                        update_install_status(db, install_id, "deploying",
                                              "helm/ha 记录已建, 待 K8s/helm 引擎执行")
        except Exception as e:
            try:
                send_event({"type": "error", "message": str(e)})
                send_event({"type": "complete", "status": "failed", "message": str(e)})
            except Exception as _exc2:
                logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)
        finally:
            db.close()

    t = threading.Thread(target=producer, daemon=True)
    t.start()
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                data = _json.loads(msg)
                if data.get("type") == "stop" and data.get("install_id"):
                    cancel_deploy(int(data["install_id"]))
                elif data.get("type") == "decision" and data.get("install_id") and data.get("id"):
                    # 用户选择/输入了 AI 决策方案, 唤醒等待的部署流
                    resolve_decision(int(data["install_id"]), str(data["id"]), str(data.get("choice") or ""))
            except Exception as _exc3:
                logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)
    except WebSocketDisconnect:
        pass
    except Exception as _exc4:
        logger.warning("[except:pass] Exception: %s", _exc4, exc_info=True)


@router.post("/api/deploys/{install_id}/stop")
def api_stop_deploy(install_id: int):
    """请求停止指定安装记录的实时部署。返回是否命中正在进行的部署流。"""
    db = next(get_db())
    _set_pending_decision_install(db, install_id, None)
    if cancel_deploy(install_id):
        return {"ok": True, "message": "已发送停止指令"}
    return {"ok": False, "message": "未找到进行中的部署流"}


@router.post("/api/deploys/{install_id}/decision")
def api_deploy_decision(install_id: int, payload: dict = Body({})):
    """HTTP 决策提交接口(组件商店): 将用户选择投递到内存注册表, 唤醒等待的部署流。
    即使 WS 已断开, 只要部署线程活跃, 此接口即可生效。"""
    db = next(get_db())
    return submit_install_decision(
        db, install_id,
        decision_id=str(payload.get("id", "")),
        choice=str(payload.get("choice", "")),
    )


@router.post("/api/deploys/{install_id}/decision")
def api_submit_install_decision(install_id: int, body: dict = Body(...)):
    """HTTP 提交 AI 决策(组件商店): 关闭弹窗后仍可从详情恢复并提交。"""
    db = next(get_db())
    return submit_install_decision(db, install_id, body.get("id", ""), body.get("choice", ""))


import logging
logger = logging.getLogger(__name__)
