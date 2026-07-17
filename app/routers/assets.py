import json
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.template_utils import get_templates
from app.services import asset_service
from app.services.connection_service import ConnectionTester
from app.models import Asset, DataSource, AssetLifecycle, ChatSession, ChatMessage, AssetSessionLink
from app.services.agent_service import get_or_create_session, add_message

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

# K8s 子资源不在 CMDB 台账中展示，由 K8sResourceListView 管理
ASSET_EXCLUDE_CI_TYPES = {"deployment", "statefulset", "daemonset", "pod", "job",
                          "service", "ingress", "pvc", "configmap", "secret",
                          "replicaset"}


@router.get("/api/list")
def asset_api_list(
    search: str = "",
    ci_type: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    assets, total = asset_service.list_assets_paged(db, search, "", ci_type, page, page_size)
    # 查询所有资产的最新生命周期状态
    all_lcs = db.query(AssetLifecycle).order_by(AssetLifecycle.asset_id, AssetLifecycle.created_at.desc()).all()
    lc_map = {}
    for lc in all_lcs:
        if lc.asset_id not in lc_map:
            lc_map[lc.asset_id] = lc.status
    result = []
    for a in assets:
        # 排除 K8s 子资源（不在 CMDB 台账展示）
        if a.ci_type in ASSET_EXCLUDE_CI_TYPES:
            continue
        # 解析 ci_attributes 取引用关系/孤岛标记（三层纳管模型）
        ref_count = None
        is_orphan = False
        try:
            attrs = json.loads(a.ci_attributes) if a.ci_attributes else {}
            if a.ci_type in ("configmap", "secret", "pvc"):
                refs = attrs.get("referenced_by", []) or []
                ref_count = len(refs)
                is_orphan = bool(attrs.get("orphan"))
        except Exception:
            pass
        lifecycle_status = lc_map.get(a.id, "provisioning")
        result.append({
            "id": a.id, "name": a.name, "type": a.ci_type, "ci_type": getattr(a, 'ci_type', None),
            "ip": a.ip, "status": a.status,
            "lifecycle_status": lifecycle_status,
            "connection_type": getattr(a, 'connection_type', None),
            "last_checked_at": a.last_checked_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, 'last_checked_at', None) else None,
            "latency_ms": getattr(a, 'latency_ms', None),
            "k8s_cluster": getattr(a, 'k8s_cluster', None) or "",
            "tags": getattr(a, 'tags', None) or "",
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if getattr(a, 'created_at', None) else None,
            "ref_count": ref_count,
            "is_orphan": is_orphan,
        })
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    return JSONResponse({"items": result, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages})


@router.get("/api/ci-types")
def asset_api_ci_types():
    return JSONResponse(CI_TYPES)


