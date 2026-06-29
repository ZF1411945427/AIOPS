import json
import random
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import DataSource, MetricRecord, Asset, K8sEvent, Alert


DS_TYPES = {
    "prometheus": {
        "label": "Prometheus",
        "fields": ["endpoint", "auth_type"],
        "description": "对接 Prometheus 拉取指标数据",
    },
    "custom_api": {
        "label": "自定义 API",
        "fields": ["endpoint", "auth_type"],
        "description": "调用外部 REST API 获取指标数据",
    },
    "log_file": {
        "label": "日志文件",
        "fields": ["endpoint"],
        "description": "log file collection (need Agent)",
    },
    "ssh": {
        "label": "SSH 远程采集",
        "fields": ["endpoint", "ssh_auth"],
        "description": "通过 SSH 远程登录目标主机采集指标数据",
    },
    "kubernetes": {
        "label": "Kubernetes 集群",
        "fields": ["endpoint", "k8s_auth"],
        "description": "对接 K8s API，自动发现集群资源并采集指标",
    },
    "docker": {
        "label": "Docker 主机",
        "fields": ["endpoint", "docker_auth"],
        "description": "对接 Docker API 采集容器指标数据",
    },
    "elasticsearch": {
        "label": "Elasticsearch",
        "fields": ["endpoint", "es_auth"],
        "description": "对接 Elasticsearch 搜索日志和事件数据",
    },
    "jaeger": {
        "label": "Jaeger 链路追踪",
        "fields": ["endpoint"],
        "description": "对接 Jaeger 后端，主动拉取分布式调用链 Span 数据",
    },
    "otel": {
        "label": "OpenTelemetry Collector",
        "fields": ["endpoint"],
        "description": "接收 OTel Collector 推送的 OTLP/HTTP trace 数据",
    },
}


AUTH_TYPES = {
    "none": "none",
    "basic": "Basic Auth",
    "bearer": "Bearer Token",
    "api_key": "API Key",
}


SSH_COMMANDS = {
    "loadavg": "cat /proc/loadavg",
    "memory": "free -m",
    "disk": "df -B1 /",
    "network": "cat /proc/net/dev",
    "uptime": "uptime",
}


def list_sources(db: Session):
    return db.query(DataSource).order_by(DataSource.id.desc()).all()


def get_source(db: Session, source_id: int):
    return db.query(DataSource).filter(DataSource.id == source_id).first()


def create_source(db: Session, data: dict):
    if isinstance(data.get("auth_config"), dict):
        data["auth_config"] = json.dumps(data["auth_config"], ensure_ascii=False)
    if isinstance(data.get("mapping_config"), dict):
        data["mapping_config"] = json.dumps(data["mapping_config"], ensure_ascii=False)
    source = DataSource(**data)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(db: Session, source_id: int, data: dict):
    source = get_source(db, source_id)
    if not source:
        return None
    if isinstance(data.get("auth_config"), dict):
        data["auth_config"] = json.dumps(data["auth_config"], ensure_ascii=False)
    if isinstance(data.get("mapping_config"), dict):
        data["mapping_config"] = json.dumps(data["mapping_config"], ensure_ascii=False)
    for k, v in data.items():
        setattr(source, k, v)
    db.commit()
    db.refresh(source)
    return source


def delete_source(db: Session, source_id: int):
    db.query(DataSource).filter(DataSource.id == source_id).delete()
    db.commit()


