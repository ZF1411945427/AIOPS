from dataclasses import dataclass, field
from typing import Any

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class ZabbixAuthConfig(BaseAuthConfig):
    endpoint: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Zabbix API 地址"})
    username: str = field(default="", metadata={"required": True, "sensitive": False, "description": "Zabbix 用户名"})
    password: str = field(default="", metadata={"required": False, "sensitive": True, "description": "Zabbix 密码"})

    def __post_init__(self):
        self.endpoint = self.endpoint.rstrip("/") if self.endpoint else ""
        self.username = self.username or ""
        self.password = self.password or ""


class ZabbixProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="zabbix",
        display_name="Zabbix",
        category=ProviderCategory.MONITORING,
        description="Zabbix 监控集成，通过 JSON-RPC API 获取主机和监控项数据",
        tags=["monitoring", "zabbix", "infrastructure", "network"],
        icon="zabbix",
        auth_config_class=ZabbixAuthConfig,
    )

    def __init__(self, source_id: int, auth_config: dict, db=None, endpoint: str = ""):
        super().__init__(source_id, auth_config, db, endpoint)
        self._auth_token: str = ""

    def validate_config(self, auth_config: dict) -> ZabbixAuthConfig:
        return ZabbixAuthConfig.from_dict(auth_config)

    def _rpc_call(self, method: str, params: list | dict = None) -> dict:
        cfg = self.auth_config
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
            "auth": self._auth_token if method != "user.login" else None,
        }
        if method == "user.login":
            payload["auth"] = None
        resp = requests.post(
            f"{cfg.endpoint}/api_jsonrpc.php",
            json=payload,
            headers={"Content-Type": "application/json-rpc"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Zabbix API 错误: {data['error'].get('message', '')} - {data['error'].get('data', '')}")
        return data

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.endpoint or not cfg.username:
            return False, "Endpoint 或用户名未配置"
        try:
            result = self._rpc_call("user.login", {"user": cfg.username, "password": cfg.password})
            token = result.get("result", "")
            if token:
                self._auth_token = token
                return True, "Zabbix 连接正常"
            return False, "Zabbix 登录失败：未返回 Token"
        except requests.RequestException as e:
            return False, f"Zabbix 连接失败: {e}"
        except RuntimeError as e:
            return False, str(e)

    def query(self, **kwargs) -> list[dict]:
        if not self._auth_token:
            return [{"error": "未登录，请先测试连接"}]
        query_type = kwargs.get("type", "hosts")
        try:
            if query_type == "hosts":
                result = self._rpc_call("host.get", {"output": "extend", "selectGroups": "extend"})
                hosts = result.get("result", [])
                return [{"hostid": h["hostid"], "host": h["host"], "name": h.get("name", ""), "status": h.get("status", "")} for h in hosts]
            elif query_type == "items":
                host_id = kwargs.get("host_id", "")
                if not host_id:
                    return [{"error": "查询监控项需要 host_id 参数"}]
                result = self._rpc_call("item.get", {"output": "extend", "hostids": host_id})
                items = result.get("result", [])
                return [{"itemid": i["itemid"], "name": i.get("name", ""), "key_": i.get("key_", ""), "value_type": i.get("value_type", ""), "lastvalue": i.get("lastvalue", "")} for i in items]
            return [{"error": f"不支持的查询类型: {query_type}"}]
        except (requests.RequestException, RuntimeError) as e:
            return [{"error": f"Zabbix 查询异常: {e}"}]

    def _ensure_login(self) -> bool:
        if self._auth_token:
            return True
        try:
            result = self._rpc_call("user.login", {"user": self.auth_config.username, "password": self.auth_config.password})
            token = result.get("result", "")
            if token:
                self._auth_token = token
                return True
        except (requests.RequestException, RuntimeError):
            pass
        return False

    def _convert_severity(self, severity: int) -> str:
        sev_map = {0: "info", 1: "info", 2: "warning", 3: "average", 4: "high", 5: "critical"}
        return sev_map.get(severity, "info")

    def _scrape_problems(self) -> list[dict]:
        """拉取 Zabbix 未关闭问题（problem.get），参考 KeepHQ 逻辑"""
        alerts = []
        if not self._ensure_login():
            alerts.append({"source": "zabbix", "error": "未登录 Zabbix"})
            return alerts
        try:
            result = self._rpc_call("problem.get", {
                "recent": False,
                "selectSuppressionData": "extend",
                "severities": [2, 3, 4, 5],  # 只拉 warning 及以上
                "filter": {"status": "0"},  # 未关闭
            })
            for p in result.get("result", []):
                severity = self._convert_severity(int(p.get("severity", 1)))
                alerts.append({
                    "id": str(p.get("eventid")),
                    "source": "zabbix",
                    "name": p.get("name"),
                    "message": p.get("name", ""),
                    "status": "firing",
                    "severity": severity,
                    "problem": {k: v for k, v in p.items() if k not in ("name", "severity", "eventid")},
                    "timestamp": p.get("clock"),
                })
        except (requests.RequestException, RuntimeError) as e:
            alerts.append({"source": "zabbix", "error": f"拉取问题异常: {e}"})
        return alerts

    def scrape(self, db=None) -> list[dict]:
        return self._scrape_problems()

    def notify(self, alert: dict, **kwargs) -> dict:
        return {"success": False, "message": "Zabbix Provider 不支持 notify，请使用 query 获取数据"}

    def dispose(self):
        self._auth_token = ""