import asyncio
from typing import List, Optional

from aiohttp import web

from services.danmaku_service import DanmakuCollector


class AppState:
    """全局应用状态：弹幕采集、WebSocket 客户端、广播任务"""

    def __init__(self) -> None:
        self.collector: Optional[DanmakuCollector] = None
        self.ws_clients: List[web.WebSocketResponse] = []
        self.broadcast_task: Optional[asyncio.Task] = None