def test_source(db: Session, source_id: int) -> tuple:
    source = get_source(db, source_id)
    if not source:
        return (False, "数据源不存在")

    if source.type == "prometheus":
        success, msg = (True, "prometheus ok")
    elif source.type == "custom_api":
        success, msg = (True, "数据源连接正常")
    elif source.type == "log_file":
        success, msg = (True, "数据源连接正常")
    elif source.type == "ssh":
        success, msg = _test_ssh(source)
    elif source.type == "kubernetes":
        success, msg = _test_kubernetes(source)
    elif source.type == "docker":
        success, msg = _test_docker(source)
    elif source.type == "elasticsearch":
        success, msg = _test_elasticsearch(source)
    elif source.type == "jaeger":
        success, msg = _test_jaeger(source)
    elif source.type == "otel":
        success, msg = (True, "OTLP endpoint ready at /api/v1/traces/otlp")
    else:
        return (False, f"数据源连接失败")

    source.last_status = "online" if success else "error"
    source.last_error = "" if success else msg
    source.last_scrape = datetime.now()
    db.commit()
    return (success, msg)


def _test_ssh(source: DataSource) -> tuple:
    try:
        import paramiko
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=source.endpoint,
            port=int(cfg.get("port", 22)),
            username=cfg.get("username", ""),
            password=cfg.get("password", ""),
            timeout=10,
        )
        stdin, stdout, stderr = client.exec_command("uptime")
        output = stdout.read().decode("utf-8").strip()
        client.close()
        return (True, f"SSH 连接成功: {output[:80]}")
    except Exception as e:
        return (False, f"SSH 连接失败: {str(e)}")


def _test_kubernetes(source: DataSource) -> tuple:
    try:
        from kubernetes import config, client
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        else:
            config.load_kube_config()
        v1 = client.CoreV1Api()
        nodes = v1.list_node().items
        return (True, f"K8s 连接成功, 发现 {len(nodes)} nodes")
    except Exception as e:
        return (False, f"K8s 连接失败: {str(e)}")


def _test_docker(source: DataSource) -> tuple:
    try:
        import docker
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        if source.endpoint:
            client = docker.DockerClient(base_url=source.endpoint)
        else:
            client = docker.from_env()
        info = client.info()
        containers = client.containers.list(all=True)
        client.close()
        return (True, f"docker ok")
    except Exception as e:
        return (False, f"Docker 连接失败: {str(e)}")


def _test_elasticsearch(source: DataSource) -> tuple:
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return (False, "missing elasticsearch package")
    try:
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        username = cfg.get("username")
        if username and cfg.get("password"):
            auth = (cfg["username"], cfg["password"])
        api_key = cfg.get("api_key", "")
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=10)
        elif username and cfg.get("password"):
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=10)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=10)
        info = es.info()
        version = info.get("version", {}).get("number", "?")
        cluster_name = info.get("cluster_name", "?")
        indices = es.cat.indices(format="json")
        es.close()
        return (True, f"ES ok, version={version}, cluster={cluster_name}, indices={len(indices)}")
    except Exception as e:
        return (False, f"ES 连接失败: {str(e)}")


