"""Agent 一键下发服务 — 通过 SSH 将 edge agent 部署到目标节点。

流程：
1. 生成 tunnel_token（云端注册用）
2. 通过 SSH 在目标节点安装 python3 + pip
3. 推送 edge_agent.py 到 /opt/aiops-agent/
4. 写入 config.json（cloud_url + tunnel_token）
5. 创建 systemd 服务
6. 启动 agent → agent 自动 WebSocket 拨出注册
"""
import json
import os
import secrets
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database import get_session_for, get_db_mode
from app.models import Asset, BackgroundJob, EdgeSession, EdgeCommandLog
from app.logger import logger
from app.services.background_task import _remote_exec_ssh

AGENT_INSTALL_DIR = "/opt/aiops-agent"
EDGE_AGENT_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "edge_agent", "edge_agent.py",
)


def _read_agent_script() -> str:
    with open(EDGE_AGENT_SOURCE, "r", encoding="utf-8") as f:
        return f.read()


def _get_ssh_credential(asset: Asset) -> tuple:
    cfg = json.loads(asset.connection_config or "{}")
    ip = asset.ip or cfg.get("ssh_host", "")
    user = cfg.get("ssh_user", "root")
    port = int(cfg.get("ssh_port", 22) or 22)
    password = cfg.get("ssh_password", "") or cfg.get("ssh_key", "")
    return ip, user, password, port


def _update_job(job_id, status=None, progress=None, message=None, error=None, result=None):
    db = get_session_for(get_db_mode())()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()
        if not job:
            return
        if status:
            job.status = status
        if progress is not None:
            job.progress = progress
        if message:
            job.progress_message = message
        if error:
            job.error_message = error
        if result:
            job.result_payload = json.dumps(result, ensure_ascii=False)
        if status == "running" and not job.started_at:
            job.started_at = datetime.now()
        if status in ("success", "failed"):
            job.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()


