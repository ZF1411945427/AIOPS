"""Edge Agent 反向隧道服务 — 云端侧核心。

职责：
1. 管理 EdgeSession 生命周期（注册、心跳、断线、重连）
2. 维护在线 edge agent 的 WebSocket 连接池（内存）
3. 路由 WebSSH / 命令执行请求到对应 edge agent
4. 命令审计日志写入 EdgeCommandLog

架构：
  浏览器 ─(WebSocket)─> 云端 webssh.py ─(内存查找)─> edge_tunnel WebSocket ─> edge agent ─> 本地 PTY

  edge agent ─(WebSocket 拨出)─> 云端 /edge/tunnel/connect ─> EdgeTunnelService.register()

关键设计：
- edge agent 拨出时携带 tunnel_token（预共享密钥），云端校验后注册
- 内存维护 agent_id → WebSocket 映射，断线自动清理
- 心跳：edge agent 每 30s 发 {"type":"heartbeat"}，云端更新 last_heartbeat_at
- 后台线程扫描超时会话（>90s 无心跳）标记 offline
"""
import json
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from fastapi import WebSocket

from sqlalchemy.orm import Session

from app.models import EdgeSession, EdgeCommandLog, Asset
from app.logger import logger


# ─── 待执行命令缓存（HTTP 轮询模式）────────────────
# agent_id -> [list of pending commands]
_PENDING_COMMANDS: Dict[str, list] = {}
_PENDING_LOCK = threading.Lock()


def add_pending_command(agent_id: str, command: dict) -> int:
    """添加待执行命令，返回 cmd_seq（序号）。"""
    with _PENDING_LOCK:
        if agent_id not in _PENDING_COMMANDS:
            _PENDING_COMMANDS[agent_id] = []
        cmd = {**command, "seq": len(_PENDING_COMMANDS[agent_id]) + 1}
        _PENDING_COMMANDS[agent_id].append(cmd)
        return cmd["seq"]


def get_pending_commands(agent_id: str) -> list:
    """取出并清空待执行命令列表。"""
    with _PENDING_LOCK:
        cmds = _PENDING_COMMANDS.pop(agent_id, [])
        return cmds


# ─── 在线 edge agent 连接池 ───────────────────────────────
# agent_id -> {"ws": WebSocket, "session_id": int, "outgoing_queue": asyncio.Queue, "sender_task": Task}
_ONLINE_AGENTS: Dict[str, dict] = {}
_ONLINE_LOCK = threading.Lock()


def register_online(agent_id: str, ws: WebSocket, session_id: int):
    """注册 edge agent 上线，创建 outgoing 消息队列。"""
    try:
        queue = asyncio.Queue(maxsize=100)
    except RuntimeError:
        # 无运行中事件循环（不应发生在 WebSocket handler 中）
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue(maxsize=100)
    with _ONLINE_LOCK:
        _ONLINE_AGENTS[agent_id] = {
            "ws": ws,
            "session_id": session_id,
            "registered_at": datetime.now(),
            "outgoing_queue": queue,
        }
    logger.info(f"Edge agent 上线: agent_id={agent_id} session_id={session_id}")


def get_outgoing_queue(agent_id: str) -> Optional["asyncio.Queue"]:
    """获取 edge agent 的 outgoing 消息队列。"""
    with _ONLINE_LOCK:
        info = _ONLINE_AGENTS.get(agent_id)
        return info["outgoing_queue"] if info else None


async def send_to_agent(agent_id: str, message: dict):
    """通过 outgoing 队列向 edge agent 发送消息（线程安全，跨协程安全）。"""
    queue = get_outgoing_queue(agent_id)
    if queue is None:
        raise RuntimeError(f"edge agent {agent_id} 不在线")
    await queue.put(message)


def unregister_online(agent_id: str):
    with _ONLINE_LOCK:
        _ONLINE_AGENTS.pop(agent_id, None)
    logger.info(f"Edge agent 下线: agent_id={agent_id}")


def get_online_ws(agent_id: str) -> Optional[WebSocket]:
    with _ONLINE_LOCK:
        info = _ONLINE_AGENTS.get(agent_id)
        return info["ws"] if info else None


def list_online_agents() -> List[str]:
    with _ONLINE_LOCK:
        return list(_ONLINE_AGENTS.keys())


def is_agent_online(agent_id: str) -> bool:
    with _ONLINE_LOCK:
        return agent_id in _ONLINE_AGENTS


