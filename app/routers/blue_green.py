import copy
import json

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import BlueGreenDeploy, DataSource, Asset
from app.template_utils import get_templates

router = APIRouter(prefix="/blue-green", tags=["blue-green"])
templates = get_templates()


def _k8s_safe_name(name: str) -> str:
    """将名称转换为 K8s RFC 1123 兼容格式（下划线→连字符，小写）"""
    return name.replace("_", "-").lower()


def _deploy_to_dict(d) -> dict:
    return {
        "id": d.id,
        "name": d.name or "",
        "namespace": d.namespace or "default",
        "cluster": getattr(d, "cluster", "") or "",
        "active_label": d.active_label or "blue",
        "standby_label": d.standby_label or "green",
        "active_replicas": d.active_replicas or 3,
        "standby_replicas": d.standby_replicas or 3,
        "status": d.status or "active",
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M:%S") if d.created_at else None,
    }


def _get_k8s_client(cluster_name: str, db: Session):
    """从 DataSource 获取 K8s 配置，创建独立的 ApiClient（不依赖本地 kubeconfig）"""
    ds = db.query(DataSource).filter(DataSource.name == cluster_name).first()
    if not ds:
        return None, None, "未找到集群 DataSource: " + cluster_name
    cfg = json.loads(ds.auth_config) if ds.auth_config else {}
    api_server = cfg.get("k8s_api_server") or ds.endpoint or ""
    token = cfg.get("k8s_token") or ""
    if not api_server or not token:
        return None, None, "DataSource 缺少 api_server 或 token"
    from kubernetes import client as k8s_client
    configuration = k8s_client.Configuration()
    configuration.host = api_server
    configuration.api_key = {"authorization": "Bearer " + token}
    configuration.verify_ssl = False
    configuration.timeout = 15
    api_client = k8s_client.ApiClient(configuration)
    return api_client, k8s_client, ""


