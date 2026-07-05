import json
from fastapi import APIRouter, Depends, Request, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates, parse_json_config
from app.models import DataSource

router = APIRouter(prefix="/k8s", tags=["k8s_resources"])
templates = get_templates()


def _get_k8s_client(ds: DataSource):
    from kubernetes import config, client
    cfg = parse_json_config(ds.auth_config)
    if cfg.get("kubeconfig"):
        config.load_kube_config_from_dict(cfg["kubeconfig"])
    else:
        config.load_kube_config()
    # 设置请求超时，避免连不通的集群卡死整个请求
    api_client = client.ApiClient()
    api_client.configuration.timeout = 2
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
            ctx["cluster_info"] = {"name": ds.name, "endpoint": ds.endpoint, "status": ds.last_status, "last_scrape": ds.last_scrape}
    return ctx


@router.get("/api/overview")
def api_overview(db: Session = Depends(get_db)):
    try:
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
        for ds in clusters:
            if ds.last_status == "error" or not ds.endpoint:
                overviews.append({
                    "name": ds.name, "endpoint": ds.endpoint,
                    "status": "error" if ds.last_status == "error" else "unknown",
                    "nodes": 0, "healthy_nodes": 0, "node_health_rate": 0,
                    "pods": 0, "running_pods": 0, "pod_running_rate": 0,
                    "deployments": 0, "namespaces": 0, "services": 0,
                    "last_scrape": str(ds.last_scrape) if ds.last_scrape else None,
                })
                if ds.last_status == "error":
                    errors.append(f"{ds.name}: 数据源状态为 error，跳过探测")
                continue
            try:
                from kubernetes import client
                v1, apps_v1, _ = _get_k8s_client(ds)
                nodes = v1.list_node().items
                pods = v1.list_pod_for_all_namespaces().items
                deployments = apps_v1.list_deployment_for_all_namespaces().items
                try:
                    ns_count = len(v1.list_namespace().items)
                except Exception:
                    ns_count = 0
                try:
                    svc_count = len(v1.list_service_for_all_namespaces().items)
                except Exception:
                    svc_count = 0
                healthy_nodes = sum(1 for n in nodes if all(c.status == "True" for c in n.status.conditions if c.type == "Ready"))
                running_pods = sum(1 for p in pods if (p.status.phase or "") == "Running")
                node_rate = round(healthy_nodes / len(nodes) * 100, 1) if nodes else 0
                pod_rate = round(running_pods / len(pods) * 100, 1) if pods else 0
                overviews.append({
                    "name": ds.name, "endpoint": ds.endpoint, "status": ds.last_status,
                    "nodes": len(nodes), "healthy_nodes": healthy_nodes, "node_health_rate": node_rate,
                    "pods": len(pods), "running_pods": running_pods, "pod_running_rate": pod_rate,
                    "deployments": len(deployments), "namespaces": ns_count, "services": svc_count,
                    "last_scrape": str(ds.last_scrape) if ds.last_scrape else None,
                })
                total_nodes += len(nodes)
                total_healthy_nodes += healthy_nodes
                total_pods += len(pods)
                total_running_pods += running_pods
                total_deployments += len(deployments)
                total_namespaces += ns_count
                total_services += svc_count
                if ds.last_status == "online":
                    healthy_clusters += 1
            except Exception as e:
                errors.append(f"{ds.name}: {e}")
                overviews.append({
                    "name": ds.name, "endpoint": ds.endpoint, "status": "error",
                    "nodes": 0, "healthy_nodes": 0, "node_health_rate": 0,
                    "pods": 0, "running_pods": 0, "pod_running_rate": 0,
                    "deployments": 0, "namespaces": 0, "services": 0,
                    "last_scrape": str(ds.last_scrape) if ds.last_scrape else None,
                })
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
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/statefulsets")
def api_statefulset_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/daemonsets")
def api_daemonset_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/services")
def api_service_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/ingresses")
def api_ingress_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/configmaps")
def api_configmap_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/secrets")
def api_secret_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/hpas")
def api_hpa_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/pvcs")
def api_pvc_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/pvs")
def api_pv_list(cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    try:
        clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
        items = []
        error = None
        ds = _get_k8s_ds(db, cluster) if cluster else None
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
            "items": items, "cluster": cluster, "namespace": namespace, "error": error,
            "clusters": [{"name": c.name, "endpoint": c.endpoint, "status": c.last_status} for c in clusters],
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/configmaps/{cluster}/{namespace}/{name}")
def api_configmap_detail(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        data = cm.data or {}
        return JSONResponse({
            "cluster": cluster, "namespace": namespace, "name": name, "data": data,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/configmaps/{cluster}/{namespace}/{name}/update")
def api_configmap_update(cluster: str, namespace: str, name: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        cm.data = payload.get("data", {})
        v1.replace_namespaced_config_map(name, namespace, cm)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


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
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
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
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/hpas/{cluster}/{namespace}/{name}/update")
def api_hpa_update(cluster: str, namespace: str, name: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        from kubernetes import client
        min_replicas = int(payload.get("min_replicas", 1))
        max_replicas = int(payload.get("max_replicas", 3))
        cpu_percent = int(payload.get("cpu_percent", 80))
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        hpa = autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        hpa.spec.min_replicas = min_replicas
        hpa.spec.max_replicas = max_replicas
        hpa.spec.target_cpu_utilization_percentage = cpu_percent
        autoscaling_v1.replace_namespaced_horizontal_pod_autoscaler(name, namespace, hpa)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/api/hpas/{cluster}/{namespace}/{name}/delete")
def api_hpa_delete(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    try:
        from kubernetes import client
        ds = _get_k8s_ds(db, cluster)
        if not ds:
            return JSONResponse({"ok": False, "error": "Cluster not found"}, status_code=404)
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        autoscaling_v1.delete_namespaced_horizontal_pod_autoscaler(name, namespace)
        return JSONResponse({"ok": True, "cluster": cluster, "namespace": namespace, "name": name})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
