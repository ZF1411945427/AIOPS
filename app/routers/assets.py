import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.template_utils import get_templates
from app.services import asset_service
from app.services.connection_service import ConnectionTester
from app.models import Asset, DataSource

router = APIRouter(prefix="/assets", tags=["assets"])
templates = get_templates()

CI_TYPES = [
    "server", "virtual_machine", "network_device", "switch", "router", "firewall", "load_balancer",
    "storage_device", "database", "middleware",
    "cloud_host", "kubernetes_cluster",
    "deployment", "statefulset", "daemonset", "pod", "job",
    "service", "ingress", "pvc", "configmap", "secret",
    "business_app", "api_service", "ssl_certificate", "dns_record", "monitoring_endpoint",
]


@router.get("/api/list")
def asset_api_list(search: str = "", ci_type: str = "", db: Session = Depends(get_db)):
    assets = asset_service.list_assets(db, search, "", ci_type)
    return JSONResponse([{
        "id": a.id, "name": a.name, "type": a.type, "ci_type": getattr(a, 'ci_type', None),
        "ip": a.ip, "status": a.status,
        "connection_type": getattr(a, 'connection_type', None),
        "last_checked": a.last_checked.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, 'last_checked', None) else None,
        "latency_ms": getattr(a, 'latency_ms', None),
        "k8s_cluster": getattr(a, 'k8s_cluster', None) or "",
        "tags": getattr(a, 'tags', None) or "",
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if getattr(a, 'created_at', None) else None,
    } for a in assets])


@router.get("/api/ci-types")
def asset_api_ci_types():
    return JSONResponse(CI_TYPES)


@router.post("/api/{asset_id}/delete")
def api_asset_delete(asset_id: int, db: Session = Depends(get_db)):
    asset_service.delete_asset(db, asset_id)
    return JSONResponse({"ok": True})


def _build_connection_config(payload: dict) -> dict:
    """根据 payload 字段构造 connection_config dict."""
    ct = payload.get("connection_type", "ssh")
    if ct == "ssh":
        return {
            "ssh_user": payload.get("ssh_user", "root"),
            "ssh_password": payload.get("ssh_password", ""),
            "ssh_port": int(payload.get("ssh_port", 22)),
        }
    elif ct == "kubernetes":
        cfg = {}
        if payload.get("connection_config"):
            try:
                cfg = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
            except Exception:
                cfg = {}
        if payload.get("k8s_api_server"):
            cfg["k8s_api_server"] = payload["k8s_api_server"]
        if payload.get("k8s_token"):
            cfg["k8s_token"] = payload["k8s_token"]
        return cfg
    elif ct == "snmp":
        cfg = {}
        if payload.get("connection_config"):
            try:
                cfg = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
            except Exception:
                cfg = {}
        cfg["snmp_community"] = payload.get("snmp_community", cfg.get("snmp_community", "public"))
        cfg["snmp_port"] = int(payload.get("snmp_port", cfg.get("snmp_port", 161)))
        cfg["snmp_version"] = payload.get("snmp_version", cfg.get("snmp_version", "v2c"))
        return cfg
    elif ct == "http":
        cfg = {}
        if payload.get("connection_config"):
            try:
                cfg = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
            except Exception:
                cfg = {}
        if payload.get("http_url"):
            cfg["http_url"] = payload["http_url"]
        if payload.get("http_auth"):
            cfg["http_auth"] = payload["http_auth"]
        if payload.get("http_credential"):
            cfg["http_credential"] = payload["http_credential"]
        return cfg
    elif ct == "database":
        cfg = {}
        if payload.get("connection_config"):
            try:
                cfg = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
            except Exception:
                cfg = {}
        cfg["db_type"] = payload.get("db_type", cfg.get("db_type", "mysql"))
        cfg["db_port"] = int(payload.get("db_port", cfg.get("db_port", 3306)))
        cfg["db_user"] = payload.get("db_user", cfg.get("db_user", "root"))
        cfg["db_password"] = payload.get("db_password", cfg.get("db_password", ""))
        if payload.get("db_name"):
            cfg["db_name"] = payload["db_name"]
        return cfg
    return {}


