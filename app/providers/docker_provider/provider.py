import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class DockerAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"description": "Docker 套接字 URL(如 unix:///var/run/docker.sock 或 tcp://10.0.0.1:2375)"})
    docker_cert_path: str = field(default="", metadata={"description": "Docker TLS 证书路径"})


class DockerProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="docker",
        display_name="Docker 主机",
        category=ProviderCategory.CONTAINER,
        description="对接 Docker API 采集容器指标数据和资产信息",
        tags=["docker", "container", "runtime"],
        icon="🐳",
        docs_url="https://docs.docker.com/engine/api",
        auth_config_class=DockerAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            import docker
        except ImportError:
            return False, "缺少 docker Python 包"
        try:
            client = self._build_client()
            info = client.info()
            client.close()
            containers = info.get("Containers", 0)
            running = info.get("ContainersRunning", 0)
            images = info.get("Images", 0)
            return True, f"Docker 连接成功, {containers} 容器({running} 运行), {images} 镜像"
        except Exception as e:
            return False, f"Docker 连接失败: {e}"

    def scrape(self, db: Any = None) -> list[dict]:
        try:
            import docker
        except ImportError:
            return []
        results = []
        now = datetime.now()
        client = self._build_client()

        try:
            info = client.info()
            host_name = info.get("Name", "docker-host")
            results.extend(self._save_metric(db, host_name, "docker_containers_total", float(info.get("Containers", 0)), "", now))
            results.extend(self._save_metric(db, host_name, "docker_containers_running", float(info.get("ContainersRunning", 0)), "", now))
            results.extend(self._save_metric(db, host_name, "docker_containers_paused", float(info.get("ContainersPaused", 0)), "", now))
            results.extend(self._save_metric(db, host_name, "docker_containers_stopped", float(info.get("ContainersStopped", 0)), "", now))
            results.extend(self._save_metric(db, host_name, "docker_images", float(info.get("Images", 0)), "", now))

            results.append({
                "kind": "summary",
                "host": host_name,
                "containers": info.get("Containers", 0),
                "running": info.get("ContainersRunning", 0),
                "images": info.get("Images", 0),
                "driver": info.get("Driver", ""),
                "kernel": info.get("KernelVersion", ""),
                "os": info.get("OperatingSystem", ""),
                "timestamp": now,
            })

            containers = client.containers.list(all=True)
            for c in containers:
                c_attrs = {
                    "image": c.image.tags[0] if c.image.tags else "",
                    "status": c.status,
                    "state": c.attrs.get("State", {}),
                    "ports": c.attrs.get("NetworkSettings", {}).get("Ports", {}),
                    "created": c.attrs.get("Created", ""),
                }
                results.append({
                    "kind": "asset",
                    "ci_type": "container",
                    "name": c.name,
                    "container_id": c.id[:12],
                    "status": "online" if c.status == "running" else "offline",
                    "attributes": c_attrs,
                    "timestamp": now,
                })
                self._sync_docker_asset(db, c.id[:12], c.name, c_attrs, c.status == "running")
                results.extend(self._save_metric(db, c.name, "docker_container_status", 1.0 if c.status == "running" else 0.0, "", now))
        finally:
            client.close()

        return results

    def _build_client(self):
        import docker
        endpoint = self.auth_config.endpoint or self.endpoint or ""
        if endpoint:
            return docker.DockerClient(base_url=endpoint)
        return docker.from_env()

    def _sync_docker_asset(self, db: Any, container_id: str, name: str, attrs: dict, is_running: bool):
        if db is None:
            return None
        from app.models import Asset
        existing = db.query(Asset).filter(Asset.ci_type == "container", Asset.name == name).first()
        if existing:
            for k, v in attrs.items():
                setattr(existing, k, v)
            db.flush()
            return existing
        from sqlalchemy import text as _sa_text
        next_id = (db.execute(_sa_text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0) + 1
        asset = Asset(
            id=next_id, name=name, ci_type="container",
            status="online" if is_running else "offline",
            ci_attributes=json.dumps(attrs, ensure_ascii=False),
        )
        db.add(asset)
        db.flush()
        return asset

    def _save_metric(self, db: Any, host: str, name: str, value: float, unit: str, timestamp: datetime) -> list[dict]:
        record = {
            "kind": "metric",
            "name": name,
            "value": value,
            "unit": unit,
            "labels": {"host": host},
            "timestamp": timestamp,
        }
        if db is not None:
            from app.models import MetricRecord
            db.add(MetricRecord(
                name=name, value=value, unit=unit,
                timestamp=timestamp, labels=json.dumps({"host": host}, ensure_ascii=False),
            ))
        return [record]