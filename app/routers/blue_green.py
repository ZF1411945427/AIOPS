from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BlueGreenDeploy, DataSource, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/blue-green", tags=["blue-green"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def blue_green_page(request: Request, db: Session = Depends(get_db)):
    deploys = db.query(BlueGreenDeploy).all()
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return templates.TemplateResponse("blue_green.html", {
        "request": request, "deploys": deploys, "clusters": clusters,
    })


@router.post("/create")
def create_deploy(
    request: Request, name: str = Form(...), namespace: str = Form("default"),
    cluster: str = Form(""), active_label: str = Form("blue"),
    standby_label: str = Form("green"), active_replicas: int = Form(3),
    standby_replicas: int = Form(3), db: Session = Depends(get_db),
):
    d = BlueGreenDeploy(
        name=name, namespace=namespace, active_label=active_label,
        standby_label=standby_label, active_replicas=active_replicas,
        standby_replicas=standby_replicas,
    )
    db.add(d)
    db.commit()
    if cluster:
        try:
            from kubernetes import config, client
            ds = db.query(DataSource).filter(DataSource.name == cluster).first()
            if ds:
                cfg = ds.auth_config
                import json
                cfg_d = json.loads(cfg) if isinstance(cfg, str) else cfg or {}
                if cfg_d.get("in_cluster"):
                    config.load_incluster_config()
                else:
                    config.load_kube_config()
            apps_v1 = client.AppsV1Api()
            # Create blue deployment
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
            # Create green deployment
            green_body = dict(blue_body)
            green_body["metadata"]["name"] = f"{name}-{standby_label}"
            green_body["metadata"]["labels"]["version"] = standby_label
            green_body["spec"]["selector"]["matchLabels"]["version"] = standby_label
            green_body["spec"]["template"]["metadata"]["labels"]["version"] = standby_label
            green_body["spec"]["replicas"] = standby_replicas
            apps_v1.create_namespaced_deployment(namespace=namespace, body=green_body)
        except Exception as e:
            return PlainTextResponse(f"Created config but K8s deploy error: {e}", 200)
    return RedirectResponse("/blue-green", status_code=303)


@router.post("/switch/{did}")
def switch_deploy(did: int, db: Session = Depends(get_db)):
    d = db.query(BlueGreenDeploy).filter(BlueGreenDeploy.id == did).first()
    if not d:
        return PlainTextResponse("Not found", 404)
    d.active_label, d.standby_label = d.standby_label, d.active_label
    d.active_replicas, d.standby_replicas = d.standby_replicas, d.active_replicas
    db.commit()
    try:
        from kubernetes import config, client
        config.load_kube_config()
        apps_v1 = client.AppsV1Api()
        # Scale up new active, scale down new standby
        apps_v1.patch_namespaced_deployment_scale(
            name=f"{d.name}-{d.active_label}", namespace=d.namespace,
            body={"spec": {"replicas": d.active_replicas}},
        )
        apps_v1.patch_namespaced_deployment_scale(
            name=f"{d.name}-{d.standby_label}", namespace=d.namespace,
            body={"spec": {"replicas": d.standby_replicas}},
        )
    except Exception:
        pass
    return RedirectResponse("/blue-green", status_code=303)