@router.post("/api/create")
def api_asset_create(payload: dict, db: Session = Depends(get_db)):
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "message": "资产名称不能为空"}, status_code=400)
    ci_type = payload.get("ci_type") or "server"
    connection_type = payload.get("connection_type") or "ssh"
    config = _build_connection_config(payload)
    ip = payload.get("ip") or ""
    status = payload.get("status") or "offline"
    probe_status = status
    if ci_type == "kubernetes_cluster":
        probe_status = "online"
    elif ip and connection_type:
        try:
            result = ConnectionTester.test(connection_type, ip, config)
            probe_status = "online" if result.get("ok") else "offline"
        except Exception:
            probe_status = status
    data = {
        "name": name,
        "type": ci_type,
        "ci_type": ci_type,
        "ip": ip,
        "status": probe_status,
        "tags": payload.get("tags") or "",
        "k8s_cluster": payload.get("k8s_cluster") or "",
        "connection_type": connection_type,
        "connection_config": json.dumps(config, ensure_ascii=False),
    }
    if payload.get("parent_id"):
        data["parent_id"] = int(payload["parent_id"])
    asset = asset_service.create_asset(db, data)
    # K8s 集群自动同步 DataSource
    if ci_type == "kubernetes_cluster" and config.get("k8s_api_server") and config.get("k8s_token"):
        _sync_k8s_datasource(db, asset, config)
    return JSONResponse({"ok": True, "id": asset.id, "status": probe_status})


