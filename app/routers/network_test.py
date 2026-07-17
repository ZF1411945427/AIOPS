"""网络测试工具 API — Ping / Traceroute / TCP 端口 / DNS / HTTP 探测 / TLS 证书 / IP 归属地.

合规说明:
- 本工具仅用于自有资产的网络连通性巡检与故障诊断
- 未经授权对他人服务器进行探测涉嫌违反《网络安全法》第二十七条
- 所有操作记录审计日志, 限制请求频率, 禁止高频探测
- TCP 端口测试仅支持单端口检测, 不提供批量端口扫描
"""
import re
import ssl
import json
import socket
import struct
import subprocess
import time
import platform
import urllib.request
import urllib.error
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/api/network-test", tags=["network-test"])
logger = logging.getLogger("aiops.network_test")

_last_call: dict[str, float] = {}
MIN_INTERVAL = 1.0
MAX_OUTPUT_LEN = 50000

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)
_IP_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_FORBIDDEN_CHARS = re.compile(r"[;|&`$(){}!\n\r#<>]")


def _validate_target(target: str) -> str:
    target = target.strip()
    if not target or len(target) > 253:
        raise HTTPException(400, "目标地址不合法")
    if _FORBIDDEN_CHARS.search(target):
        raise HTTPException(400, "目标地址包含非法字符")
    m = _IP_RE.match(target)
    if m:
        parts = [int(m.group(i)) for i in range(1, 5)]
        if any(p > 255 for p in parts):
            raise HTTPException(400, "IP 地址不合法")
        return target
    if _DOMAIN_RE.match(target):
        return target
    raise HTTPException(400, "目标地址格式不正确，需为合法 IP 或域名")


def _check_rate(key: str):
    now = time.time()
    if key in _last_call and now - _last_call[key] < MIN_INTERVAL:
        wait = round(MIN_INTERVAL - (now - _last_call[key]), 1)
        raise HTTPException(429, f"请求过于频繁，请 {wait} 秒后重试")
    _last_call[key] = now


def _log_action(tool: str, target: str, extra: str = ""):
    logger.info("[网络测试] tool=%s target=%s %s", tool, target, extra)


class PingRequest(BaseModel):
    target: str = Field(..., description="目标 IP 或域名")
    count: int = Field(4, ge=1, le=10, description="探测次数")
    timeout: int = Field(5, ge=1, le=30, description="超时(秒)")


class TraceRouteRequest(BaseModel):
    target: str = Field(..., description="目标 IP 或域名")
    max_hops: int = Field(20, ge=1, le=50, description="最大跳数")
    timeout: int = Field(5, ge=1, le=30, description="超时(秒)")


class TcpPortRequest(BaseModel):
    target: str = Field(..., description="目标 IP 或域名")
    port: int = Field(..., ge=1, le=65535, description="端口号")
    timeout: int = Field(3, ge=1, le=10, description="超时(秒)")


class DnsRequest(BaseModel):
    target: str = Field(..., description="要解析的域名")
    dns_server: Optional[str] = Field(None, description="指定 DNS 服务器")
    record_type: str = Field("A", description="记录类型 A/AAAA/CNAME/MX/TXT/NS")


@router.get("/tools")
def list_tools():
    return {
        "tools": [
            {"id": "ping", "name": "Ping 连通性测试", "description": "ICMP 探测目标主机连通性与延迟", "risk_level": "low"},
            {"id": "traceroute", "name": "Traceroute 路由追踪", "description": "追踪到目标的网络路由路径", "risk_level": "low"},
            {"id": "tcp-port", "name": "TCP 端口连通性", "description": "检测目标 TCP 端口是否开放", "risk_level": "medium"},
            {"id": "dns", "name": "DNS 解析查询", "description": "查询域名 DNS 解析记录", "risk_level": "low"},
            {"id": "http", "name": "HTTP/HTTPS 探测", "description": "检测网站可访问性、状态码、响应头", "risk_level": "low"},
            {"id": "tls-cert", "name": "TLS 证书查询", "description": "查询 HTTPS 证书信息及有效期", "risk_level": "low"},
            {"id": "ip-location", "name": "IP 归属地查询", "description": "查询 IP 地址的地理位置和 ISP 信息", "risk_level": "low"},
        ],
        "compliance_notice": "本工具仅用于自有资产网络连通性巡检。未经授权探测他人服务器涉嫌违反《网络安全法》。",
    }