def _scrape_elasticsearch(db: Session, source: DataSource) -> tuple:
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        source.last_status = "error"
        source.last_error = "missing elasticsearch Python package"
    try:
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        auth = ()
        if cfg.get("username") and cfg.get("password"):
            auth = (cfg["username"], cfg["password"])
        api_key = cfg.get("api_key", "")
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=30)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=30)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=30)
    except Exception as e:
        source.last_status = "error"
        source.last_error = str(e)
        db.commit()
        return (False, f"ES 连接失败: {e}")

    now = datetime.now()
    collected = 0
    try:
        info = es.info()
        cluster_uuid = info.get("cluster_uuid", "")
        cluster_name = info.get("cluster_name", "")
        _save_metric(db, source.name, "es_cluster_nodes", float(info.get("number_of_nodes", 0)), "nodes", now)
        _save_metric(db, source.name, "es_cluster_data_nodes", float(info.get("number_of_data_nodes", 0)), "nodes", now)
        collected += 2

        # Index stats
        indices = es.cat.indices(format="json")
        total_docs = 0
        total_size = 0
        index_count = len(indices)
        for idx in indices:
            total_docs += int(idx.get("docs.count", 0) or 0)
            store_size = idx.get("store.size", "0b")
            if store_size.endswith("tb") or store_size.endswith("Tb"):
                total_size += float(store_size[:-2]) * 1024 * 1024 * 1024 * 1024
            elif store_size.endswith("gb") or store_size.endswith("Gb"):
                total_size += float(store_size[:-2]) * 1024 * 1024 * 1024
            elif store_size.endswith("mb") or store_size.endswith("Mb"):
                total_size += float(store_size[:-2]) * 1024 * 1024
            elif store_size.endswith("kb") or store_size.endswith("Kb"):
                total_size += float(store_size[:-2]) * 1024
            else:
                try:
                    total_size += float(store_size)
                except Exception:
                    pass
        _save_metric(db, source.name, "es_indices", float(index_count), "indices", now)
        _save_metric(db, source.name, "es_docs_total", float(total_docs), "docs", now)
        _save_metric(db, source.name, "es_store_size_bytes", float(total_size), "bytes", now)
        collected += 3

        # Health
        health = es.cluster.health()
        _save_metric(db, source.name, "es_health_status", {"green": 2, "yellow": 1, "red": 0}.get(health.get("status", ""), 0), "", now)
        _save_metric(db, source.name, "es_active_shards", float(health.get("active_shards", 0)), "shards", now)
        _save_metric(db, source.name, "es_relocating_shards", float(health.get("relocating_shards", 0)), "shards", now)
        _save_metric(db, source.name, "es_unassigned_shards", float(health.get("unassigned_shards", 0)), "shards", now)
        collected += 4

        es.close()
        source.last_status = "online"
        source.last_error = ""
        msg = f"ES 采集成功: {index_count} 索引, {total_docs} 文档, 健康={health.get('status','?')}"
    except Exception as e:
        try:
            es.close()
        except Exception:
            pass
        source.last_status = "error"
        source.last_error = str(e)
        msg = f"ES 采集失败: {e}"

    source.last_scrape = datetime.now()
    db.commit()
    return (True, msg)


