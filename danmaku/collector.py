import asyncio
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import blivedm
import blivedm.models.web as web_models


@dataclass
class DanmakuItem:
    room_id: int
    uname: str
    msg: str
    ts_ms: int
    color: str


class _Handler(blivedm.BaseHandler):
    def __init__(self, out_queue: "asyncio.Queue[DanmakuItem]", color_map: Dict[int, str]):
        super().__init__()
        self._out = out_queue
        self._color_map = color_map

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        color = self._color_map.get(client.room_id, "#ffffff")
        item = DanmakuItem(
            room_id=client.room_id,
            uname=message.uname,
            msg=message.msg,
            ts_ms=int(message.timestamp * 1000) if getattr(message, "timestamp", None) else 0,
            color=color,
        )
        try:
            self._out.put_nowait(item)
        except asyncio.QueueFull:
            # 丢弃最旧
            try:
                self._out.get_nowait()
            except Exception:
                pass
            try:
                self._out.put_nowait(item)
            except Exception:
                pass


class DanmakuCollector:
    def __init__(self, room_ids: Iterable[int], color_map: Optional[Dict[int, str]] = None,
                 queue_maxsize: int = 1024) -> None:
        self.room_ids = list(room_ids)
        self.color_map = color_map or {}
        self.queue: "asyncio.Queue[DanmakuItem]" = asyncio.Queue(maxsize=queue_maxsize)
        self.clients: List[blivedm.BLiveClient] = []

    async def start(self) -> None:
        handler = _Handler(self.queue, self.color_map)
        for rid in self.room_ids:
            client = blivedm.BLiveClient(rid)
            client.set_handler(handler)
            client.start()
            self.clients.append(client)

        # 并行等待，直到手动停止
        await asyncio.gather(*(c.join() for c in self.clients))

    async def stop(self) -> None:
        await asyncio.gather(*(c.stop_and_close() for c in self.clients), return_exceptions=True)


