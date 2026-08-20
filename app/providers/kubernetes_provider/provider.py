import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class KubernetesAuthConfig(BaseAuthConfig):
    k8s_api_server: str = field(default="", metadata={"required": True, "description": "K8s API Server 地址(如 https://192.168.1.100:6443)"})
    k8s_token: str = field(default="", metadata={"sensitive": True, "description": "K8s ServiceAccount Token"})
    kubeconfig: str = field(default="", metadata={"sensitive": True, "description": "Kubeconfig 内容(YAML)"})
    verify_ssl: bool = field(default=False, metadata={"description": "是否校验 SSL 证书"})


class KubernetesProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="kubernetes",
        display_name="Kubernetes 集群",
        category=ProviderCategory.CLOUD_INFRA,
        description="对接 K8s API，自动发现集群资源(Node/Pod/Deployment/Service)并采集指标",
        tags=["kubernetes", "k8s", "container", "orchestration"],
        icon="☸️",
        docs_url="https://kubernetes.io/docs",
        auth_config_class=KubernetesAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            from kubernetes import client
            api_client = self._build_client()
            v1 = client.CoreV1Api(api_client=api_client)
            nodes = v1.list_node().items
            return True, f"K8s 连接成功, 发现 {len(nodes)} 个节点"
        except Exception as e:
            return False, f"K8s 连接失败: {e}"

    def scrape(self, db: Any = None) -> list[dict]:
        try:
            from kubernetes import client
        except ImportError:
            return []

        results = []
        now = datetime.now()
        api_client = self._build_client()
        v1 = client.CoreV1Api(api_client=api_client)
        apps_v1 = client.AppsV1Api(api_client=api_client)
        cluster_name = self.auth_config.k8s_api_server or self.endpoint or "unknown"

        try:
            cluster_asset = self._sync_k8s_asset(db, "kubernetes_cluster", cluster_name, 0, cluster_name, {"endpoint": cluster_name, "status": "Active"})
            if cluster_asset:
                results.append({"kind": "asset", "ci_type": "kubernetes_cluster", "name": cluster_name, "status": "online"})

            namespaces = v1.list_namespace().items
            ns_map = {}
            for ns in namespaces:
                ns_asset = self._sync_k8s_asset(db, "namespace", ns.metadata.name, cluster_asset.id if cluster_asset else 0, cluster_name, {"phase": ns.status.phase})
                ns_map[ns.metadata.name] = ns_asset.id if ns_asset else 0
                results.append({"kind": "asset", "ci_type": "namespace", "name": ns.metadata.name, "status": ns.status.phase})

            nodes = v1.list_node().items
            for node in nodes:
                node_ready = "Unknown"
                for cond in (node.status.conditions or []):
                    if getattr(cond, "type", "") == "Ready":
                        node_ready = "Ready" if getattr(cond, "status", "") == "True" else "NotReady"
                        break
                attrs = {
                    "kubelet_version": node.status.node_info.kubelet_version,
                    "os_image": node.status.node_info.os_image,
                    "cpu_capacity": node.status.capacity.get("cpu", "?"),
                    "memory_capacity": node.status.capacity.get("memory", "?"),
                    "pod_capacity": node.status.capacity.get("pods", "?"),
                    "ready": node_ready,
                }
                node_asset = self._sync_k8s_asset(db, "node", node.metadata.name, cluster_asset.id if cluster_asset else 0, cluster_name, {"status": node_ready} | attrs)
                node_aid = node_asset.id if node_asset else 0
                results.append({"kind": "asset", "ci_type": "node", "name": node.metadata.name, "ready": node_ready, "attributes": attrs})
                self._save_metric(db, node.metadata.name, "node_cpu_capacity", float(str(node.status.capacity.get("cpu", 0)).rstrip("n") or 0), "cores", now, node_aid, cluster_name)
                self._save_metric(db, node.metadata.name, "node_memory_capacity", float(self._parse_memory(str(node.status.capacity.get("memory", "0Ki")))), "bytes", now, node_aid, cluster_name)

            deps = apps_v1.list_deployment_for_all_namespaces().items
            for dep in deps:
                parent = ns_map.get(dep.metadata.namespace, cluster_asset.id if cluster_asset else 0)
                dep_available = dep.status.available_replicas or 0
                dep_replicas = dep.spec.replicas or 0
                attrs = {
                    "replicas": dep_replicas,
                    "available_replicas": dep_available,
                    "strategy": str(dep.spec.strategy.type) if dep.spec.strategy else "RollingUpdate",
                    "image": dep.spec.template.spec.containers[0].image if dep.spec.template.spec.containers else "",
                    "status": "Ready" if dep_available >= dep_replicas else "NotReady",
                }
                dep_asset = self._sync_k8s_asset(db, "deployment", f"{dep.metadata.namespace}/{dep.metadata.name}", parent, cluster_name, attrs)
                dep_aid = dep_asset.id if dep_asset else 0
                results.append({"kind": "asset", "ci_type": "deployment", "name": f"{dep.metadata.namespace}/{dep.metadata.name}", "attributes": attrs})
                self._save_metric(db, dep.metadata.name, "deployment_replicas", float(dep.spec.replicas or 0), "", now, dep_aid, cluster_name)
                self._save_metric(db, dep.metadata.name, "deployment_available", float(dep.status.available_replicas or 0), "", now, dep_aid, cluster_name)

            pods = v1.list_pod_for_all_namespaces().items
            for pod in pods:
                parent = ns_map.get(pod.metadata.namespace, cluster_asset.id if cluster_asset else 0)
                restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))
                attrs = {
                    "phase": pod.status.phase,
                    "node": pod.spec.node_name or "",
                    "pod_ip": pod.status.pod_ip or "",
                    "restarts": restarts,
                    "qos_class": str(pod.status.qos_class or ""),
                    "containers": [c.name for c in (pod.spec.containers or [])],
                    "status": pod.status.phase,
                }
                pod_asset = self._sync_k8s_asset(db, "pod", f"{pod.metadata.namespace}/{pod.metadata.name}", parent, cluster_name, attrs)
                pod_aid = pod_asset.id if pod_asset else 0
                results.append({"kind": "asset", "ci_type": "pod", "name": f"{pod.metadata.namespace}/{pod.metadata.name}", "attributes": attrs})
                self._save_metric(db, pod.metadata.name, "pod_restarts", float(restarts), "cnt", now, pod_aid, cluster_name)
                self._save_metric(db, pod.metadata.name, "pod_containers", float(len(pod.spec.containers or [])), "", now, pod_aid, cluster_name)

            svcs = v1.list_service_for_all_namespaces().items
            for svc in svcs:
                parent = ns_map.get(svc.metadata.namespace, cluster_asset.id if cluster_asset else 0)
                attrs = {
                    "type": svc.spec.type,
                    "cluster_ip": svc.spec.cluster_ip or "",
                    "ports": [f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])],
                    "status": "Active",
                }
                self._sync_k8s_asset(db, "service", f"{svc.metadata.namespace}/{svc.metadata.name}", parent, cluster_name, attrs)
                results.append({"kind": "asset", "ci_type": "service", "name": f"{svc.metadata.namespace}/{svc.metadata.name}", "attributes": attrs})
        finally:
            api_client.close()
        return results

    def _build_client(self):
        from kubernetes import client
        cfg = self.auth_config
        if cfg.kubeconfig:
            from kubernetes import config as k8s_config
            import yaml as _yaml
            kc_raw = cfg.kubeconfig
            if isinstance(kc_raw, str):
                kc_raw = _yaml.safe_load(kc_raw)
            k8s_config.load_kube_config_from_dict(kc_raw)
            return client.ApiClient()
        endpoint = cfg.k8s_api_server or self.endpoint or ""
        if not endpoint:
            raise ValueError("k8s_api_server 未配置")
        configuration = client.Configuration()
        configuration.host = endpoint
        if cfg.k8s_token:
            configuration.api_key = {"authorization": "Bearer " + cfg.k8s_token}
        configuration.verify_ssl = cfg.verify_ssl
        configuration.timeout = 10
        return client.ApiClient(configuration=configuration)

    def _sync_k8s_asset(self, db: Any, ci_type: str, name: str, parent_id: int, k8s_cluster: str, attrs: dict):
        if db is None:
            return None
        from app.models import Asset
        status = attrs.pop("status", None)
        asset_status = "online" if status in ("Ready", "Running", "Active", "online") else ("offline" if status in ("NotReady", "Failed", "Unknown", "Terminating", "Succeeded", "offline") else None)
        existing = db.query(Asset).filter(Asset.ci_type == ci_type, Asset.name == name, Asset.k8s_cluster == k8s_cluster).first()
        if not existing:
            existing = db.query(Asset).filter(Asset.ci_type == ci_type, Asset.name == name).first()
        if existing:
            for k, v in attrs.items():
                setattr(existing, k, v)
            if parent_id:
                existing.parent_id = parent_id
            existing.k8s_cluster = k8s_cluster
            if asset_status:
                existing.status = asset_status
            existing.ci_attributes = json.dumps(attrs, ensure_ascii=False)
            db.flush()
            return existing
        from sqlalchemy import text as _sa_text
        next_id = (db.execute(_sa_text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0) + 1
        asset = Asset(
            id=next_id, name=name, ci_type=ci_type,
            parent_id=(parent_id if parent_id else None),
            status=asset_status or "online", k8s_cluster=k8s_cluster,
            ci_attributes=json.dumps(attrs, ensure_ascii=False),
        )
        db.add(asset)
        db.flush()
        return asset

    def _save_metric(self, db: Any, host: str, name: str, value: float, unit: str, timestamp: datetime,
                     asset_id: int = 0, cluster: str = "unknown"):
        if db is None:
            return
        from app.models import MetricRecord
        db.add(MetricRecord(
            name=name, value=value, unit=unit,
            timestamp=timestamp,
            asset_id=asset_id if asset_id else None,
            labels=json.dumps({"host": host, "cluster": cluster}, ensure_ascii=False),
        ))
        try:
            from app.services.metric_v2_service import write_metrics_batch
            write_metrics_batch([{
                "name": name,
                "value": value,
                "timestamp": timestamp,
                "labels": {"host": host, "cluster": cluster},
                "asset_id": asset_id if asset_id else None,
            }])
        except Exception:
            pass

    def _parse_memory(self, val: str) -> float:
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