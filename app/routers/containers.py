import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import Asset, DataSource
from app.services import asset_service, topology_service, pod_health_service

router = APIRouter(prefix="/containers", tags=["containers"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def container_overview(request: Request, db: Session = Depends(get_db)):
    clusters = db.query(Asset).filter(Asset.ci_type == "cluster").all()
    pods = db.query(Asset).filter(Asset.ci_type == "pod").all()
    deployments = db.query(Asset).filter(Asset.ci_type == "deployment").all()
    nodes = db.query(Asset).filter(Asset.ci_type == "node").all()
    namespaces = db.query(Asset).filter(Asset.ci_type == "namespace").all()
    services = db.query(Asset).filter(Asset.ci_type == "service").all()
    docker_containers = db.query(Asset).filter(Asset.ci_type == "container").all()
    return templates.TemplateResponse("containers.html", {
        "request": request,
        "clusters": clusters,
        "pods": pods,
        "deployments": deployments,
        "nodes": nodes,
        "namespaces": namespaces,
        "services": services,
        "docker_containers": docker_containers,
    })


@router.get("/pods", response_class=HTMLResponse)
def pod_list(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    q = db.query(Asset).filter(Asset.ci_type == "pod")
    if cluster:
        q = q.filter(Asset.k8s_cluster == cluster)
    if namespace:
        q = q.filter(Asset.name.like(f"{namespace}/%"))
    pods = q.order_by(Asset.name).all()
    clusters = db.query(Asset).filter(Asset.ci_type == "cluster").all()
    cluster_info = None
    if cluster:
        c = db.query(Asset).filter(Asset.ci_type == "cluster", Asset.name == cluster).first()
        if c:
            cluster_info = {"name": c.name, "endpoint": c.ip or "-", "status": c.status, "last_scrape": c.updated_at}
    return templates.TemplateResponse("container_pods.html", {
        "request": request, "pods": pods, "clusters": clusters,
        "cluster": cluster, "namespace": namespace, "cluster_info": cluster_info,
    })


@router.get("/deployments", response_class=HTMLResponse)
def deployment_list(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    q = db.query(Asset).filter(Asset.ci_type == "deployment")
    if cluster:
        q = q.filter(Asset.k8s_cluster == cluster)
    if namespace:
        q = q.filter(Asset.name.like(f"{namespace}/%"))
    deployments = q.order_by(Asset.name).all()
    clusters = db.query(Asset).filter(Asset.ci_type == "cluster").all()
    cluster_info = None
    if cluster:
        c = db.query(Asset).filter(Asset.ci_type == "cluster", Asset.name == cluster).first()
        if c:
            cluster_info = {"name": c.name, "endpoint": c.ip or "-", "status": c.status, "last_scrape": c.updated_at}
    return templates.TemplateResponse("container_deployments.html", {
        "request": request, "deployments": deployments, "clusters": clusters,
        "cluster": cluster, "namespace": namespace, "cluster_info": cluster_info,
    })


@router.get("/topology", response_class=HTMLResponse)
def container_topology(request: Request, db: Session = Depends(get_db)):
    trees = topology_service.build_container_topo(db)
    return templates.TemplateResponse("container_topology.html", {
        "request": request, "trees": trees,
    })


@router.get("/pod/{asset_id}", response_class=HTMLResponse)
def pod_detail(request: Request, asset_id: int, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return RedirectResponse("/containers/pods", status_code=303)
    pod_name = pod.name.split("/")[-1] if "/" in pod.name else pod.name
    anomalies = pod_health_service.get_pod_anomalies(db, pod_name)
    return templates.TemplateResponse("container_pod_detail.html", {
        "request": request, "pod": pod, "anomalies": anomalies,
    })


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
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        else:
            config.load_kube_config()
        v1 = client.CoreV1Api()
        logs = v1.read_namespaced_pod_log(name=name, namespace=ns, tail_lines=tail)
        return PlainTextResponse(logs)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)


@router.websocket("/ws/pod/{asset_id}/logs")
async def pod_log_ws(websocket: WebSocket, asset_id: int):
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
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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


@router.get("/pod/{asset_id}/terminal", response_class=HTMLResponse)
def pod_terminal_page(request: Request, asset_id: int, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return RedirectResponse("/containers/pods", status_code=303)
    return templates.TemplateResponse("container_terminal.html", {
        "request": request, "pod": pod,
    })


@router.get("/pod/{asset_id}/logs", response_class=HTMLResponse)
def pod_logs_page(request: Request, asset_id: int, db: Session = Depends(get_db)):
    pod = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "pod").first()
    if not pod:
        return RedirectResponse("/containers/pods", status_code=303)
    return templates.TemplateResponse("container_pod_logs.html", {
        "request": request, "pod": pod,
    })


@router.get("/docker", response_class=HTMLResponse)
def docker_container_list(request: Request, search: str = "", host: str = "", status: str = "", db: Session = Depends(get_db)):
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
    return templates.TemplateResponse("container_docker.html", {
        "request": request, "containers": containers,
        "hosts": hosts, "search": search, "host_filter": host, "status_filter": status,
    })


@router.get("/docker/{asset_id}", response_class=HTMLResponse)
def docker_container_detail(request: Request, asset_id: int, db: Session = Depends(get_db)):
    container = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "container").first()
    if not container:
        return RedirectResponse("/containers/docker", status_code=303)
    return templates.TemplateResponse("container_docker_detail.html", {
        "request": request, "container": container,
    })


@router.get("/deploy/{asset_id}/manage", response_class=HTMLResponse)
def deployment_manage(request: Request, asset_id: int, db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    return templates.TemplateResponse("container_deploy_manage.html", {
        "request": request, "dep": dep,
    })


@router.post("/deploy/{asset_id}/rollout")
def deployment_rollout(asset_id: int, image: str = Form(""), db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    from app.database import get_session_for, get_db_mode
    try:
        attrs = json.loads(dep.ci_attributes) if isinstance(dep.ci_attributes, str) else dep.ci_attributes or {}
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("K8s data source not found", status_code=404)

        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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
        return RedirectResponse(f"/containers/deploy/{asset_id}/manage", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Rollout error: {e}", status_code=500)


@router.post("/deploy/{asset_id}/scale")
def deployment_scale(asset_id: int, replicas: int = Form(...), db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    try:
        attrs = json.loads(dep.ci_attributes) if isinstance(dep.ci_attributes, str) else dep.ci_attributes or {}
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("K8s data source not found", status_code=404)

        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        else:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        apps_v1.patch_namespaced_deployment_scale(name=name, namespace=ns, body={"spec": {"replicas": replicas}})
        return RedirectResponse(f"/containers/deploy/{asset_id}/manage", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Scale error: {e}", status_code=500)


@router.post("/deploy/{asset_id}/canary")
def deployment_canary(asset_id: int, canary_replicas: int = Form(1), db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    try:
        attrs = json.loads(dep.ci_attributes) if isinstance(dep.ci_attributes, str) else dep.ci_attributes or {}
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("K8s data source not found", status_code=404)
        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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
        return RedirectResponse(f"/containers/deploy/{asset_id}/manage", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Canary error: {e}", status_code=500)


@router.post("/deploy/{asset_id}/promote")
def deployment_promote(asset_id: int, db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    try:
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("K8s data source not found", status_code=404)
        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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
        return RedirectResponse(f"/containers/deploy/{asset_id}/manage", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Promote error: {e}", status_code=500)


@router.post("/deploy/{asset_id}/rollback")
def deployment_rollback(asset_id: int, revision: int = Form(0), db: Session = Depends(get_db)):
    dep = db.query(Asset).filter(Asset.id == asset_id, Asset.ci_type == "deployment").first()
    if not dep:
        return RedirectResponse("/containers/deployments", status_code=303)
    try:
        attrs = json.loads(dep.ci_attributes) if isinstance(dep.ci_attributes, str) else dep.ci_attributes or {}
        ns, name = dep.name.split("/", 1)
        cluster = dep.k8s_cluster
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("K8s data source not found", status_code=404)

        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
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
        return RedirectResponse(f"/containers/deploy/{asset_id}/manage", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Rollback error: {e}", status_code=500)


@router.get("/deploy/create", response_class=HTMLResponse)
def deploy_create_form(request: Request, db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return templates.TemplateResponse("deploy_create.html", {
        "request": request, "clusters": clusters,
    })


@router.post("/deploy/create")
def deploy_create(
    request: Request,
    cluster: str = Form(...),
    namespace: str = Form("default"),
    name: str = Form(...),
    image: str = Form(...),
    replicas: int = Form(1),
    container_port: int = Form(80),
    cpu_request: str = Form("100m"),
    mem_request: str = Form("128Mi"),
    cpu_limit: str = Form("500m"),
    mem_limit: str = Form("512Mi"),
    db: Session = Depends(get_db),
):
    try:
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        if not ds:
            return PlainTextResponse("Cluster not found", status_code=404)
        from kubernetes import config, client
        cfg = json.loads(ds.auth_config) if isinstance(ds.auth_config, str) else ds.auth_config or {}
        try:
            if cfg.get("in_cluster"):
                config.load_incluster_config()
            elif cfg.get("kubeconfig"):
                config.load_kube_config_from_dict(cfg["kubeconfig"])
            else:
                config.load_kube_config()
        except Exception:
            config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        body = {
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
        apps_v1.create_namespaced_deployment(namespace=namespace, body=body)
        return RedirectResponse(f"/containers/deployments?cluster={cluster}&namespace={namespace}", status_code=303)
    except Exception as e:
        return PlainTextResponse(f"Create deployment error: {e}", status_code=500)

