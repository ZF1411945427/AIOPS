from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BlueGreenDeploy, DataSource, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/blue-green", tags=["blue-green"])
templates = get_templates()


def _deploy_to_dict(d) -> dict:
    return {
        "id": d.id,
        "name": d.name or "",
        "namespace": d.namespace or "default",
        "active_label": d.active_label or "blue",
        "standby_label": d.standby_label or "green",
        "active_replicas": d.active_replicas or 3,
        "standby_replicas": d.standby_replicas or 3,
        "status": d.status or "active",
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
    }


@router.get("/api/list")
def api_deploy_list(db: Session = Depends(get_db)):
    """蓝绿发布列表 JSON API."""
    deploys = db.query(BlueGreenDeploy).all()
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return JSONResponse({
        "deploys": [_deploy_to_dict(d) for d in deploys],
        "clusters": [{"id": c.id, "name": c.name} for c in clusters],
        "total": len(deploys),
    })


@router.post("/api/create")
def api_deploy_create(
    name: str = Form(...),
    namespace: str = Form("default"),
    cluster: str = Form(""),
    active_label: str = Form("blue"),
    standby_label: str = Form("green"),
    active_replicas: int = Form(3),
    standby_replicas: int = Form(3),
    db: Session = Depends(get_db)):
    """创建蓝绿发布 JSON API."""
    d = BlueGreenDeploy(
        name=name, namespace=namespace, active_label=active_label,
        standby_label=standby_label, active_replicas=active_replicas,
        standby_replicas=standby_replicas)
    db.add(d)
    db.commit()
    db.refresh(d)
    k8s_msg = ""
    if cluster:
        try:
            from kubernetes import config, client
            ds = db.query(DataSource).filter(DataSource.name == cluster).first()
            if ds:
                cfg = ds.auth_config
                import json as _json
                cfg_d = _json.loads(cfg) if isinstance(cfg, str) else cfg or {}
                if cfg_d.get("in_cluster"):
                    config.load_incluster_config()
                else:
                    config.load_kube_config()
            apps_v1 = client.AppsV1Api()
            blue_body = {
                "apiVersion": "apps/v1", "kind": "Deployment",
                "metadata": {"name": f"{name}-{active_label}", "namespace": namespace,
                             "labels": {"app": name, "version": active_label}},
                "spec": {
                    "replicas": active_replicas,
                    "selector": {"matchLabels": {"app": name, "version": active_label}},
                    "template": {
                        "metadata": {"labels": {"app": name, "version": active_label}},
                        "spec": {"containers": [{"name": name, "image": "nginx:latest"}]},
                    },
                },
            }
            apps_v1.create_namespaced_deployment(namespace=namespace, body=blue_body)
            green_body = dict(blue_body)
            green_body["metadata"]["name"] = f"{name}-{standby_label}"
            green_body["metadata"]["labels"]["version"] = standby_label
            green_body["spec"]["selector"]["matchLabels"]["version"] = standby_label
            green_body["spec"]["template"]["metadata"]["labels"]["version"] = standby_label
            green_body["spec"]["replicas"] = standby_replicas
            apps_v1.create_namespaced_deployment(namespace=namespace, body=green_body)
        except Exception as e:
            k8s_msg = f"K8s deploy error: {e}"
    return JSONResponse({"ok": True, "id": d.id, "k8s_msg": k8s_msg})


@router.post("/api/{did}/switch")
def api_deploy_switch(did: int, db: Session = Depends(get_db)):
    """切换蓝绿 JSON API."""
    d = db.query(BlueGreenDeploy).filter(BlueGreenDeploy.id == did).first()
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    d.active_label, d.standby_label = d.standby_label, d.active_label
    d.active_replicas, d.standby_replicas = d.standby_replicas, d.active_replicas
    db.commit()
    k8s_msg = ""
    try:
        from kubernetes import config, client
        config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        apps_v1.patch_namespaced_deployment_scale(
            name=f"{d.name}-{d.active_label}", namespace=d.namespace,
            body={"spec": {"replicas": d.active_replicas}})
        apps_v1.patch_namespaced_deployment_scale(
            name=f"{d.name}-{d.standby_label}", namespace=d.namespace,
            body={"spec": {"replicas": d.standby_replicas}})
    except Exception as e:
        k8s_msg = str(e)
    return JSONResponse({"ok": True, "active_label": d.active_label, "k8s_msg": k8s_msg})