@router.post("/api/{asset_id}/update")
def api_asset_update(asset_id: int, payload: dict, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    data = {}
    for k in ("name", "ci_type", "ip", "status", "tags", "k8s_cluster", "connection_type"):
        if k in payload:
            data[k] = payload[k]
    if "ci_type" in data and "type" not in data:
        data["type"] = data["ci_type"]
    if "connection_config" in payload:
        cfg = payload["connection_config"]
        data["connection_config"] = json.dumps(cfg, ensure_ascii=False) if isinstance(cfg, dict) else cfg
    elif any(k in payload for k in ("ssh_user", "ssh_password", "ssh_port", "k8s_api_server", "k8s_token", "http_url", "db_type")):
        config = _build_connection_config(payload)
        data["connection_config"] = json.dumps(config, ensure_ascii=False)
    if data.get("connection_config") and data.get("connection_type"):
        try:
            cfg = json.loads(data["connection_config"])
            host = data.get("ip") or asset.ip or cfg.get("k8s_api_server", cfg.get("http_url", ""))
            ctype = data.get("connection_type", asset.connection_type)
            if host and ctype:
                result = ConnectionTester.test(ctype, host, cfg)
                data["status"] = "online" if result.get("ok") else "offline"
        except Exception:
            pass
    if "parent_id" in payload:
        data["parent_id"] = int(payload["parent_id"]) if payload["parent_id"] else None
    updated = asset_service.update_asset(db, asset_id, data)
    # K8s 集群更新后同步 DataSource
    if data.get("ci_type") == "kubernetes_cluster" or asset.ci_type == "kubernetes_cluster":
        cfg = _build_connection_config(payload) if any(k in payload for k in ("k8s_api_server", "k8s_token")) else {}
        if not cfg:
            try:
                cfg = json.loads(data.get("connection_config", "{}")) if isinstance(data.get("connection_config"), str) else data.get("connection_config", {})
            except:
                cfg = {}
        if cfg.get("k8s_api_server") and cfg.get("k8s_token"):
            _sync_k8s_datasource(db, asset, cfg)
    return JSONResponse({"ok": bool(updated), "status": data.get("status", asset.status)})


@router.get("/api/{asset_id}/detail")
def api_asset_detail(asset_id: int, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    config = {}
    try:
        config = json.loads(asset.connection_config) if asset.connection_config else {}
    except Exception:
        config = {}
    attrs = {}
    try:
        attrs = json.loads(asset.ci_attributes) if asset.ci_attributes else {}
    except Exception:
        attrs = {}
    return JSONResponse({
        "id": asset.id, "name": asset.name, "type": asset.type, "ci_type": asset.ci_type,
        "ip": asset.ip, "status": asset.status, "tags": asset.tags or "",
        "k8s_cluster": asset.k8s_cluster or "", "parent_id": asset.parent_id,
        "connection_type": asset.connection_type or "ssh",
        "ci_attributes": attrs,
        "ssh_user": config.get("ssh_user", "root"),
        "ssh_password": config.get("ssh_password", ""),
        "ssh_port": config.get("ssh_port", 22),
        "k8s_api_server": config.get("k8s_api_server", ""),
        "k8s_token": config.get("k8s_token", ""),
        "k8s_namespace": config.get("k8s_namespace", ""),
        "http_url": config.get("http_url", ""),
        "http_auth": config.get("http_auth", ""),
        "http_credential": config.get("http_credential", ""),
        "db_subtype": config.get("db_subtype", config.get("db_type", "mysql")),
        "db_port": config.get("db_port", 3306),
        "db_user": config.get("db_user", "root"),
        "db_password": config.get("db_password", ""),
        "db_name": config.get("db_name", ""),
        "snmp_community": config.get("snmp_community", "public"),
        "snmp_port": config.get("snmp_port", 161),
        "snmp_version": config.get("snmp_version", "v2c"),
        "mw_subtype": config.get("mw_subtype", config.get("middleware_type", "nginx")),
        "mw_port": config.get("mw_port", 80),
        "mw_admin_url": config.get("mw_admin_url", ""),
        "app_url": config.get("app_url", ""),
        "app_auth": config.get("app_auth", ""),
        "app_credential": config.get("app_credential", ""),
        "cert_domain": config.get("cert_domain", ""),
        "cert_issuer": config.get("cert_issuer", ""),
        "cert_expiry": config.get("cert_expiry", ""),
        "dns_domain": config.get("dns_domain", ""),
        "dns_type": config.get("dns_type", "A"),
        "dns_value": config.get("dns_value", ""),
        "monitor_url": config.get("monitor_url", ""),
        "monitor_type": config.get("monitor_type", "http"),
        "monitor_interval": config.get("monitor_interval", 60),
        "storage_type": config.get("storage_type", "nfs"),
        "storage_mount": config.get("storage_mount", ""),
        "storage_capacity": config.get("storage_capacity", 0),
    })


@router.post("/api/test-connection")
def test_connection(
    connection_type: str = Form("ssh"),
    host: str = Form(""),
    connection_config: str = Form("{}")):
    try:
        config = json.loads(connection_config) if connection_config else {}
    except:
        config = {}
    result = ConnectionTester.test(connection_type, host, config)
    return JSONResponse(result)


def _sync_k8s_datasource(db: Session, asset, config: dict):
    """在 DataSource 表中同步创建/更新 K8s 集群的连接信息。"""
    api_server = config.get("k8s_api_server", "")
    token = config.get("k8s_token", "")
    if not api_server or not token:
        return
    ds_name = asset.name
    existing = db.query(DataSource).filter(
        DataSource.type == "kubernetes", DataSource.name == ds_name
    ).first()
    auth_config = json.dumps({
        "api_server": api_server,
        "token": token,
        "verify_ssl": False,
    }, ensure_ascii=False)
    if existing:
        existing.endpoint = api_server
        existing.auth_config = auth_config
        existing.last_status = "unknown"
    else:
        ds = DataSource(
            name=ds_name, type="kubernetes", endpoint=api_server,
            auth_type="bearer", auth_config=auth_config,
            scrape_interval=60, enabled=True,
        )
        db.add(ds)
    db.commit()


@router.post("/api/{asset_id}/sync-k8s")
def api_asset_sync_k8s(asset_id: int, db: Session = Depends(get_db)):
    """手动触发 K8s 集群同步：从 DataSource 实时拉取资源并写入 Asset 表。"""
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.rest import ApiException

    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    if asset.ci_type != "kubernetes_cluster":
        return JSONResponse({"ok": False, "message": "仅支持 K8s 集群类型资产同步"}, status_code=400)

    ds = db.query(DataSource).filter(
        DataSource.type == "kubernetes", DataSource.name == asset.name
    ).first()
    if not ds:
        return JSONResponse({"ok": False, "message": "未找到对应的 DataSource，请先测试连接"}, status_code=400)

    try:
        cfg = json.loads(ds.auth_config) if ds.auth_config else {}
        api_server = cfg.get("api_server", ds.endpoint or "")
        token = cfg.get("token", "")
        if not api_server or not token:
            return JSONResponse({"ok": False, "message": "DataSource 缺少 API Server 或 Token"}, status_code=400)

        configuration = k8s_client.Configuration()
        configuration.host = api_server
        configuration.api_key = {"authorization": f"Bearer {token}"}
        configuration.verify_ssl = False
        configuration.timeout = 10
        api_client = k8s_client.ApiClient(configuration)
        v1 = k8s_client.CoreV1Api(api_client)
        apps_v1 = k8s_client.AppsV1Api(api_client)
        net_v1 = k8s_client.NetworkingV1Api(api_client)

        # 拉取各种资源
        pods = v1.list_pod_for_all_namespaces().items
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces().items
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces().items
        services = v1.list_service_for_all_namespaces().items
        namespaces = v1.list_namespace().items
        ingresses = net_v1.list_ingress_for_all_namespaces().items
        pvcs = v1.list_persistent_volume_claim_for_all_namespaces().items
        configmaps = v1.list_config_map_for_all_namespaces().items
        secrets = v1.list_secret_for_all_namespaces().items

        now = datetime.now()
        synced = {"pods": 0, "deployments": 0, "statefulsets": 0, "daemonsets": 0,
                   "services": 0, "namespaces": 0, "ingresses": 0, "pvcs": 0,
                   "configmaps": 0, "secrets": 0}

        def _upsert_k8s_asset(name, ci_type_val, ns="", extra_attrs=None):
            existing = db.query(Asset).filter(Asset.name == name, Asset.ci_type == ci_type_val).first()
            attrs = {"k8s_cluster": asset.name, "namespace": ns}
            if extra_attrs:
                attrs.update(extra_attrs)
            if existing:
                existing.ci_attributes = json.dumps(attrs)
                existing.last_checked = now
                existing.status = "online"
                existing.k8s_cluster = asset.name
            else:
                a = Asset(
                    name=name, type=ci_type_val, ci_type=ci_type_val,
                    ip="", status="online", tags=json.dumps(["k8s", asset.name]),
                    k8s_cluster=asset.name, parent_id=asset.id,
                    connection_type="kubernetes",
                    ci_attributes=json.dumps(attrs),
                    created_at=now, last_checked=now,
                )
                db.add(a)
            synced[ci_type_val + "s" if ci_type_val[-1] != 'y' else ci_type_val[:-1] + "ies"] += 1

        for ns in namespaces:
            _upsert_k8s_asset(f"{asset.name}/{ns.metadata.name}", "namespace", ns.metadata.name)
        for deploy in deployments:
            avail = deploy.status.available_replicas or 0
            total = deploy.spec.replicas or 0
            _upsert_k8s_asset(f"{asset.name}/{deploy.metadata.namespace}/{deploy.metadata.name}", "deployment", deploy.metadata.namespace, {"replicas": total, "available": avail})
        for sts in statefulsets:
            _upsert_k8s_asset(f"{asset.name}/{sts.metadata.namespace}/{sts.metadata.name}", "statefulset", sts.metadata.namespace)
        for ds in daemonsets:
            _upsert_k8s_asset(f"{asset.name}/{ds.metadata.namespace}/{ds.metadata.name}", "daemonset", ds.metadata.namespace)
        for pod in pods:
            phase = pod.status.phase or "Unknown"
            restarts = sum(s.restart_count for s in (pod.status.container_statuses or []))
            _upsert_k8s_asset(f"{asset.name}/{pod.metadata.namespace}/{pod.metadata.name}", "pod", pod.metadata.namespace, {"phase": phase, "restarts": restarts})
        for svc in services:
            _upsert_k8s_asset(f"{asset.name}/{svc.metadata.namespace}/{svc.metadata.name}", "service", svc.metadata.namespace)
        for ing in ingresses:
            _upsert_k8s_asset(f"{asset.name}/{ing.metadata.namespace}/{ing.metadata.name}", "ingress", ing.metadata.namespace)
        for pvc in pvcs:
            _upsert_k8s_asset(f"{asset.name}/{pvc.metadata.namespace}/{pvc.metadata.name}", "pvc", pvc.metadata.namespace)
        for cm in configmaps:
            _upsert_k8s_asset(f"{asset.name}/{cm.metadata.namespace}/{cm.metadata.name}", "configmap", cm.metadata.namespace)
        for sec in secrets:
            _upsert_k8s_asset(f"{asset.name}/{sec.metadata.namespace}/{sec.metadata.name}", "secret", sec.metadata.namespace)

        db.commit()
        ds.last_status = "healthy"
        ds.last_scrape = now
        db.commit()

        return JSONResponse({"ok": True, "synced": synced})
    except ApiException as e:
        ds.last_status = "error"
        ds.last_error = str(e)
        db.commit()
        return JSONResponse({"ok": False, "message": f"K8s API 错误: {e}"}, status_code=502)
    except ImportError:
        return JSONResponse({"ok": False, "message": "未安装 kubernetes 库"}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"同步异常: {e}"}, status_code=500)
