"""Agent 下发/管理 API — 部署、监控、命令、统一执行路由。"""
import json
import asyncio
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, get_session_for, get_db_mode
from app.models import Asset, BackgroundJob, EdgeSession, EdgeCommandLog, User
from app.services.edge_tunnel_service import (
    is_agent_online, execute_command_via_tunnel, list_sessions,
)
from app.services.agent_deploy_service import deploy_agent_background
from app.logger import logger

router = APIRouter(prefix="/agent", tags=["agent-deploy"])

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent_deploy_")


def _get_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None, JSONResponse({"error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    return user, None


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def route_exec(asset_id: int, command: str, user_id: int = 0, username: str = "",
               client_ip: str = "", timeout: int = 30) -> dict:
    """统一命令路由（同步版）：有在线 agent 走隧道，否则 SSH 回退。

    供其他模块（自愈/巡检/AI Agent）在同步上下文中调用。
    """
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        ch = {"channel": "ssh"}
        if not asset:
            return {"exit_code": -1, "stdout": "", "stderr": "资产不存在", "status": "failed", **ch}

        if asset.edge_agent_id and is_agent_online(asset.edge_agent_id):
            logger.info(f"命令路由 -> 隧道: asset_id={asset_id} agent_id={asset.edge_agent_id}")
            result = _run_async(execute_command_via_tunnel(
                db, asset.edge_agent_id, command, user_id, username, client_ip, timeout))
            result["channel"] = "tunnel"
            return result

        return _ssh_fallback(asset, command, ch, timeout)
    finally:
        db.close()


async def route_exec_async(asset_id: int, command: str, user_id: int = 0, username: str = "",
                           client_ip: str = "", timeout: int = 30) -> dict:
    """统一命令路由（异步版）：供 FastAPI 路由 handler 在 async 上下文中直接 await。

    避免 _run_async() 在已有 event loop 中创建新 loop 导致 RuntimeError。
    """
    db = get_session_for(get_db_mode())()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        ch = {"channel": "ssh"}
        if not asset:
            return {"exit_code": -1, "stdout": "", "stderr": "资产不存在", "status": "failed", **ch}

        if asset.edge_agent_id and is_agent_online(asset.edge_agent_id):
            logger.info(f"命令路由(async) -> 隧道: asset_id={asset_id} agent_id={asset.edge_agent_id}")
            result = await execute_command_via_tunnel(
                db, asset.edge_agent_id, command, user_id, username, client_ip, timeout)
            result["channel"] = "tunnel"
            return result

        return _ssh_fallback(asset, command, ch, timeout)
    finally:
        db.close()


def _ssh_fallback(asset, command: str, ch: dict, timeout: int = 30) -> dict:
    """SSH 回退执行（同步）。"""
    cfg = json.loads(asset.connection_config or "{}")
    ip = asset.ip or cfg.get("ssh_host", "")
    if not ip:
        return {"exit_code": -1, "stdout": "", "stderr": "资产无 IP 且无在线 agent", "status": "failed", **ch}
    ssh_user = cfg.get("ssh_user", "root")
    ssh_port = int(cfg.get("ssh_port", 22) or 22)
    ssh_password = cfg.get("ssh_password", "") or cfg.get("ssh_key", "")
    from app.services.background_task import _remote_exec_ssh
    success, output = _remote_exec_ssh(ip, ssh_user, ssh_password, ssh_port, command, timeout=timeout)
    return {
        "exit_code": 0 if success else -1,
        "stdout": output if success else "",
        "stderr": "" if success else output,
        "status": "success" if success else "failed",
        "channel": "ssh",
    }


# ─── Agent 下发 ─────────────────────────────────────────────

@router.post("/deploy")
async def deploy_agent(request: Request, db: Session = Depends(get_db)):
    """一键下发 edge agent 到目标资产。"""
    user, err = _get_user(request, db)
    if err:
        return err
    data = await request.json()
    asset_id = data.get("asset_id")
    if not asset_id:
        return JSONResponse({"error": "asset_id 必填"}, status_code=400)
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "资产不存在"}, status_code=404)

    cloud_url = data.get("cloud_url", f"http://{request.url.hostname}:{request.url.port or 8000}")
    tunnel_token = data.get("tunnel_token") or secrets.token_urlsafe(32)

    job_id = str(uuid.uuid4())
    job = BackgroundJob(
        job_id=job_id,
        action_type="deploy_agent",
        title=f"部署 Agent 到 {asset.name}",
        status="pending",
        progress=0,
        progress_message="任务已提交...",
        asset_id=asset_id,
        session_id=None,
    )
    db.add(job)
    db.commit()

    _executor.submit(deploy_agent_background, job_id, asset_id, cloud_url, tunnel_token)

    return {"ok": True, "job_id": job_id, "tunnel_token": tunnel_token, "message": "Agent 部署任务已提交"}


