import json
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
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


@router.get("/configmaps", response_class=HTMLResponse)
def configmap_list(
    request: Request,
    cluster: str = "",
    namespace: str = "",
    db: Session = Depends(get_db),
):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    configmaps = []
    error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            v1, _, _ = _get_k8s_client(ds)
            if namespace:
                items = v1.list_namespaced_config_map(namespace).items
            else:
                items = v1.list_config_map_for_all_namespaces().items
            for cm in items:
                configmaps.append({
                    "name": cm.metadata.name,
                    "namespace": cm.metadata.namespace,
                    "data_keys": list(cm.data.keys()) if cm.data else [],
                    "data_count": len(cm.data) if cm.data else 0,
                })
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_configmaps.html", _add_cluster_info({
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "namespace": namespace,
        "configmaps": configmaps,
        "error": error,
    }, db))


@router.get("/configmaps/{cluster}/{namespace}/{name}", response_class=HTMLResponse)
def configmap_detail(
    request: Request,
    cluster: str,
    namespace: str,
    name: str,
    db: Session = Depends(get_db),
):
    ds = _get_k8s_ds(db, cluster)
    if not ds:
        return PlainTextResponse("Cluster not found", status_code=404)
    try:
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        data = cm.data or {}
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    return templates.TemplateResponse("k8s_configmap_detail.html", {
        "request": request,
        "cluster": cluster,
        "namespace": namespace,
        "name": name,
        "data": data,
    })


@router.post("/configmaps/{cluster}/{namespace}/{name}/update")
def configmap_update(
    request: Request,
    cluster: str,
    namespace: str,
    name: str,
    db: Session = Depends(get_db),
):
    ds = _get_k8s_ds(db, cluster)
    if not ds:
        return PlainTextResponse("Cluster not found", status_code=404)
    try:
        form = request.form()
        v1, _, _ = _get_k8s_client(ds)
        cm = v1.read_namespaced_config_map(name, namespace)
        new_data = {}
        for key in form.keys():
            if key.startswith("data_"):
                actual_key = key[5:]
                new_data[actual_key] = form[key]
        cm.data = new_data
        v1.replace_namespaced_config_map(name, namespace, cm)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    return RedirectResponse(f"/k8s/configmaps/{cluster}/{namespace}/{name}", status_code=303)


@router.get("/secrets", response_class=HTMLResponse)
def secret_list(
    request: Request,
    cluster: str = "",
    namespace: str = "",
    db: Session = Depends(get_db),
):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    secrets = []
    error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            v1, _, _ = _get_k8s_client(ds)
            if namespace:
                items = v1.list_namespaced_secret(namespace).items
            else:
                items = v1.list_secret_for_all_namespaces().items
            for s in items:
                s_type = s.type or "Opaque"
                secrets.append({
                    "name": s.metadata.name,
                    "namespace": s.metadata.namespace,
                    "type": s_type,
                    "data_count": len(s.data) if s.data else 0,
                })
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_secrets.html", _add_cluster_info({
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "namespace": namespace,
        "secrets": secrets,
        "error": error,
    }, db))


@router.get("/services", response_class=HTMLResponse)
def service_list(
    request: Request,
    cluster: str = "",
    namespace: str = "",
    db: Session = Depends(get_db),
):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    services = []
    error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            v1, _, _ = _get_k8s_client(ds)
            if namespace:
                items = v1.list_namespaced_service(namespace).items
            else:
                items = v1.list_service_for_all_namespaces().items
            for svc in items:
                ports = []
                for p in (svc.spec.ports or []):
                    ports.append(f"{p.port}/{p.protocol}" + (f"->{p.node_port}" if p.node_port else ""))
                services.append({
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "type": svc.spec.type or "ClusterIP",
                    "cluster_ip": svc.spec.cluster_ip or "-",
                    "ports": ", ".join(ports),
                })
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_services.html", _add_cluster_info({
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "namespace": namespace,
        "services": services,
        "error": error,
    }, db))


