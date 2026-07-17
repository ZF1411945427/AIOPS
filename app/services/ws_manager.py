"""
WebSocket 连接管理器
支持房间/频道模式，前端按 room 订阅实时消息
"""
import asyncio
import json
from typing import Dict, Set
from fastapi import WebSocket
from app.logger import logger


class ConnectionManager:
    _instance = None

    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = {}

    @classmethod
    def get_instance(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def connect(self, websocket: WebSocket, room: str = "default"):
        await websocket.accept()
        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(websocket)
        logger.info(f"WS connect: room={room}, total={len(self.rooms[room])}")

    def disconnect(self, websocket: WebSocket, room: str = "default"):
        if room in self.rooms:
            self.rooms[room].discard(websocket)
            if not self.rooms[room]:
                del self.rooms[room]

    async def broadcast(self, room: str, message: dict):
        if room not in self.rooms:
            return
        dead = set()
        for ws in self.rooms[room]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.rooms[room].discard(ws)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception:
            pass

    def room_size(self, room: str) -> int:
        return len(self.rooms.get(room, set()))

    async def publish_alert(self, alert_data: dict, user_ids: list = None):
        """推送告警到指定用户频道，user_ids 为空则广播到所有 alert: 开头的房间."""
        if user_ids:
            for uid in user_ids:
                await self.broadcast(f"alert:{uid}", {"type": "alert", "data": alert_data})
        else:
            for room in list(self.rooms.keys()):
                if room.startswith("alert:"):
                    await self.broadcast(room, {"type": "alert", "data": alert_data})


ws_manager = ConnectionManager.get_instance()