@router.get("/deploy/{job_id}")
def get_deploy_job(job_id: str, db: Session = Depends(get_db)):
    """查询部署任务状态。"""
    job = db.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()
    if not job:
        return {"error": "任务不存在"}
    result = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "progress_message": job.progress_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if job.error_message:
        result["error"] = job.error_message
    if job.result_payload and job.result_payload != "{}":
        try:
            result["result"] = json.loads(job.result_payload)
        except Exception:
            result["result"] = job.result_payload
    return result


@router.post("/deploy/{job_id}/cancel")
def cancel_deploy_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()
    if not job:
        return {"error": "任务不存在"}
    if job.status in ("pending", "running"):
        job.status = "canceled"
        job.finished_at = datetime.now()
        db.commit()
    return {"ok": True}


# ─── Agent 清单 ─────────────────────────────────────────────

@router.get("/agents")
def list_agents(request: Request, db: Session = Depends(get_db)):
    """返回所有已注册 agent 及其在线状态、关联资产信息。"""
    sessions = list_sessions(db, online_only=False)
    assets = {a.id: a for a in db.query(Asset).all()}
    return {
        "total": len(sessions),
        "online_count": sum(1 for s in sessions if is_agent_online(s.agent_id)),
        "agents": [
            {
                "agent_id": s.agent_id,
                "session_id": s.id,
                "hostname": s.hostname,
                "os_type": s.os_type,
                "status": s.status,
                "online": is_agent_online(s.agent_id),
                "asset_id": s.asset_id,
                "asset_name": assets[s.asset_id].name if s.asset_id and s.asset_id in assets else "",
                "agent_version": s.agent_version,
                "ip_addresses": s.get_ip_addresses(),
                "last_heartbeat_at": s.last_heartbeat_at.isoformat() if s.last_heartbeat_at else None,
                "connected_at": s.connected_at.isoformat() if s.connected_at else None,
                "reconnect_count": s.reconnect_count,
            }
            for s in sessions
        ],
    }


# ─── 通过 Agent 执行命令 ────────────────────────────────────

@router.post("/exec")
async def exec_command(request: Request, db: Session = Depends(get_db)):
    """通过统一路由执行命令（agent 隧道优先，SSH 回退）。"""
    user, err = _get_user(request, db)
    if err:
        return err
    data = await request.json()
    asset_id = data.get("asset_id")
    command = data.get("command", "")
    timeout = data.get("timeout", 30)
    if not asset_id or not command:
        return JSONResponse({"error": "asset_id 和 command 必填"}, status_code=400)
    client_ip = request.client.host if request.client else ""
    result = await route_exec_async(asset_id, command, user.id, user.username, client_ip, timeout)
    return result


@router.post("/exec/tunnel")
async def exec_via_tunnel(request: Request, db: Session = Depends(get_db)):
    """强制通过 agent 隧道执行命令（不走 SSH 回退）。"""
    user, err = _get_user(request, db)
    if err:
        return err
    data = await request.json()
    agent_id = data.get("agent_id")
    command = data.get("command", "")
    timeout = data.get("timeout", 30)
    if not agent_id or not command:
        return JSONResponse({"error": "agent_id 和 command 必填"}, status_code=400)
    if not is_agent_online(agent_id):
        return JSONResponse({"error": "edge agent 不在线"}, status_code=400)
    client_ip = request.client.host if request.client else ""
    result = await execute_command_via_tunnel(
        db, agent_id, command, user.id, user.username, client_ip, timeout)
    result["channel"] = "tunnel"
    return result


# ─── 命令审计日志 ───────────────────────────────────────────

@router.get("/commands")
def list_agent_commands(
    request: Request,
    db: Session = Depends(get_db),
    agent_id: str = Query(None),
    limit: int = Query(50, le=200),
):
    q = db.query(EdgeCommandLog)
    if agent_id:
        session = db.query(EdgeSession).filter(EdgeSession.agent_id == agent_id).first()
        if session:
            q = q.filter(EdgeCommandLog.session_id == session.id)
    logs = q.order_by(EdgeCommandLog.created_at.desc()).limit(limit).all()
    return {
        "total": len(logs),
        "commands": [
            {
                "id": l.id,
                "session_id": l.session_id,
                "username": l.username,
                "command": l.command,
                "exit_code": l.exit_code,
                "stdout": (l.stdout or "")[:500],
                "stderr": (l.stderr or "")[:500],
                "duration_ms": l.duration_ms,
                "status": l.status,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }


# ─── 可部署的资产清单（有 SSH 凭证） ────────────────────────

@router.get("/deployable-assets")
def list_deployable_assets(request: Request, db: Session = Depends(get_db)):
    """返回可部署 agent 的资产（有 IP，unbound 类型）。"""
    assets = db.query(Asset).filter(Asset.ip != "", Asset.ip.isnot(None)).all()
    result = []
    for a in assets:
        has_agent = bool(a.edge_agent_id)
        online = is_agent_online(a.edge_agent_id) if has_agent else False
        result.append({
            "id": a.id,
            "name": a.name,
            "ip": a.ip,
            "ci_type": a.ci_type,
            "has_agent": has_agent,
            "agent_online": online,
            "edge_agent_id": a.edge_agent_id or "",
        })
    return {"assets": result, "total": len(result)}