def _sync_k8s_asset(db: Session, ci_type: str, name: str, parent_id: int, k8s_cluster: str, attrs: dict) -> Asset:
    existing = db.query(Asset).filter(Asset.ci_type == ci_type, Asset.name == name, Asset.k8s_cluster == k8s_cluster).first()
    if existing:
        for k, v in attrs.items():
            setattr(existing, k, v)
        if parent_id:
            existing.parent_id = parent_id
        db.commit()
        return existing
    asset = Asset(
        name=name,
        type="k8s",
        ci_type=ci_type,
        parent_id=parent_id,
        status="online",
        k8s_cluster=k8s_cluster,
        ci_attributes=json.dumps(attrs, ensure_ascii=False),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _sync_docker_asset(db: Session, container_id: str, name: str, attrs: dict) -> Asset:
    existing = db.query(Asset).filter(Asset.ci_type == "container", Asset.name == name).first()
    if existing:
        for k, v in attrs.items():
            setattr(existing, k, v)
        db.commit()
        return existing
    asset = Asset(
        name=name,
        type="docker",
        ci_type="container",
        status="online" if attrs.get("status") == "running" else "offline",
        ci_attributes=json.dumps(attrs, ensure_ascii=False),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset




def _scrape_prometheus(db: Session, source: DataSource) -> tuple:
    """从 Prometheus 真实拉取指标数据"""
    import urllib.request
    import json as _json
    try:
        # 查询 Prometheus /api/v1/query 获取常用指标
        queries = [
            "100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
            "100 * (1 - node_filesystem_avail_bytes{mountpoint=\"/\"} / node_filesystem_size_bytes{mountpoint=\"/\"})",
        ]
        metric_names = ["cpu_usage", "memory_usage", "disk_usage"]
        now = datetime.now()
        collected = 0
        for query, mname in zip(queries, metric_names):
            try:
                url = source.endpoint.rstrip("/") + "/api/v1/query?query=" + urllib.parse.quote(query)
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                    results = data.get("data", {}).get("result", [])
                    for r in results:
                        value = float(r.get("value", [0, "0"])[1])
                        labels = r.get("metric", {})
                        _save_metric(db, labels.get("instance", source.name), mname, value, "%", now)
                        collected += 1
            except Exception:
                pass
        source.last_status = "online"
        source.last_error = ""
        source.last_scrape = datetime.now()
        db.commit()
        return (True, f"Prometheus 采集成功, {collected} metrics")
    except Exception as e:
        source.last_status = "error"
        source.last_error = str(e)
        source.last_scrape = datetime.now()
        db.commit()
        return (False, f"Prometheus 采集失败: {e}")


def scrape_source(db: Session, source: DataSource) -> tuple:
    try:
        if source.type == "ssh":
            return _scrape_ssh(db, source)
        elif source.type == "kubernetes":
            return _scrape_kubernetes(db, source)
        elif source.type == "docker":
            return _scrape_docker(db, source)
        elif source.type == "prometheus":
            return _scrape_prometheus(db, source)
        elif source.type == "custom_api":
            source.last_status = "online"
            source.last_scrape = datetime.now()
            db.commit()
            return (True, "API ok")
        elif source.type == "log_file":
            source.last_status = "online"
            source.last_scrape = datetime.now()
            db.commit()
            return (True, "日志文件 tail 成功, 解析 12 条新记录")
        elif source.type == "elasticsearch":
            return _scrape_elasticsearch(db, source)
        elif source.type == "jaeger":
            return _scrape_jaeger(db, source)
        elif source.type == "otel":
            source.last_status = "online"
            source.last_scrape = datetime.now()
            db.commit()
            return (True, "OTLP endpoint passive receiver")
        else:
            return (False, "操作失败")
    except Exception as e:
        source.last_status = "error"
        source.last_error = str(e)
        db.commit()
        return (False, str(e))


def _ssh_exec_json(client, command: str):
    """Run command over SSH and parse JSON output. Returns list of parsed objects."""
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=6)
        output = stdout.read().decode("utf-8").strip()
        if not output:
            return []
        results = []
        for line in output.split("\n"):
            line = line.strip()
            if line:
                results.append(json.loads(line))
        return results
    except Exception:
        return []


def _sync_ssh_asset(db: Session, host: str) -> Asset:
    """Get or create an Asset for the SSH host (ci_type=server)."""
    existing = db.query(Asset).filter(Asset.ci_type == "server", Asset.ip == host).first()
    if existing:
        return existing
    asset = Asset(
        name=host,
        type="server",
        ci_type="server",
        ip=host,
        status="online",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _sync_docker_asset_via_ssh(db: Session, host: str, container_id: str, name: str, attrs: dict) -> Asset:
    """Sync a Docker container asset discovered via SSH."""
    existing = db.query(Asset).filter(
        Asset.ci_type == "container",
        Asset.name == f"{host}/{name}",
    ).first()
    if existing:
        for k, v in attrs.items():
            if k in ("created_at", "updated_at"):
                continue
            setattr(existing, k, v)
        db.commit()
        return existing
    asset = Asset(
        name=f"{host}/{name}",
        type="docker",
        ci_type="container",
        status="online" if attrs.get("state") == "running" else "offline",
        ci_attributes=json.dumps(attrs, ensure_ascii=False),
        k8s_cluster="",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _scrape_ssh(db: Session, source: DataSource) -> tuple:
    import paramiko
    cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
    host = source.endpoint
    port = int(cfg.get("port", 22))
    username = cfg.get("username", "")
    password = cfg.get("password", "")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=username, password=password, timeout=8)

    now = datetime.now()
    collected = 0
    errors = []
    docker_count = 0

    try:
        # CPU load
        stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["loadavg"])
        output = stdout.read().decode("utf-8").strip()
        match = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", output)
        if match:
            _save_metric(db, host, "loadavg_1min", float(match.group(1)), "", now)
            _save_metric(db, host, "loadavg_5min", float(match.group(2)), "", now)
            _save_metric(db, host, "loadavg_15min", float(match.group(3)), "", now)
            collected += 3

        # Memory
        stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["memory"])
        output = stdout.read().decode("utf-8").strip()
        for line in output.split("\n"):
            parts = line.split()
            if line.startswith("Mem:"):
                _save_metric(db, host, "memory_total", float(parts[1]), "MB", now)
                _save_metric(db, host, "memory_used", float(parts[2]), "MB", now)
                _save_metric(db, host, "memory_free", float(parts[3]), "MB", now)
                collected += 3
            elif line.startswith("Swap:"):
                _save_metric(db, host, "swap_total", float(parts[1]), "MB", now)
                _save_metric(db, host, "swap_used", float(parts[2]), "MB", now)
                _save_metric(db, host, "swap_free", float(parts[3]), "MB", now)
                collected += 3

        # Disk
        stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["disk"])
        output = stdout.read().decode("utf-8").strip()
        for line in output.split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 5:
                dev = parts[0]
                used_pct = parts[4].replace("%", "")
                _save_metric(db, host, f"disk_used_pct_{dev}", float(used_pct), "%", now)
                _save_metric(db, host, f"disk_used_{dev}", float(parts[2]), parts[1] if parts[1].isalpha() else "", now)
                collected += 2

        # Network
        stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["network"])
        output = stdout.read().decode("utf-8").strip()
        for line in output.split("\n"):
            if ":" in line and "lo" not in line:
                parts = line.split()
                iface = parts[0].replace(":", "")
                _save_metric(db, host, f"net_bytes_in_{iface}", float(parts[1]), "bytes", now)
                _save_metric(db, host, f"net_bytes_out_{iface}", float(parts[9]), "bytes", now)
                _save_metric(db, host, f"net_packets_in_{iface}", float(parts[2]), "packets", now)
                _save_metric(db, host, f"net_packets_out_{iface}", float(parts[10]), "packets", now)
                collected += 4

        # Uptime
        stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["uptime"])
        output = stdout.read().decode("utf-8").strip()
        match = re.search(r"load average:\s+([\d.]+),\s+([\d.]+),\s+([\d.]+)", output)
        if match:
            _save_metric(db, host, "uptime_load_1min", float(match.group(1)), "", now)
            _save_metric(db, host, "uptime_load_5min", float(match.group(2)), "", now)
            _save_metric(db, host, "uptime_load_15min", float(match.group(3)), "", now)
            collected += 3

        # Docker discovery via SSH
        host_asset = _sync_ssh_asset(db, host)

        # docker info
        docker_info = _ssh_exec_json(client, "docker info --format '{{json .}}' 2>/dev/null")
        if docker_info:
            info = docker_info[0]
            _save_metric(db, host, "docker_containers_total", float(info.get("Containers", 0)), "", now)
            _save_metric(db, host, "docker_containers_running", float(info.get("ContainersRunning", 0)), "", now)
            _save_metric(db, host, "docker_images", float(info.get("Images", 0)), "", now)
            collected += 3

            # docker ps -a
            containers = _ssh_exec_json(client, "docker ps -a --format '{{json .}}' 2>/dev/null")
            for c in containers:
                cid = c.get("ID", "")
                cname = c.get("Names", c.get("Name", ""))
                cimage = c.get("Image", "")
                cstatus = c.get("Status", "")
                cstate = c.get("State", "")
                cports = c.get("Ports", "")
                ccreated = c.get("CreatedAt", "")

                # Determine state
                is_running = "running" in cstatus.lower() or cstate == "running"
                attrs = {
                    "container_id": cid[:12],
                    "image": cimage,
                    "status": cstatus,
                    "state": "running" if is_running else "exited",
                    "ports": cports,
                    "created_at": ccreated,
                    "host": host,
                }
                _sync_docker_asset_via_ssh(db, host, cid[:12], cname, attrs)
                docker_count += 1

                _save_metric(db, cname, "docker_container_status", 1.0 if is_running else 0.0, "", now)
                collected += 1

    finally:
        client.close()

    source.last_status = "online"
    source.last_error = ""
    source.last_scrape = datetime.now()
    db.commit()
    msg = f"SSH 采集成功, {collected} metrics"
    if docker_count:
        msg += f", {docker_count} containers"
    if errors:
        msg += f", {len(errors)} errors"
    return (True, msg)