@router.get("/api/services")
def asset_api_services(
    search: str = "",
    ci_types: str = "service,business_app,api_service",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """轻量级服务列表 API，专供 ServicePicker 组件使用。"""
    types = [t.strip() for t in ci_types.split(",") if t.strip()]
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if types:
        q = q.filter(Asset.ci_type.in_(types))
    total = q.count()
    items = q.order_by(Asset.name).offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    return JSONResponse({
        "items": [{"id": a.id, "name": a.name, "ci_type": a.ci_type, "ip": a.ip or ""} for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    })


@router.get("/api/{asset_id}")
def asset_api_get(asset_id: int, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"error": "Asset not found"}, status_code=404)
    return JSONResponse({
        "id": asset.id,
        "name": asset.name,
        "type": asset.ci_type,
        "ci_type": getattr(asset, 'ci_type', None),
        "ip": asset.ip,
        "status": asset.status,
        "tags": getattr(asset, 'tags', '') or '',
        "k8s_cluster": getattr(asset, 'k8s_cluster', '') or '',
        "connection_type": getattr(asset, 'connection_type', '') or '',
    })


@router.post("/api/{asset_id}/delete")
def api_asset_delete(asset_id: int, db: Session = Depends(get_db)):
    asset_service.delete_asset(db, asset_id)
    return JSONResponse({"ok": True})


def _build_connection_config(payload: dict) -> dict:
    """根据 payload 字段构造 connection_config dict.

    字段名以 CONTRACT.md 为准（Single Source of Truth）。
    """
    ct = payload.get("connection_type", "ssh")
    # 合并已有 config（编辑场景：connection_config 已存则作为 base）
    base = {}
    if payload.get("connection_config"):
        try:
            base = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
        except Exception:
            base = {}

    if ct == "ssh":
        return {
            "ssh_user": payload.get("ssh_user", base.get("ssh_user", "root")),
            "ssh_password": payload.get("ssh_password", base.get("ssh_password", "")),
            "ssh_port": int(payload.get("ssh_port", base.get("ssh_port", 22))),
        }
    elif ct == "winrm":
        return {
            "winrm_user": payload.get("winrm_user", base.get("winrm_user", "Administrator")),
            "winrm_password": payload.get("winrm_password", base.get("winrm_password", "")),
            "winrm_port": int(payload.get("winrm_port", base.get("winrm_port", 5985))),
            "winrm_transport": payload.get("winrm_transport", base.get("winrm_transport", "ntlm")),
            "winrm_ssl": payload.get("winrm_ssl", base.get("winrm_ssl", False)),
        }
    elif ct == "kubernetes":
        cfg = dict(base)
        if payload.get("k8s_api_server"):
            cfg["k8s_api_server"] = payload["k8s_api_server"]
        if payload.get("k8s_token"):
            cfg["k8s_token"] = payload["k8s_token"]
        if payload.get("k8s_namespace"):
            cfg["k8s_namespace"] = payload["k8s_namespace"]
        return cfg
    elif ct == "snmp":
        return {
            "snmp_community": payload.get("snmp_community", base.get("snmp_community", "public")),
            "snmp_port": int(payload.get("snmp_port", base.get("snmp_port", 161))),
            "snmp_version": payload.get("snmp_version", base.get("snmp_version", "v2c")),
        }
    elif ct == "http":
        cfg = dict(base)
        if payload.get("http_url"):
            cfg["http_url"] = payload["http_url"]
        if payload.get("http_auth"):
            cfg["http_auth"] = payload["http_auth"]
        if payload.get("http_credential"):
            cfg["http_credential"] = payload["http_credential"]
        return cfg
    elif ct == "database":
        return {
            "db_type": payload.get("db_type", base.get("db_type", "mysql")),
            "db_port": int(payload.get("db_port", base.get("db_port", 3306))),
            "db_user": payload.get("db_user", base.get("db_user", "root")),
            "db_password": payload.get("db_password", base.get("db_password", "")),
            "db_name": payload.get("db_name", base.get("db_name", "")),
        }
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
            connection_result = result
        except Exception:
            probe_status = status
            connection_result = None
    else:
        connection_result = None

    # 数据库资产强制权限检测，非 safe 附加风险警告
    risk_warning = None
    if connection_result and connection_result.get("permission_check"):
        pc = connection_result["permission_check"]
        if pc.get("risk_level") == "high":
            risk_warning = f"🔴 高危权限警告：该数据库账号拥有极高危权限（DCL/DDL/授权），接入 AI 存在重大风险。建议更换为只读账号后再接入。详细：{pc.get('risk_desc', '')}"
        elif pc.get("risk_level") == "medium":
            risk_warning = f"⚠️ 权限警告：该数据库账号拥有 DML 权限，AI 可能修改业务数据。确认要接入吗？详细：{pc.get('risk_desc', '')}"
        elif pc.get("risk_level") == "unknown":
            risk_warning = f"❓ 权限未知：无法判定该账号权限等级，人工确认后再接入 AI。详细：{pc.get('risk_desc', '')}"

    data = {
        "name": name,
        "ci_type": ci_type,
        "ip": ip,
        "status": probe_status,
        "tags": payload.get("tags") or "",
        "k8s_cluster": payload.get("k8s_cluster") or "",
        "connection_type": connection_type,
        "connection_config": json.dumps(config, ensure_ascii=False),
        "ci_attributes": json.dumps(payload.get("ci_attributes") or {}, ensure_ascii=False),
    }
    if payload.get("parent_id"):
        data["parent_id"] = int(payload["parent_id"])
    asset = asset_service.create_asset(db, data)
    # K8s 集群自动同步 DataSource
    if ci_type == "kubernetes_cluster" and config.get("k8s_api_server") and config.get("k8s_token"):
        _sync_k8s_datasource(db, asset, config)
    resp = {"ok": True, "id": asset.id, "status": probe_status}
    if risk_warning:
        resp["risk_warning"] = risk_warning
    return JSONResponse(resp)


@router.post("/api/{asset_id}/update")
def api_asset_update(asset_id: int, payload: dict, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_id)
    if not asset:
        return JSONResponse({"ok": False, "message": "资产不存在"}, status_code=404)
    data = {}
    for k in ("name", "ci_type", "ip", "status", "tags", "k8s_cluster", "connection_type"):
        if k in payload:
            data[k] = payload[k]
    if "connection_config" in payload:
        cfg = payload["connection_config"]
        data["connection_config"] = json.dumps(cfg, ensure_ascii=False) if isinstance(cfg, dict) else cfg
    elif any(k in payload for k in ("ssh_user", "ssh_password", "ssh_port", "k8s_api_server", "k8s_token", "http_url", "http_auth", "http_credential", "db_type", "db_port", "db_user", "db_password", "db_name", "snmp_community", "snmp_port", "snmp_version", "winrm_user", "winrm_password", "winrm_port", "winrm_transport", "winrm_ssl")):
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
    if "ci_attributes" in payload:
        data["ci_attributes"] = json.dumps(payload["ci_attributes"], ensure_ascii=False) if isinstance(payload["ci_attributes"], dict) else payload["ci_attributes"]
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
        "id": asset.id, "name": asset.name, "ci_type": asset.ci_type,
        "ip": asset.ip, "status": asset.status, "tags": asset.tags or "",
        "k8s_cluster": asset.k8s_cluster or "", "parent_id": asset.parent_id,
        "connection_type": asset.connection_type or "ssh",
        "ci_attributes": attrs,
        "ssh_user": config.get("ssh_user", "root"),
        "ssh_password": "***" if config.get("ssh_password") else "",
        "has_ssh_password": bool(config.get("ssh_password")),
        "ssh_port": config.get("ssh_port", 22),
        "k8s_api_server": config.get("k8s_api_server", ""),
        "k8s_token": "***" if config.get("k8s_token") else "",
        "has_k8s_token": bool(config.get("k8s_token")),
        "k8s_namespace": config.get("k8s_namespace", ""),
        "http_url": config.get("http_url", ""),
        "http_auth": config.get("http_auth", ""),
        "http_credential": "***" if config.get("http_credential") else "",
        "has_http_credential": bool(config.get("http_credential")),
        "db_type": config.get("db_type", "mysql"),
        "db_port": config.get("db_port", 3306),
        "db_user": config.get("db_user", "root"),
        "db_password": "***" if config.get("db_password") else "",
        "has_db_password": bool(config.get("db_password")),
        "db_name": config.get("db_name", ""),
        "snmp_community": config.get("snmp_community", "public"),
        "snmp_port": config.get("snmp_port", 161),
        "snmp_version": config.get("snmp_version", "v2c"),
        "winrm_user": config.get("winrm_user", "Administrator"),
        "winrm_password": "***" if config.get("winrm_password") else "",
        "has_winrm_password": bool(config.get("winrm_password")),
        "winrm_port": config.get("winrm_port", 5985),
        "winrm_transport": config.get("winrm_transport", "ntlm"),
        "winrm_ssl": config.get("winrm_ssl", False),
        "mw_subtype": attrs.get("mw_subtype", config.get("mw_subtype", "nginx")),
        "mw_port": attrs.get("mw_port", config.get("mw_port", 80)),
        "mw_admin_url": attrs.get("mw_admin_url", config.get("mw_admin_url", "")),
        "http_url": config.get("http_url", config.get("app_url", "")),
        "http_auth": config.get("http_auth", config.get("app_auth", "")),
        "http_credential": "***" if (config.get("http_credential") or config.get("app_credential")) else "",
        "has_http_credential": bool(config.get("http_credential") or config.get("app_credential")),
        "cert_domain": attrs.get("cert_domain", config.get("cert_domain", "")),
        "cert_issuer": attrs.get("cert_issuer", config.get("cert_issuer", "")),
        "cert_expiry": attrs.get("cert_expiry", config.get("cert_expiry", "")),
        "dns_domain": attrs.get("dns_domain", config.get("dns_domain", "")),
        "dns_type": attrs.get("dns_type", config.get("dns_type", "A")),
        "dns_value": attrs.get("dns_value", config.get("dns_value", "")),
        "monitor_url": attrs.get("monitor_url", config.get("monitor_url", "")),
        "monitor_type": attrs.get("monitor_type", config.get("monitor_type", "http")),
        "monitor_interval": attrs.get("monitor_interval", config.get("monitor_interval", 60)),
        "storage_type": attrs.get("storage_type", config.get("storage_type", "nfs")),
        "storage_mount": attrs.get("storage_mount", config.get("storage_mount", "")),
        "storage_capacity": attrs.get("storage_capacity", config.get("storage_capacity", 0)),
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
        "k8s_api_server": api_server,
        "k8s_token": token,
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
    """手动触发 K8s 集群同步：三层纳管模型（Dynamic CI + OwnerReference + 弱引用扫描）。

    纳管分层（参考 ServiceNow Dynamic CI / OpenTelemetry 资源稳定性分层标准）：
      第一层 持久化 CI（入库，变更频率天~周）:
        cluster / node / namespace / deployment / statefulset / daemonset / service / ingress / pv / pvc
      第二层 弱纳管 CI（入库但只存引用关系，不存内容）:
        configmap / secret —— 记录 referenced_by 与 orphan 标记；secret 数据内容不入库（合规）
      第三层 实时视图（不入库，在工作负载 attrs 聚合 Pod 概要）:
        pod / replicaset —— 通过 OwnerReference 链判定为派生资源，不入 Asset 表

    关键机制:
      - OwnerReference 链追溯: Pod → ReplicaSet → Deployment，派生资源不纳管
      - 弱引用扫描: 遍历 Pod.spec.volumes 收集 ConfigMap/Secret/PVC 引用关系
      - 孤岛检测: 无任何引用的 ConfigMap/Secret/PVC 标记 orphan=true（配置漂移信号）
      - 工作负载聚合: Pod 概要（total/running/pending/failed/restarts）聚合到 Deployment attrs.pod_summary
    """
    from kubernetes import client as k8s_client
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
        api_server = cfg.get("k8s_api_server") or ds.endpoint or ""
        token = cfg.get("k8s_token") or ""
        if not api_server or not token:
            return JSONResponse({"ok": False, "message": "DataSource 缺少 k8s_api_server 或 k8s_token"}, status_code=400)

        configuration = k8s_client.Configuration()
        configuration.host = api_server
        configuration.api_key = {"authorization": f"Bearer {token}"}
        configuration.verify_ssl = False
        configuration.timeout = 10
        api_client = k8s_client.ApiClient(configuration)
        v1 = k8s_client.CoreV1Api(api_client)
        apps_v1 = k8s_client.AppsV1Api(api_client)
        net_v1 = k8s_client.NetworkingV1Api(api_client)

        # ── 拉取资源 ──
        pods = v1.list_pod_for_all_namespaces().items
        deployments = apps_v1.list_deployment_for_all_namespaces().items
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces().items
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces().items
        replicasets = apps_v1.list_replica_set_for_all_namespaces().items
        services = v1.list_service_for_all_namespaces().items
        namespaces = v1.list_namespace().items
        ingresses = net_v1.list_ingress_for_all_namespaces().items
        pvcs = v1.list_persistent_volume_claim_for_all_namespaces().items
        pvs = v1.list_persistent_volume().items
        configmaps = v1.list_config_map_for_all_namespaces().items
        secrets = v1.list_secret_for_all_namespaces().items
        nodes = v1.list_node().items

        now = datetime.now()
        synced = {"namespaces": 0, "nodes": 0, "deployments": 0, "statefulsets": 0,
                  "daemonsets": 0, "services": 0, "ingresses": 0, "pvcs": 0, "pvs": 0,
                  "configmaps": 0, "secrets": 0, "pods_scanned": 0, "pods_skipped": 0,
                  "orphans": 0, "stale_cleaned": 0}

        def _upsert(name, ci_type_val, ns="", extra_attrs=None, parent=None):
            existing = db.query(Asset).filter(Asset.name == name, Asset.ci_type == ci_type_val).first()
            attrs = {"k8s_cluster": asset.name, "namespace": ns}
            if extra_attrs:
                attrs.update(extra_attrs)
            attrs_json = json.dumps(attrs, ensure_ascii=False)
            if existing:
                existing.ci_attributes = attrs_json
                existing.last_checked_at = now
                existing.status = "online"
                existing.k8s_cluster = asset.name
                if parent:
                    existing.parent_id = parent
            else:
                a = Asset(
                    name=name, type=ci_type_val, ci_type=ci_type_val,
                    ip="", status="online", tags=json.dumps(["k8s", asset.name]),
                    k8s_cluster=asset.name, parent_id=parent,
                    connection_type="kubernetes",
                    ci_attributes=attrs_json,
                    created_at=now, last_checked_at=now,
                )
                db.add(a)
            key = ci_type_val + "s" if ci_type_val[-1] != 'y' else ci_type_val[:-1] + "ies"
            if key in synced:
                synced[key] += 1

        # ── ReplicaSet → Deployment 映射（用于 Pod ownerRef 链追溯）──
        rs_to_deploy = {}
        for rs in replicasets:
            for r in (rs.metadata.owner_references or []):
                if r.kind == "Deployment":
                    rs_to_deploy[f"{rs.metadata.namespace}/{rs.metadata.name}"] = r.name
                    break

        cluster_id = asset.id

        # ── Namespace（cluster 子节点）──
        ns_asset_map = {}
        for ns in namespaces:
            ns_name = ns.metadata.name
            full = f"{asset.name}/{ns_name}"
            _upsert(full, "namespace", ns_name, parent=cluster_id)
            ns_obj = db.query(Asset).filter(Asset.name == full, Asset.ci_type == "namespace").first()
            if ns_obj:
                ns_asset_map[ns_name] = ns_obj.id

        # ── Node（cluster 子节点）──
        for node in nodes:
            ni = node.status.node_info
            node_attrs = {
                "kubelet_version": ni.kubelet_version if ni else "",
                "os_image": ni.os_image if ni else "",
                "cpu": (node.status.capacity.get("cpu", "") if node.status.capacity else ""),
                "memory": (node.status.capacity.get("memory", "") if node.status.capacity else ""),
                "node_status": "Ready" if any(
                    c.type == "Ready" and c.status == "True" for c in (node.status.conditions or [])
                ) else "NotReady",
            }
            _upsert(f"{asset.name}/node/{node.metadata.name}", "node", "", node_attrs, parent=cluster_id)

        # ── 工作负载聚合 Pod 概要（Pod 不入库，扫描聚合到工作负载 attrs.pod_summary）──
        def _pod_summary_for_workload(wl_name, wl_ns, wl_kind):
            summary = {"total": 0, "running": 0, "pending": 0, "failed": 0, "restarts": 0}
            for pod in pods:
                if pod.metadata.namespace != wl_ns:
                    continue
                owner_match = False
                for r in (pod.metadata.owner_references or []):
                    if r.kind == "ReplicaSet" and wl_kind == "deployment":
                        deploy_name = rs_to_deploy.get(f"{pod.metadata.namespace}/{r.name}")
                        if deploy_name == wl_name:
                            owner_match = True
                            break
                    elif r.kind.lower() == wl_kind and r.name == wl_name:
                        owner_match = True
                        break
                if not owner_match:
                    continue
                summary["total"] += 1
                phase = pod.status.phase or "Unknown"
                if phase == "Running":
                    summary["running"] += 1
                elif phase == "Pending":
                    summary["pending"] += 1
                elif phase in ("Failed", "Unknown"):
                    summary["failed"] += 1
                summary["restarts"] += sum(s.restart_count for s in (pod.status.container_statuses or []))
            return summary

        def _upsert_workload(item, kind):
            ns = item.metadata.namespace
            name = item.metadata.name
            parent_id = ns_asset_map.get(ns)
            summary = _pod_summary_for_workload(name, ns, kind)
            # 不同工作负载的副本数/就绪数字段不同
            if kind == "deployment":
                replicas = item.spec.replicas or 0
                available = getattr(item.status, "available_replicas", None) or 0
            elif kind == "statefulset":
                replicas = item.spec.replicas or 0
                available = getattr(item.status, "ready_replicas", None) or 0
            else:  # daemonset 无 replicas，用 desired/ready
                replicas = getattr(item.status, "desired_number_scheduled", None) or 0
                available = getattr(item.status, "number_ready", None) or 0
            extra = {
                "replicas": replicas,
                "available": available,
                "pod_summary": summary,
            }
            _upsert(f"{asset.name}/{ns}/{name}", kind, ns, extra, parent=parent_id)

        for deploy in deployments:
            _upsert_workload(deploy, "deployment")
        for sts in statefulsets:
            _upsert_workload(sts, "statefulset")
        for ds in daemonsets:
            _upsert_workload(ds, "daemonset")

        # ── Service / Ingress（namespace 子节点）──
        for svc in services:
            ns = svc.metadata.namespace
            extra = {
                "cluster_ip": svc.spec.cluster_ip or "",
                "type": svc.spec.type or "ClusterIP",
                "selector": dict(svc.spec.selector or {}),
            }
            _upsert(f"{asset.name}/{ns}/{svc.metadata.name}", "service", ns, extra, parent=ns_asset_map.get(ns))

        for ing in ingresses:
            ns = ing.metadata.namespace
            _upsert(f"{asset.name}/{ns}/{ing.metadata.name}", "ingress", ns, parent=ns_asset_map.get(ns))

        # ── 弱引用扫描：遍历 Pod.spec.volumes 收集 ConfigMap/Secret/PVC 引用 ──
        pvc_refs, cm_refs, secret_refs = {}, {}, {}
        for pod in pods:
            ns = pod.metadata.namespace
            pod_deploy = None
            for r in (pod.metadata.owner_references or []):
                if r.kind == "ReplicaSet":
                    pod_deploy = rs_to_deploy.get(f"{ns}/{r.name}")
                    break
                elif r.kind in ("Deployment", "StatefulSet", "DaemonSet"):
                    pod_deploy = r.name
                    break
            for vol in (pod.spec.volumes or []):
                if vol.config_map and vol.config_map.name:
                    cm_refs.setdefault(f"{ns}/{vol.config_map.name}", set()).add(pod_deploy or "?")
                if vol.secret and vol.secret.secret_name:
                    secret_refs.setdefault(f"{ns}/{vol.secret.secret_name}", set()).add(pod_deploy or "?")
                if vol.persistent_volume_claim and vol.persistent_volume_claim.claim_name:
                    pvc_refs.setdefault(f"{ns}/{vol.persistent_volume_claim.claim_name}", set()).add(pod_deploy or "?")
        synced["pods_scanned"] = len(pods)

        # ── PVC（弱纳管：存引用关系 + 孤岛标记）──
        for pvc in pvcs:
            ns = pvc.metadata.namespace
            key = f"{ns}/{pvc.metadata.name}"
            refs = sorted(pvc_refs.get(key, []))
            is_orphan = not refs
            if is_orphan:
                synced["orphans"] += 1
            extra = {
                "storage_class": pvc.spec.storage_class_name or "",
                "requested_size": (pvc.spec.resources.requests.get("storage", "")
                                   if pvc.spec.resources and pvc.spec.resources.requests else ""),
                "referenced_by": refs,
                "orphan": is_orphan,
            }
            _upsert(f"{asset.name}/{ns}/{pvc.metadata.name}", "pvc", ns, extra, parent=ns_asset_map.get(ns))

        # ── PV（集群级独立 CI）──
        for pv in pvs:
            extra = {
                "capacity": (pv.spec.capacity.get("storage", "") if pv.spec.capacity else ""),
                "storage_class": pv.spec.storage_class_name or "",
                "access_modes": list(pv.spec.access_modes or []),
            }
            _upsert(f"{asset.name}/pv/{pv.metadata.name}", "pv", "", extra, parent=cluster_id)

        # ── ConfigMap（弱纳管：只存键名 + 引用关系，不存 data 内容）──
        for cm in configmaps:
            ns = cm.metadata.namespace
            key = f"{ns}/{cm.metadata.name}"
            refs = sorted(cm_refs.get(key, []))
            is_orphan = not refs
            if is_orphan:
                synced["orphans"] += 1
            extra = {
                "referenced_by": refs,
                "orphan": is_orphan,
                "data_keys": list(cm.data.keys()) if cm.data else [],
            }
            _upsert(f"{asset.name}/{ns}/{cm.metadata.name}", "configmap", ns, extra, parent=ns_asset_map.get(ns))

        # ── Secret（弱纳管：只存键名 + 引用关系，不存 data 内容——合规要求）──
        for sec in secrets:
            ns = sec.metadata.namespace
            key = f"{ns}/{sec.metadata.name}"
            refs = sorted(secret_refs.get(key, []))
            is_orphan = not refs
            if is_orphan:
                synced["orphans"] += 1
            extra = {
                "type": sec.type or "Opaque",
                "referenced_by": refs,
                "orphan": is_orphan,
                "data_keys": list(sec.data.keys()) if sec.data else [],
            }
            _upsert(f"{asset.name}/{ns}/{sec.metadata.name}", "secret", ns, extra, parent=ns_asset_map.get(ns))

        # ── 旧派生资源（pod/replicaset）降级：标记 deprecated，不删除（保留历史审计）──
        stale = db.query(Asset).filter(
            Asset.ci_type.in_(["pod", "replicaset"]),
            Asset.k8s_cluster == asset.name
        ).all()
        for s in stale:
            s.status = "deprecated"
            s.last_checked_at = now
            synced["stale_cleaned"] += 1
        synced["pods_skipped"] = len(pods)

        db.commit()
        ds.last_status = "healthy"
        ds.last_scraped_at = now
        db.commit()

        return JSONResponse({"ok": True, "synced": synced, "model": "tiered-dynamic-ci"})
    except ApiException as e:
        ds.last_status = "error"
        ds.last_error = str(e)
        db.commit()
        return JSONResponse({"ok": False, "message": f"K8s API 错误: {e}"}, status_code=502)
    except ImportError:
        return JSONResponse({"ok": False, "message": "未安装 kubernetes 库"}, status_code=500)
    except Exception as e:
        return JSONResponse({"ok": False, "message": f"同步异常: {e}"}, status_code=500)


# ─── 从资产跳转 AI 助手（创建/复用会话并注入资产上下文） ───

@router.post("/api/{asset_id}/open-assistant")
def open_assistant_from_asset(asset_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id", 1)
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)

    existing = db.query(AssetSessionLink).filter(AssetSessionLink.asset_id == asset_id).first()
    if existing:
        return JSONResponse({"session_id": existing.session_id, "new": False})

    session = get_or_create_session(db, user_id, None)

    context = {
        "asset_id": asset.id,
        "asset_name": asset.name,
        "asset_ip": asset.ip,
        "asset_ci_type": asset.ci_type,
        "asset_status": asset.status,
    }

    session.context = json.dumps(context, ensure_ascii=False)
    session.title = f"资产 {asset.name} ({asset.ip or 'N/A'})"

    db.add(AssetSessionLink(
        asset_id=asset_id,
        session_id=session.id,
        context_summary="来自资产管理的关联会话"
    ))

    summary_content = (
        f"**系统上下文注入**\n"
        f"已关联资产 **{asset.name}** ({asset.ip or 'N/A'})\n"
        f"- CI 类型：{asset.ci_type}，状态：{asset.status}\n"
        f"你可以直接问我关于这个资产的诊断、监控、运维方案，我会调用工具查询详细信息。"
    )
    add_message(db, session.id, "system", summary_content, message_type="text")

    return JSONResponse({"session_id": session.id, "new": True})


@router.get("/api/health-score")
def api_asset_health_score(asset_id: int = 0, db: Session = Depends(get_db)):
    """查询资产健康评分（可指定 asset_id 或查全部）."""
    from app.services.asset_change_service import get_asset_health_score, get_all_asset_health
    if asset_id > 0:
        return get_asset_health_score(db, asset_id)
    return get_all_asset_health(db)


@router.post("/api/health-scan")
def api_health_scan(db: Session = Depends(get_db)):
    """触发所有资产健康扫描，记录变更日志."""
    from app.services.asset_change_service import scan_asset_health_changes
    changed = scan_asset_health_changes(db)
    return {"ok": True, "changed": changed}
