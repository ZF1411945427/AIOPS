"""
AIOps 服务器一键重启脚本 — 重启 39.96.51.45 上的后端服务

服务器部署模式下, Web 前端 + Mobile 前端均为构建好的静态文件,
由后端 FastAPI 8000 端口统一服务, 故只需重启一个后端进程即可恢复全部访问。

用法:
  python tools/restart.py           # 重启后端 (杀旧进程 → 启动 → 等待 → 验证)
  python tools/restart.py status    # 查看后端运行状态
  python tools/restart.py logs      # 查看后端日志尾部 (默认 40 行)
  python tools/restart.py logs 100  # 查看后端日志尾部 100 行

访问地址:
  Web    -> http://39.96.51.45:8000/
  Mobile -> http://39.96.51.45:8000/mobile-app/
"""
import paramiko
import sys
import time
import socket

HOST = "39.96.51.45"
USER = "root"
PASSWORD = "A892wYxn"
REMOTE = "/data/AIOPS"
LOG_FILE = "/tmp/aiops_backend.log"
START_CMD = f"cd {REMOTE} && setsid python3 run.py > {LOG_FILE} 2>&1 & echo STARTED"
WAIT_TIMEOUT = 180
POLL_INTERVAL = 5


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    return ssh


def run(ssh, cmd, timeout=30):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    code = out.channel.recv_exit_status()
    return code, out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")


def cmd_restart():
    ssh = connect()
    try:
        log("killing old backend ...")
        run(ssh, "pkill -f '[p]ython.*run\\.py' 2>/dev/null", timeout=5)
        killed = False
        for w in range(8):
            time.sleep(2)
            _, out, _ = run(ssh, "ps -ef | grep '[p]ython.*run.py' | grep -v grep || echo CLEAN")
            if "CLEAN" in out:
                killed = True
                break
        if not killed:
            log("  graceful shutdown timed out, sending SIGKILL ...")
            run(ssh, "pkill -9 -f '[p]ython.*run\\.py' 2>/dev/null", timeout=5)
            time.sleep(2)
        for w in range(6):
            _, out, _ = run(ssh, "ss -tlnp | grep -q 8000 && echo BUSY || echo FREE")
            if "FREE" in out:
                break
            time.sleep(2)
        log(f"  old process stopped, port 8000 {'free' if 'FREE' in out else 'still busy?'}")

        log("starting backend ...")
        transport = ssh.get_transport()
        chan = transport.open_session()
        chan.exec_command(START_CMD)
        chan.settimeout(5)
        try:
            o = chan.recv(4096).decode()
            log(f"  {o.strip()}")
        except socket.timeout:
            log("  (started)")
        chan.close()

        log(f"waiting for backend (up to {WAIT_TIMEOUT}s, model loading ~10-30s) ...")
        ok = False
        for i in range(WAIT_TIMEOUT // POLL_INTERVAL):
            time.sleep(POLL_INTERVAL)
            _, out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ 2>&1", timeout=10)
            hc = out.strip()
            if hc in ("303", "200", "307", "301"):
                log(f"backend UP (HTTP {hc}) after {(i+1)*POLL_INTERVAL}s")
                ok = True
                break
            log(f"  ... {(i+1)*POLL_INTERVAL}s HTTP={hc}")

        if not ok:
            log("[ERROR] backend not responding, log tail:")
            _, out, _ = run(ssh, f"tail -40 {LOG_FILE} 2>&1", timeout=10)
            print(out)
            sys.exit(1)

        log("verifying endpoints ...")
        _, web, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/login 2>&1", timeout=10)
        _, mob, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/mobile-app/ 2>&1", timeout=10)
        log(f"  Web  (/login)        : HTTP {web.strip()}")
        log(f"  Mobile (/mobile-app/): HTTP {mob.strip()}")

        log("=== restart complete ===")
        print(f"  Web    -> http://{HOST}:8000/")
        print(f"  Mobile -> http://{HOST}:8000/mobile-app/")
    finally:
        ssh.close()


def cmd_status():
    ssh = connect()
    try:
        _, out, _ = run(ssh, "ps -ef | grep '[p]ython.*run.py' || echo 'NOT RUNNING'")
        print("=== backend process ===")
        print(out.strip())
        _, out, _ = run(ssh, "ss -tlnp | grep 8000 || echo 'port 8000 free'")
        print("\n=== port 8000 ===")
        print(out.strip())
        _, out, _ = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ 2>&1", timeout=10)
        print(f"\n=== HTTP probe ===\n{out.strip()}")
    finally:
        ssh.close()


def cmd_logs(n=40):
    ssh = connect()
    try:
        _, out, _ = run(ssh, f"tail -{n} {LOG_FILE} 2>&1", timeout=10)
        print(out)
    finally:
        ssh.close()


def usage():
    print("Usage: python tools/restart.py [command] [args]")
    print()
    print("Commands:")
    print("  (none)    restart backend (kill -> start -> wait -> verify)")
    print("  status    show backend process / port / HTTP probe")
    print("  logs [N]  show last N lines of backend log (default 40)")
    sys.exit(1)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "restart"
    if arg == "restart":
        cmd_restart()
    elif arg == "status":
        cmd_status()
    elif arg == "logs":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        cmd_logs(n)
    else:
        usage()
