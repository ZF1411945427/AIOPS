"""浏览器 WebSSH WebSocket — 通过反向隧道连到 edge agent 的 PTY。

流程：
  浏览器 ─(WebSocket)─> /webssh/{agent_id} ─(查找 edge agent ws)─> 发 pty_open 给 edge agent
  edge agent ─> 启动本地 PTY ─> pty_output 回传 ─> 转发给浏览器
  浏览器按键 ─> pty_input ─> edge agent ─> PTY

支持：
  - xterm.js 兼容（浏览器侧用 xterm.js 渲染）
  - 终端 resize（pty_resize）
  - 断线自动清理
"""
import json
import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EdgeSession, EdgeCommandLog, User
from app.services.edge_tunnel_service import get_online_ws, is_agent_online, send_to_agent
from app.routers.edge_tunnel import register_pty, unregister_pty
from app.logger import logger

router = APIRouter(prefix="/webssh", tags=["webssh"])


def _verify_token(token: str) -> int:
    """校验 WebSocket query 中的 token，返回 user_id。"""
    if not token:
        return None
    from app.services.mobile_push_service import verify_login_token
    if verify_login_token(token):
        # 解析 user_id（token 是 JWT）
        try:
            import jwt as _jwt
            from app.config import SECRET_KEY
            payload = _jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return payload.get("user_id")
        except Exception:
            return None
    return None


@router.websocket("/{agent_id}")
async def webssh_terminal(websocket: WebSocket, agent_id: str,
                          token: str = Query(""), cols: int = Query(80), rows: int = Query(24)):
    """浏览器 WebSSH 终端。

    query: token=JWT&cols=80&rows=24
    """
    user_id = _verify_token(token)
    if not user_id:
        await websocket.accept()
        await websocket.send_text("\r\n❌ 未认证，请先登录\r\n")
        await websocket.close()
        return

    await websocket.accept()

    # 检查 edge agent 是否在线
    if not is_agent_online(agent_id):
        await websocket.send_text(f"\r\n❌ Edge agent ({agent_id}) 不在线\r\n")
        await websocket.close()
        return

    edge_ws = get_online_ws(agent_id)
    if not edge_ws:
        await websocket.send_text(f"\r\n❌ Edge agent 隧道未建立\r\n")
        await websocket.close()
        return

    pty_id = str(uuid.uuid4())[:8]
    await register_pty(pty_id, websocket)

    # 发 pty_open 给 edge agent（通过 outgoing 队列，跨协程安全）
    try:
        await send_to_agent(agent_id, {
            "type": "pty_open",
            "pty_id": pty_id,
            "cols": cols,
            "rows": rows,
        })
    except Exception as e:
        await websocket.send_text(f"\r\n❌ 隧道通信失败: {e}\r\n")
        await websocket.close()
        return

    # 记录审计日志
    from app.database import get_session_for, get_db_mode
    db = get_session_for(get_db_mode())()
    session = db.query(EdgeSession).filter(EdgeSession.agent_id == agent_id).first()
    log = None
    if session:
        user = db.query(User).filter(User.id == user_id).first()
        log = EdgeCommandLog(
            session_id=session.id,
            user_id=user_id,
            username=user.username if user else "",
            command=f"[WebSSH PTY] agent={agent_id} pty_id={pty_id}",
            status=EdgeCommandLog.STATUS_RUNNING,
            client_ip="",
        )
        db.add(log)
        db.commit()
        db.refresh(log)
    db.close()

    logger.info(f"WebSSH 开启: agent_id={agent_id} pty_id={pty_id} user_id={user_id}")

    try:
        # 浏览器 → edge agent
        async def browser_to_edge():
            try:
                while True:
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        # 纯文本输入（xterm.js 发送按键）
                        await send_to_agent(agent_id, {
                            "type": "pty_input",
                            "pty_id": pty_id,
                            "data": data,
                        })
                        continue
                    m_type = msg.get("type", "")
                    if m_type == "input":
                        await send_to_agent(agent_id, {
                            "type": "pty_input",
                            "pty_id": pty_id,
                            "data": msg.get("data", ""),
                        })
                    elif m_type == "resize":
                        await send_to_agent(agent_id, {
                            "type": "pty_resize",
                            "pty_id": pty_id,
                            "cols": msg.get("cols", 80),
                            "rows": msg.get("rows", 24),
                        })
                    elif m_type == "ping":
                        await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.debug(f"browser_to_edge 异常: {e}")

        # 启动浏览器→edge 转发
        await browser_to_edge()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSSH 异常: {e}")
    finally:
        # 通知 edge agent 关闭 PTY
        try:
            await send_to_agent(agent_id, {"type": "pty_close", "pty_id": pty_id})
        except Exception:
            pass
        await unregister_pty(pty_id)
        # 更新审计日志
        if log:
            db = get_session_for(get_db_mode())()
            try:
                log_obj = db.query(EdgeCommandLog).filter(EdgeCommandLog.id == log.id).first()
                if log_obj:
                    log_obj.status = EdgeCommandLog.STATUS_SUCCESS
                    log_obj.finished_at = __import__("datetime").datetime.now()
                    db.commit()
            finally:
                db.close()
        logger.info(f"WebSSH 关闭: agent_id={agent_id} pty_id={pty_id}")
