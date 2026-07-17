import json
import subprocess
import asyncio
from collections import Counter
from datetime import datetime
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates, parse_json_config
from app.models import Asset, DataSource
from app.services import asset_service, topology_service, pod_health_service
from app.services.mobile_push_service import verify_login_token

router = APIRouter(prefix="/containers", tags=["containers"])
templates = get_templates()


def _parse_attrs(c):
    """安全解析 ci_attributes JSON，兼容 str/dict/None"""
    if not c.ci_attributes:
        return {}
    if isinstance(c.ci_attributes, dict):
        return c.ci_attributes
    try:
        return json.loads(c.ci_attributes)
    except Exception:
        return {}


@router.get("/topology/graph")
def container_topology_graph(db: Session = Depends(get_db)):
    """K8s 资源关系图数据（d3 力导向图用）：nodes + links + clusters + stats"""
    from fastapi.responses import JSONResponse
    data = topology_service.build_k8s_topo_graph(db)
    return JSONResponse(data)


@router.get("/pod/{asset_id}/logdata")
def pod_logs(asset_id: int, tail: int = 100, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return PlainTextResponse("Pod not found", status_code=404)
    try:
        attrs = json.loads(pod.ci_attributes) if isinstance(pod.ci_attributes, str) else pod.ci_attributes or {}
    except Exception:
        attrs = {}
    ns, name = pod.name.split("/", 1)
    cluster = pod.k8s_cluster

    ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
    if not ds:
        return PlainTextResponse("K8s data source not found for this cluster", status_code=404)

    try:
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        v1 = client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=name, namespace=ns, tail_lines=tail)
        return PlainTextResponse(logs)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)