@router.post("/ping")
def ping(req: PingRequest):
    target = _validate_target(req.target)
    _check_rate(target)
    _log_action("ping", target, f"count={req.count}")
    is_win = platform.system() == "Windows"
    if is_win:
        cmd = ["ping", "-n", str(req.count), "-w", str(req.timeout * 1000), target]
    else:
        cmd = ["ping", "-c", str(req.count), "-W", str(req.timeout), target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=req.count * req.timeout + 15)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output[:MAX_OUTPUT_LEN],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Ping 执行超时", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "output": "系统未安装 ping 命令", "returncode": -1}
    except Exception as e:
        return {"success": False, "output": f"执行异常: {e}", "returncode": -1}


@router.post("/traceroute")
def traceroute(req: TraceRouteRequest):
    target = _validate_target(req.target)
    _check_rate(target)
    _log_action("traceroute", target, f"max_hops={req.max_hops}")
    is_win = platform.system() == "Windows"
    if is_win:
        cmd = ["tracert", "-d", "-h", str(req.max_hops), "-w", str(req.timeout * 1000), target]
    else:
        cmd = ["traceroute", "-m", str(req.max_hops), "-w", str(req.timeout), target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=req.max_hops * req.timeout + 30)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output[:MAX_OUTPUT_LEN],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Traceroute 执行超时", "returncode": -1}
    except FileNotFoundError:
        hint = "系统未安装 traceroute 命令" + ("，Linux 可执行: yum install -y traceroute 或 apt install -y traceroute" if not is_win else "")
        return {"success": False, "output": hint, "returncode": -1}
    except Exception as e:
        return {"success": False, "output": f"执行异常: {e}", "returncode": -1}


@router.post("/tcp-port")
def tcp_port(req: TcpPortRequest):
    target = _validate_target(req.target)
    _check_rate(f"{target}:{req.port}")
    _log_action("tcp-port", target, f"port={req.port}")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(req.timeout)
        start = time.time()
        result_code = sock.connect_ex((target, req.port))
        elapsed = round((time.time() - start) * 1000, 1)
        sock.close()
        if result_code == 0:
            return {
                "success": True,
                "output": f"端口 {req.port} 开放，TCP 连接耗时 {elapsed}ms",
                "elapsed_ms": elapsed,
                "port": req.port,
                "open": True,
            }
        else:
            reason = {
                111: "连接被拒绝(Connection refused)",
                110: "连接超时(Connection timed out)",
                113: "无路由到主机(No route to host)",
            }.get(result_code, f"错误码 {result_code}")
            return {
                "success": False,
                "output": f"端口 {req.port} 不可达: {reason}，耗时 {elapsed}ms",
                "elapsed_ms": elapsed,
                "port": req.port,
                "open": False,
            }
    except socket.gaierror:
        return {"success": False, "output": "域名解析失败，无法连接", "elapsed_ms": 0, "port": req.port, "open": False}
    except Exception as e:
        return {"success": False, "output": f"连接异常: {e}", "elapsed_ms": 0, "port": req.port, "open": False}


@router.post("/dns")
def dns_lookup(req: DnsRequest):
    target = _validate_target(req.target)
    _check_rate(target)
    _log_action("dns", target, f"type={req.record_type} server={req.dns_server}")
    rt = req.record_type.upper()
    cmd = ["nslookup", "-type=" + rt, target]
    if req.dns_server:
        cmd.append(req.dns_server)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output[:MAX_OUTPUT_LEN],
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        try:
            addrs = socket.getaddrinfo(target, None)
            ips = sorted(set(a[4][0] for a in addrs))
            return {
                "success": True,
                "output": f"域名 {target} 解析结果 (A/AAAA):\n" + "\n".join(ips),
                "returncode": 0,
            }
        except Exception as e:
            return {"success": False, "output": f"DNS 解析失败: {e}", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "DNS 查询超时", "returncode": -1}
    except Exception as e:
        return {"success": False, "output": f"执行异常: {e}", "returncode": -1}