# ─── EdgeSession 数据库操作 ───────────────────────────────

def find_session_by_agent(db: Session, agent_id: str) -> Optional[EdgeSession]:
    return db.query(EdgeSession).filter(EdgeSession.agent_id == agent_id).first()


def register_or_update_session(
    db: Session,
    agent_id: str,
    hostname: str,
    os_type: str,
    ip_addresses: List[str],
    agent_version: str,
    tunnel_token: str,
) -> EdgeSession:
    """edge agent 拨出时注册或更新会话。"""
    session = find_session_by_agent(db, agent_id)
    now = datetime.now()
    if session:
        session.hostname = hostname
        session.os_type = os_type
        session.ip_addresses = json.dumps(ip_addresses, ensure_ascii=False)
        session.agent_version = agent_version
        session.status = EdgeSession.STATUS_ONLINE
        session.connected_at = now
        session.last_heartbeat_at = now
        session.tunnel_token = tunnel_token
    else:
        session = EdgeSession(
            agent_id=agent_id,
            hostname=hostname,
            os_type=os_type,
            ip_addresses=json.dumps(ip_addresses, ensure_ascii=False),
            agent_version=agent_version,
            status=EdgeSession.STATUS_ONLINE,
            connected_at=now,
            last_heartbeat_at=now,
            tunnel_token=tunnel_token,
        )
        db.add(session)
    db.commit()
    db.refresh(session)

    # 自动绑定到 Asset（按 hostname 或 IP 匹配）
    _bind_to_asset(db, session)
    return session


def _bind_to_asset(db: Session, session: EdgeSession):
    """把 EdgeSession 绑定到 Asset（按 hostname 优先，其次 IP）。"""
    if session.asset_id:
        return  # 已绑定
    asset = None
    if session.hostname:
        asset = db.query(Asset).filter(Asset.name == session.hostname).first()
    if not asset:
        for ip in session.get_ip_addresses():
            asset = db.query(Asset).filter(Asset.ip == ip).first()
            if asset:
                break
    if asset:
        session.asset_id = asset.id
        asset.edge_agent_id = session.agent_id
        db.commit()
        logger.info(f"EdgeSession {session.agent_id} 绑定到 Asset #{asset.id} ({asset.name})")


def update_heartbeat(db: Session, agent_id: str):
    session = find_session_by_agent(db, agent_id)
    if session:
        session.last_heartbeat_at = datetime.now()
        if session.status != EdgeSession.STATUS_ONLINE:
            session.status = EdgeSession.STATUS_ONLINE
        db.commit()


def mark_offline(db: Session, agent_id: str):
    session = find_session_by_agent(db, agent_id)
    if session:
        session.status = EdgeSession.STATUS_OFFLINE
        session.disconnected_at = datetime.now()
        db.commit()
    unregister_online(agent_id)


def list_sessions(db: Session, online_only: bool = False) -> List[EdgeSession]:
    q = db.query(EdgeSession)
    if online_only:
        q = q.filter(EdgeSession.status == EdgeSession.STATUS_ONLINE)
    return q.order_by(EdgeSession.updated_at.desc()).all()


# ─── 命令执行（通过反向隧道）────────────────────────

