"""
AIOps 部署脚本 — 一键部署后端 + Web 前端 + Mobile 前端到 39.96.51.45

用法:
  python tools/deploy.py all       # 全量部署（备份 + 代码 + 依赖 + 重启）
  python tools/deploy.py backend   # 仅后端（app/ run.py requirements_lock.txt + pip + 重启）
  python tools/deploy.py frontend  # 仅 Web 前端（frontend/dist/）
  python tools/deploy.py mobile    # 仅移动端（mobile/dist/build/h5/）
  python tools/deploy.py web       # Web + Mobile 两个前端一起更新
"""
import paramiko
import os
import sys
import time
import tarfile
import socket

HOST = "39.96.51.45"
USER = "root"
PASSWORD = "A892wYxn"
REMOTE_PATH = "/data/AIOPS"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP_TAR = "/tmp/aiops_deploy.tar"

PIP_MIRROR = "-i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn"

WINDOWS_ONLY_PKGS = {"pywin32", "win32_setctime"}

BACKUP_EXCLUDES = [
    "models", "bin", "node_modules", ".git", "__pycache__",
    "logs", ".opencode", ".vscode", "tests",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ── SSH helpers ──────────────────────────────────────────────

def _connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    return ssh


def _run(ssh, cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=True)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err


def _upload(ssh, local_path, remote_path):
    size_mb = os.path.getsize(local_path) / 1024 / 1024
    log(f"uploading {os.path.basename(local_path)} ({size_mb:.1f} MB) ...")
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    log("upload done")


# ── Requirements filtering ───────────────────────────────────

def _filter_requirements(local_path):
    """过滤 requirements_lock.txt，生成服务器兼容版本（排除 Windows 专属包 + torch GPU 锁版本）"""
    filtered = []
    skipped = []
    with open(local_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                filtered.append(line)
                continue
            pkg_name = stripped.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip().lower()
            if pkg_name in WINDOWS_ONLY_PKGS:
                skipped.append(stripped)
                continue
            filtered.append(line)
    if skipped:
        log(f"  filtered out Windows-only: {', '.join(skipped)}")
    return "".join(filtered)


# ── Step helpers ─────────────────────────────────────────────

def _step_backup(ssh):
    """轻量备份 — 排除 models/bin/node_modules/.git/logs 等大目录"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = f"/data/AIOPS.bak.{ts}.tar.gz"
    exclude_args = " ".join(f"--exclude={e}" for e in BACKUP_EXCLUDES)
    log(f"backing up -> {bak} (lightweight)")
    code, out, err = _run(
        ssh,
        f"cd /data && tar -czf {bak} {exclude_args} AIOPS/ 2>&1 && echo BACKUP_OK",
        timeout=120,
    )
    if "BACKUP_OK" not in out:
        log(f"[WARN] backup may have failed: {err[:200]}")
    else:
        code, out, err = _run(ssh, f"ls -lh {bak} 2>&1", timeout=10)
        log(f"backup done: {out.strip().split()[-2] if out else '?'}")


def _step_extract(ssh, strip_prefix=None):
    cmd = f"tar -xf {TMP_TAR} -C {REMOTE_PATH}/"
    if strip_prefix:
        cmd += f" --strip-components={strip_prefix}"
    cmd += f" && rm -f {TMP_TAR} && echo EXTRACT_OK"
    code, out, err = _run(ssh, cmd, timeout=120)
    if "EXTRACT_OK" not in out:
        log(f"[ERROR] extract failed: {err}")
        sys.exit(1)
    log("extract done")


def _step_pip_install(ssh):
    """安装依赖 — 清华镜像 + 过滤后的 requirements_lock.txt"""
    log("preparing requirements ...")
    req_local = os.path.join(PROJECT_ROOT, "requirements_lock.txt")
    if not os.path.exists(req_local):
        log(f"[ERROR] {req_local} not found")
        sys.exit(1)

    filtered = _filter_requirements(req_local)
    sftp = ssh.open_sftp()
    with sftp.file(f"{REMOTE_PATH}/requirements_server.txt", "w") as f:
        f.write(filtered)
    sftp.close()
    log(f"  uploaded requirements_server.txt ({len(filtered)} bytes)")

    log("pip install (this may take several minutes) ...")
    code, out, err = _run(
        ssh,
        f"cd {REMOTE_PATH} && pip3 install {PIP_MIRROR} -r requirements_server.txt 2>&1 | tail -20",
        timeout=600,
    )
    if "Successfully installed" in out or "already satisfied" in out:
        log("pip install done")
    else:
        log(f"[WARN] pip install may have issues. Last output:")
        log(out[-500:])

    code, out, err = _run(
        ssh,
        f'cd {REMOTE_PATH} && pip3 install {PIP_MIRROR} "starlette==0.41.3" "sse-starlette<3.4" 2>&1 | tail -5',
        timeout=120,
    )
    log("starlette version pinned")


def _step_restart(ssh):
    """重启后端 — 轮询等待模型加载完成"""
    log("restarting backend ...")
    _run(ssh, f"pkill -f '[p]ython.*run\\.py' 2>/dev/null", timeout=5)
    time.sleep(2)

    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.exec_command(f"cd {REMOTE_PATH} && setsid python3 run.py > /tmp/aiops_backend.log 2>&1 & echo STARTED")
    chan.settimeout(5)
    try:
        out = chan.recv(4096).decode()
        log(f"start: {out.strip()}")
    except socket.timeout:
        pass
    chan.close()

    log("waiting for backend to start (model loading takes ~30s) ...")
    for i in range(12):
        time.sleep(5)
        code, out, err = _run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ 2>&1", timeout=10)
        http_code = out.strip()
        if http_code in ("303", "200"):
            log(f"backend running (HTTP {http_code}) after {(i+1)*5}s")
            return
        log(f"  ... waiting ({(i+1)*5}s, HTTP={http_code})")

    log("[WARN] backend not responding, checking log...")
    code, out, err = _run(ssh, "tail -20 /tmp/aiops_backend.log 2>&1", timeout=10)
    log(out.strip())


# ── Tar builders ────────────────────────────────────────────

def _make_tar(patterns, tar_name="aiops_deploy.tar"):
    path = os.path.join(PROJECT_ROOT, tar_name)
    if os.path.exists(path):
        os.remove(path)
    log(f"building {tar_name} ...")
    with tarfile.open(path, "w") as tf:
        for pattern in patterns:
            full = os.path.join(PROJECT_ROOT, pattern)
            if not os.path.exists(full):
                log(f"  [skip] {pattern} not found")
                continue
            tf.add(full, arcname=pattern)
    log(f"  -> {os.path.getsize(path)/1024/1024:.1f} MB")
    return path


def _make_full_tar():
    """全量打包 — 排除大目录和服务器数据（db/ 由服务器维护，不覆盖）"""
    excludes = {
        "node_modules", ".git", "__pycache__", ".vscode", ".opencode",
        "nul", "aiops_deploy.tar", "bin", "models",
        "功能测试", "projects",
        "db", "logs", "tests",
    }
    path = os.path.join(PROJECT_ROOT, "aiops_deploy.tar")
    if os.path.exists(path):
        os.remove(path)
    log("building full tar ...")
    with tarfile.open(path, "w") as tf:
        for entry in os.listdir(PROJECT_ROOT):
            if entry in excludes or entry.startswith("."):
                continue
            full = os.path.join(PROJECT_ROOT, entry)
            try:
                tf.add(full, arcname=entry)
            except Exception as e:
                log(f"  [warn] {entry}: {e}")
    log(f"  -> {os.path.getsize(path)/1024/1024:.1f} MB")
    return path


# ── Subcommands ─────────────────────────────────────────────

def cmd_all():
    """Full deploy: everything → backup → extract → pip → restart"""
    tar = _make_full_tar()
    ssh = _connect()
    try:
        _upload(ssh, tar, TMP_TAR)
        _step_backup(ssh)
        _step_extract(ssh)
        _step_pip_install(ssh)
        _step_restart(ssh)
    finally:
        ssh.close()
    log("=== full deploy complete ===")


def cmd_backend():
    """Backend only: app/ run.py requirements_lock.txt → pip → restart"""
    tar = _make_tar(["app", "run.py", "requirements_lock.txt"], "backend_deploy.tar")
    ssh = _connect()
    try:
        _upload(ssh, tar, TMP_TAR)
        _step_extract(ssh)
        _step_pip_install(ssh)
        _step_restart(ssh)
    finally:
        ssh.close()
    log("=== backend deploy complete ===")


def cmd_frontend():
    """Frontend only: frontend/dist/"""
    tar = _make_tar(["frontend/dist"], "frontend_deploy.tar")
    ssh = _connect()
    try:
        _upload(ssh, tar, TMP_TAR)
        _run(ssh, f"rm -rf {REMOTE_PATH}/frontend/dist 2>/dev/null")
        _step_extract(ssh)
        log("frontend updated (no restart needed)")
    finally:
        ssh.close()
    log("=== frontend deploy complete ===")


def cmd_mobile():
    """Mobile only: mobile/dist/build/h5/"""
    tar = _make_tar(["mobile/dist/build/h5"], "mobile_deploy.tar")
    ssh = _connect()
    try:
        _upload(ssh, tar, TMP_TAR)
        _run(ssh, f"rm -rf {REMOTE_PATH}/mobile/dist/build/h5 2>/dev/null")
        _step_extract(ssh)
        log("mobile updated (no restart needed)")
    finally:
        ssh.close()
    log("=== mobile deploy complete ===")


def cmd_web():
    """Web + Mobile 两个前端一起更新"""
    frontend_tar = _make_tar(["frontend/dist"], "frontend_deploy.tar")
    mobile_tar = _make_tar(["mobile/dist/build/h5"], "mobile_deploy.tar")
    ssh = _connect()
    try:
        _upload(ssh, frontend_tar, "/tmp/frontend_deploy.tar")
        _upload(ssh, mobile_tar, "/tmp/mobile_deploy.tar")
        _run(ssh, f"rm -rf {REMOTE_PATH}/frontend/dist 2>/dev/null")
        _run(ssh, f"rm -rf {REMOTE_PATH}/mobile/dist/build/h5 2>/dev/null")
        _run(ssh, f"tar -xf /tmp/frontend_deploy.tar -C {REMOTE_PATH}/ && rm -f /tmp/frontend_deploy.tar && echo OK1", timeout=60)
        _run(ssh, f"tar -xf /tmp/mobile_deploy.tar -C {REMOTE_PATH}/ && rm -f /tmp/mobile_deploy.tar && echo OK2", timeout=60)
        log("web + mobile updated (no restart needed)")
    finally:
        ssh.close()
    log("=== web deploy complete ===")


# ── Entry ────────────────────────────────────────────────────

def usage():
    print("Usage: python tools/deploy.py <command>")
    print()
    print("Commands:")
    print("  all       — full deploy (backup + code + pip + restart)")
    print("  backend   — backend only (app/ run.py + pip + restart)")
    print("  frontend  — Web frontend only (frontend/dist/)")
    print("  mobile    — Mobile frontend only (mobile/dist/build/h5/)")
    print("  web       — Web + Mobile together (both frontends)")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
    cmds = {
        "all": cmd_all,
        "backend": cmd_backend,
        "frontend": cmd_frontend,
        "mobile": cmd_mobile,
        "web": cmd_web,
    }
    fn = cmds.get(sys.argv[1])
    if fn is None:
        usage()
    else:
        fn()