@router.get("/hpas", response_class=HTMLResponse)
def hpa_list(
    request: Request,
    cluster: str = "",
    namespace: str = "",
    db: Session = Depends(get_db),
):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    hpas = []
    error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            from kubernetes import client
            _, apps_v1, _ = _get_k8s_client(ds)
            autoscaling_v1 = client.AutoscalingV1Api()
            if namespace:
                items = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace).items
            else:
                items = autoscaling_v1.list_horizontal_pod_autoscaler_for_all_namespaces().items
            for hpa in items:
                hpas.append({
                    "name": hpa.metadata.name,
                    "namespace": hpa.metadata.namespace,
                    "min_replicas": hpa.spec.min_replicas or 1,
                    "max_replicas": hpa.spec.max_replicas,
                    "current_replicas": hpa.status.current_replicas or 0,
                    "desired_replicas": hpa.status.desired_replicas or 0,
                    "target_cpu_utilization": hpa.spec.target_cpu_utilization_percentage or "-",
                    "current_cpu_utilization": (hpa.status.current_cpu_utilization_percentage or "-") if hasattr(hpa.status, 'current_cpu_utilization_percentage') else "-",
                })
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_hpas.html", _add_cluster_info({
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "namespace": namespace,
        "hpas": hpas,
        "error": error,
    }, db))