# ── HTTP/HTTPS 探测 ──

class HttpRequest(BaseModel):
    url: str = Field(..., description="目标 URL，如 https://example.com")
    method: str = Field("GET", description="HTTP 方法")
    timeout: int = Field(10, ge=1, le=30, description="超时(秒)")
    follow_redirects: bool = Field(True, description="是否跟随重定向")


_URL_RE = re.compile(r"^https?://[^\s\"'<>]+$", re.IGNORECASE)


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url or len(url) > 2048:
        raise HTTPException(400, "URL 不合法")
    if not _URL_RE.match(url):
        raise HTTPException(400, "URL 格式不正确，需以 http:// 或 https:// 开头")
    if _FORBIDDEN_CHARS.search(url):
        raise HTTPException(400, "URL 包含非法字符")
    return url


@router.post("/http")
def http_probe(req: HttpRequest):
    url = _validate_url(req.url)
    method = req.method.upper() if req.method.upper() in ("GET", "HEAD") else "GET"
    _check_rate(url)
    _log_action("http", url, f"method={method}")
    start = time.time()
    try:
        headers = {"User-Agent": "AIOps-NetworkTest/1.0"}
        req_obj = urllib.request.Request(url, headers=headers, method=method)
        opener = urllib.request.build_opener()
        if not req.follow_redirects:
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **kw):
                    return None
            opener = urllib.request.build_opener(_NoRedirect)
        resp = opener.open(req_obj, timeout=req.timeout)
        elapsed = round((time.time() - start) * 1000, 1)
        body_preview = ""
        try:
            body_preview = resp.read(2048).decode("utf-8", errors="replace")
        except Exception:
            pass
        resp_headers = dict(resp.headers.items())
        return {
            "success": True,
            "status_code": resp.status,
            "reason": resp.reason,
            "elapsed_ms": elapsed,
            "content_type": resp.headers.get("Content-Type", ""),
            "content_length": resp.headers.get("Content-Length", ""),
            "server": resp.headers.get("Server", ""),
            "headers": json.dumps(resp_headers, ensure_ascii=False)[:MAX_OUTPUT_LEN],
            "body_preview": body_preview[:2000],
            "final_url": resp.url,
        }
    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - start) * 1000, 1)
        return {
            "success": False,
            "status_code": e.code,
            "reason": str(e.reason),
            "elapsed_ms": elapsed,
            "output": f"HTTP {e.code} {e.reason}",
        }
    except urllib.error.URLError as e:
        return {"success": False, "output": f"连接失败: {e.reason}", "elapsed_ms": 0}
    except Exception as e:
        return {"success": False, "output": f"执行异常: {e}", "elapsed_ms": 0}


# ── TLS 证书查询 ──

class TlsCertRequest(BaseModel):
    target: str = Field(..., description="目标域名")
    port: int = Field(443, ge=1, le=65535, description="端口")
    timeout: int = Field(10, ge=1, le=30, description="超时(秒)")