async def execute_command_via_tunnel(
    db: Session,
    agent_id: str,
    command: str,
    user_id: int,
    username: str,
    client_ip: str = "",
    timeout: int = 30,
) -> dict:
    """通过反向隧道向 edge agent 发送命令并等待结果。

    返回 {"exit_code": int, "stdout": str, "stderr": str, "duration_ms": int, "status": str}
    """
    ws = get_online_ws(agent_id)
    if not ws:
        return {"exit_code": -1, "stdout": "", "stderr": "edge agent 不在线",
                "duration_ms": 0, "status": "failed"}

    session = find_session_by_agent(db, agent_id)
    if not session:
        return {"exit_code": -1, "stdout": "", "stderr": "edge session 不存在",
                "duration_ms": 0, "status": "failed"}

    # 写审计日志
    log = EdgeCommandLog(
        session_id=session.id,
        user_id=user_id,
        username=username,
        command=command,
        status=EdgeCommandLog.STATUS_RUNNING,
        client_ip=client_ip,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    start = time.time()
    try:
        # 把命令放入待执行队列，edge agent 会通过 HTTP 轮询获取
        add_pending_command(agent_id, {
            "type": "exec",
            "command": command,
            "log_id": log.id,
            "timeout": timeout,
        })
        # 等待 edge agent 回传结果（通过 WebSocket exec_result 消息）
        result = await _await_exec_result(log.id, timeout + 5)
        duration_ms = int((time.time() - start) * 1000)
        log.exit_code = result.get("exit_code", -1)
        log.stdout = (result.get("stdout") or "")[:60000]
        log.stderr = (result.get("stderr") or "")[:60000]
        log.duration_ms = duration_ms
        log.status = EdgeCommandLog.STATUS_SUCCESS if log.exit_code == 0 else EdgeCommandLog.STATUS_FAILED
        log.finished_at = datetime.now()
        db.commit()
        return {
            "exit_code": log.exit_code,
            "stdout": log.stdout,
            "stderr": log.stderr,
            "duration_ms": duration_ms,
            "status": log.status,
            "log_id": log.id,
        }
    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        log.status = EdgeCommandLog.STATUS_TIMEOUT
        log.duration_ms = duration_ms
        log.stderr = f"命令执行超时（{timeout}s）"
        log.finished_at = datetime.now()
        db.commit()
        return {"exit_code": -1, "stdout": "", "stderr": log.stderr,
                "duration_ms": duration_ms, "status": "timeout", "log_id": log.id}
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        log.status = EdgeCommandLog.STATUS_FAILED
        log.stderr = str(e)[:1000]
        log.duration_ms = duration_ms
        log.finished_at = datetime.now()
        db.commit()
        return {"exit_code": -1, "stdout": "", "stderr": log.stderr,
                "duration_ms": duration_ms, "status": "failed", "log_id": log.id}


# ─── exec 结果等待池 ───────────────────────────────────────
# log_id -> asyncio.Future
_EXEC_FUTURES: Dict[int, asyncio.Future] = {}
_EXEC_LOCK = threading.Lock()


def register_exec_future(log_id: int, future: asyncio.Future):
    with _EXEC_LOCK:
        _EXEC_FUTURES[log_id] = future


def resolve_exec_future(log_id: int, result: dict):
    with _EXEC_LOCK:
        future = _EXEC_FUTURES.pop(log_id, None)
    if future and not future.done():
        future.set_result(result)


async def _await_exec_result(log_id: int, timeout: int) -> dict:
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    register_exec_future(log_id, future)
    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        with _EXEC_LOCK:
            _EXEC_FUTURES.pop(log_id, None)
        raise


def resolve_exec_future(log_id: int, result: dict):
    """从 WebSocket handler 调用，resolve exec future。"""
    with _EXEC_LOCK:
        future = _EXEC_FUTURES.pop(log_id, None)
    if future is None:
        logger.warning(f"resolve_exec_future: log_id={log_id} 无等待中的 future（可能已超时）")
        return
    if future.done():
        logger.warning(f"resolve_exec_future: log_id={log_id} future 已 done")
        return
    try:
        loop = future.get_loop()
        loop.call_soon_threadsafe(future.set_result, result)
        logger.info(f"resolve_exec_future: log_id={log_id} 已 resolve")
    except Exception as e:
        logger.error(f"resolve_exec_future 异常: {e}")
        if not future.done():
            future.set_result(result)


# ─── 心跳超时扫描后台线程 ───────────────────────────────

def start_heartbeat_monitor():
    """启动后台线程，扫描超时的 edge session（>90s 无心跳）标记 offline。"""
    def _monitor():
        from app.database import get_session_for, get_db_mode
        while True:
            try:
                db = get_session_for(get_db_mode())()
                threshold = datetime.now() - timedelta(seconds=90)
                stale = db.query(EdgeSession).filter(
                    EdgeSession.status == EdgeSession.STATUS_ONLINE,
                    EdgeSession.last_heartbeat_at < threshold,
                ).all()
                for s in stale:
                    s.status = EdgeSession.STATUS_OFFLINE
                    s.disconnected_at = datetime.now()
                    unregister_online(s.agent_id)
                    logger.warning(f"Edge agent 心跳超时: agent_id={s.agent_id} last={s.last_heartbeat_at}")
                if stale:
                    db.commit()
                db.close()
            except Exception as e:
                logger.error(f"心跳监控异常: {e}")
            time.sleep(30)

    t = threading.Thread(target=_monitor, daemon=True, name="edge-heartbeat-monitor")
    t.start()
    return t