@router.get("/overview", response_class=HTMLResponse)
def cluster_overview(request: Request, db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    overviews = []
    errors = []
    # 全局汇总
    total_nodes = 0
    total_healthy_nodes = 0
    total_pods = 0
    total_running_pods = 0
    total_deployments = 0
    total_namespaces = 0
    total_services = 0
    healthy_clusters = 0
    for ds in clusters:
        # 跳过已知不可达的数据源，避免 K8s API 调用超时卡死页面
        if ds.last_status == "error" or not ds.endpoint:
            overviews.append({
                "name": ds.name,
                "endpoint": ds.endpoint,
                "status": "error" if ds.last_status == "error" else "unknown",
                "nodes": 0, "healthy_nodes": 0, "node_health_rate": 0,
                "pods": 0, "running_pods": 0, "pod_running_rate": 0,
                "deployments": 0, "namespaces": 0, "services": 0,
                "last_scrape": ds.last_scrape,
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
                namespaces = v1.list_namespace().items
                ns_count = len(namespaces)
            except Exception:
                ns_count = 0
            try:
                services = v1.list_service_for_all_namespaces().items
                svc_count = len(services)
            except Exception:
                svc_count = 0
            healthy_nodes = sum(1 for n in nodes if all(c.status == "True" for c in n.status.conditions if c.type == "Ready"))
            running_pods = sum(1 for p in pods if (p.status.phase or "") == "Running")
            node_rate = round(healthy_nodes / len(nodes) * 100, 1) if nodes else 0
            pod_rate = round(running_pods / len(pods) * 100, 1) if pods else 0
            overviews.append({
                "name": ds.name,
                "endpoint": ds.endpoint,
                "status": ds.last_status,
                "nodes": len(nodes),
                "healthy_nodes": healthy_nodes,
                "node_health_rate": node_rate,
                "pods": len(pods),
                "running_pods": running_pods,
                "pod_running_rate": pod_rate,
                "deployments": len(deployments),
                "namespaces": ns_count,
                "services": svc_count,
                "last_scrape": ds.last_scrape,
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
                "name": ds.name,
                "endpoint": ds.endpoint,
                "status": "error",
                "nodes": 0, "healthy_nodes": 0, "node_health_rate": 0,
                "pods": 0, "running_pods": 0, "pod_running_rate": 0,
                "deployments": 0, "namespaces": 0, "services": 0,
                "last_scrape": ds.last_scrape,
            })
    summary = {
        "cluster_count": len(clusters),
        "healthy_clusters": healthy_clusters,
        "total_nodes": total_nodes,
        "total_healthy_nodes": total_healthy_nodes,
        "node_health_rate": round(total_healthy_nodes / total_nodes * 100, 1) if total_nodes else 0,
        "total_pods": total_pods,
        "total_running_pods": total_running_pods,
        "pod_running_rate": round(total_running_pods / total_pods * 100, 1) if total_pods else 0,
        "total_deployments": total_deployments,
        "total_namespaces": total_namespaces,
        "total_services": total_services,
    }
    return templates.TemplateResponse("k8s_overview.html", {
        "request": request,
        "overviews": overviews,
        "errors": errors,
        "summary": summary,
    })


@router.get("/hpas/new", response_class=HTMLResponse)
def hpa_new_form(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return templates.TemplateResponse("k8s_hpa_form.html", _add_cluster_info({
        "request": request, "clusters": clusters, "cluster": cluster, "namespace": namespace, "hpa": None,
    }, db))


@router.post("/hpas/create")
def hpa_create(request: Request, db: Session = Depends(get_db)):
    from kubernetes import client
    form = request.form()
    cluster = form["cluster"]
    namespace = form.get("namespace", "default")
    name = form["name"]
    target_kind = form.get("target_kind", "Deployment")
    target_name = form["target_name"]
    min_replicas = int(form.get("min_replicas", 1))
    max_replicas = int(form.get("max_replicas", 3))
    cpu_target = int(form.get("cpu_target", 80))

    ds = _get_k8s_ds(db, cluster)
    if not ds:
        return PlainTextResponse("Cluster not found", status_code=404)
    try:
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        body = {
            "apiVersion": "autoscaling/v1",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": target_kind,
                    "name": target_name,
                },
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "targetCPUUtilizationPercentage": cpu_target,
            },
        }
        autoscaling_v1.create_namespaced_horizontal_pod_autoscaler(namespace, body)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    return RedirectResponse(f"/k8s/hpas?cluster={cluster}&namespace={namespace}", status_code=303)


@router.post("/hpas/delete")
def hpa_delete(request: Request, db: Session = Depends(get_db)):
    from kubernetes import client
    form = request.form()
    cluster = form["cluster"]
    namespace = form.get("namespace", "default")
    name = form["name"]
    ds = _get_k8s_ds(db, cluster)
    if not ds:
        return PlainTextResponse("Cluster not found", status_code=404)
    try:
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        autoscaling_v1.delete_namespaced_horizontal_pod_autoscaler(name, namespace)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    return RedirectResponse(f"/k8s/hpas?cluster={cluster}&namespace={namespace}", status_code=303)


@router.post("/hpas/update")
def hpa_update(request: Request, db: Session = Depends(get_db)):
    from kubernetes import client
    form = request.form()
    cluster = form["cluster"]
    namespace = form.get("namespace", "default")
    name = form["name"]
    min_replicas = int(form.get("min_replicas", 1))
    max_replicas = int(form.get("max_replicas", 3))
    cpu_target = int(form.get("cpu_target", 80))

    ds = _get_k8s_ds(db, cluster)
    if not ds:
        return PlainTextResponse("Cluster not found", status_code=404)
    try:
        _, _, _ = _get_k8s_client(ds)
        autoscaling_v1 = client.AutoscalingV1Api()
        hpa = autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        hpa.spec.min_replicas = min_replicas
        hpa.spec.max_replicas = max_replicas
        hpa.spec.target_cpu_utilization_percentage = cpu_target
        autoscaling_v1.replace_namespaced_horizontal_pod_autoscaler(name, namespace, hpa)
    except Exception as e:
        return PlainTextResponse(f"Error: {e}", status_code=500)
    return RedirectResponse(f"/k8s/hpas?cluster={cluster}&namespace={namespace}", status_code=303)


@router.get("/ingresses", response_class=HTMLResponse)
def ingress_list(
    request: Request,
    cluster: str = "",
    namespace: str = "",
    db: Session = Depends(get_db),
):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    ingresses = []
    error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            _, _, net_v1 = _get_k8s_client(ds)
            if namespace:
                items = net_v1.list_namespaced_ingress(namespace).items
            else:
                items = net_v1.list_ingress_for_all_namespaces().items
            for ing in items:
                rules = []
                for rule in (ing.spec.rules or []):
                    host = rule.host or "*"
                    for path in (rule.http.paths or []):
                        rules.append(f"{host}{path.path} -> {path.backend.service.name if path.backend.service else '?'}:{path.backend.service.port.number if path.backend.service and path.backend.service.port else '?'}")
                ingresses.append({
                    "name": ing.metadata.name,
                    "namespace": ing.metadata.namespace,
                    "rules": rules,
                    "tls": [t.hosts for t in (ing.spec.tls or [])],
                })
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_ingresses.html", _add_cluster_info({
        "request": request,
        "clusters": clusters,
        "cluster": cluster,
        "namespace": namespace,
        "ingresses": ingresses,
        "error": error,
    }, db))


