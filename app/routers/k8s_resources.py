import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Query, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates, parse_json_config
from app.models import DataSource

router = APIRouter(prefix="/k8s", tags=["k8s_resources"])
templates = get_templates()


def _get_k8s_client(ds: DataSource):
    if ds.enabled is False:
        raise Exception(f"K8s 集群 [{ds.name}] 已被禁用")
    from kubernetes import client
    cfg = parse_json_config(ds.auth_config)
    if cfg.get("kubeconfig"):
        from kubernetes import config as k8s_config
        k8s_config.load_kube_config_from_dict(cfg["kubeconfig"])
        api_client = client.ApiClient()
    elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
        import socket
        from urllib.parse import urlparse
        _u = urlparse(cfg["k8s_api_server"])
        _host, _port = _u.hostname, _u.port or 443
        try:
            with socket.create_connection((_host, _port), timeout=5):
                pass
        except Exception as e:
            raise Exception(f"K8s 集群 [{ds.name}] 连接失败({_host}:{_port}): {e}")
        configuration = client.Configuration()
        configuration.host = cfg["k8s_api_server"]
        configuration.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
        configuration.verify_ssl = cfg.get("verify_ssl", False)
        configuration.timeout = 10
        configuration.retries = 0
        api_client = client.ApiClient(configuration=configuration)
    else:
        raise Exception(f"K8s 集群 [{ds.name}] 缺少 k8s_api_server/k8s_token 配置")
    api_client.configuration.timeout = 10
    api_client.configuration.retries = 0
    return client.CoreV1Api(api_client=api_client), client.AppsV1Api(api_client=api_client), client.NetworkingV1Api(api_client=api_client)


def _get_k8s_ds(db: Session, cluster: str = ""):
    q = db.query(DataSource).filter(DataSource.type == "kubernetes")
    if cluster:
        q = q.filter(DataSource.name == cluster)
    return q.first()

def _add_cluster_info(ctx: dict, db: Session):
    cluster_name = ctx.get("cluster", "")
    if cluster_name:
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster_name).first()
        if ds:
            ctx["cluster_info"] = {"name": ds.name, "endpoint": ds.endpoint, "status": ds.last_status, "last_scraped_at": ds.last_scraped_at}
    return ctx


