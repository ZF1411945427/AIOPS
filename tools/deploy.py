import paramiko
import os
import sys
import time
import tarfile
import shutil

HOST = "39.96.51.45"
USER = "root"
PASSWORD = "A892wYxn"
REMOTE_PATH = "/data/AIOPS"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP_TAR = "/tmp/aiops_deploy.tar"


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
    log(f"uploading {local_path} ({os.path.getsize(local_path)/1024/1024:.1f} MB) ...")
    sftp = ssh.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()
    log("upload done")


# ── Step helpers ─────────────────────────────────────────────

def _step_backup(ssh):
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = f"/data/AIOPS.bak.{ts}.tar.gz"
    log(f"backing up -> {bak}")
    code, out, err = _run(ssh, f"cd /data && tar -czf {bak} AIOPS/ 2>&1", timeout=120)
    if err.strip():
        log(f"backup stderr: {err}")
    log("backup done")


def _step_extract(ssh, strip_prefix=None):
    cmd = f"tar -xf {TMP_TAR} -C {REMOTE_PATH}/"
    if strip_prefix:
        cmd += f" --strip-components={strip_prefix}"
    cmd += f" && rm -f {TMP_TAR} && echo EXTRACT_OK"
    code, out, err = _run(ssh, cmd, timeout=60)
    if "EXTRACT_OK" not in out:
        log(f"[ERROR] extract failed: {err}")
        sys.exit(1)
    log("extract done")


def _step_pip_install(ssh):
    log("pip install ...")
    code, out, err = _run(ssh, f"cd {REMOTE_PATH} && pip3 install -r requirements.txt 2>&1 | tail -5", timeout=180)
    if err.strip():
        log(f"pip stderr: {err}")
    log("pip done")


def _step_restart(ssh):
    log("restarting backend ...")
    _run(ssh, f"pkill -f '[p]ython.*run\\.py' 2>/dev/null", timeout=5)
    time.sleep(2)
    # Start backend in background — don't use _run (get_pty=True kills bg processes)
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.exec_command(f"cd {REMOTE_PATH} && setsid python3 run.py > /tmp/aiops_backend.log 2>&1 & echo STARTED")
    import socket
    chan.settimeout(5)
    try:
        out = chan.recv(4096).decode()
        log(f"start: {out.strip()}")
    except socket.timeout:
        pass
    chan.close()
    time.sleep(5)
    code, out, err = _run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/", timeout=10)
    log(f"verify HTTP {out.strip()}")
    if out.strip() in ("303", "200"):
        log("backend running")
    else:
        log("[WARN] checking log...")
        code, out, err = _run(ssh, "tail -10 /tmp/aiops_backend.log 2>&1", timeout=5)
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
    excludes = {"node_modules", ".git", "__pycache__", ".vscode", ".opencode", "nul", "aiops_deploy.tar"}
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
    """Full deploy: everything → backup all → extract all → pip → restart"""
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


def cmd_backend():
    """Backend only: app/ run.py requirements.txt → pip → restart (excludes bin/ with large helm binaries)"""
    tar = _make_tar(["app", "run.py", "requirements.txt"], "backend_deploy.tar")
    ssh = _connect()
    try:
        _upload(ssh, tar, TMP_TAR)
        _step_extract(ssh)
        _step_pip_install(ssh)
        _step_restart(ssh)
    finally:
        ssh.close()


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


# ── Entry ────────────────────────────────────────────────────

def usage():
    print("Usage: python tools/deploy.py <command>")
    print("  all       — full deploy (backup + all components + pip + restart)")
    print("  backend   — backend only (app/ run.py requirements.txt + pip + restart)")
    print("  frontend  — frontend only (frontend/dist/ static files)")
    print("  mobile    — mobile only (mobile/dist/build/h5/ static files)")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
    cmds = {"all": cmd_all, "backend": cmd_backend, "frontend": cmd_frontend, "mobile": cmd_mobile}
    fn = cmds.get(sys.argv[1])
    if not fn:
        usage()
    fn()
