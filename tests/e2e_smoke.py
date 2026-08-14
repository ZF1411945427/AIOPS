"""端到端冒烟测试: 真实启动后端 + 打真实 API 端点。

对齐 ongrid e2e 思路 — 验证关键业务链路在真实进程下的行为,
而非单元级的 DB/网络 mock。

用法:
    python tests/e2e_smoke.py [port]

依赖: 后端 run.py 所在目录已包含 app/, 首次会自动建 SQLite 库并种 admin。
"""
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HOME = os.path.dirname(PROJECT_ROOT)
HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8011
BASE = f"http://{HOST}:{PORT}"
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 优先使用项目 venv 的解释器, 避免误用系统/外部 venv
_VENV_PY = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
PYTHON = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable

_PASS = 0
_FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def http_json(path, token=None, method="GET", data=None, timeout=20):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
        req.data = body
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, text
    return status, text


def wait_port(host, port, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def stop(proc):
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass


def main():
    proc = None
    try:
        log_f = open(os.path.join(LOG_DIR, "_e2e_backend.log"), "w", encoding="utf-8")
        env = dict(os.environ)
        env["AIOPS_LOG_DIR"] = LOG_DIR
        env["PORT"] = str(PORT)
        proc = subprocess.Popen(
            [PYTHON, "run.py"],
            cwd=PROJECT_ROOT,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
        )
        if not wait_port(HOST, PORT):
            print("FATAL: backend did not start in time")
            sys.exit(2)

        # ── 1. 健康检查 ──
        status, body = http_json("/healthz")
        check("healthz returns 200", status == 200, f"got {status}")

        # ── 2. 登录(JSON)──
        status, body = http_json("/login", method="POST",
                                 data={"username": "admin", "password": os.environ.get("AIOPS_ADMIN_PASSWORD", "admin123")})
        check("login returns token", status == 200 and body.get("ok") and body.get("token"), f"got {status} body={str(body)[:100]}")
        token = body.get("token", "")

        # ── 3. 核心系统端点 ──
        status, body = http_json("/api/system/overview", token=token)
        check("system overview 200", status == 200, f"got {status}")

        status, body = http_json("/api/system/reload-menu", token=token)
        check("reload-menu 200", status == 200 and body.get("status") == "ok", f"got {status} body={str(body)[:100]}")

        # ── 4. 资产/监控 ──
        status, body = http_json("/assets/api/list", token=token)
        check("assets list 200", status == 200, f"got {status}")

        # ── 5. SLO ──
        status, body = http_json("/api/sre/slo", token=token)
        check("slo 200", status == 200, f"got {status}")

        # ── 6. 观测/关联分析 ──
        status, body = http_json("/observability/correlation/analyze", token=token)
        check("correlation analyze 200", status == 200, f"got {status}")

        # ── 7. Agent 端点(可能较重, 容错)──
        try:
            status, body = http_json("/agent/chat/send", token=token, method="POST",
                                     data={"message": "你好", "stream": False})
            check("agent chat reachable", status in (200, 201, 422, 401), f"got {status}")
        except Exception as ex:
            check("agent chat reachable", False, f"ex={ex}")

        print(f"\nE2E SMOKE RESULT: {_PASS} passed, {_FAIL} failed")
        sys.exit(1 if _FAIL else 0)
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