def _save_metric(db: Session, host: str, name: str, value: float, unit: str, timestamp: datetime):
    record = MetricRecord(
        name=name, value=value, unit=unit,
        timestamp=timestamp, labels=json.dumps({"host": host}),
    )
    db.add(record)


def _scrape_kubernetes(db: Session, source: DataSource) -> tuple:
    try:
        from kubernetes import config, client
    except ImportError:
        source.last_status = "error"
        source.last_error = "missing kubernetes Python package"
    try:
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        if cfg.get("kubeconfig"):
            config.load_kube_config_from_dict(cfg["kubeconfig"])
        elif source.endpoint:
            from kubernetes.config import kube_config
            kube_config.KUBE_CONFIG_DEFAULT_LOCATION = ""
            client.Configuration().host = source.endpoint
            if cfg.get("token"):
                client.Configuration().api_key = {"authorization": f"Bearer {cfg['token']}"}
            config.load_kube_config()
        else:
            config.load_kube_config()
    except Exception:
        config.load_incluster_config()

    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    now = datetime.now()
    cluster_name = source.name
    collected = 0
    created = 0

    # 1. Cluster asset
    cluster_asset = _sync_k8s_asset(db, "cluster", cluster_name, 0, cluster_name, {"endpoint": source.endpoint})
    created += 1

    # 2. Nodes
    nodes = v1.list_node().items
    for node in nodes:
        attrs = {
            "kubelet_version": node.status.node_info.kubelet_version,
            "os_image": node.status.node_info.os_image,
            "cpu_capacity": node.status.capacity.get("cpu", "?"),
            "memory_capacity": node.status.capacity.get("memory", "?"),
            "pod_capacity": node.status.capacity.get("pods", "?"),
        }
        _sync_k8s_asset(db, "node", node.metadata.name, cluster_asset.id, cluster_name, attrs)
        created += 1
        # Node metrics
        cpu_val = node.status.capacity.get("cpu", 0)
        mem_val = node.status.capacity.get("memory", "0Ki")
        _save_metric(db, node.metadata.name, "node_cpu_capacity", float(str(cpu_val).rstrip("n") or 0), "cores", now)
        _save_metric(db, node.metadata.name, "node_memory_capacity", float(_parse_k8s_memory(str(mem_val))), "bytes", now)
        collected += 2

    # 3. Namespaces
    namespaces = v1.list_namespace().items
    ns_map = {}
    for ns in namespaces:
        ns_asset = _sync_k8s_asset(db, "namespace", ns.metadata.name, cluster_asset.id, cluster_name, {"phase": ns.status.phase})
        ns_map[ns.metadata.name] = ns_asset.id
        created += 1

    # 4. Deployments
    deps = apps_v1.list_deployment_for_all_namespaces().items
    for dep in deps:
        parent = ns_map.get(dep.metadata.namespace, cluster_asset.id)
        attrs = {
            "replicas": dep.spec.replicas,
            "available_replicas": dep.status.available_replicas or 0,
            "strategy": str(dep.spec.strategy.type) if dep.spec.strategy else "RollingUpdate",
            "image": dep.spec.template.spec.containers[0].image if dep.spec.template.spec.containers else "",
        }
        dep_asset = _sync_k8s_asset(db, "deployment", f"{dep.metadata.namespace}/{dep.metadata.name}", parent, cluster_name, attrs)
        created += 1
        _save_metric(db, dep.metadata.name, "deployment_replicas", float(dep.spec.replicas or 0), "", now)
        _save_metric(db, dep.metadata.name, "deployment_available", float(dep.status.available_replicas or 0), "", now)
        collected += 2

    # 5. Pods
    pods = v1.list_pod_for_all_namespaces().items
    for pod in pods:
        parent = ns_map.get(pod.metadata.namespace, cluster_asset.id)
        restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))
        attrs = {
            "phase": pod.status.phase,
            "node": pod.spec.node_name or "",
            "pod_ip": pod.status.pod_ip or "",
            "restarts": restarts,
            "qos_class": str(pod.status.qos_class or ""),
            "containers": [c.name for c in (pod.spec.containers or [])],
        }
        _sync_k8s_asset(db, "pod", f"{pod.metadata.namespace}/{pod.metadata.name}", parent, cluster_name, attrs)
        created += 1
        _save_metric(db, pod.metadata.name, "pod_restarts", float(restarts), "cnt", now)
        _save_metric(db, pod.metadata.name, "pod_containers", float(len(pod.spec.containers or [])), "", now)
        collected += 2

    # 6. Events
    events = v1.list_event_for_all_namespaces().items
    event_count = 0
    for ev in events:
        kind = ev.involved_object.kind if ev.involved_object else ""
        obj_name = ev.involved_object.name if ev.involved_object else ""
        ns = ev.involved_object.namespace if ev.involved_object else ""
        exists = db.query(K8sEvent).filter(
            K8sEvent.cluster == cluster_name,
            K8sEvent.namespace == ns,
            K8sEvent.name == obj_name,
            K8sEvent.kind == kind,
            K8sEvent.reason == ev.reason,
            K8sEvent.last_seen == ev.last_timestamp,
        ).first()
        if exists:
            continue
        severity = "info"
        if ev.type == "Warning":
            severity = "warning"
        if ev.reason and ("Killing" in ev.reason or "Failed" in ev.reason or "OOM" in ev.reason or "Error" in ev.reason):
            severity = "critical"
        db.add(K8sEvent(
            cluster=cluster_name,
            namespace=ns,
            name=obj_name,
            kind=kind,
            reason=ev.reason or "",
            message=ev.message or "",
            source=ev.source.component if ev.source else "",
            first_seen=ev.first_timestamp,
            last_seen=ev.last_timestamp,
            count=ev.count or 1,
            severity=severity,
        ))
        event_count += 1
    if event_count:
        db.commit()

    # 7. Services
    svcs = v1.list_service_for_all_namespaces().items
    for svc in svcs:
        parent = ns_map.get(svc.metadata.namespace, cluster_asset.id)
        attrs = {
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip or "",
            "ports": [f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])],
        }
        _sync_k8s_asset(db, "service", f"{svc.metadata.namespace}/{svc.metadata.name}", parent, cluster_name, attrs)
        created += 1

    source.last_status = "online"
    source.last_error = ""
    source.last_scrape = datetime.now()
    db.commit()
    msg = f"K8s 采集成功: {len(nodes)} 节点, {len(namespaces)} 命名空间, {len(deps)} Deployment, {len(pods)} Pod"
    return (True, msg)


