import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class SSHAuthConfig(BaseAuthConfig):
    ssh_host: str = field(default="", metadata={"required": True, "description": "SSH 主机地址(IP 或域名)"})
    ssh_port: int = field(default=22, metadata={"description": "SSH 端口"})
    ssh_user: str = field(default="root", metadata={"required": True, "description": "SSH 用户名"})
    ssh_password: str = field(default="", metadata={"sensitive": True, "description": "SSH 密码"})
    ssh_private_key: str = field(default="", metadata={"sensitive": True, "description": "SSH 私钥内容(PEM)"})


SSH_COMMANDS = {
    "loadavg": "cat /proc/loadavg",
    "memory": "free -m",
    "disk": "df -B1 /",
    "network": "cat /proc/net/dev",
    "uptime": "uptime",
}


class SSHProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="ssh",
        display_name="SSH 远程采集",
        category=ProviderCategory.CLOUD_INFRA,
        description="通过 SSH 远程登录目标主机采集 CPU/内存/磁盘/网络指标",
        tags=["ssh", "linux", "metrics"],
        icon="🖥️",
        docs_url="",
        auth_config_class=SSHAuthConfig,
    )

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._connect()
            try:
                stdin, stdout, stderr = client.exec_command("uptime", timeout=10)
                output = stdout.read().decode("utf-8").strip()
            finally:
                client.close()
            return True, f"SSH 连接成功: {output[:80]}"
        except Exception as e:
            return False, f"SSH 连接失败: {e}"

    def scrape(self, db: Any = None, **kwargs) -> list[dict]:
        results = []
        host = self.auth_config.ssh_host or self.endpoint or ""
        now = datetime.now()
        client = self._connect()
        try:
            host_asset = self._sync_ssh_asset(db, host)

            stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["loadavg"], timeout=8)
            output = stdout.read().decode("utf-8").strip()
            match = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)", output)
            if match:
                for i, mname in enumerate(["loadavg_1min", "loadavg_5min", "loadavg_15min"], start=1):
                    results.extend(self._save(host, mname, float(match.group(i)), "", now, db))

            stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["memory"], timeout=8)
            output = stdout.read().decode("utf-8").strip()
            for line in output.split("\n"):
                parts = line.split()
                if line.startswith("Mem:") and len(parts) >= 4:
                    results.extend([
                        *self._save(host, "memory_total", float(parts[1]), "MB", now, db),
                        *self._save(host, "memory_used", float(parts[2]), "MB", now, db),
                        *self._save(host, "memory_free", float(parts[3]), "MB", now, db),
                    ])
                elif line.startswith("Swap:") and len(parts) >= 4:
                    results.extend([
                        *self._save(host, "swap_total", float(parts[1]), "MB", now, db),
                        *self._save(host, "swap_used", float(parts[2]), "MB", now, db),
                        *self._save(host, "swap_free", float(parts[3]), "MB", now, db),
                    ])

            stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["disk"], timeout=8)
            output = stdout.read().decode("utf-8").strip()
            for line in output.split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    dev = parts[0]
                    results.extend([
                        *self._save(host, f"disk_used_pct_{dev}", float(parts[4].replace("%", "")), "%", now, db),
                        *self._save(host, f"disk_used_{dev}", float(parts[2]), parts[1] if parts[1].isalpha() else "", now, db),
                    ])

            stdin, stdout, stderr = client.exec_command(SSH_COMMANDS["network"], timeout=8)
            output = stdout.read().decode("utf-8").strip()
            for line in output.split("\n"):
                if ":" in line and "lo" not in line:
                    parts = line.split()
                    if len(parts) >= 11:
                        iface = parts[0].replace(":", "")
                        results.extend([
                            *self._save(host, f"net_bytes_in_{iface}", float(parts[1]), "bytes", now, db),
                            *self._save(host, f"net_bytes_out_{iface}", float(parts[9]), "bytes", now, db),
                        ])

            results.extend(self._discover_docker_via_ssh(db, client, host, now))
        finally:
            client.close()
        return results

    def _connect(self):
        from app.services.ssh_helper import connect_ssh
        pkey = None
        if self.auth_config.ssh_private_key:
            pkey = self._load_pkey(self.auth_config.ssh_private_key)
        return connect_ssh(
            self.auth_config.ssh_host or self.endpoint,
            port=int(self.auth_config.ssh_port or 22),
            username=self.auth_config.ssh_user or "root",
            password=self.auth_config.ssh_password or "",
            pkey=pkey,
            timeout=10,
        )

    def _load_pkey(self, private_key: str):
        import paramiko
        for loader in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                return loader.from_private_key(io.StringIO(private_key))
            except Exception:
                continue
        raise ValueError("无法解析 SSH 私钥(支持 RSA/Ed25519/ECDSA/DSS)")

    def _exec(self, client, command: str) -> str:
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=8)
            return stdout.read().decode("utf-8").strip()
        except Exception:
            return ""

    def _exec_json(self, client, command: str) -> list[dict]:
        output = self._exec(client, command)
        if not output:
            return []
        results = []
        for line in output.split("\n"):
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except Exception:
                    continue
        return results

    def _discover_docker_via_ssh(self, db: Any, client, host: str, now: datetime, results: list[dict] = None) -> list[dict]:
        out = []
        info = self._exec_json(client, "docker info --format '{{json .}}' 2>/dev/null")
        if info:
            data = info[0]
            out.extend([
                *self._save(host, "docker_containers_total", float(data.get("Containers", 0)), "", now, db),
                *self._save(host, "docker_containers_running", float(data.get("ContainersRunning", 0)), "", now, db),
                *self._save(host, "docker_images", float(data.get("Images", 0)), "", now, db),
            ])
            containers = self._exec_json(client, "docker ps -a --format '{{json .}}' 2>/dev/null")
            for c in containers:
                cname = c.get("Names", c.get("Name", ""))
                is_running = "running" in c.get("Status", "").lower() or c.get("State", "") == "running"
                attrs = {
                    "name": cname,
                    "container_id": c.get("ID", "")[:12],
                    "image": c.get("Image", ""),
                    "status": c.get("Status", ""),
                    "state": "running" if is_running else "exited",
                    "ports": c.get("Ports", ""),
                    "host": host,
                }
                out.append({
                    "kind": "asset",
                    "ci_type": "container",
                    "name": f"{host}/{cname}" if cname else cname,
                    "status": "online" if is_running else "offline",
                    "attributes": attrs,
                    "timestamp": now,
                })
                try:
                    self._sync_ssh_container_asset(db, host, cname, attrs, is_running)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("[providers.ssh] docker asset sync failed: %s", e)
            out.extend(self._save(host, "docker_containers_discovered", float(len(containers)), "", now, db))
        return out

    def _sync_ssh_asset(self, db: Any, host: str):
        if db is None:
            return None
        from app.models import Asset
        existing = db.query(Asset).filter(Asset.ci_type == "server", Asset.ip == host).first()
        if existing:
            return existing
        from sqlalchemy import text as _sa_text
        next_id = (db.execute(_sa_text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0) + 1
        asset = Asset(id=next_id, name=host, ci_type="server", ip=host, status="online")
        db.add(asset)
        db.flush()
        return asset

    def _sync_ssh_container_asset(self, db: Any, host: str, name: str, attrs: dict, is_running: bool):
        if db is None or not name:
            return None
        from app.models import Asset
        existing = db.query(Asset).filter(Asset.ci_type == "container", Asset.name == f"{host}/{name}").first()
        if existing:
            for k, v in attrs.items():
                if k in ("created_at", "updated_at"):
                    continue
                setattr(existing, k, v)
            db.flush()
            return existing
        from sqlalchemy import text as _sa_text
        next_id = (db.execute(_sa_text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0) + 1
        asset = Asset(
            id=next_id,
            name=f"{host}/{name}",
            ci_type="container",
            status="online" if is_running else "offline",
            ci_attributes=json.dumps(attrs, ensure_ascii=False),
        )
        db.add(asset)
        db.flush()
        return asset

    def _save(self, host: str, name: str, value: float, unit: str, timestamp: datetime, db: Any) -> list[dict]:
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