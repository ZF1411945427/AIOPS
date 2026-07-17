"""
BackgroundTaskRunner - 后台异步任务执行器
支持长耗时任务（如 SSH 安装、部署），不受 LLM timeout 约束。
LLM 通过 get_task_status 轮询任务进度。
"""

import uuid
import json
import time
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import BackgroundJob, Asset


# ─── 全局线程池执行器 ───────────────────────────────────────────────

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="bg_task_")
_running_tasks: Dict[str, Future] = {}  # job_id -> Future
_tasks_lock = threading.Lock()


# ─── 任务进度更新 ───────────────────────────────────────────────────

def _update_job(job_id: str, status: str = None, progress: int = None,
                progress_message: str = None, result: Dict = None, error: str = None):
    """更新后台任务状态（线程安全）"""
    db = get_session_for(get_db_mode())()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()
        if not job:
            return
        if status:
            job.status = status
        if progress is not None:
            job.progress = progress
        if progress_message is not None:
            job.progress_message = progress_message
        if result is not None:
            job.result_payload = json.dumps(result, ensure_ascii=False)
        if error is not None:
            job.error_message = error
        if status == "running" and not job.started_at:
            job.started_at = datetime.now()
        if status in ("success", "failed", "canceled"):
            job.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()


# ─── SSH 远程执行封装 ──────────────────────────────────────────────

def _remote_exec_ssh(ip: str, user: str, password: str, port: int, command: str, timeout: int = 300) -> tuple:
    """
    通过 SSH 在远程主机执行命令，返回 (success: bool, output: str)
    timeout 单位秒，默认 5 分钟（安装类任务需要）
    """
    import paramiko

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=password, port=port, timeout=30, banner_timeout=30)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        client.close()
        return (exit_status == 0, output + ("\n[STDERR]\n" + err if err else ""))
    except Exception as e:
        return (False, str(e))


# ─── 安装执行函数 ──────────────────────────────────────────────────

def _detect_os(ip: str, user: str, password: str, port: int) -> str:
    """检测操作系统类型"""
    success, output = _remote_exec_ssh(ip, user, password, port, "cat /etc/os-release", timeout=30)
    if not success:
        return "unknown"
    output_lower = output.lower()
    if "ubuntu" in output_lower or "debian" in output_lower:
        return "debian"
    if "centos" in output_lower or "rhel" in output_lower or "rocky" in output_lower or "almalinux" in output_lower:
        return "rhel"
    if "alpine" in output_lower:
        return "alpine"
    if "amzn" in output_lower:  # Amazon Linux
        return "amzn"
    return "unknown"