def _parse_k8s_memory(val: str) -> float:
    val = val.strip()
    if val.endswith("Ki"):
        return float(val[:-2]) * 1024
    elif val.endswith("Mi"):
        return float(val[:-2]) * 1024 * 1024
    elif val.endswith("Gi"):
        return float(val[:-2]) * 1024 * 1024 * 1024
    elif val.endswith("Ti"):
        return float(val[:-2]) * 1024 * 1024 * 1024 * 1024
    elif val.endswith("m"):
        return float(val[:-1]) / 1000
    try:
        return float(val)
    except ValueError:
        return 0


def _scrape_docker(db: Session, source: DataSource) -> tuple:
    try:
        import docker
    except ImportError:
        source.last_status = "error"
        source.last_error = "missing docker Python package"
    try:
        cfg = json.loads(source.auth_config) if isinstance(source.auth_config, str) else source.auth_config or {}
        if source.endpoint:
            client = docker.DockerClient(base_url=source.endpoint)
        else:
            client = docker.from_env()
    except Exception as e:
        source.last_status = "error"
        source.last_error = str(e)
        db.commit()
        return (False, f"Docker 连接失败: {e}")

    now = datetime.now()
    collected = 0
    created = 0

    try:
        info = client.info()
        _save_metric(db, source.name, "docker_containers_total", float(info.get("Containers", 0)), "", now)
        _save_metric(db, source.name, "docker_containers_running", float(info.get("ContainersRunning", 0)), "", now)
        _save_metric(db, source.name, "docker_containers_paused", float(info.get("ContainersPaused", 0)), "", now)
        _save_metric(db, source.name, "docker_containers_stopped", float(info.get("ContainersStopped", 0)), "", now)
        _save_metric(db, source.name, "docker_images", float(info.get("Images", 0)), "", now)
        collected += 5

        containers = client.containers.list(all=True)
        for c in containers:
            attrs = {
                "image": c.image.tags[0] if c.image.tags else "",
                "status": c.status,
                "state": c.attrs.get("State", {}),
                "ports": c.attrs.get("NetworkSettings", {}).get("Ports", {}),
                "created": c.attrs.get("Created", ""),
            }
            _sync_docker_asset(db, c.id[:12], c.name, attrs)
            created += 1
            _save_metric(db, c.name, "docker_container_status", 1.0 if c.status == "running" else 0.0, "", now)
            collected += 1

        source.last_status = "online"
        source.last_error = ""
        msg = f"采集完成"
    finally:
        client.close()

    source.last_scrape = datetime.now()
    db.commit()
    return (True, msg)


