from dataclasses import dataclass, field
import datetime
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import quote

import requests

from app.providers.base import BaseProvider, BaseAuthConfig, ProviderMeta, ProviderCategory


@dataclass
class CloudWatchAuthConfig(BaseAuthConfig):
    region: str = field(default="us-east-1", metadata={"required": True, "sensitive": False, "description": "AWS 区域"})
    access_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "AWS Access Key"})
    secret_key: str = field(default="", metadata={"required": True, "sensitive": True, "description": "AWS Secret Key"})
    session_token: str = field(default="", metadata={"required": False, "sensitive": True, "description": "AWS Session Token (可选)"})

    def __post_init__(self):
        self.region = self.region or "us-east-1"
        self.access_key = self.access_key or ""
        self.secret_key = self.secret_key or ""


def _sigv4_sign(access_key: str, secret_key: str, region: str, service: str,
                host: str, method: str, path: str, headers: dict, body: bytes,
                session_token: str = "") -> dict:
    """AWS Signature Version 4 请求签名"""
    signing_headers = dict(headers)
    t = datetime.datetime.utcnow()
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")
    signing_headers["X-Amz-Date"] = amz_date
    if session_token:
        signing_headers["X-Amz-Security-Token"] = session_token
    signing_headers["Host"] = host

    def _sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    payload_hash = _sha256_hex(body)
    canonical_headers = "".join(
        f"{k.lower()}:{v.strip()}\n" for k, v in sorted(signing_headers.items())
    )
    signed_headers = ";".join(k.lower() for k in sorted(signing_headers.keys()))

    canonical_request = "\n".join([
        method,
        path,
        "",
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        _sha256_hex(canonical_request.encode()),
    ])

    def _sign(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _sign(("AWS4" + secret_key).encode(), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    signing_headers["Authorization"] = auth_header
    return signing_headers


class CloudWatchProvider(BaseProvider):
    PROVIDER_META = ProviderMeta(
        name="cloudwatch",
        display_name="CloudWatch",
        category=ProviderCategory.MONITORING,
        description="AWS CloudWatch 监控集成，拉取告警(Alarm)状态",
        tags=["monitoring", "aws", "cloudwatch", "alarms"],
        icon="cloudwatch",
        auth_config_class=CloudWatchAuthConfig,
    )

    _SEV_MAP = {
        "0": "critical",
        "1": "high",
        "2": "warning",
        "3": "info",
    }

    def validate_config(self, auth_config: dict) -> CloudWatchAuthConfig:
        return CloudWatchAuthConfig.from_dict(auth_config)

    def _client_call(self, action: str, params: dict) -> dict:
        cfg = self.auth_config
        host = f"monitoring.{cfg.region}.amazonaws.com"
        path = "/"
        body = b""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json",
        }
        # 构建 form-encoded 请求体
        form = {"Action": action, "Version": "2010-08-01", **params}
        body = "&".join(f"{quote(k, safe='')}={quote(str(v), safe='')}" for k, v in form.items()).encode()
        headers["Content-Length"] = str(len(body))

        signed = _sigv4_sign(
            cfg.access_key, cfg.secret_key, cfg.region, "monitoring",
            host, "POST", path, headers, body, cfg.session_token,
        )
        url = f"https://{host}{path}"
        resp = requests.post(url, headers=signed, data=body, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"CloudWatch API 错误: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def test_connection(self) -> tuple[bool, str]:
        cfg = self.auth_config
        if not cfg.access_key or not cfg.secret_key or not cfg.region:
            return False, "Access Key / Secret Key / Region 未配置"
        try:
            data = self._client_call("DescribeAlarms", {"StateValue": "ALARM", "MaxRecords": "1"})
            resp = data.get("DescribeAlarmsResponse", {}).get("DescribeAlarmsResult", {}).get("MetricAlarms", [])
            return True, f"AWS CloudWatch 连接正常（{len(resp)} 个告警）"
        except RuntimeError as e:
            return False, str(e)
        except requests.RequestException as e:
            return False, f"CloudWatch 连接失败: {e}"

    def _scrape_alarms(self) -> list[dict]:
        alerts = []
        try:
            data = self._client_call("DescribeAlarms", {"StateValue": "ALARM", "MaxRecords": "100"})
            platforms_enc = {'<': '&lt;', '>': '&gt;'}
            raw = data.get("DescribeAlarmsResponse", {}).get("DescribeAlarmsResult", {}).get("MetricAlarms", [])
            for alarm in raw or []:
                name = alarm.get("AlarmName", "")
                state = alarm.get("StateValue", "ALARM").lower()
                comparison = alarm.get("ComparisonOperator", "")
                # severity 从阈值判断
                severity = "warning"
                alerts.append({
                    "id": alarm.get("AlarmArn", name),
                    "source": "cloudwatch",
                    "name": name,
                    "message": (alarm.get("AlarmDescription") or "")
                               + f" [{comparison} {alarm.get('Threshold')}]",
                    "status": "firing" if state == "alarm" else state,
                    "severity": severity,
                    "namespace": alarm.get("Namespace", ""),
                    "metric": alarm.get("MetricName", ""),
                    "dimensions": alarm.get("Dimensions", []),
                    "state_reason": alarm.get("StateReason", ""),
                    "timestamp": alarm.get("StateUpdatedTimestamp", ""),
                })
            if not alerts:
                return []
        except RuntimeError as e:
            alerts.append({"source": "cloudwatch", "error": f"拉取告警异常: {e}"})
        except requests.RequestException as e:
            alerts.append({"source": "cloudwatch", "error": f"拉取告警异常: {e}"})
        return alerts

    def scrape(self, db=None) -> list[dict]:
        return self._scrape_alarms()

    def query(self, **kwargs) -> list[dict]:
        try:
            data = self._client_call("DescribeAlarms", {"MaxRecords": "100"})
            return data.get("DescribeAlarmsResponse", {}).get("DescribeAlarmsResult", {}).get("MetricAlarms", [])
        except (RuntimeError, requests.RequestException) as e:
            return [{"error": f"CloudWatch 查询异常: {e}"}]

    def dispose(self):
        pass