@router.get("/api/overview")
def api_overview(db: Session = Depends(get_db)):
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        _RT = (5, 10)
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        overviews = []
        errors = []
        total_nodes = 0
        total_healthy_nodes = 0
        total_pods = 0
        total_running_pods = 0
        total_deployments = 0
        total_namespaces = 0
        total_services = 0
        healthy_clusters = 0

        def _ov_unknown(ds):
            return {
                "name": ds.name, "endpoint": ds.endpoint, "status": "unknown",
                "nodes": 0, "healthy_nodes": 0, "node_health_rate": 0,
                "pods": 0, "running_pods": 0, "pod_running_rate": 0,
                "deployments": 0, "namespaces": 0, "services": 0,
                "last_scraped_at": str(ds.last_scraped_at) if ds.last_scraped_at else None,
            }

        def _ov_error(ds):
            ov = _ov_unknown(ds)
            ov["status"] = "error"
            return ov

        def _probe(ds):
            if not ds.endpoint:
                return ds.name, _ov_unknown(ds), None, None
            try:
                from kubernetes import client
                v1, apps_v1, _ = _get_k8s_client(ds)
                nodes = v1.list_node(_request_timeout=_RT).items
                pods = v1.list_pod_for_all_namespaces(_request_timeout=_RT).items
                deployments = apps_v1.list_deployment_for_all_namespaces(_request_timeout=_RT).items
                try:
                    ns_count = len(v1.list_namespace(_request_timeout=_RT).items)
                except Exception:
                    ns_count = 0
                try:
                    svc_count = len(v1.list_service_for_all_namespaces(_request_timeout=_RT).items)
                except Exception:
                    svc_count = 0
                healthy_nodes = sum(1 for n in nodes if all(c.status == "True" for c in n.status.conditions if c.type == "Ready"))
                running_pods = sum(1 for p in pods if (p.status.phase or "") == "Running")
                node_rate = round(healthy_nodes / len(nodes) * 100, 1) if nodes else 0
                pod_rate = round(running_pods / len(pods) * 100, 1) if pods else 0
                ov = {
                    "name": ds.name, "endpoint": ds.endpoint, "status": "online",
                    "nodes": len(nodes), "healthy_nodes": healthy_nodes, "node_health_rate": node_rate,
                    "pods": len(pods), "running_pods": running_pods, "pod_running_rate": pod_rate,
                    "deployments": len(deployments), "namespaces": ns_count, "services": svc_count,
                    "last_scraped_at": str(ds.last_scraped_at) if ds.last_scraped_at else None,
                }
                stats = (len(nodes), healthy_nodes, len(pods), running_pods, len(deployments), ns_count, svc_count)
                return ds.name, ov, stats, None
            except Exception as e:
                return ds.name, _ov_error(ds), None, str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            fut_map = {pool.submit(_probe, ds): ds for ds in clusters}
            for fut in as_completed(fut_map, timeout=45):
                ds = fut_map[fut]
                try:
                    results[ds.name] = fut.result(timeout=45)
                except Exception as e:
                    results[ds.name] = (ds.name, _ov_error(ds), None, f"探测超时/异常: {e}")

        for ds in clusters:
            name, ov, stats, err = results.get(ds.name, (ds.name, _ov_error(ds), None, "未探测"))
            overviews.append(ov)
            if err:
                errors.append(f"{ds.name}: {err}")
                ds.last_status = "error"
                ds.last_error = str(err)
            elif stats:
                ds.last_status = "online"
                ds.last_error = ""
                healthy_clusters += 1
                total_nodes += stats[0]
                total_healthy_nodes += stats[1]
                total_pods += stats[2]
                total_running_pods += stats[3]
                total_deployments += stats[4]
                total_namespaces += stats[5]
                total_services += stats[6]
            else:
                ds.last_status = "unknown"
        db.commit()
        summary = {
            "cluster_count": len(clusters), "healthy_clusters": healthy_clusters,
            "total_nodes": total_nodes, "total_healthy_nodes": total_healthy_nodes,
            "node_health_rate": round(total_healthy_nodes / total_nodes * 100, 1) if total_nodes else 0,
            "total_pods": total_pods, "total_running_pods": total_running_pods,
            "pod_running_rate": round(total_running_pods / total_pods * 100, 1) if total_pods else 0,
            "total_deployments": total_deployments, "total_namespaces": total_namespaces, "total_services": total_services,
        }
        return JSONResponse({
            "overviews": overviews, "errors": errors, "summary": summary,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/statefulsets")
def api_statefulset_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                _, apps_v1, _ = _get_k8s_client(ds)
                raw = apps_v1.list_namespaced_stateful_set(namespace) if namespace else apps_v1.list_stateful_set_for_all_namespaces().items
                for s in raw:
                    items.append({
                        "name": s.metadata.name, "namespace": s.metadata.namespace,
                        "replicas": s.spec.replicas, "ready": s.status.ready_replicas or 0,
                        "service": s.spec.service_name or "-",
                        "image": s.spec.template.spec.containers[0].image if s.spec.template.spec.containers else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/deployments")
def api_deployment_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                _, apps_v1, _ = _get_k8s_client(ds)
                raw = apps_v1.list_namespaced_deployment(namespace) if namespace else apps_v1.list_deployment_for_all_namespaces().items
                for d in raw:
                    available = d.status.available_replicas or 0
                    total = d.spec.replicas or 0
                    items.append({
                        "name": d.metadata.name, "namespace": d.metadata.namespace,
                        "cluster": ds.name,
                        "replicas": total, "available": available,
                        "strategy": (d.spec.strategy.type or "RollingUpdate") if d.spec.strategy else "RollingUpdate",
                        "image": d.spec.template.spec.containers[0].image if d.spec.template.spec.containers else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/deployment/{cluster}/{namespace}/{name}/manage")
def api_deployment_manage(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"error": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        d = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        available = d.status.available_replicas or 0
        total = d.spec.replicas or 0
        containers = d.spec.template.spec.containers or []
        return JSONResponse({"deployment": {
            "name": d.metadata.name, "namespace": d.metadata.namespace, "cluster": cluster,
            "replicas": total, "available": available,
            "strategy": (d.spec.strategy.type or "RollingUpdate") if d.spec.strategy else "RollingUpdate",
            "image": containers[0].image if containers else "-",
            "attrs": {
                "replicas": total, "ready_replicas": available,
                "strategy": (d.spec.strategy.type or "RollingUpdate") if d.spec.strategy else "RollingUpdate",
                "image": containers[0].image if containers else "-",
            },
        }})
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/deployment/{cluster}/{namespace}/{name}/rollout")
def api_deployment_rollout(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        from datetime import datetime
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body={
            "spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now().isoformat()}}}}
        })
        return JSONResponse({"ok": True, "message": "rollout triggered"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/deployment/{cluster}/{namespace}/{name}/scale")
def api_deployment_scale(cluster: str, namespace: str, name: str, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        replicas = int(body.get("replicas", 1))
        apps_v1.patch_namespaced_deployment_scale(name=name, namespace=namespace, body={"spec": {"replicas": replicas}})
        return JSONResponse({"ok": True, "message": "scaled", "replicas": replicas})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/deployment/{cluster}/{namespace}/{name}/canary")
def api_deployment_canary(cluster: str, namespace: str, name: str, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        canary_replicas = int(body.get("canary_replicas", 1))
        deploy = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        canary_name = f"{name}-canary"
        existing = None
        try:
            existing = apps_v1.read_namespaced_deployment(name=canary_name, namespace=namespace)
        except Exception:
            pass
        if existing:
            apps_v1.patch_namespaced_deployment_scale(name=canary_name, namespace=namespace, body={"spec": {"replicas": canary_replicas}})
        else:
            deploy.metadata.name = canary_name
            deploy.metadata.resource_version = None
            deploy.metadata.uid = None
            deploy.spec.replicas = canary_replicas
            if deploy.spec.selector and deploy.spec.selector.match_labels:
                deploy.spec.selector.match_labels["canary"] = "true"
            if deploy.spec.template.metadata and deploy.spec.template.metadata.labels:
                deploy.spec.template.metadata.labels["canary"] = "true"
            apps_v1.create_namespaced_deployment(namespace=namespace, body=deploy)
        return JSONResponse({"ok": True, "message": "canary created/updated", "canary_name": canary_name, "canary_replicas": canary_replicas})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/deployment/{cluster}/{namespace}/{name}/promote")
def api_deployment_promote(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        canary_name = f"{name}-canary"
        canary = apps_v1.read_namespaced_deployment(name=canary_name, namespace=namespace)
        main_deploy = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        new_image = canary.spec.template.spec.containers[0].image
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body={
            "spec": {"template": {"spec": {"containers": [{"name": main_deploy.spec.template.spec.containers[0].name, "image": new_image}]}}}
        })
        apps_v1.delete_namespaced_deployment(name=canary_name, namespace=namespace)
        return JSONResponse({"ok": True, "message": "canary promoted", "new_image": new_image})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/deployment/{cluster}/{namespace}/{name}/rollback")
def api_deployment_rollback(cluster: str, namespace: str, name: str, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "K8s data source not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        revision = int(body.get("revision", 0))
        from datetime import datetime
        if revision:
            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body={
                "spec": {"rollbackTo": {"revision": revision}}
            })
        else:
            apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body={
                "spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now().isoformat()}}}}
            })
        return JSONResponse({"ok": True, "message": "rollback triggered", "revision": revision or None})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/api/pods")
def api_pod_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_namespaced_pod(namespace) if namespace else v1.list_pod_for_all_namespaces().items
                for p in raw:
                    container_images = [c.image for c in (p.spec.containers or [])]
                    items.append({
                        "name": p.metadata.name, "namespace": p.metadata.namespace,
                        "cluster": ds.name,
                        "node": p.spec.node_name or "-",
                        "phase": p.status.phase or "Unknown",
                        "pod_ip": p.status.pod_ip or "-",
                        "host_ip": p.status.host_ip or "-",
                        "restarts": sum(s.restart_count for s in (p.status.container_statuses or [])),
                        "age": str(p.metadata.creation_timestamp)[:19] if p.metadata.creation_timestamp else "",
                        "images": ", ".join(container_images),
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/daemonsets")
def api_daemonset_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                _, apps_v1, _ = _get_k8s_client(ds)
                raw = apps_v1.list_namespaced_daemon_set(namespace) if namespace else apps_v1.list_daemon_set_for_all_namespaces().items
                for d in raw:
                    items.append({
                        "name": d.metadata.name, "namespace": d.metadata.namespace,
                        "desired": d.status.desired_number_scheduled or 0,
                        "ready": d.status.number_ready or 0,
                        "node_selector": str(d.spec.selector.match_labels) if d.spec.selector else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/services")
def api_service_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_namespaced_service(namespace) if namespace else v1.list_service_for_all_namespaces().items
                for svc in raw:
                    ports = []
                    for p in (svc.spec.ports or []):
                        ports.append(f"{p.port}/{p.protocol}" + (f"->{p.node_port}" if p.node_port else ""))
                    items.append({
                        "name": svc.metadata.name, "namespace": svc.metadata.namespace,
                        "type": svc.spec.type or "ClusterIP",
                        "cluster_ip": svc.spec.cluster_ip or "-",
                        "ports": ", ".join(ports),
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/ingresses")
def api_ingress_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                _, _, net_v1 = _get_k8s_client(ds)
                raw = net_v1.list_namespaced_ingress(namespace) if namespace else net_v1.list_ingress_for_all_namespaces().items
                for ing in raw:
                    rules = []
                    for rule in (ing.spec.rules or []):
                        host = rule.host or "*"
                        for path in (rule.http.paths or []):
                            svc_name = path.backend.service.name if path.backend.service else "?"
                            svc_port = path.backend.service.port.number if path.backend.service and path.backend.service.port else "?"
                            rules.append(f"{host}{path.path} -> {svc_name}:{svc_port}")
                    items.append({
                        "name": ing.metadata.name, "namespace": ing.metadata.namespace,
                        "rules": rules, "tls": [t.hosts for t in (ing.spec.tls or [])],
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/configmaps")
def api_configmap_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_namespaced_config_map(namespace) if namespace else v1.list_config_map_for_all_namespaces().items
                for cm in raw:
                    items.append({
                        "name": cm.metadata.name, "namespace": cm.metadata.namespace,
                        "data_keys": list(cm.data.keys()) if cm.data else [],
                        "data_count": len(cm.data) if cm.data else 0,
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/secrets")
def api_secret_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_namespaced_secret(namespace) if namespace else v1.list_secret_for_all_namespaces().items
                for s in raw:
                    items.append({
                        "name": s.metadata.name, "namespace": s.metadata.namespace,
                        "type": s.type or "Opaque",
                        "data_count": len(s.data) if s.data else 0,
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/hpas")
def api_hpa_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                from kubernetes import client
                _, _, _ = _get_k8s_client(ds)
                autoscaling_v1 = client.AutoscalingV1Api()
                raw = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace).items if namespace else autoscaling_v1.list_horizontal_pod_autoscaler_for_all_namespaces().items
                for hpa in raw:
                    items.append({
                        "name": hpa.metadata.name, "namespace": hpa.metadata.namespace,
                        "min_replicas": hpa.spec.min_replicas or 1,
                        "max_replicas": hpa.spec.max_replicas,
                        "current_replicas": hpa.status.current_replicas or 0,
                        "desired_replicas": hpa.status.desired_replicas or 0,
                        "target_cpu_utilization": hpa.spec.target_cpu_utilization_percentage or "-",
                        "current_cpu_utilization": (hpa.status.current_cpu_utilization_percentage or "-") if hasattr(hpa.status, "current_cpu_utilization_percentage") else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/pvcs")
def api_pvc_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_namespaced_persistent_volume_claim(namespace) if namespace else v1.list_persistent_volume_claim_for_all_namespaces().items
                for p in raw:
                    status = "Bound" if p.status.phase == "Bound" else "Pending"
                    storage = p.spec.resources.requests.get("storage", "?") if p.spec.resources and p.spec.resources.requests else "?"
                    items.append({
                        "name": p.metadata.name, "namespace": p.metadata.namespace,
                        "status": status, "storage": storage,
                        "access_modes": ",".join(p.spec.access_modes or []),
                        "volume": p.spec.volume_name or "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/pvs")
def api_pv_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                raw = v1.list_persistent_volume().items
                for p in raw:
                    capacity = p.spec.capacity.get("storage", "?") if p.spec.capacity else "?"
                    items.append({
                        "name": p.metadata.name, "capacity": capacity,
                        "access_modes": ",".join(p.spec.access_modes or []),
                        "reclaim": str(p.spec.persistent_volume_reclaim_policy or "?"),
                        "status": p.status.phase or "?",
                        "claim": p.spec.claim_ref.name if p.spec.claim_ref else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/configmaps/{cluster}/{namespace}/{name}")
def api_configmap_detail(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        data = cm.data or {}
        return JSONResponse({
            "cluster": cluster, "namespace": namespace, "name": name, "data": data,
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.post("/api/configmaps/{cluster}/{namespace}/{name}/update")
def api_configmap_update(cluster: str, namespace: str, name: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        cm.data = payload.get("data", {})
        v1.replace_namespaced_config_map(name, namespace, cm)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/hpas/create")
def api_hpa_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        from kubernetes import client
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        target = payload.get("target", "")
        min_replicas = int(payload.get("min_replicas", 1))
        max_replicas = int(payload.get("max_replicas", 3))
        cpu_percent = int(payload.get("cpu_percent", 80))
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        body = {
            "apiVersion": "autoscaling/v1",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": target,
                },
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "targetCPUUtilizationPercentage": cpu_percent,
            },
        }
        autoscaling_v1.create_namespaced_horizontal_pod_autoscaler(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/hpas/{cluster}/{namespace}/{name}/update")
def api_hpa_update(cluster: str, namespace: str, name: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        from kubernetes import client
        min_replicas = int(payload.get("min_replicas", 1))
        max_replicas = int(payload.get("max_replicas", 3))
        cpu_percent = int(payload.get("cpu_percent", 80))
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        hpa = autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        hpa.spec.min_replicas = min_replicas
        hpa.spec.max_replicas = max_replicas
        hpa.spec.target_cpu_utilization_percentage = cpu_percent
        autoscaling_v1.replace_namespaced_horizontal_pod_autoscaler(name, namespace, hpa)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/hpas/{cluster}/{namespace}/{name}/delete")
def api_hpa_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        from kubernetes import client
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        autoscaling_v1.delete_namespaced_horizontal_pod_autoscaler(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/api/namespaces")
def api_namespace_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if ds:
            try:
                v1, _, _ = _get_k8s_client(ds)
                for ns in v1.list_namespace().items:
                    items.append({
                        "name": ns.metadata.name,
                        "status": ns.status.phase or "Active",
                        "age": str(ns.metadata.creation_timestamp) if ns.metadata.creation_timestamp else "-",
                    })
            except Exception as e:
                error = str(e)
        return JSONResponse({
            "items": items, "cluster": cluster, "namespace": namespace, "warning": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


def _build_resources(payload):
    requests = {}
    limits = {}
    if payload.get("cpu_request"):
        requests["cpu"] = payload["cpu_request"]
    if payload.get("mem_request"):
        requests["memory"] = payload["mem_request"]
    if payload.get("cpu_limit"):
        limits["cpu"] = payload["cpu_limit"]
    if payload.get("mem_limit"):
        limits["memory"] = payload["mem_limit"]
    resources = {}
    if requests:
        resources["requests"] = requests
    if limits:
        resources["limits"] = limits
    return resources


@router.post("/api/namespaces/create")
def api_namespace_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        name = payload.get("name", "")
        if not cluster or not name:
            return JSONResponse({"ok": False, "message": "cluster 和 name 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.create_namespace({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}})
        return JSONResponse({"ok": True, "cluster": cluster, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/namespaces/{cluster}/{name}/delete")
def api_namespace_delete(cluster: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.delete_namespace(name)
        return JSONResponse({"ok": True, "cluster": cluster, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/statefulsets/create")
def api_statefulset_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        image = payload.get("image", "")
        if not cluster or not name or not image:
            return JSONResponse({"ok": False, "message": "cluster、name、image 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        replicas = int(payload.get("replicas", 1))
        service_name = payload.get("service_name") or name
        container_port = int(payload.get("container_port", 80))
        resources = _build_resources(payload)
        container = {
            "name": name,
            "image": image,
            "ports": [{"containerPort": container_port}],
        }
        if resources:
            container["resources"] = resources
        body = {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "serviceName": service_name,
                "replicas": replicas,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {"containers": [container]},
                },
            },
        }
        apps_v1.create_namespaced_stateful_set(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/statefulsets/{cluster}/{namespace}/{name}/delete")
def api_statefulset_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        apps_v1.delete_namespaced_stateful_set(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/daemonsets/create")
def api_daemonset_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        image = payload.get("image", "")
        if not cluster or not name or not image:
            return JSONResponse({"ok": False, "message": "cluster、name、image 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        container_port = int(payload.get("container_port", 80))
        resources = _build_resources(payload)
        container = {
            "name": name,
            "image": image,
            "ports": [{"containerPort": container_port}],
        }
        if resources:
            container["resources"] = resources
        body = {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {"containers": [container]},
                },
            },
        }
        apps_v1.create_namespaced_daemon_set(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/daemonsets/{cluster}/{namespace}/{name}/delete")
def api_daemonset_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, apps_v1, _ = _get_k8s_client(ds)
        apps_v1.delete_namespaced_daemon_set(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/services/create")
def api_service_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        if not cluster or not name:
            return JSONResponse({"ok": False, "message": "cluster、name 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        svc_type = payload.get("type", "ClusterIP")
        port = int(payload.get("port", 80))
        target_port = int(payload.get("target_port", port))
        protocol = payload.get("protocol", "TCP")
        body = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "type": svc_type,
                "selector": {"app": payload.get("selector_app", name)},
                "ports": [{"port": port, "targetPort": target_port, "protocol": protocol}],
            },
        }
        v1.create_namespaced_service(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/services/{cluster}/{namespace}/{name}/delete")
def api_service_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.delete_namespaced_service(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/ingresses/create")
def api_ingress_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        host = payload.get("host", "")
        if not cluster or not name or not host:
            return JSONResponse({"ok": False, "message": "cluster、name、host 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, _, net_v1 = _get_k8s_client(ds)
        path = payload.get("path", "/")
        service_name = payload.get("service_name", "")
        service_port = int(payload.get("service_port", 80))
        tls = bool(payload.get("tls", False))
        spec = {
            "rules": [{
                "host": host,
                "http": {
                    "paths": [{
                        "path": path,
                        "pathType": "Prefix",
                        "backend": {
                            "service": {"name": service_name, "port": {"number": service_port}},
                        },
                    }],
                },
            }],
        }
        if tls:
            spec["tls"] = [{"hosts": [host], "secretName": f"{name}-tls"}]
        body = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }
        net_v1.create_namespaced_ingress(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/ingresses/{cluster}/{namespace}/{name}/delete")
def api_ingress_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        _, _, net_v1 = _get_k8s_client(ds)
        net_v1.delete_namespaced_ingress(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/configmaps/create")
def api_configmap_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        if not cluster or not name:
            return JSONResponse({"ok": False, "message": "cluster、name 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        body = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": name, "namespace": namespace},
            "data": payload.get("data", {}) or {},
        }
        v1.create_namespaced_config_map(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/configmaps/{cluster}/{namespace}/{name}/delete")
def api_configmap_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.delete_namespaced_config_map(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/secrets/create")
def api_secret_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        import base64
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        if not cluster or not name:
            return JSONResponse({"ok": False, "message": "cluster、name 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        secret_type = payload.get("type", "Opaque")
        raw_data = payload.get("data", {}) or {}
        encoded = {k: base64.b64encode(str(v).encode("utf-8")).decode("utf-8") for k, v in raw_data.items()}
        body = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": namespace},
            "type": secret_type,
            "data": encoded,
        }
        v1.create_namespaced_secret(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/secrets/{cluster}/{namespace}/{name}/delete")
def api_secret_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.delete_namespaced_secret(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/pvcs/create")
def api_pvc_create(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        cluster = payload.get("cluster", "")
        namespace = payload.get("namespace", "default")
        name = payload.get("name", "")
        if not cluster or not name:
            return JSONResponse({"ok": False, "message": "cluster、name 必填"}, status_code=400)
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        storage = payload.get("storage", "5Gi")
        access_mode = payload.get("access_mode", "ReadWriteOnce")
        storage_class = payload.get("storage_class", "")
        spec = {
            "accessModes": [access_mode],
            "resources": {"requests": {"storage": storage}},
        }
        if storage_class:
            spec["storageClassName"] = storage_class
        body = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": name, "namespace": namespace},
            "spec": spec,
        }
        v1.create_namespaced_persistent_volume_claim(namespace, body)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.post("/api/pvcs/{cluster}/{namespace}/{name}/delete")
def api_pvc_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        v1.delete_namespaced_persistent_volume_claim(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


_K8S_DESCRIBE_READERS = {
    "pods": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespaced_pod(name, ns),
    "deployments": lambda v1, apps_v1, net_v1, ns, name: apps_v1.read_namespaced_deployment(name, ns),
    "statefulsets": lambda v1, apps_v1, net_v1, ns, name: apps_v1.read_namespaced_stateful_set(name, ns),
    "daemonsets": lambda v1, apps_v1, net_v1, ns, name: apps_v1.read_namespaced_daemon_set(name, ns),
    "services": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespaced_service(name, ns),
    "ingresses": lambda v1, apps_v1, net_v1, ns, name: net_v1.read_namespaced_ingress(name, ns),
    "configmaps": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespaced_config_map(name, ns),
    "secrets": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespaced_secret(name, ns),
    "hpas": lambda v1, apps_v1, net_v1, ns, name: __import__("kubernetes").client.AutoscalingV1Api(v1.api_client).read_namespaced_horizontal_pod_autoscaler(name, ns),
    "pvcs": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespaced_persistent_volume_claim(name, ns),
    "pvs": lambda v1, apps_v1, net_v1, ns, name: v1.read_persistent_volume(name),
    "namespaces": lambda v1, apps_v1, net_v1, ns, name: v1.read_namespace(name),
}


@router.get("/api/describe/{resource_type}/{cluster}/{namespace}/{name}")
def api_describe_resource(resource_type: str, cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"error": "K8s data source not found"}, status_code=404)
        v1, apps_v1, net_v1 = _get_k8s_client(ds)
        reader = _K8S_DESCRIBE_READERS.get(resource_type)
        if not reader:
            return JSONResponse({"error": f"Unsupported resource type: {resource_type}"}, status_code=400)
        obj = reader(v1, apps_v1, net_v1, namespace, name)
        import yaml
        data = obj.to_dict() if hasattr(obj, 'to_dict') else str(obj)
        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return JSONResponse({"yaml": yaml_str, "resource_type": resource_type, "name": name, "namespace": namespace, "cluster": cluster})
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/pod/{cluster}/{namespace}/{name}/logs")
def api_pod_logs(cluster: str, namespace: str, name: str, tail: int = 500, container: str = "", since_seconds: int = 0, previous: bool = False, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "message": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        containers = []
        try:
            pod_obj = v1.read_namespaced_pod(name, namespace)
            containers = [c.name for c in (pod_obj.spec.containers or [])]
        except Exception:
            pass
        if not containers:
            containers = [name]
        use_container = container if container and container in containers else containers[0]
        tail_lines = min(max(tail, 1), 10000)
        kwargs = {"tail_lines": tail_lines, "_preload_content": False}
        if since_seconds and since_seconds > 0:
            kwargs["since_seconds"] = since_seconds
        if previous:
            kwargs["previous"] = True
        try:
            resp = v1.read_namespaced_pod_log(name, namespace, container=use_container, **kwargs)
            raw = resp.data if hasattr(resp, "data") else resp
            if isinstance(raw, bytes):
                log_data = raw.decode("utf-8", errors="replace")
            else:
                log_data = str(raw)
                if log_data.startswith("b'") or log_data.startswith('b"'):
                    import ast
                    try:
                        log_data = ast.literal_eval(log_data).decode("utf-8", errors="replace")
                    except Exception:
                        pass
        except Exception as le:
            return JSONResponse({"ok": False, "message": str(le), "containers": containers, "warning": str(le)}, status_code=200)
        lines = log_data.count("\n") + (1 if log_data and not log_data.endswith("\n") else 0)
        truncated = lines >= tail_lines
        max_show = 2000
        show_data = log_data
        truncated_display = False
        if lines > max_show:
            show_data = "\n".join(log_data.split("\n")[:max_show])
            truncated_display = True
        return JSONResponse({
            "ok": True, "logs": show_data, "full_logs": log_data,
            "pod": name, "namespace": namespace, "cluster": cluster,
            "container": use_container, "containers": containers,
            "lines": lines, "tail": tail_lines, "truncated": truncated,
            "display_truncated": truncated_display, "max_show": max_show,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=200)


@router.get("/api/pod/{cluster}/{namespace}/{name}/logs/download")
def api_pod_logs_download(cluster: str, namespace: str, name: str, tail: int = 10000, container: str = "", since_seconds: int = 0, previous: bool = False, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return PlainTextResponse("Cluster not found", status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        containers = []
        try:
            pod_obj = v1.read_namespaced_pod(name, namespace)
            containers = [c.name for c in (pod_obj.spec.containers or [])]
        except Exception:
            pass
        if not containers:
            containers = [name]
        use_container = container if container and container in containers else containers[0]
        tail_lines = min(max(tail, 1), 50000)
        kwargs = {"tail_lines": tail_lines, "_preload_content": False}
        if since_seconds and since_seconds > 0:
            kwargs["since_seconds"] = since_seconds
        if previous:
            kwargs["previous"] = True
        resp = v1.read_namespaced_pod_log(name, namespace, container=use_container, **kwargs)
        raw = resp.data if hasattr(resp, "data") else resp
        if isinstance(raw, bytes):
            log_data = raw.decode("utf-8", errors="replace")
        else:
            log_data = str(raw)
            if log_data.startswith("b'") or log_data.startswith('b"'):
                import ast
                try:
                    log_data = ast.literal_eval(log_data).decode("utf-8", errors="replace")
                except Exception:
                    pass
        fname = f"{name}-{use_container}-{datetime.now().strftime('%Y%m%d%H%M%S')}.log"
        return PlainTextResponse(log_data, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={fname}"})
    except Exception as e:
        return PlainTextResponse(f"日志下载失败: {e}", status_code=200)


@router.get("/api/pod/{cluster}/{namespace}/{name}/logs-page")
def api_pod_logs_page(request: Request, cluster: str, namespace: str, name: str, tail: int = 200):
    return templates.TemplateResponse("pod_logs.html", {
        "request": request, "cluster": cluster,
        "namespace": namespace, "pod": name, "tail": tail,
    })


@router.get("/api/pod/{cluster}/{namespace}/{name}/terminal-page")
def api_pod_terminal_page(request: Request, cluster: str, namespace: str, name: str):
    return templates.TemplateResponse("k8s_terminal.html", {
        "request": request, "cluster": cluster,
        "namespace": namespace, "pod": name,
    })


@router.websocket("/ws/pod/{cluster}/{namespace}/{name}/terminal")
async def api_pod_terminal_ws(websocket: WebSocket, cluster: str, namespace: str, name: str):
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
        ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
        db.close()
        if not ds:
            await websocket.send_text("K8s data source not found")
            await websocket.close()
            return

        from kubernetes import client
        from app.services.connection_service import ConnectionTester
        cfg = parse_json_config(ds.auth_config)

        configuration = client.Configuration()
        if cfg.get("kubeconfig"):
            from kubernetes import config
            config.load_kube_config_from_dict(cfg["kubeconfig"])
            api_client = client.ApiClient()
        elif cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            configuration.host = cfg["k8s_api_server"]
            configuration.api_key = {"authorization": "Bearer " + cfg["k8s_token"]}
            configuration.verify_ssl = cfg.get("verify_ssl", False)
            configuration.timeout = 30
            api_client = client.ApiClient(configuration)
        else:
            await websocket.send_text("K8s 连接配置不完整")
            await websocket.close()
            return

        v1 = client.CoreV1Api(api_client)
        from kubernetes import stream as k8s_stream
        try:
            kws = k8s_stream.stream(
                v1.connect_get_namespaced_pod_exec,
                name, namespace,
                command=["/bin/sh", "-c", "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi"],
                stderr=True, stdin=True, stdout=True, tty=True,
                _preload_content=False,
            )
        except Exception:
            kws = k8s_stream.stream(
                v1.connect_get_namespaced_pod_exec,
                name, namespace, command=["sh"],
                stderr=True, stdin=True, stdout=True, tty=True,
                _preload_content=False,
            )
        kws.sock.settimeout(None)

        import asyncio

        async def k8s_to_browser():
            loop = asyncio.get_event_loop()
            try:
                while True:
                    data = await loop.run_in_executor(None, kws.sock.recv)
                    if isinstance(data, bytes) and len(data) > 1:
                        channel = data[0]
                        payload = data[1:]
                        if channel in (1, 2, 3):
                            await websocket.send_bytes(payload)
                        elif channel == 4:
                            pass
                    elif isinstance(data, str) and data:
                        await websocket.send_text(data)
            except Exception:
                pass

        async def browser_to_k8s():
            loop = asyncio.get_event_loop()
            try:
                while True:
                    data = await websocket.receive()
                    if data.get("type") == "websocket.disconnect":
                        break
                    msg = data.get("text") or data.get("bytes")
                    if msg:
                        if isinstance(msg, str):
                            await loop.run_in_executor(None, kws.sock.send, "\x00" + msg)
                        else:
                            await loop.run_in_executor(None, kws.sock.send_binary, b"\x00" + msg)
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
            await websocket.send_text(f"连接异常: {e}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/api/hpa/recommend")
def api_hpa_recommend(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    """基于当前资源用量推荐 HPA 配置"""
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if not ds:
            return JSONResponse({"items": [], "total": 0, "cluster": "", "cluster_count": len(clusters), "warning": "未配置任何 K8s 集群，请先在「数据源管理」中添加集群"})

        # 集群被禁用或连不通时返回空数据 + 友好提示，不抛 500
        if ds.enabled is False:
            return JSONResponse({"items": [], "total": 0, "cluster": ds.name, "cluster_count": len(clusters), "warning": f"K8s 集群 [{ds.name}] 已被禁用，请在「数据源管理」中启用"})
        try:
            _, apps_v1, _ = _get_k8s_client(ds)
        except Exception as ce:
            return JSONResponse({"items": [], "total": 0, "cluster": ds.name, "cluster_count": len(clusters), "warning": f"K8s 集群 [{ds.name}] 连接失败: {ce}"})

        raw = apps_v1.list_namespaced_deployment(namespace) if namespace else apps_v1.list_deployment_for_all_namespaces().items

        v1, _, _ = _get_k8s_client(ds)

        recommendations = []
        for d in raw:
            name = d.metadata.name
            ns = d.metadata.namespace
            replicas = d.spec.replicas or 1
            available = d.status.available_replicas or 0

            containers = d.spec.template.spec.containers or []
            cpu_request = 0
            mem_request = 0
            for c in containers:
                if c.resources and c.resources.requests:
                    cpu_request += _parse_k8s_resource(c.resources.requests.get("cpu", "0"))
                    mem_request += _parse_k8s_resource(c.resources.requests.get("memory", "0"), is_memory=True)

            # 从 metrics 获取实际使用率（若无 metrics server 则基于 replicas 估算）
            actual_cpu_usage = 0
            actual_mem_usage = 0
            try:
                from kubernetes.client import CustomObjectsApi
                custom = CustomObjectsApi(v1.api_client)
                metrics_data = custom.list_namespaced_custom_object(
                    group="metrics.k8s.io", version="v1beta1",
                    namespace=ns, plural="pods",
                )
                pod_metrics = metrics_data.get("items", [])
                for pm in pod_metrics:
                    p_name = pm.get("metadata", {}).get("name", "")
                    if p_name.startswith(name):
                        containers_metrics = pm.get("containers", [])
                        for cm in containers_metrics:
                            actual_cpu_usage += _parse_k8s_resource(cm.get("usage", {}).get("cpu", "0"))
                            actual_mem_usage += _parse_k8s_resource(cm.get("usage", {}).get("memory", "0"), is_memory=True)
            except Exception:
                pass

            if replicas > 0:
                avg_cpu_per_pod = actual_cpu_usage / replicas if actual_cpu_usage else cpu_request * 0.3
                avg_mem_per_pod = actual_mem_usage / replicas if actual_mem_usage else mem_request * 0.4
                cpu_util_pct = round(avg_cpu_per_pod / cpu_request * 100, 1) if cpu_request else 0
                mem_util_pct = round(avg_mem_per_pod / mem_request * 100, 1) if mem_request else 0
            else:
                cpu_util_pct = 0
                mem_util_pct = 0

            target_cpu = 50
            target_mem = 50
            if cpu_util_pct > 0:
                suggested_cpu_replicas = max(1, round(replicas * cpu_util_pct / target_cpu))
            else:
                suggested_cpu_replicas = replicas
            if mem_util_pct > 0:
                suggested_mem_replicas = max(1, round(replicas * mem_util_pct / target_mem))
            else:
                suggested_mem_replicas = replicas

            suggested_replicas = max(suggested_cpu_replicas, suggested_mem_replicas, 1)

            needs_hpa = (cpu_util_pct > 60 or mem_util_pct > 60 or replicas <= 1)
            recommendations.append({
                "name": name,
                "namespace": ns,
                "cluster": ds.name,
                "current_replicas": replicas,
                "available_replicas": available,
                "cpu_request_m": cpu_request,
                "mem_request_mb": round(mem_request / (1024 * 1024), 1),
                "cpu_util_pct": cpu_util_pct,
                "mem_util_pct": mem_util_pct,
                "suggested_min_replicas": max(1, suggested_replicas),
                "suggested_max_replicas": max(suggested_replicas * 3, 3),
                "target_cpu_util_pct": target_cpu,
                "target_mem_util_pct": target_mem,
                "needs_hpa": needs_hpa,
                "has_metrics": bool(actual_cpu_usage or actual_mem_usage),
            })

        recommendations.sort(key=lambda x: x["needs_hpa"], reverse=True)
        return JSONResponse({
            "items": recommendations,
            "total": len(recommendations),
            "cluster": ds.name,
            "cluster_count": len(clusters),
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/resource-optimization")
def api_resource_optimization(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    """分析 Pod 资源请求/限制，给出优化建议"""
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        ds = _get_k8s_ds(db, cluster) if cluster else (clusters[0] if clusters else None)
        if not ds:
            return JSONResponse({"suggestions": [], "summary": {"total": 0, "critical": 0, "warning": 0, "ok": 0}, "cluster": "", "warning": "未配置任何 K8s 集群，请先在「数据源管理」中添加集群"})

        # 集群被禁用或连不通时返回空数据 + 友好提示，不抛 500
        if ds.enabled is False:
            return JSONResponse({"suggestions": [], "summary": {"total": 0, "critical": 0, "warning": 0, "ok": 0}, "cluster": ds.name, "warning": f"K8s 集群 [{ds.name}] 已被禁用，请在「数据源管理」中启用"})
        try:
            v1, apps_v1, _ = _get_k8s_client(ds)
        except Exception as ce:
            return JSONResponse({"suggestions": [], "summary": {"total": 0, "critical": 0, "warning": 0, "ok": 0}, "cluster": ds.name, "warning": f"K8s 集群 [{ds.name}] 连接失败: {ce}"})

        raw_pods = v1.list_pod_for_all_namespaces().items
        raw_deployments = apps_v1.list_deployment_for_all_namespaces().items

        ns_filter = namespace or None

        suggestions = []
        dep_map = {}
        for d in raw_deployments:
            key = f"{d.metadata.namespace}/{d.metadata.name}"
            dep_map[key] = d

        for pod in raw_pods:
            ns = pod.metadata.namespace
            if ns_filter and ns != ns_filter:
                continue

            owner_refs = pod.metadata.owner_references or []
            is_controlled = any(r.controller for r in owner_refs if r.controller)

            containers = pod.spec.containers or []
            for c in containers:
                name = c.name
                req = c.resources.requests if c.resources else None
                lim = c.resources.limits if c.resources else None

                c_req_cpu = _parse_k8s_resource(req.get("cpu", "0")) if req else 0
                c_req_mem = _parse_k8s_resource(req.get("memory", "0"), is_memory=True) if req else 0
                c_lim_cpu = _parse_k8s_resource(lim.get("cpu", "0")) if lim else 0
                c_lim_mem = _parse_k8s_resource(lim.get("memory", "0"), is_memory=True) if lim else 0

                issues = []
                if c_req_cpu == 0 and c_req_mem == 0:
                    issues.append("未设置资源请求 (resources.requests)")
                if c_lim_cpu == 0 and c_lim_mem == 0:
                    issues.append("未设置资源限制 (resources.limits)")
                if c_lim_cpu > 0 and c_req_cpu > 0 and c_lim_cpu / c_req_cpu > 5:
                    issues.append(f"CPU limits/requests 比例过大 ({c_lim_cpu//c_req_cpu}x)")
                if c_lim_mem > 0 and c_req_mem > 0 and c_lim_mem / c_req_mem > 5:
                    issues.append(f"内存 limits/requests 比例过大 ({c_lim_mem//c_req_mem}x)")
                if c_req_cpu > 8000:
                    issues.append(f"CPU request 过大 ({c_req_cpu}m)")
                if c_req_mem > 8 * 1024 * 1024 * 1024:
                    issues.append(f"内存 request 过大 ({c_req_mem/(1024*1024*1024):.1f}Gi)")

                suggestions.append({
                    "pod_name": pod.metadata.name,
                    "namespace": ns,
                    "container": name,
                    "cluster": ds.name,
                    "is_controlled": is_controlled,
                    "cpu_request_m": c_req_cpu,
                    "cpu_limit_m": c_lim_cpu,
                    "mem_request_mb": round(c_req_mem / (1024 * 1024), 1) if c_req_mem else 0,
                    "mem_limit_mb": round(c_lim_mem / (1024 * 1024), 1) if c_lim_mem else 0,
                    "issues": issues,
                    "severity": "critical" if not c_req_cpu else ("warning" if issues else "ok"),
                })

        critical = [s for s in suggestions if s["severity"] == "critical"]
        warning = [s for s in suggestions if s["severity"] == "warning"]
        ok = [s for s in suggestions if s["severity"] == "ok"]

        return JSONResponse({
            "suggestions": suggestions,
            "summary": {
                "total": len(suggestions),
                "critical": len(critical),
                "warning": len(warning),
                "ok": len(ok),
            },
            "cluster": ds.name,
        })
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


def _parse_k8s_resource(value: str, is_memory: bool = False) -> int:
    """解析 K8s 资源值为 millicores (cpu) 或 bytes (memory)"""
    value = str(value).strip()
    if not value:
        return 0
    if is_memory:
        multipliers = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4, "k": 1000, "M": 1000**2, "G": 1000**3}
        for suffix, mul in multipliers.items():
            if value.endswith(suffix):
                try:
                    return int(float(value[:-len(suffix)]) * mul)
                except ValueError:
                    return 0
        if value.endswith("m"):
            return 0
        try:
            return int(float(value))
        except ValueError:
            return 0
    else:
        if value.endswith("m"):
            try:
                return int(value[:-1])
            except ValueError:
                return 0
        multipliers = {"": 1000, "k": 1000**2}
        for suffix, mul in multipliers.items():
            if value.endswith(suffix) if suffix else not any(s in value for s in ("m", "k")):
                try:
                    return int(float(value) * mul)
                except ValueError:
                    pass
        try:
            return int(float(value) * 1000)
        except ValueError:
            return 0