@router.get("/statefulsets", response_class=HTMLResponse)
def statefulset_list(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    items = []; error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            _, apps_v1, _ = _get_k8s_client(ds)
            raw = apps_v1.list_namespaced_stateful_set(namespace) if namespace else apps_v1.list_stateful_set_for_all_namespaces().items
            for s in raw:
                items.append({"name": s.metadata.name, "namespace": s.metadata.namespace, "replicas": s.spec.replicas, "ready": s.status.ready_replicas or 0, "service": s.spec.service_name or "-", "image": s.spec.template.spec.containers[0].image if s.spec.template.spec.containers else "-"})
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_list.html", _add_cluster_info({"request": request, "clusters": clusters, "cluster": cluster, "namespace": namespace, "items": items, "error": error, "title": "StatefulSet", "columns": ["名称","命名空间","副本","就绪","Service","镜像"], "keys": ["name","namespace","replicas","ready","service","image"]}, db))


@router.get("/daemonsets", response_class=HTMLResponse)
def daemonset_list(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    items = []; error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            _, apps_v1, _ = _get_k8s_client(ds)
            raw = apps_v1.list_namespaced_daemon_set(namespace) if namespace else apps_v1.list_daemon_set_for_all_namespaces().items
            for d in raw:
                items.append({"name": d.metadata.name, "namespace": d.metadata.namespace, "desired": d.status.desired_number_scheduled or 0, "ready": d.status.number_ready or 0, "node_selector": str(d.spec.selector.match_labels) if d.spec.selector else "-"})
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_list.html", _add_cluster_info({"request": request, "clusters": clusters, "cluster": cluster, "namespace": namespace, "items": items, "error": error, "title": "DaemonSet", "columns": ["名称","命名空间","期望","就绪","节点选择"], "keys": ["name","namespace","desired","ready","node_selector"]}, db))


@router.get("/pvcs", response_class=HTMLResponse)
def pvc_list(request: Request, cluster: str = "", namespace: str = "", db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    items = []; error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            v1, _, _ = _get_k8s_client(ds)
            raw = v1.list_namespaced_persistent_volume_claim(namespace) if namespace else v1.list_persistent_volume_claim_for_all_namespaces().items
            for p in raw:
                status = "Bound" if p.status.phase == "Bound" else "Pending"
                items.append({"name": p.metadata.name, "namespace": p.metadata.namespace, "status": status, "storage": (p.spec.resources.requests.get("storage","?") if p.spec.resources and p.spec.resources.requests else "?"), "access_modes": ",".join(p.spec.access_modes or []), "volume": p.spec.volume_name or "-"})
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_list.html", _add_cluster_info({"request": request, "clusters": clusters, "cluster": cluster, "namespace": namespace, "items": items, "error": error, "title": "PVC", "columns": ["名称","命名空间","状态","容量","访问模式","Volume"], "keys": ["name","namespace","status","storage","access_modes","volume"]}, db))


@router.get("/pvs", response_class=HTMLResponse)
def pv_list(request: Request, cluster: str = "", db: Session = Depends(get_db)):
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    items = []; error = None
    ds = _get_k8s_ds(db, cluster) if cluster else None
    if ds:
        try:
            v1, _, _ = _get_k8s_client(ds)
            raw = v1.list_persistent_volume().items
            for p in raw:
                items.append({"name": p.metadata.name, "capacity": (p.spec.capacity.get("storage","?") if p.spec.capacity else "?"), "access_modes": ",".join(p.spec.access_modes or []), "reclaim": str(p.spec.persistent_volume_reclaim_policy or "?"), "status": p.status.phase or "?", "claim": (p.spec.claim_ref.name if p.spec.claim_ref else "-")})
        except Exception as e:
            error = str(e)
    return templates.TemplateResponse("k8s_list.html", _add_cluster_info({"request": request, "clusters": clusters, "cluster": cluster, "namespace": "", "items": items, "error": error, "title": "PV", "columns": ["名称","容量","访问模式","回收策略","状态","绑定PVC"], "keys": ["name","capacity","access_modes","reclaim","status","claim"]}, db))
