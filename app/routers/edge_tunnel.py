"""Edge Agent 反向隧道云端端点。

端点：
- WebSocket /edge/tunnel/connect   edge agent 主动拨出接入点
- GET     /edge/sessions           列出所有 edge session
- GET     /edge/sessions/online    在线 edge agent
- POST    /edge/sessions/{id}/bind 手动绑定 asset
- POST    /edge/command            通过隧道执行命令
- GET     /edge/commands           命令审计日志
- GET     /edge/agents/manifest    前端用精简清单
- POST    /edge/tokens             生成 tunnel_token（admin）
"""
import json
import asyncio
import hashlib
import secrets
from datetime import datetime
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EdgeSession, EdgeCommandLog, Asset, User
from app.services.edge_tunnel_service import (
    register_online, unregister_online, get_online_ws, is_agent_online,
    register_or_update_session, update_heartbeat, mark_offline, list_sessions,
    execute_command_via_tunnel, resolve_exec_future, start_heartbeat_monitor,
    get_outgoing_queue, send_to_agent, get_pending_commands,
)
from app.logger import logger

router = APIRouter(prefix="/edge", tags=["edge-tunnel"])


# ─── edge agent 拨入 WebSocket ───────────────────────────────

@router.websocket("/tunnel/connect")
async def edge_tunnel_connect(websocket: WebSocket):
    """edge agent 主动拨出接入点。

    握手协议：
    1. edge agent 连接后发 {"type":"register", "agent_id":..., "tunnel_token":..., "hostname":..., "os_type":..., "ip_addresses":[...], "agent_version":...}
    2. 云端校验 tunnel_token，注册 EdgeSession，回 {"type":"registered", "session_id":...}
    3. 之后 edge agent 每 30s 发 {"type":"heartbeat"}
    4. 云端可发 {"type":"exec", "command":..., "log_id":..., "timeout":...}
    5. edge agent 回 {"type":"exec_result", "log_id":..., "exit_code":..., "stdout":..., "stderr":...}
    6. WebSSH 终端流量: {"type":"pty_open", "cols":..., "rows":...} / {"type":"pty_input", "data":...} / {"type":"pty_output", "data":...} / {"type":"pty_resize", "cols":..., "rows":...} / {"type":"pty_close"}
    """
    await websocket.accept()
    from app.database import get_session_for, get_db_mode

    agent_id = None
    incoming_queue = asyncio.Queue()

    # 独立 reader task：持续读取 incoming 消息，避免取消 receive_text 导致消息丢失
    async def _reader():
        try:
            while True:
                raw = await websocket.receive_text()
                await incoming_queue.put(raw)
        except WebSocketDisconnect:
            await incoming_queue.put(None)  # 哨兵通知主循环退出
        except Exception as e:
            logger.warning(f"edge tunnel reader 异常: {e}")
            await incoming_queue.put(None)

    reader_task = asyncio.create_task(_reader())

    try:
        while True:
            # 1. 处理 outgoing 队列（非阻塞）
            if agent_id:
                queue = get_outgoing_queue(agent_id)
                if queue and not queue.empty():
                    while not queue.empty():
                        try:
                            msg_out = queue.get_nowait()
                            if msg_out is not None:
                                await websocket.send_json(msg_out)
                        except Exception:
                            break

            # 2. 从 incoming 队列读取消息（带短 timeout 以便及时处理 outgoing）
            try:
                raw = await asyncio.wait_for(incoming_queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                continue

            if raw is None:  # reader 退出哨兵
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "register":
                agent_id = msg.get("agent_id", "")
                tunnel_token = msg.get("tunnel_token", "")
                if not agent_id:
                    await websocket.send_json({"type": "error", "message": "agent_id required"})
                    continue

                db = get_session_for(get_db_mode())()
                try:
                    session = register_or_update_session(
                        db, agent_id,
                        hostname=msg.get("hostname", ""),
                        os_type=msg.get("os_type", "linux"),
                        ip_addresses=msg.get("ip_addresses", []),
                        agent_version=msg.get("agent_version", ""),
                        tunnel_token=tunnel_token,
                    )
                    register_online(agent_id, websocket, session.id)
                    await websocket.send_json({
                        "type": "registered",
                        "session_id": session.id,
                        "agent_id": agent_id,
                    })
                    logger.info(f"Edge agent 注册成功: agent_id={agent_id} session_id={session.id}")
                finally:
                    db.close()

            elif msg_type == "heartbeat":
                if not agent_id:
                    continue
                db = get_session_for(get_db_mode())()
                try:
                    update_heartbeat(db, agent_id)
                finally:
                    db.close()
                await websocket.send_json({"type": "heartbeat_ack", "ts": datetime.now().isoformat()})

            elif msg_type == "exec_result":
                log_id = msg.get("log_id")
                logger.info(f"收到 edge agent exec_result: log_id={log_id} exit_code={msg.get('exit_code')}")
                resolve_exec_future(log_id, {
                    "exit_code": msg.get("exit_code", -1),
                    "stdout": msg.get("stdout", ""),
                    "stderr": msg.get("stderr", ""),
                })

            elif msg_type == "pty_output":
                pty_id = msg.get("pty_id")
                _forward_pty_output(pty_id, msg.get("data", ""))

            elif msg_type == "pty_exit":
                pty_id = msg.get("pty_id")
                _finish_pty(pty_id, msg.get("exit_code", 0))

    except WebSocketDisconnect:
        logger.info(f"Edge agent WebSocket 断开: agent_id={agent_id}")
    except Exception as e:
        logger.error(f"Edge tunnel 异常: {e}")
    finally:
        reader_task.cancel()
        if agent_id:
            db = get_session_for(get_db_mode())()
            try:
                mark_offline(db, agent_id)
            finally:
                db.close()


# ─── PTY 会话转发池（WebSSH 用）──────────────────────

_PTY_SESSIONS: dict = {}  # pty_id -> {"ws_browser": WebSocket, "future": asyncio.Future}
_PTY_LOCK = asyncio.Lock()


async def register_pty(pty_id: str, ws_browser: WebSocket):
    async with _PTY_LOCK:
        _PTY_SESSIONS[pty_id] = {"ws_browser": ws_browser}


async def unregister_pty(pty_id: str):
    async with _PTY_LOCK:
        _PTY_SESSIONS.pop(pty_id, None)


def _forward_pty_output(pty_id: str, data: str):
    """edge agent 回传的 PTY 输出转发给浏览器。"""
    if not pty_id:
        return
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(_async_forward_pty(pty_id, data))


async def _async_forward_pty(pty_id: str, data: str):
    session = _PTY_SESSIONS.get(pty_id)
    if session and session.get("ws_browser"):
        try:
            await session["ws_browser"].send_text(data)
        except Exception:
            pass


def _finish_pty(pty_id: str, exit_code: int):
    session = _PTY_SESSIONS.get(pty_id)
    if session and session.get("future") and not session["future"].done():
        session["future"].set_result({"exit_code": exit_code})


# ─── 管理 API ─────────────────────────────────────────────

def _get_user_id(request: Request):
    return request.session.get("user_id")


def _require_admin(request: Request, db: Session):
    user_id = _get_user_id(request)
    if not user_id:
        return None, JSONResponse({"error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
        return None, JSONResponse({"error": "需要管理员权限"}, status_code=403)
    return user_id, None


@router.get("/commands/pending")
def get_pending(agent_id: str = Query(...), db: Session = Depends(get_db)):
    """edge agent 轮询获取待执行命令（HTTP 轮询模式）。"""
    # 同时更新心跳
    from app.services.edge_tunnel_service import update_heartbeat
    update_heartbeat(db, agent_id)
    cmds = get_pending_commands(agent_id)
    if cmds:
        logger.info(f"edge agent {agent_id} 轮询取走 {len(cmds)} 条命令")
    return {"commands": cmds}


@router.get("/sessions")
def list_all_sessions(request: Request, db: Session = Depends(get_db),
                      online_only: bool = Query(False)):
    sessions = list_sessions(db, online_only=online_only)
    return {
        "total": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "agent_id": s.agent_id,
                "asset_id": s.asset_id,
                "hostname": s.hostname,
                "os_type": s.os_type,
                "ip_addresses": s.get_ip_addresses(),
                "agent_version": s.agent_version,
                "status": s.status,
                "online": is_agent_online(s.agent_id),
                "last_heartbeat_at": s.last_heartbeat_at.isoformat() if s.last_heartbeat_at else None,
                "connected_at": s.connected_at.isoformat() if s.connected_at else None,
                "disconnected_at": s.disconnected_at.isoformat() if s.disconnected_at else None,
                "reconnect_count": s.reconnect_count,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    }


@router.get("/sessions/online")
def list_online(request: Request, db: Session = Depends(get_db)):
    sessions = list_sessions(db, online_only=True)
    return {
        "total": len(sessions),
        "sessions": [
            {
                "id": s.id, "agent_id": s.agent_id, "hostname": s.hostname,
                "os_type": s.os_type, "ip_addresses": s.get_ip_addresses(),
                "asset_id": s.asset_id,
                "last_heartbeat_at": s.last_heartbeat_at.isoformat() if s.last_heartbeat_at else None,
            }
            for s in sessions
        ],
    }


@router.get("/agents/manifest")
def agents_manifest(request: Request, db: Session = Depends(get_db)):
    """前端精简清单（在线 + 离线都列）。"""
    sessions = list_sessions(db, online_only=False)
    return {
        "total": len(sessions),
        "online_count": sum(1 for s in sessions if is_agent_online(s.agent_id)),
        "agents": [
            {
                "agent_id": s.agent_id,
                "hostname": s.hostname,
                "os_type": s.os_type,
                "status": s.status,
                "online": is_agent_online(s.agent_id),
                "asset_id": s.asset_id,
                "asset_name": db.query(Asset).filter(Asset.id == s.asset_id).first().name if s.asset_id else "",
            }
            for s in sessions
        ],
    }


@router.post("/sessions/{session_id}/bind")
async def bind_asset(session_id: int, request: Request, db: Session = Depends(get_db)):
    uid, err = _require_admin(request, db)
    if err:
        return err
    data = await request.json()
    asset_id = data.get("asset_id")
    session = db.query(EdgeSession).filter(EdgeSession.id == session_id).first()
    if not session:
        return JSONResponse({"error": "session 不存在"}, status_code=404)
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return JSONResponse({"error": "asset 不存在"}, status_code=404)
    session.asset_id = asset_id
    asset.edge_agent_id = session.agent_id
    db.commit()
    return {"status": "ok", "asset_id": asset_id, "agent_id": session.agent_id}


@router.post("/command")
async def execute_command(request: Request, db: Session = Depends(get_db)):
    """通过反向隧道执行命令（同步等待结果）。"""
    user_id = _get_user_id(request)
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    user = db.query(User).filter(User.id == user_id).first()
    data = await request.json()
    agent_id = data.get("agent_id", "")
    command = data.get("command", "")
    timeout = data.get("timeout", 30)
    if not agent_id or not command:
        return JSONResponse({"error": "agent_id 和 command 必填"}, status_code=400)
    if not is_agent_online(agent_id):
        return JSONResponse({"error": "edge agent 不在线"}, status_code=400)
    client_ip = request.client.host if request.client else ""
    result = await execute_command_via_tunnel(
        db, agent_id, command, user_id, user.username if user else "", client_ip, timeout
    )
    return result


@router.get("/commands")
def list_commands(
    request: Request,
    db: Session = Depends(get_db),
    session_id: int = Query(None),
    limit: int = Query(50, le=200),
):
    q = db.query(EdgeCommandLog)
    if session_id:
        q = q.filter(EdgeCommandLog.session_id == session_id)
    logs = q.order_by(EdgeCommandLog.created_at.desc()).limit(limit).all()
    return {
        "total": len(logs),
        "commands": [
            {
                "id": l.id,
                "session_id": l.session_id,
                "user_id": l.user_id,
                "username": l.username,
                "command": l.command,
                "exit_code": l.exit_code,
                "stdout": (l.stdout or "")[:500],
                "stderr": (l.stderr or "")[:500],
                "duration_ms": l.duration_ms,
                "status": l.status,
                "client_ip": l.client_ip,
                "created_at": l.created_at.isoformat(),
                "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            }
            for l in logs
        ],
    }


@router.post("/tokens")
async def generate_token(request: Request, db: Session = Depends(get_db)):
    """生成 tunnel_token（admin）。edge agent 拨出时携带此 token。"""
    uid, err = _require_admin(request, db)
    if err:
        return err
    token = secrets.token_urlsafe(32)
    return {"tunnel_token": token, "usage": "在 edge agent 配置文件中填入此 token"}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    uid, err = _require_admin(request, db)
    if err:
        return err
    session = db.query(EdgeSession).filter(EdgeSession.id == session_id).first()
    if not session:
        return JSONResponse({"error": "session 不存在"}, status_code=404)
    # 解绑 asset
    if session.asset_id:
        asset = db.query(Asset).filter(Asset.id == session.asset_id).first()
        if asset:
            asset.edge_agent_id = ""
    # 删除命令日志
    db.query(EdgeCommandLog).filter(EdgeCommandLog.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"status": "ok"}