@router.get("/api/list")
def api_deploy_list(page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    """蓝绿发布列表 JSON API（分页）."""
    q = db.query(BlueGreenDeploy).order_by(BlueGreenDeploy.id.desc())
    total = q.count()
    deploys = q.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    clusters = db.query(DataSource).filter(DataSource.type == "kubernetes").all()
    return JSONResponse({
        "deploys": [_deploy_to_dict(d) for d in deploys],
        "clusters": [{"id": c.id, "name": c.name} for c in clusters],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
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
    image: str = Form("nginx:latest"),
    db: Session = Depends(get_db)):
    """创建蓝绿发布 JSON API.

    在 K8s 中创建两个 Deployment（blue/green），各自带 version 标签。
    同时创建一个 Service，selector 指向当前 active 版本。
    切换时只需 patch Service 的 selector，无需重建 Deployment。
    """
    d = BlueGreenDeploy(
        name=name, namespace=namespace, cluster=cluster,
        active_label=active_label, standby_label=standby_label,
        active_replicas=active_replicas, standby_replicas=standby_replicas)
    db.add(d)
    db.commit()
    db.refresh(d)

    # K8s 资源名称需符合 RFC 1123（下划线→连字符）
    k8s_name = _k8s_safe_name(name)
    k8s_container_name = k8s_name

    k8s_msg = ""
    if cluster:
        try:
            api_client, k8s_client, err = _get_k8s_client(cluster, db)
            if err:
                k8s_msg = "K8s config error: " + err
            else:
                apps_v1 = k8s_client.AppsV1Api(api_client)
                core_v1 = k8s_client.CoreV1Api(api_client)

                # 创建 blue Deployment
                blue_body = {
                    "apiVersion": "apps/v1", "kind": "Deployment",
                    "metadata": {"name": k8s_name + "-" + active_label, "namespace": namespace,
                                 "labels": {"app": k8s_name, "version": active_label}},
                    "spec": {
                        "replicas": active_replicas,
                        "selector": {"matchLabels": {"app": k8s_name, "version": active_label}},
                        "template": {
                            "metadata": {"labels": {"app": k8s_name, "version": active_label}},
                            "spec": {"containers": [{"name": k8s_container_name, "image": image, "ports": [{"containerPort": 80}]}]},
                        },
                    },
                }
                apps_v1.create_namespaced_deployment(namespace=namespace, body=blue_body)

                # 创建 green Deployment（深拷贝避免引用污染）
                green_body = copy.deepcopy(blue_body)
                green_body["metadata"]["name"] = k8s_name + "-" + standby_label
                green_body["metadata"]["labels"]["version"] = standby_label
                green_body["spec"]["selector"]["matchLabels"]["version"] = standby_label
                green_body["spec"]["template"]["metadata"]["labels"]["version"] = standby_label
                green_body["spec"]["replicas"] = standby_replicas
                apps_v1.create_namespaced_deployment(namespace=namespace, body=green_body)

                # 创建 Service，selector 指向 active 版本
                svc_body = {
                    "apiVersion": "v1", "kind": "Service",
                    "metadata": {"name": k8s_name, "namespace": namespace,
                                 "labels": {"app": k8s_name}},
                    "spec": {
                        "selector": {"app": k8s_name, "version": active_label},
                        "ports": [{"port": 80, "targetPort": 80}],
                        "type": "ClusterIP",
                    },
                }
                try:
                    core_v1.create_namespaced_service(namespace=namespace, body=svc_body)
                except Exception:
                    pass  # Service 可能已存在

                k8s_msg = "Deployments created: " + k8s_name + "-{blue,green}, Service: " + k8s_name
        except Exception as e:
            k8s_msg = "K8s deploy error: " + str(e)
    return JSONResponse({"ok": True, "id": d.id, "k8s_msg": k8s_msg})


@router.post("/api/{did}/switch")
def api_deploy_switch(did: int, db: Session = Depends(get_db)):
    """切换蓝绿 JSON API.

    核心逻辑：patch Service 的 selector 指向新的 active 版本。
    同时调整副本数（active scale up, standby scale down）。
    """
    d = db.query(BlueGreenDeploy).filter(BlueGreenDeploy.id == did).first()
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)

    old_active = d.active_label
    old_standby = d.standby_label
    # 交换 active/standby
    d.active_label, d.standby_label = d.standby_label, d.active_label
    d.active_replicas, d.standby_replicas = d.standby_replicas, d.active_replicas
    db.commit()

    k8s_msg = ""
    cluster = getattr(d, "cluster", "") or ""
    if cluster:
        try:
            api_client, k8s_client, err = _get_k8s_client(cluster, db)
            if err:
                k8s_msg = "K8s config error: " + err
            else:
                apps_v1 = k8s_client.AppsV1Api(api_client)
                core_v1 = k8s_client.CoreV1Api(api_client)
                k8s_name = _k8s_safe_name(d.name)

                # 1. scale up 新 active
                apps_v1.patch_namespaced_deployment_scale(
                    name=k8s_name + "-" + d.active_label, namespace=d.namespace,
                    body={"spec": {"replicas": d.active_replicas}})

                # 2. scale down 新 standby
                apps_v1.patch_namespaced_deployment_scale(
                    name=k8s_name + "-" + d.standby_label, namespace=d.namespace,
                    body={"spec": {"replicas": d.standby_replicas}})

                # 3. 切换 Service selector 指向新 active（蓝绿切换核心）
                core_v1.patch_namespaced_service(
                    name=k8s_name, namespace=d.namespace,
                    body={"spec": {"selector": {"app": k8s_name, "version": d.active_label}}})

                k8s_msg = "Switched: " + old_active + " -> " + d.active_label
        except Exception as e:
            k8s_msg = "K8s switch error: " + str(e)

    return JSONResponse({
        "ok": True,
        "active_label": d.active_label,
        "standby_label": d.standby_label,
        "active_replicas": d.active_replicas,
        "standby_replicas": d.standby_replicas,
        "k8s_msg": k8s_msg,
    })


@router.post("/api/{did}/delete")
def api_deploy_delete(did: int, db: Session = Depends(get_db)):
    """删除蓝绿发布，同时清理 K8s 资源"""
    d = db.query(BlueGreenDeploy).filter(BlueGreenDeploy.id == did).first()
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)

    k8s_msg = ""
    cluster = getattr(d, "cluster", "") or ""
    if cluster:
        try:
            api_client, k8s_client, err = _get_k8s_client(cluster, db)
            if err:
                k8s_msg = "K8s config error: " + err
            else:
                apps_v1 = k8s_client.AppsV1Api(api_client)
                core_v1 = k8s_client.CoreV1Api(api_client)
                k8s_name = _k8s_safe_name(d.name)
                # 删除 Deployments
                for label in [d.active_label, d.standby_label]:
                    try:
                        apps_v1.delete_namespaced_deployment(
                            name=k8s_name + "-" + label, namespace=d.namespace)
                    except Exception:
                        pass
                # 删除 Service
                try:
                    core_v1.delete_namespaced_service(name=k8s_name, namespace=d.namespace)
                except Exception:
                    pass
                k8s_msg = "K8s resources cleaned"
        except Exception as e:
            k8s_msg = "K8s cleanup error: " + str(e)

    db.delete(d)
    db.commit()
    return JSONResponse({"ok": True, "k8s_msg": k8s_msg})