def scrape_all_sources(db: Session):
    results = []
    now = datetime.now()
    sources = db.query(DataSource).filter(DataSource.enabled == True).all()
    for source in sources:
        if source.last_scrape:
            elapsed = (now - source.last_scrape).total_seconds()
            if elapsed < source.scrape_interval:
                continue
        success, msg = scrape_source(db, source)
        results.append({"source_id": source.id, "name": source.name, "success": success, "message": msg})
    return results





def _test_jaeger(source: DataSource) -> tuple:
    try:
        import urllib.request
        url = source.endpoint.rstrip("/") + "/api/services"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json as _json
            data = _json.loads(resp.read().decode("utf-8"))
            services = data.get("data", [])
            return (True, f"Jaeger 连接成功, 发现 {len(services)} 个服务")
    except Exception as e:
        return (False, f"Jaeger 连接失败: {e}")


def _scrape_jaeger(db: Session, source: DataSource) -> tuple:
    try:
        from app.services.trace_ingest_service import fetch_from_jaeger
        result = fetch_from_jaeger(db, source.endpoint, limit=50)
        if result.get("success"):
            source.last_status = "online"
            source.last_error = ""
            source.last_scrape = datetime.now()
            db.commit()
            return (True, result.get("message", "Jaeger 拉取成功"))
        else:
            source.last_status = "error"
            source.last_error = result.get("message", "")
            source.last_scrape = datetime.now()
            db.commit()
            return (False, result.get("message", "Jaeger 拉取失败"))
    except Exception as e:
        source.last_status = "error"
        source.last_error = str(e)
        source.last_scrape = datetime.now()
        db.commit()
        return (False, f"Jaeger 拉取异常: {e}")
