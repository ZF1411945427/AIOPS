import base64
import hashlib
import json
import os
import platform
import subprocess
import time
import uuid
from datetime import datetime, date, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmoJ21Zauv5BAcGTSQnHD
94thzmdeEFYNf1rpauZDmOjGjSYUm9OdVwxtl+3Gw5Y9YKGDUCl3IREa33NnpOsu
PO+LteAdhUDmWCmH+UPI4FS0+ZfNMCIowqYzzVANI2iZprzKa11wHMBsOvwkw4Hf
oHGEs3bvKRjDU92aodAUYdc2G5g63j1C+E/NqkDeqfwcoVFwFPWdHv0R3ggGIQVS
g6l3UkE2IJb1cDD90jmFytIRArSdCpoYkjfHvUQhzV/E84sFbWRMKnbC9lxi36W4
PozJ6NGE9U8gfRzXy+z164Fq+2H3aOnk5HkSEEADd23ew4qoYvAQOeHNso5BcE6H
vQIDAQAB
-----END PUBLIC KEY-----"""


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LICENSE_FILE = os.path.join(_PROJECT_ROOT, "license.lic")
STATE_DIR = os.path.join(_PROJECT_ROOT, "data")
STATE_FILE = os.path.join(STATE_DIR, "license_state.json")

CLOCK_TOLERANCE_SECONDS = 60
CACHE_TTL_SECONDS = 10

_cache = {"ts": 0.0, "result": None}

_LICENSE_PUBLIC_PREFIXES = (
    "/license",
    "/login",
    "/static",
    "/assets",
    "/vue-assets",
    "/product",
    "/api/menu",
    "/api/system/db-mode",
    "/api/system/db-switch",
    "/api/v1/traces",
)


def _load_public_key():
    return serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode("utf-8"))


def _collect_mac():
    try:
        node = uuid.getnode()
        return format(node, "012x")
    except Exception:
        return "00"


def _collect_cpu():
    try:
        proc = platform.processor() or ""
        if proc:
            return proc.strip()
    except Exception:
        pass
    if os.name == "posix":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    try:
        return platform.machine() or "unknown"
    except Exception:
        return "unknown"


def _collect_disk():
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["wmic", "diskdrive", "get", "serialnumber"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip() and l.lower() != "serialnumber"]
            if lines:
                return "|".join(lines)
        except Exception:
            pass
    else:
        try:
            out = subprocess.run(
                ["lsblk", "-dno", "SERIAL"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
            if lines:
                return "|".join(lines)
        except Exception:
            pass
    return "unknown"


def get_machine_fingerprint() -> str:
    mac = _collect_mac()
    cpu = _collect_cpu()
    disk = _collect_disk()
    host = platform.node() or "unknown"
    raw = f"{mac}|{cpu}|{disk}|{host}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _verify_signature(payload_bytes: bytes, signature: bytes) -> bool:
    try:
        public_key = _load_public_key()
        public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def parse_license(license_text: str) -> dict:
    if not license_text:
        return {"valid": False, "reason": "授权文件为空", "payload": None}
    text = license_text.strip()
    if "." not in text:
        return {"valid": False, "reason": "授权文件格式错误", "payload": None}
    payload_b64, sig_b64 = text.split(".", 1)
    try:
        payload_bytes = base64.b64decode(payload_b64)
        signature = base64.b64decode(sig_b64)
    except Exception:
        return {"valid": False, "reason": "授权文件Base64解码失败", "payload": None}
    if not _verify_signature(payload_bytes, signature):
        return {"valid": False, "reason": "授权签名验证失败（许可证可能被篡改或伪造）", "payload": None}
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return {"valid": False, "reason": "授权内容JSON解析失败", "payload": None}
    return {"valid": True, "reason": "ok", "payload": payload}


def _read_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _write_state(data: dict) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _clock_rollback_check() -> tuple[bool, str]:
    state = _read_state()
    last_str = state.get("last_check_time")
    now = datetime.now()
    if last_str:
        try:
            last = datetime.fromisoformat(last_str)
            if now < last - timedelta(seconds=CLOCK_TOLERANCE_SECONDS):
                return False, f"检测到系统时钟回拨（当前 {now.isoformat()} < 上次记录 {last.isoformat()}）"
        except Exception:
            pass
    state["last_check_time"] = now.isoformat()
    _write_state(state)
    return True, "ok"


def _parse_expire(expire_at) -> date | None:
    if not expire_at:
        return None
    try:
        return datetime.strptime(str(expire_at)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def check_license() -> dict:
    now_ts = time.time()
    if _cache["result"] is not None and (now_ts - _cache["ts"]) < CACHE_TTL_SECONDS:
        return _cache["result"]

    fingerprint = get_machine_fingerprint()
    base = {
        "valid": False,
        "status": "invalid",
        "info": None,
        "remaining_days": 0,
        "reason": "未授权",
        "fingerprint": fingerprint,
    }

    if not os.path.exists(LICENSE_FILE):
        result = {**base, "status": "invalid", "reason": "未找到授权文件，请上传许可证"}
        _cache.update({"ts": now_ts, "result": result})
        return result

    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            license_text = f.read()
    except Exception as e:
        result = {**base, "status": "invalid", "reason": f"授权文件读取失败: {e}"}
        _cache.update({"ts": now_ts, "result": result})
        return result

    parsed = parse_license(license_text)
    if not parsed["valid"]:
        result = {**base, "status": "invalid", "reason": parsed["reason"]}
        _cache.update({"ts": now_ts, "result": result})
        return result

    payload = parsed["payload"]

    expire_date = _parse_expire(payload.get("expire_at"))
    today = date.today()
    if expire_date is None:
        result = {**base, "status": "invalid", "reason": "授权文件缺少到期时间", "info": payload}
        _cache.update({"ts": now_ts, "result": result})
        return result

    remaining = (expire_date - today).days
    if remaining < 0:
        ok_clock, _ = _clock_rollback_check()
        if not ok_clock:
            result = {**base, "status": "locked", "reason": "系统时钟异常", "info": payload}
        else:
            result = {
                **base,
                "status": "expired",
                "reason": f"授权已于 {expire_date.isoformat()} 到期",
                "info": payload,
                "remaining_days": 0,
            }
        _cache.update({"ts": now_ts, "result": result})
        return result

    ok_clock, clock_reason = _clock_rollback_check()
    if not ok_clock:
        result = {**base, "status": "locked", "reason": clock_reason, "info": payload}
        _cache.update({"ts": now_ts, "result": result})
        return result

    result = {
        "valid": True,
        "status": "active",
        "info": payload,
        "remaining_days": remaining,
        "reason": "ok",
        "fingerprint": fingerprint,
    }
    _cache.update({"ts": now_ts, "result": result})
    return result


def save_license(license_text: str) -> dict:
    parsed = parse_license(license_text)
    if not parsed["valid"]:
        return {"ok": False, "message": parsed["reason"], "info": None}
    payload = parsed["payload"]
    expire_date = _parse_expire(payload.get("expire_at"))
    if expire_date is None:
        return {"ok": False, "message": "授权文件缺少到期时间", "info": payload}
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(license_text.strip())
    except Exception as e:
        return {"ok": False, "message": f"授权文件保存失败: {e}", "info": None}
    _cache.update({"ts": 0.0, "result": None})
    return {"ok": True, "message": "授权文件上传成功", "info": payload}


def get_status() -> dict:
    result = check_license()
    info = result.get("info") or {}
    fingerprint = result.get("fingerprint", get_machine_fingerprint())
    return {
        "status": result.get("status", "invalid"),
        "valid": result.get("valid", False),
        "reason": result.get("reason", ""),
        "remaining_days": result.get("remaining_days", 0),
        "fingerprint": fingerprint,
        "fingerprint_masked": fingerprint[:8] + "..." if fingerprint else "",
        "customer": info.get("customer", ""),
        "edition": info.get("edition", ""),
        "issued_at": info.get("issued_at", ""),
        "expire_at": info.get("expire_at", ""),
        "max_nodes": info.get("max_nodes", 0),
        "features": info.get("features", []),
    }


def invalidate_cache():
    _cache.update({"ts": 0.0, "result": None})


class LicenseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _LICENSE_PUBLIC_PREFIXES):
            return await call_next(request)
        try:
            result = check_license()
        except Exception:
            return await call_next(request)
        status = result.get("status")
        if status == "active":
            return await call_next(request)
        if status == "expired":
            detail = "授权已过期，请联系管理员续期"
        elif status == "locked":
            detail = "授权校验失败：系统时钟异常，平台已锁定"
        else:
            detail = result.get("reason") or "授权无效，请上传有效许可证"
        return JSONResponse(
            status_code=403,
            content={"detail": detail, "license_status": status},
        )