def _exec_steps(job_id: str, ip: str, user: str, password: str, port: int,
                package_name: str, version: str, options: Dict) -> Dict:
    """
    分步执行安装，每步记录补偿命令。
    失败时逆序执行回滚（补偿式回滚 / Saga Pattern）。
    """
    # 每步记录：(step_name, commit_cmds[], rollback_cmds[])
    # 回滚时逆序执行 rollback_cmds
    steps_log = []  # {"name": str, "status": str, "commit": [], "rollback": []}
    os_type = options.get("os_type", "auto")
    install_type = options.get("install_type", "binary")
    extra_packages = options.get("extra_packages", [])
    start_service = options.get("start_service", True)

    def _run_cmds(cmds: list, step_name: str) -> tuple:
        """执行一组命令，全部成功返回 True"""
        for cmd in cmds:
            ok, out = _remote_exec_ssh(ip, user, password, port, cmd, timeout=300)
            if not ok:
                return False, f"命令失败 [{cmd}]: {out[:100]}"
        return True, ""

    def _rollback():
        """逆序执行所有已成功步骤的回滚命令"""
        _update_job(job_id, progress_message="⚠️ 执行回滚...")
        rollback_results = []
        for step in reversed(steps_log):
            if step["status"] != "committed":
                continue
            step_name = step["name"]
            for rb_cmd in step.get("rollback", []):
                if not rb_cmd:
                    continue
                ok, out = _remote_exec_ssh(ip, user, password, port, rb_cmd, timeout=120)
                rollback_results.append(f"  回滚 {step_name}: {'✓' if ok else '✗ ' + out[:60]}")
        return rollback_results

    # ─── Step 1: 检测 OS ───────────────────────────────────────────
    _update_job(job_id, status="running", progress=5, progress_message="检测操作系统类型...")
    if os_type == "auto":
        detected = _detect_os(ip, user, password, port)
        os_type = detected if detected != "unknown" else "debian"
    steps_log.append({
        "name": f"检测OS({os_type})",
        "status": "committed",
        "commit": [],
        "rollback": [],
    })
    _update_job(job_id, progress=10, progress_message=f"操作系统: {os_type}")

    # ─── Step 2: 安装依赖 ──────────────────────────────────────────
    _update_job(job_id, progress=15, progress_message="安装系统依赖...")
    dep_cmds = []
    rollback_dep = []
    if os_type in ("debian", "amzn"):
        dep_cmds = ["apt-get update -qq", "apt-get install -y -qq openjdk-17-jdk wget curl gnupg ca-certificates"]
        rollback_dep = ["apt-get remove -y openjdk-17-jdk wget curl 2>/dev/null || true"]
    else:
        dep_cmds = ["yum install -y java-17-openjdk wget curl"]
        rollback_dep = ["yum remove -y java-17-openjdk wget curl 2>/dev/null || true"]
    ok, err = _run_cmds(dep_cmds, "安装依赖")
    if not ok:
        rollback_results = _rollback()
        _update_job(job_id, status="failed", progress=0,
                    progress_message="安装依赖失败，已回滚",
                    error=f"依赖安装失败: {err}",
                    result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
        return
    steps_log.append({"name": "安装依赖", "status": "committed", "commit": dep_cmds, "rollback": rollback_dep})
    _update_job(job_id, progress=25)

    # ─── Step 3: 下载并安装 ES ─────────────────────────────────────
    if package_name in ("elasticsearch", "es"):
        _update_job(job_id, progress=30, progress_message=f"下载 Elasticsearch {version}...")

        if os_type in ("debian",):
            es_dir = f"/opt/elasticsearch-{version}"
            es_short = "/opt/elasticsearch"
            es_url = f"https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-{version}-linux-x86_64.tar.gz"
            install_cmds = [
                f"cd /tmp && wget -q '{es_url}' -O elasticsearch.tar.gz",
                f"tar -xzf /tmp/elasticsearch.tar.gz -C /opt/",
                f"mv {es_dir} {es_short}",
                f"useradd -M -s /sbin/nologin elasticsearch 2>/dev/null || true",
                f"chown -R elasticsearch:elasticsearch {es_short}",
                f"mkdir -p {es_short}/data {es_short}/logs",
                f"chown elasticsearch:elasticsearch {es_short}/data",
            ]
            rollback_cmds = [
                f"systemctl stop elasticsearch 2>/dev/null || true",
                f"rm -rf {es_short}",
                f"rm -f /tmp/elasticsearch.tar.gz",
                f"userdel elasticsearch 2>/dev/null || true",
            ]
        else:
            es_dir = f"/opt/elasticsearch-{version}"
            es_short = "/opt/elasticsearch"
            es_url = f"https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-{version}-linux-x86_64.tar.gz"
            install_cmds = [
                f"cd /tmp && wget -q '{es_url}' -O elasticsearch.tar.gz",
                f"tar -xzf /tmp/elasticsearch.tar.gz -C /opt/",
                f"mv {es_dir} {es_short}",
                f"useradd -M -s /sbin/nologin elasticsearch 2>/dev/null || true",
                f"chown -R elasticsearch:elasticsearch {es_short}",
                f"mkdir -p {es_short}/data {es_short}/logs",
            ]
            rollback_cmds = [
                f"systemctl stop elasticsearch 2>/dev/null || true",
                f"rm -rf {es_short}",
                f"rm -f /tmp/elasticsearch.tar.gz",
                f"userdel elasticsearch 2>/dev/null || true",
            ]

        ok, err = _run_cmds(install_cmds, "下载安装ES")
        if not ok:
            rollback_results = _rollback()
            _update_job(job_id, status="failed", progress=0,
                        progress_message="下载/安装 ES 失败，已回滚",
                        error=f"ES安装失败: {err}",
                        result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
            return
        steps_log.append({"name": "安装ES程序", "status": "committed", "commit": install_cmds, "rollback": rollback_cmds})
        _update_job(job_id, progress=50)

        # ─── Step 4: 配置 ES ─────────────────────────────────────
        _update_job(job_id, progress=60, progress_message="配置 Elasticsearch...")
        es_cfg = "bootstrap.memory_lock=true\nnetwork.host: 0.0.0.0\nhttp.port: 9200\ndiscovery.type: single-node\nxpack.security.enabled: false\nES_JAVA_OPTS=-Xms512m -Xmx512m\n"
        cfg_cmd = f"cat > /opt/elasticsearch/config/elasticsearch.yml << 'EOF'\n{es_cfg}EOF"
        ok, err = _remote_exec_ssh(ip, user, password, port, cfg_cmd, timeout=30)
        if not ok:
            rollback_results = _rollback()
            _update_job(job_id, status="failed", progress=0,
                        progress_message="配置 ES 失败，已回滚",
                        error=f"ES配置写入失败: {err}",
                        result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
            return
        steps_log.append({"name": "配置ES", "status": "committed",
                          "commit": [cfg_cmd],
                          "rollback": ["rm -f /opt/elasticsearch/config/elasticsearch.yml"]})
        _update_job(job_id, progress=70)

        # ─── Step 5: 配置 systemd ─────────────────────────────────
        _update_job(job_id, progress=75, progress_message="配置 systemd 服务...")
        svc_content = """[Unit]\nDescription=Elasticsearch\nAfter=network.target\n\n[Service]\nType=simple\nUser=root\nWorkingDirectory=/opt/elasticsearch\nExecStart=/opt/elasticsearch/bin/elasticsearch\nRestart=on-failure\n\n[Install]\nWantedBy=multi-user.target\n"""
        svc_cmd = f"cat > /etc/systemd/system/elasticsearch.service << 'EOF'\n{svc_content}EOF"
        ok, err = _remote_exec_ssh(ip, user, password, port, svc_cmd, timeout=30)
        if not ok:
            rollback_results = _rollback()
            _update_job(job_id, status="failed", progress=0,
                        progress_message="systemd 配置失败，已回滚",
                        error=f"systemd配置失败: {err}",
                        result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
            return
        steps_log.append({"name": "配置systemd", "status": "committed",
                          "commit": [svc_cmd],
                          "rollback": ["rm -f /etc/systemd/system/elasticsearch.service", "systemctl daemon-reload"]})
        _update_job(job_id, progress=80)

        # ─── Step 6: 启动 ES ─────────────────────────────────────
        if start_service:
            _update_job(job_id, progress=85, progress_message="启动 Elasticsearch...")
            start_cmds = [
                "systemctl daemon-reload",
                "systemctl enable elasticsearch",
                "systemctl start elasticsearch",
            ]
            rollback_start = [
                "systemctl stop elasticsearch 2>/dev/null || true",
                "systemctl disable elasticsearch 2>/dev/null || true",
            ]
            ok, err = _run_cmds(start_cmds, "启动ES")
            if not ok:
                rollback_results = _rollback()
                _update_job(job_id, status="failed", progress=0,
                            progress_message="启动 ES 失败，已回滚",
                            error=f"ES启动失败: {err}",
                            result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
                return
            steps_log.append({"name": "启动ES", "status": "committed", "commit": start_cmds, "rollback": rollback_start})
            _update_job(job_id, progress=92, progress_message="等待 ES 启动（10秒）...")
            _remote_exec_ssh(ip, user, password, port, "sleep 10", timeout=30)

            # 验证
            _update_job(job_id, progress=95, progress_message="验证 ES 运行状态...")
            ok, es_info = _remote_exec_ssh(ip, user, password, port, "curl -s http://localhost:9200 2>&1 | head -10", timeout=30)
            final_ok = ok and "cluster_name" in es_info
            final_status = "ES 运行正常 ✓" if final_ok else f"ES 启动但验证失败: {es_info[:100]}"
            if not final_ok:
                rollback_results = _rollback()
                _update_job(job_id, status="failed", progress=0,
                            progress_message="ES 验证失败，已回滚",
                            error=final_status,
                            result={"package": package_name, "os_type": os_type, "steps": steps_log, "rollback_results": rollback_results})
                return
            steps_log.append({"name": "验证ES", "status": "committed", "commit": [], "rollback": []})

    elif package_name == "nginx":
        _update_job(job_id, progress=40, progress_message="安装 Nginx...")
        if os_type == "debian":
            install_cmds = ["apt-get install -y nginx"]
            rollback_cmds = ["apt-get remove -y nginx"]
        else:
            install_cmds = ["yum install -y nginx"]
            rollback_cmds = ["yum remove -y nginx"]
        ok, err = _run_cmds(install_cmds, "安装Nginx")
        if not ok:
            rollback_results = _rollback()
            _update_job(job_id, status="failed", progress=0, progress_message="安装 Nginx 失败，已回滚", error=err, result={"rollback_results": rollback_results})
            return
        steps_log.append({"name": "安装Nginx", "status": "committed", "commit": install_cmds, "rollback": rollback_cmds})
        _update_job(job_id, progress=70)

        if start_service:
            _update_job(job_id, progress=80, progress_message="启动 Nginx...")
            start_cmds = ["systemctl enable nginx", "systemctl start nginx"]
            rollback_start = ["systemctl stop nginx 2>/dev/null || true", "systemctl disable nginx 2>/dev/null || true"]
            ok, err = _run_cmds(start_cmds, "启动Nginx")
            if not ok:
                rollback_results = _rollback()
                _update_job(job_id, status="failed", progress=0, progress_message="启动 Nginx 失败，已回滚", error=err, result={"rollback_results": rollback_results})
                return
            steps_log.append({"name": "启动Nginx", "status": "committed", "commit": start_cmds, "rollback": rollback_start})

    else:
        # 通用包安装
        _update_job(job_id, progress=40, progress_message=f"安装 {package_name}...")
        if os_type == "debian":
            install_cmds = [f"apt-get install -y {package_name}"]
            rollback_cmds = [f"apt-get remove -y {package_name} 2>/dev/null || true"]
        else:
            install_cmds = [f"yum install -y {package_name}"]
            rollback_cmds = [f"yum remove -y {package_name} 2>/dev/null || true"]
        ok, err = _run_cmds(install_cmds, f"安装{package_name}")
        if not ok:
            rollback_results = _rollback()
            _update_job(job_id, status="failed", progress=0, progress_message=f"安装 {package_name} 失败，已回滚", error=err, result={"rollback_results": rollback_results})
            return
        steps_log.append({"name": f"安装{package_name}", "status": "committed", "commit": install_cmds, "rollback": rollback_cmds})
        _update_job(job_id, progress=90)

    _update_job(job_id, status="success", progress=100,
                progress_message="安装完成",
                result={
                    "package": package_name,
                    "version": version,
                    "os_type": os_type,
                    "ip": ip,
                    "port": 9200 if package_name in ("elasticsearch", "es") else (80 if package_name == "nginx" else 0),
                    "install_type": install_type,
                    "steps": steps_log,
                })


# ─── 任务提交入口 ─────────────────────────────────────────────────

def submit_install_job(package_name: str, asset_id: int, version: str,
                      options: Dict, session_id: int = None,
                      pending_action_id: int = None) -> str:
    """
    提交一个异步安装任务，返回 job_id。
    任务在线程池中执行，不阻塞调用者。
    """
    job_id = str(uuid.uuid4())

    # 查资产获取连接信息
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"资产 {asset_id} 不存在")
        ip = asset.ip
        ssh_user = getattr(asset, "ssh_user", "root") or "root"
        ssh_port = int(getattr(asset, "ssh_port", 22) or 22)
        ssh_password = getattr(asset, "ssh_password", "") or ""

        # 创建 job 记录
        job = BackgroundJob(
            job_id=job_id,
            action_type="install_package",
            title=f"安装 {package_name} 到 {ip}",
            status="pending",
            progress=0,
            progress_message="任务已提交，等待执行...",
            asset_id=asset_id,
            session_id=session_id,
            pending_action_id=pending_action_id,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    # 提交到线程池
    with _tasks_lock:
        future = _executor.submit(
            _exec_steps,
            job_id, ip, ssh_user, ssh_password, ssh_port,
            package_name, version, options
        )
        _running_tasks[job_id] = future

    return job_id


def submit_generic_job(action_type: str, title: str, asset_id: int,
                       command: str, session_id: int = None) -> str:
    """提交一个通用远程命令任务（用于长耗时的 run_command）"""
    job_id = str(uuid.uuid4())

    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"资产 {asset_id} 不存在")
        ip = asset.ip
        ssh_user = getattr(asset, "ssh_user", "root") or "root"
        ssh_port = int(getattr(asset, "ssh_port", 22) or 22)
        ssh_password = getattr(asset, "ssh_password", "") or ""

        job = BackgroundJob(
            job_id=job_id,
            action_type=action_type,
            title=title or f"执行命令: {command[:50]}",
            status="pending",
            progress=0,
            progress_message="任务已提交...",
            asset_id=asset_id,
            session_id=session_id,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    def _run():
        _update_job(job_id, status="running", progress=10, progress_message=f"连接 {ip}...")
        success, output = _remote_exec_ssh(ip, ssh_user, ssh_password, ssh_port, command, timeout=600)
        if success:
            _update_job(job_id, status="success", progress=100,
                        progress_message="命令执行完成",
                        result={"command": command, "output": output[:2000], "exit_code": 0})
        else:
            _update_job(job_id, status="failed", progress=100,
                        progress_message="命令执行失败",
                        error=output[:500])

    with _tasks_lock:
        future = _executor.submit(_run)
        _running_tasks[job_id] = future

    return job_id


# ─── 状态查询 ──────────────────────────────────────────────────────

def get_background_job(job_id: str) -> Optional[Dict]:
    """查询后台任务状态，供 LLM 轮询使用"""
    db = get_session_for(get_db_mode())()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()
        if not job:
            return None
        result = {
            "job_id": job.job_id,
            "action_type": job.action_type,
            "title": job.title,
            "status": job.status,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
        if job.result_payload and job.result_payload != "{}":
            try:
                result["result"] = json.loads(job.result_payload)
            except Exception:
                result["result"] = job.result_payload
        if job.error_message:
            result["error"] = job.error_message
        return result
    finally:
        db.close()


def list_running_jobs(session_id: int = None, limit: int = 20) -> list:
    """列出最近的运行中/刚结束的任务"""
    db = get_session_for(get_db_mode())()
    try:
        q = db.query(BackgroundJob)
        if session_id:
            q = q.filter(BackgroundJob.session_id == session_id)
        jobs = q.order_by(BackgroundJob.created_at.desc()).limit(limit).all()
        return [
            {
                "job_id": j.job_id,
                "action_type": j.action_type,
                "title": j.title,
                "status": j.status,
                "progress": j.progress,
                "progress_message": j.progress_message,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
    finally:
        db.close()


# ─── restart_service 异步任务 ─────────────────────────────────────

def submit_restart_job(service: str, asset_id: int, session_id: int = None,
                      pending_action_id: int = None) -> str:
    """提交重启服务异步任务"""
    job_id = str(uuid.uuid4())
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"资产 {asset_id} 不存在")
        ip = asset.ip
        ssh_user = getattr(asset, "ssh_user", "root") or "root"
        ssh_port = int(getattr(asset, "ssh_port", 22) or 22)
        ssh_password = getattr(asset, "ssh_password", "") or ""

        job = BackgroundJob(
            job_id=job_id, action_type="restart_service",
            title=f"重启服务 {service}@{ip}",
            status="pending", progress=0,
            progress_message=f"重启服务 {service}...",
            asset_id=asset_id, session_id=session_id,
            pending_action_id=pending_action_id,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    def _run():
        _update_job(job_id, status="running", progress=10,
                    progress_message=f"正在重启 {service}...")
        cmd = f"systemctl restart {service}"
        success, output = _remote_exec_ssh(ip, ssh_user, ssh_password, ssh_port, cmd, timeout=120)
        if success:
            _update_job(job_id, status="success", progress=100,
                        progress_message=f"服务 {service} 重启成功",
                        result={"service": service, "asset_id": asset_id,
                                "ip": ip, "command": cmd, "output": output[:500]})
        else:
            _update_job(job_id, status="failed", progress=100,
                        progress_message=f"服务 {service} 重启失败",
                        error=output[:300],
                        result={"service": service, "asset_id": asset_id,
                                "ip": ip, "command": cmd, "output": output[:500]})

    with _tasks_lock:
        _running_tasks[job_id] = _executor.submit(_run)
    return job_id


# ─── run_script 异步任务 ──────────────────────────────────────────

def submit_script_job(script: str, asset_id: int, session_id: int = None,
                     pending_action_id: int = None) -> str:
    """提交远程脚本执行异步任务"""
    job_id = str(uuid.uuid4())
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"资产 {asset_id} 不存在")
        ip = asset.ip
        ssh_user = getattr(asset, "ssh_user", "root") or "root"
        ssh_port = int(getattr(asset, "ssh_port", 22) or 22)
        ssh_password = getattr(asset, "ssh_password", "") or ""

        job = BackgroundJob(
            job_id=job_id, action_type="run_script",
            title=f"执行脚本 {script}",
            status="pending", progress=0,
            progress_message=f"执行脚本 {script}...",
            asset_id=asset_id, session_id=session_id,
            pending_action_id=pending_action_id,
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    def _run():
        _update_job(job_id, status="running", progress=10,
                    progress_message=f"正在执行脚本 {script}...")
        cmd = f"bash {script}"
        success, output = _remote_exec_ssh(ip, ssh_user, ssh_password, ssh_port, cmd, timeout=600)
        if success:
            _update_job(job_id, status="success", progress=100,
                        progress_message="脚本执行成功",
                        result={"script": script, "asset_id": asset_id,
                                "ip": ip, "command": cmd, "output": output[:2000]})
        else:
            _update_job(job_id, status="failed", progress=100,
                        progress_message="脚本执行失败",
                        error=output[:300],
                        result={"script": script, "asset_id": asset_id,
                                "ip": ip, "command": cmd, "output": output[:2000]})

    with _tasks_lock:
        _running_tasks[job_id] = _executor.submit(_run)
    return job_id