def deploy_agent_background(job_id: str, asset_id: int, cloud_url: str, tunnel_token: str):
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            _update_job(job_id, status="failed", progress=0, error="资产不存在")
            return
        ip, user, password, port = _get_ssh_credential(asset)
        if not ip:
            _update_job(job_id, status="failed", progress=0, error="资产 IP 为空")
            return

        _update_job(job_id, status="running", progress=5, message=f"连接 {ip}...")

        # Step 1: 检测 OS
        ok, out = _remote_exec_ssh(ip, user, password, port, "cat /etc/os-release 2>/dev/null || echo unknown", timeout=15)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"SSH 连接失败: {out[:200]}", result={"ip": ip})
            return
        os_type = "unknown"
        ol = out.lower()
        if "ubuntu" in ol or "debian" in ol:
            os_type = "debian"
        elif "centos" in ol or "rhel" in ol or "rocky" in ol:
            os_type = "rhel"
        _update_job(job_id, progress=15, message=f"OS: {os_type}")

        # Step 2: 安装 python3
        _update_job(job_id, progress=20, message="正在安装 python3（可能需要几分钟，取决于网络）...")
        if os_type == "debian":
            install_cmd = "apt-get update -qq && apt-get install -y -qq python3 python3-pip"
        else:
            install_cmd = "yum install -y python3 2>/dev/null || dnf install -y python3"
        ok, out = _remote_exec_ssh(ip, user, password, port, install_cmd, timeout=300)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"安装 python3 失败: {out[:200]}")
            return
        _update_job(job_id, progress=25, message="Python3 已安装")

        # Step 2b: 确保 pip 可用
        _update_job(job_id, progress=28, message="配置 pip...")
        if os_type != "debian":
            ok, _ = _remote_exec_ssh(ip, user, password, port, "python3 -m ensurepip --upgrade 2>/dev/null; python3 -m pip install --upgrade pip 2>/dev/null", timeout=60)

        # Step 3: 安装 websockets
        _update_job(job_id, progress=32, message="安装 websockets 依赖...")
        ok, out = _remote_exec_ssh(ip, user, password, port, "python3 -m pip install -q websockets", timeout=90)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"安装 websockets 失败: {out[:200]}")
            return
        _update_job(job_id, progress=40, message="依赖已安装")

        # Step 4: 创建目录并推送 edge_agent.py
        agent_script = _read_agent_script()
        _update_job(job_id, progress=50, message="推送 agent 程序...")

        # 用 base64 编码绕过 shell 特殊字符
        import base64
        b64_script = base64.b64encode(agent_script.encode("utf-8")).decode("ascii")
        push_cmd = (
            f"mkdir -p {AGENT_INSTALL_DIR} && "
            f"echo '{b64_script}' | base64 -d > {AGENT_INSTALL_DIR}/edge_agent.py && "
            f"chmod +x {AGENT_INSTALL_DIR}/edge_agent.py"
        )
        ok, out = _remote_exec_ssh(ip, user, password, port, push_cmd, timeout=30)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"推送 agent 失败: {out[:200]}")
            return
        _update_job(job_id, progress=60, message="agent 程序已推送")

        # Step 5: 写入 config.json
        config = {
            "cloud_url": cloud_url,
            "tunnel_token": tunnel_token,
            "agent_id": "",
            "installed_at": datetime.now().isoformat(),
        }
        config_b64 = base64.b64encode(json.dumps(config, ensure_ascii=False).encode("utf-8")).decode("ascii")
        ok, out = _remote_exec_ssh(ip, user, password, port, f"echo '{config_b64}' | base64 -d > {AGENT_INSTALL_DIR}/config.json", timeout=10)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"写入 config 失败: {out[:200]}")
            return
        _update_job(job_id, progress=70, message="配置已写入")

        # Step 6: 创建 systemd 服务
        svc_content = f"""[Unit]
Description=AIOps Edge Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={AGENT_INSTALL_DIR}
ExecStart=/usr/bin/python3 {AGENT_INSTALL_DIR}/edge_agent.py --cloud {cloud_url} --token {tunnel_token}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        svc_b64 = base64.b64encode(svc_content.encode("utf-8")).decode("ascii")
        svc_cmd = (
            f"echo '{svc_b64}' | base64 -d > /etc/systemd/system/aiops-edge-agent.service && "
            f"systemctl daemon-reload"
        )
        ok, out = _remote_exec_ssh(ip, user, password, port, svc_cmd, timeout=15)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"创建 systemd 服务失败: {out[:200]}")
            return
        _update_job(job_id, progress=80, message="systemd 服务已创建")

        # Step 7: 启动/重启 agent
        _update_job(job_id, progress=85, message="启动 agent...")
        ok, out = _remote_exec_ssh(ip, user, password, port, "systemctl enable aiops-edge-agent 2>/dev/null; systemctl restart aiops-edge-agent", timeout=30)
        if not ok:
            _update_job(job_id, status="failed", progress=0, error=f"启动 agent 失败: {out[:200]}")
            return

        _update_job(job_id, progress=90, message="agent 已启动，等待注册...")

        # Step 8: 等待 agent 注册（最多等 15 秒）
        for _ in range(15):
            time.sleep(1)
            session = db.query(EdgeSession).filter(
                EdgeSession.asset_id == asset_id,
                EdgeSession.status == EdgeSession.STATUS_ONLINE,
            ).first()
            if session:
                _update_job(job_id, status="success", progress=100,
                            message=f"agent 已注册（session_id={session.id}）",
                            result={"agent_id": session.agent_id, "session_id": session.id, "ip": ip})
                logger.info(f"Agent 部署成功: asset_id={asset_id} agent_id={session.agent_id}")
                return

        _update_job(job_id, status="success", progress=100,
                    message="agent 已启动，注册可能需要几秒，请刷新页面查看",
                    result={"ip": ip, "note": "agent 已启动，等待首次心跳注册"})
    except Exception as e:
        logger.error(f"Agent 部署异常: {e}")
        _update_job(job_id, status="failed", progress=0, error=str(e)[:500])
    finally:
        db.close()