@router.post("/tls-cert")
def tls_cert_check(req: TlsCertRequest):
    target = _validate_target(req.target)
    _check_rate(f"tls:{target}:{req.port}")
    _log_action("tls-cert", target, f"port={req.port}")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        with socket.create_connection((target, req.port), timeout=req.timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=target) as ssock:
                cert_bin = ssock.getpeercert(binary_form=True)
                if not cert_bin:
                    return {"success": False, "output": "未获取到证书数据"}
                cert_dict = ssock.getpeercert()
                if not cert_dict:
                    cert_dict = {}
        if not cert_dict:
            x509 = ssl.DER_cert_to_PEM_cert(cert_bin)
            return {
                "success": True,
                "output": f"=== TLS 证书信息 ===\n目标: {target}:{req.port}\n(证书已获取，但未配置 CA 信任链，无法解析详细字段)\nPEM 证书长度: {len(x509)} 字节",
            }
        subject = dict(x[0] for x in cert_dict.get("subject", []))
        issuer = dict(x[0] for x in cert_dict.get("issuer", []))
        not_before = cert_dict.get("notBefore", "")
        not_after = cert_dict.get("notAfter", "")
        san_list = []
        for ext in cert_dict.get("subjectAltName", []):
            san_list.append(f"{ext[0]}: {ext[1]}")
        try:
            expire_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_left = (expire_dt - now).days
        except Exception:
            days_left = None
        lines = []
        lines.append("=== TLS 证书信息 ===")
        lines.append(f"目标: {target}:{req.port}")
        lines.append(f"颁发给(CN): {subject.get('commonName', '-')}")
        lines.append(f"颁发机构(O): {issuer.get('organizationName', '-')}")
        lines.append(f"颁发机构(CN): {issuer.get('commonName', '-')}")
        lines.append(f"序列号: {cert_dict.get('serialNumber', '-')}")
        lines.append(f"生效时间: {not_before}")
        lines.append(f"过期时间: {not_after}")
        if days_left is not None:
            tag = "正常" if days_left > 0 else "已过期"
            lines.append(f"剩余天数: {days_left} 天 ({tag})")
        if san_list:
            lines.append("SAN 备用名称:")
            for s in san_list[:20]:
                lines.append(f"  {s}")
        lines.append(f"证书版本: v{cert_dict.get('version', '?')}")
        return {
            "success": True,
            "output": "\n".join(lines),
            "days_left": days_left,
            "issuer": issuer.get('organizationName', ''),
            "subject_cn": subject.get('commonName', ''),
            "not_before": not_before,
            "not_after": not_after,
        }
    except socket.timeout:
        return {"success": False, "output": "连接超时"}
    except socket.gaierror:
        return {"success": False, "output": "域名解析失败"}
    except Exception as e:
        return {"success": False, "output": f"执行异常: {e}"}


# ── IP 归属地查询 ──

class IpLocationRequest(BaseModel):
    target: str = Field(..., description="IP 地址或域名")


@router.post("/ip-location")
def ip_location(req: IpLocationRequest):
    target = _validate_target(req.target)
    _check_rate(f"iploc:{target}")
    _log_action("ip-location", target)
    try:
        addrs = socket.getaddrinfo(target, None)
        ip = addrs[0][4][0]
    except Exception as e:
        return {"success": False, "output": f"域名解析失败: {e}"}
    if ":" in ip:
        return {"success": False, "output": f"IPv6 地址暂不支持归属地查询: {ip}", "ip": ip}
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp,org,as,query,timezone,lat,lon"
        req_obj = urllib.request.Request(url, headers={"User-Agent": "AIOps-NetworkTest/1.0"})
        resp = urllib.request.urlopen(req_obj, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "success":
            return {"success": False, "output": f"查询失败: {data.get('message', '未知错误')}", "ip": ip}
        lines = []
        lines.append("=== IP 归属地信息 ===")
        lines.append(f"IP 地址: {data.get('query', ip)}")
        lines.append(f"国家: {data.get('country', '-')}")
        lines.append(f"地区: {data.get('regionName', '-')}")
        lines.append(f"城市: {data.get('city', '-')}")
        lines.append(f"ISP: {data.get('isp', '-')}")
        lines.append(f"组织: {data.get('org', '-')}")
        lines.append(f"AS 号: {data.get('as', '-')}")
        lines.append(f"时区: {data.get('timezone', '-')}")
        lines.append(f"经纬度: {data.get('lat', '-')}, {data.get('lon', '-')}")
        return {
            "success": True,
            "output": "\n".join(lines),
            "ip": data.get("query", ip),
            "country": data.get("country", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "isp": data.get("isp", ""),
        }
    except Exception as e:
        return {"success": False, "output": f"查询异常: {e}", "ip": ip}