@router.get("/pod/{asset_id}/logs", response_class=HTMLResponse)
def pod_logs_page(request: Request, asset_id: int, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return PlainTextResponse("Pod not found", status_code=404)
    return templates.TemplateResponse("container_pod_logs.html", {"request": request, "pod": pod})


@router.get("/pod/{asset_id}/terminal", response_class=HTMLResponse)
def pod_terminal_page(request: Request, asset_id: int, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return PlainTextResponse("Pod not found", status_code=404)
    return templates.TemplateResponse("container_terminal.html", {"request": request, "pod": pod})


@router.websocket("/ws/pod/{asset_id}/logs")
async def pod_log_ws(websocket: WebSocket, asset_id: int):
    # 认证检查：WebSocket 无法直接读 session，通过 query param token 验证
    token = websocket.query_params.get("token", "")
    from app.services.mobile_push_service import verify_login_token
    payload = None
    if token:
        payload = verify_login_token(token)
    if not payload:
        await websocket.accept()
        await websocket.send_text("未认证，请先登录")
        await websocket.close()
        return
    await websocket.accept()
    from app.database import get_session_for, get_db_mode
    try:
        db = get_session_for(get_db_mode())()
        pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
        if not pod:
            await websocket.send_text("Pod not found")
            await websocket.close()
            db.close()
            return
        attrs = json.loads(pod.ci_attributes) if isinstance(pod.ci_attributes, str) else pod.ci_attributes or {}
        ns, name = pod.name.split("/", 1)
        cluster = pod.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        db.close()
        if not ds:
            await websocket.send_text("K8s data source not found")
            await websocket.close()
            return

        from kubernetes import config, client, watch
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        v1 = client.CoreV1Api()
        w = watch.Watch()
        for line in w.stream(v1.read_namespaced_pod_log, name=name, namespace=ns):
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {e}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/pod/{asset_id}/terminal")
async def pod_terminal_ws(websocket: WebSocket, asset_id: int):
    token = websocket.query_params.get("token", "")
    from app.services.mobile_push_service import verify_login_token
    if not token or not verify_login_token(token):
        await websocket.accept()
        await websocket.send_text("未认证，请先登录")
        await websocket.close()
        return
    await websocket.accept()
    from app.database import get_session_for, get_db_mode
    try:
        db = get_session_for(get_db_mode())()
        pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
        if not pod:
            await websocket.send_text("Pod not found")
            await websocket.close()
            db.close()
            return
        attrs = json.loads(pod.ci_attributes) if isinstance(pod.ci_attributes, str) else pod.ci_attributes or {}
        ns, name = pod.name.split("/", 1)
        cluster = pod.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        db.close()
        if not ds:
            await websocket.send_text("K8s data source not found")
            await websocket.close()
            return

        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()

        import subprocess, asyncio, threading

        v1 = client.CoreV1Api()
        exec_url = f"/api/v1/namespaces/{ns}/pods/{name}/exec?command=/bin/sh&command=-c&command=if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi&stdin=true&stdout=true&stderr=true&tty=true"
        import urllib.parse
        exec_url_compat = f"/api/v1/namespaces/{ns}/pods/{name}/exec"
        params = "command=bash&stdin=true&stdout=true&stderr=true&tty=true"
        try:
            resp = v1.connect_get_namespaced_pod_exec(name, ns, command=["/bin/sh", "-c", "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi"], stderr=True, stdin=True, stdout=True, tty=True)
        except Exception:
            resp = v1.connect_get_namespaced_pod_exec(name, ns, command=["sh"], stderr=True, stdin=True, stdout=True, tty=True)

        ws_url = resp.url if hasattr(resp, 'url') else str(resp)
        import websocket as k8s_ws
        k8s_ws_url = ws_url.replace("https://", "wss://").replace("http://", "ws://")
        kws = k8s_ws.create_connection(k8s_ws_url, subprotocols=["channel.k8s.io"])
        kws.settimeout(30)

        async def k8s_to_browser():
            try:
                while True:
                    data = kws.recv()
                    if isinstance(data, bytes) and len(data) > 1:
                        await websocket.send_bytes(data[1:])
                    elif isinstance(data, str):
                        await websocket.send_text(data)
            except Exception:
                pass

        async def browser_to_k8s():
            try:
                while True:
                    data = await websocket.receive()
                    if data.get("type") == "websocket.disconnect":
                        break
                    msg = data.get("text") or data.get("bytes")
                    if msg:
                        if isinstance(msg, str):
                            kws.send("\x00" + msg)
                        else:
                            kws.send_binary(b"\x00" + msg)
            except Exception:
                pass

        t1 = asyncio.create_task(k8s_to_browser())
        t2 = asyncio.create_task(browser_to_k8s())
        await asyncio.gather(t1, t2)
        kws.close()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {e}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _event_to_dict(e):
    return {
        "id": e.id,
        "cluster": e.cluster,
        "namespace": e.namespace,
        "name": e.name,
        "kind": e.kind,
        "reason": e.reason,
        "message": e.message,
        "source": e.source,
        "first_seen_at": e.first_seen_at.isoformat() if e.first_seen_at else None,
        "last_seen_at": e.last_seen_at.isoformat() if e.last_seen_at else None,
        "count": e.count,
        "severity": e.severity,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _container_to_dict(c):
    attrs = _parse_attrs(c)
    host = c.name.split("/")[0] if "/" in c.name else (attrs.get("host", "-"))
    name = c.name.split("/")[-1] if "/" in c.name else c.name
    state = attrs.get("state", "")
    is_running = (state == "running") or (c.status == "online")
    return {
        "id": c.id,
        "name": name,
        "full_name": c.name,
        "host": host,
        "image": attrs.get("image", "-"),
        "state": "running" if is_running else "stopped",
        "status": c.status,
        "status_text": attrs.get("status", "-"),
        "ports": attrs.get("ports", "-"),
        "created_at": attrs.get("created_at", ""),
        "ip": c.ip,
        "tags": c.tags,
        "attrs": attrs,
    }


def _pod_to_dict(p):
    attrs = _parse_attrs(p)
    ns = p.name.split("/")[0] if "/" in p.name else ""
    name = p.name.split("/")[-1] if "/" in p.name else p.name
    return {
        "id": p.id,
        "name": name,
        "full_name": p.name,
        "namespace": ns,
        "cluster": p.k8s_cluster,
        "ip": p.ip,
        "status": p.status,
        "tags": p.tags,
        "attrs": attrs,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "last_checked_at": p.last_checked_at.isoformat() if p.last_checked_at else None,
    }


def _deployment_to_dict(d):
    attrs = _parse_attrs(d)
    ns = d.name.split("/")[0] if "/" in d.name else ""
    name = d.name.split("/")[-1] if "/" in d.name else d.name
    return {
        "id": d.id,
        "name": name,
        "full_name": d.name,
        "namespace": ns,
        "cluster": d.k8s_cluster,
        "ip": d.ip,
        "status": d.status,
        "tags": d.tags,
        "attrs": attrs,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "last_checked_at": d.last_checked_at.isoformat() if d.last_checked_at else None,
    }


def _cluster_to_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "endpoint": c.ip or "-",
        "status": c.status,
        "last_scraped_at": c.last_checked_at.isoformat() if c.last_checked_at else None,
    }


@router.get("/api/overview")
def api_container_overview(db: Session = Depends(get_db)):
    try:
        docker_containers = db.query(Asset).filter(Asset.ci_type == "container").all()
        total = len(docker_containers)
        running_count = 0
        stopped_count = 0
        host_map = {}
        image_counter = Counter()
        host_set = set()
        recent_containers = []
        for c in docker_containers:
            attrs = _parse_attrs(c)
            state = attrs.get("state", "")
            image = attrs.get("image", "-")
            host = c.name.split("/")[0] if "/" in c.name else (attrs.get("host", "-"))
            host_set.add(host)
            is_running = (state == "running") or (c.status == "online")
            if is_running:
                running_count += 1
            else:
                stopped_count += 1
            if image and image != "-":
                image_counter[image] += 1
            if host not in host_map:
                host_map[host] = {"total": 0, "running": 0, "stopped": 0}
            host_map[host]["total"] += 1
            if is_running:
                host_map[host]["running"] += 1
            else:
                host_map[host]["stopped"] += 1
            created = attrs.get("created_at", "")
            recent_containers.append({
                "id": c.id,
                "name": c.name.split("/")[-1] if "/" in c.name else c.name,
                "host": host,
                "image": image,
                "state": "running" if is_running else "stopped",
                "status_text": attrs.get("status", "-"),
                "ports": attrs.get("ports", "-"),
                "created_at": created,
            })
        recent_containers.sort(key=lambda x: x["created_at"], reverse=True)
        recent_containers = recent_containers[:10]
        host_stats = [
            {"host": h, **v, "running_rate": round(v["running"] / v["total"] * 100, 1) if v["total"] else 0}
            for h, v in host_map.items()
        ]
        host_stats.sort(key=lambda x: x["total"], reverse=True)
        top_images = [{"image": img, "count": cnt} for img, cnt in image_counter.most_common(5)]
        summary = {
            "total": total,
            "running": running_count,
            "stopped": stopped_count,
            "host_count": len(host_set),
            "running_rate": round(running_count / total * 100, 1) if total else 0,
        }
        return JSONResponse({
            "summary": summary,
            "host_stats": host_stats,
            "top_images": top_images,
            "recent_containers": recent_containers,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/docker")
def api_docker_list(search: str = "", host: str = "", status: str = "", db: Session = Depends(get_db)):
    try:
        q = db.query(Asset).filter(Asset.ci_type == "container")
        if search:
            q = q.filter(Asset.name.ilike(f"%{search}%"))
        if host:
            q = q.filter(Asset.name.like(f"{host}/%"))
        if status == "running":
            q = q.filter(Asset.status == "online")
        elif status == "exited":
            q = q.filter(Asset.status == "offline")
        containers = q.order_by(Asset.name).all()
        hosts = [c.name.split("/")[0] for c in db.query(Asset).filter(Asset.ci_type == "container").all() if "/" in c.name]
        hosts = sorted(set(hosts))
        items = [_container_to_dict(c) for c in containers]
        return JSONResponse({
            "items": items,
            "hosts": hosts,
            "search": search,
            "host_filter": host,
            "status_filter": status,
            "count": len(items),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/docker/{asset_id}")
def api_docker_detail(asset_id: int, db: Session = Depends(get_db)):
    try:
        container = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "container").first()
        if not container:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"container": _container_to_dict(container)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/docker/{asset_id}/logs")
def api_docker_container_logs(asset_id: int, tail: int = 200, db: Session = Depends(get_db)):
    try:
        container = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "container").first()
        if not container:
            return JSONResponse({"error": "容器未找到"}, status_code=404)
        name = container.name.split("/")[-1]
        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), name],
            capture_output=True, timeout=15
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        if result.returncode != 0:
            return JSONResponse({"error": result.stderr.decode("utf-8", errors="replace") or "获取日志失败"}, status_code=500)
        lines = stdout.count("\n")
        return JSONResponse({
            "ok": True, "logs": stdout or "(无日志输出)",
            "lines": lines, "container": name, "truncated": lines >= tail,
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "日志获取超时"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/docker/local/scan")
def api_docker_local_scan(db: Session = Depends(get_db)):
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{json .}}"],
            capture_output=True, timeout=15
        )
        if result.returncode != 0:
            return JSONResponse({"ok": False, "error": result.stderr.decode("utf-8", errors="replace")})
        stdout = result.stdout.decode("utf-8", errors="replace")
        imported = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            c = json.loads(line)
            cid = c.get("ID", "")
            cname = c.get("Names", "")
            image = c.get("Image", "")
            status = c.get("Status", "")
            ports = c.get("Ports", "")
            created = c.get("CreatedAt", "")
            state = "running" if "Up" in status else "exited"
            exists = db.query(Asset).filter(Asset.ci_type == "container", Asset.name == cname).first()
            attrs = {"image": image, "status": state, "state": {"Status": "running" if state == "running" else "exited"}, "ports": ports, "created_at": created}
            if exists:
                exists.status = "online" if state == "running" else "offline"
                exists.ci_attributes = json.dumps(attrs, ensure_ascii=False)
            else:
                asset = Asset(
                    name=cname, type="docker", ci_type="container",
                    status="online" if state == "running" else "offline",
                    ci_attributes=json.dumps(attrs, ensure_ascii=False),
                )
                db.add(asset)
            imported.append({"id": cid[:12], "name": cname, "image": image, "state": state})
        db.commit()
        return JSONResponse({"ok": True, "count": len(imported), "containers": imported})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.websocket("/ws/docker/{asset_id}/terminal")
async def docker_terminal_ws(websocket: WebSocket, asset_id: int):
    token = websocket.query_params.get("token", "")
    if not token or not verify_login_token(token):
        await websocket.accept()
        await websocket.send_text("未认证，请先登录")
        await websocket.close()
        return
    await websocket.accept()
    try:
        from app.database import get_session_for, get_db_mode
        db = get_session_for(get_db_mode())()
        container_asset = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "container").first()
        db.close()
        if not container_asset:
            await websocket.send_text("容器未找到")
            await websocket.close()
            return
        cname = container_asset.name.split("/")[-1]
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", cname, "sh",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def docker_to_browser():
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    await websocket.send_text(line.decode("utf-8", errors="replace").replace("\n", "\r\n"))
            except Exception:
                pass

        async def browser_to_docker():
            try:
                while True:
                    data = await websocket.receive()
                    if data.get("type") == "websocket.disconnect":
                        break
                    msg = data.get("text") or ""
                    if "\x1b[6n" in msg:
                        await websocket.send_text("\x1b[1;1R")
                        msg = msg.replace("\x1b[6n", "")
                    if proc.stdin and msg:
                        msg = msg.replace("\r", "\n")
                        proc.stdin.write(msg.encode("utf-8"))
                        await proc.stdin.drain()
            except Exception:
                pass

        t1 = asyncio.create_task(docker_to_browser())
        t2 = asyncio.create_task(browser_to_docker())
        await asyncio.gather(t1, t2)
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"Error: {e}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/api/pods")
def api_pod_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        q = db.query(Asset).filter(Asset.ci_type == "pod")
        if cluster:
            q = q.filter(Asset.k8s_cluster == cluster)
        if namespace:
            q = q.filter(Asset.name.like(f"{namespace}/%"))
        pods = q.order_by(Asset.name).all()
        clusters = db.query(Asset).filter(Asset.ci_type == "kubernetes_cluster").all()
        cluster_info = None
        if cluster:
            c = db.query(Asset).filter(Asset.ci_type == "kubernetes_cluster", Asset.name == cluster).first()
            if c:
                cluster_info = _cluster_to_dict(c)
        items = [_pod_to_dict(p) for p in pods]
        return JSONResponse({
            "items": items,
            "clusters": [_cluster_to_dict(c) for c in clusters],
            "cluster": cluster,
            "namespace": namespace,
            "cluster_info": cluster_info,
            "count": len(items),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/pod/{asset_id}")
def api_pod_detail(asset_id: int, db: Session = Depends(get_db)):
    try:
        pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
        if not pod:
            return JSONResponse({"error": "not found"}, status_code=404)
        pod_name = pod.name.split("/")[-1] if "/" in pod.name else pod.name
        anomalies = pod_health_service.get_pod_anomalies(db, pod_name)
        return JSONResponse({
            "pod": _pod_to_dict(pod),
            "anomalies": [_event_to_dict(a) for a in anomalies],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/deployments")
def api_deployment_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        q = db.query(Asset).filter(Asset.ci_type == "deployment")
        if cluster:
            q = q.filter(Asset.k8s_cluster == cluster)
        if namespace:
            q = q.filter(Asset.name.like(f"{namespace}/%"))
        deployments = q.order_by(Asset.name).all()
        clusters = db.query(Asset).filter(Asset.ci_type == "kubernetes_cluster").all()
        cluster_info = None
        if cluster:
            c = db.query(Asset).filter(Asset.ci_type == "kubernetes_cluster", Asset.name == cluster).first()
            if c:
                cluster_info = _cluster_to_dict(c)
        items = [_deployment_to_dict(d) for d in deployments]
        return JSONResponse({
            "items": items,
            "clusters": [_cluster_to_dict(c) for c in clusters],
            "cluster": cluster,
            "namespace": namespace,
            "cluster_info": cluster_info,
            "count": len(items),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/deploy/{asset_id}/manage")
def api_deployment_manage(asset_id: int, db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"deployment": _deployment_to_dict(dep)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/deploy/create")
def api_deploy_create(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = body.get("cluster", "")
        namespace = body.get("namespace", "default")
        name = body.get("name", "")
        image = body.get("image", "")
        replicas = int(body.get("replicas", 1))
        container_port = int(body.get("container_port", 80))
        cpu_request = body.get("cpu_request", "100m")
        mem_request = body.get("mem_request", "128Mi")
        cpu_limit = body.get("cpu_limit", "500m")
        mem_limit = body.get("mem_limit", "512Mi")
        if not cluster or not name or not image:
            return JSONResponse({"ok": False, "error": "cluster/name/image required"}, status_code=400)
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        try:
            if cfg.get("in_cluster"):
                config.load_incluster_config()
            elif cfg.get("kubeconfig"):
                config.load_kube_config_from_dict(cfg["kubeconfig"])
            elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
                from kubernetes import client as _k8s_client
                _cfg = _k8s_client.Configuration()
                _cfg.host = cfg["k8s_api_server"]
                _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
                _cfg.verify_ssl = cfg.get("verify_ssl", False)
                _k8s_client.Configuration.set_default(_cfg)
            else:
                config.load_kube_config()
        except Exception:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        k8s_body = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "containers": [{
                            "name": name,
                            "image": image,
                            "ports": [{"containerPort": container_port}],
                            "resources": {
                                "requests": {"cpu": cpu_request, "memory": mem_request},
                                "limits": {"cpu": cpu_limit, "memory": mem_limit},
                            },
                        }],
                    },
                },
            },
        }
        apps_v1.create_namespaced_deployment(namespace=namespace, body=k8s_body)
        return JSONResponse({
            "ok": True,
            "message": "deployment created",
            "cluster": cluster,
            "namespace": namespace,
            "name": name,
            "replicas": replicas,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/deploy/{asset_id}/rollout")
def api_deployment_rollout(asset_id: int, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"ok": False, "error": "deployment not found"}, status_code=404)
        image = body.get("image", "") if body else ""
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "K8s data source not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        deploy = apps_v1.read_namespaced_deployment(name=name, namespace=ns)
        if image:
            deploy.spec.template.spec.containers[0].image = image
        apps_v1.patch_namespaced_deployment(name=name, namespace=ns, body={
            "spec": {
                "template": {
                    "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now().isoformat()}}
                }
            }
        })
        return JSONResponse({"ok": True, "message": "rollout triggered", "image": image or None})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/deploy/{asset_id}/scale")
def api_deployment_scale_api(asset_id: int, body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"ok": False, "error": "deployment not found"}, status_code=404)
        replicas = int(body.get("replicas", 1))
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "K8s data source not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        apps_v1.patch_namespaced_deployment_scale(name=name, namespace=ns, body={"spec": {"replicas": replicas}})
        return JSONResponse({"ok": True, "message": "scaled", "replicas": replicas})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/deploy/{asset_id}/canary")
def api_deployment_canary_api(asset_id: int, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"ok": False, "error": "deployment not found"}, status_code=404)
        canary_replicas = int(body.get("canary_replicas", 1)) if body else 1
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "K8s data source not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        deploy = apps_v1.read_namespaced_deployment(name=name, namespace=ns)
        canary_name = f"{name}-canary"
        existing_canary = None
        try:
            existing_canary = apps_v1.read_namespaced_deployment(name=canary_name, namespace=ns)
        except Exception:
            pass
        if existing_canary:
            apps_v1.patch_namespaced_deployment_scale(name=canary_name, namespace=ns, body={"spec": {"replicas": canary_replicas}})
        else:
            deploy.metadata.name = canary_name
            deploy.metadata.resource_version = None
            deploy.metadata.uid = None
            deploy.spec.replicas = canary_replicas
            if deploy.spec.selector and deploy.spec.selector.match_labels:
                deploy.spec.selector.match_labels["canary"] = "true"
            if deploy.spec.template.metadata and deploy.spec.template.metadata.labels:
                deploy.spec.template.metadata.labels["canary"] = "true"
            apps_v1.create_namespaced_deployment(namespace=ns, body=deploy)
        return JSONResponse({
            "ok": True,
            "message": "canary created/updated",
            "canary_name": canary_name,
            "canary_replicas": canary_replicas,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/deploy/{asset_id}/promote")
def api_deployment_promote_api(asset_id: int, db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"ok": False, "error": "deployment not found"}, status_code=404)
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "K8s data source not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        canary_name = f"{name}-canary"
        canary = apps_v1.read_namespaced_deployment(name=canary_name, namespace=ns)
        main_deploy = apps_v1.read_namespaced_deployment(name=name, namespace=ns)
        new_image = canary.spec.template.spec.containers[0].image
        main_deploy.spec.template.spec.containers[0].image = new_image
        apps_v1.patch_namespaced_deployment(name=name, namespace=ns, body={
            "spec": {"template": {"spec": {"containers": [{"name": main_deploy.spec.template.spec.containers[0].name, "image": new_image}]}}}
        })
        apps_v1.delete_namespaced_deployment(name=canary_name, namespace=ns)
        return JSONResponse({"ok": True, "message": "canary promoted", "new_image": new_image})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/deploy/{asset_id}/rollback")
def api_deployment_rollback_api(asset_id: int, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
        if not dep:
            return JSONResponse({"ok": False, "error": "deployment not found"}, status_code=404)
        revision = int(body.get("revision", 0)) if body else 0
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return JSONResponse({"ok": False, "error": "K8s data source not found"}, status_code=404)
        from kubernetes import config, client
        cfg = parse_json_config(ds.auth_config)
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            from kubernetes import client as _k8s_client
            _cfg = _k8s_client.Configuration()
            _cfg.host = cfg["k8s_api_server"]
            _cfg.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            _cfg.verify_ssl = cfg.get("verify_ssl", False)
            _k8s_client.Configuration.set_default(_cfg)
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        if revision:
            apps_v1.patch_namespaced_deployment(name=name, namespace=ns, body={
                "spec": {"rollbackTo": {"revision": revision}}
            })
        else:
            apps_v1.patch_namespaced_deployment(name=name, namespace=ns, body={
                "spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now().isoformat()}}}}
            })
        return JSONResponse({"ok": True, "message": "rollback triggered", "revision": revision or None})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

