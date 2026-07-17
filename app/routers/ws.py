import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.ws_manager import ws_manager

router = APIRouter()


def _get_user_id_from_token(token: str) -> int:
    """从 Bearer token 提取 user_id（Token 格式: base64(user_id:timestamp），简化版）."""
    if not token:
        return 0
    try:
        import base64
        decoded = base64.b64decode(token).decode("utf-8", errors="ignore")
        uid = int(decoded.split(":")[0])
        return uid
    except Exception:
        return 0


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, token: str = Query("")):
    """WebSocket 实时告警推送.
    连接时从 token 提取 user_id，加入 alert:{user_id} 房间。
    服务器在告警触发时向该房间广播，前端实时收到新告警并插入列表顶部。
    """
    user_id = _get_user_id_from_token(token)
    room = f"alert:{user_id}"
    await ws_manager.connect(websocket, room=room)
    try:
        await websocket.send_json({"type": "connected", "msg": "告警频道已连接", "user_id": user_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room=room)
    except Exception:
        ws_manager.disconnect(websocket, room=room)


@router.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket, token: str = Query("")):
    """WebSocket 实时推送 AI 智能体消息"""
    await ws_manager.connect(websocket, room="agent")
    try:
        await websocket.send_json({"type": "connected", "msg": "WebSocket 已连接"})
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            room = payload.get("room", "agent")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room="agent")
    except Exception:
        ws_manager.disconnect(websocket, room="agent")


@router.websocket("/ws/correlation")
async def ws_correlation(websocket: WebSocket, token: str = Query("")):
    """
    WebSocket 关联分析实时推送.
    每 30 秒推送一次心跳 + 当前时间戳，前端收到后判断是否需要重新拉取全量数据。
    前端也可主动发送 {"action":"ping"} 保活或 {"action":"refresh","hours":1} 请求刷新。
    """
    await ws_manager.connect(websocket, room="correlation")
    try:
        await websocket.send_json({"type": "connected", "msg": "关联分析频道已连接"})
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                payload = json.loads(data)
                action = payload.get("action", "")
                if action == "ping":
                    await websocket.send_json({"type": "pong", "ts": datetime.now().isoformat()})
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "heartbeat",
                    "ts": datetime.now().isoformat(),
                    "interval_seconds": 30,
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room="correlation")
    except Exception:
        ws_manager.disconnect(websocket, room="correlation")
