import asyncio
import json
import logging
from typing import Dict, List

from aiohttp import web

from app.services.danmaku_service import DanmakuItem
from app.services.stream_resolver import pick_best_hls, resolve_room_id
from app.state import AppState

logger = logging.getLogger('multiplelive')


async def api_resolve(req: web.Request) -> web.Response:
    """解析房间 URL/ID 为 m3u8 直链，同时返回真实 room_id"""
    payload = await req.json()
    source = str(payload.get('source', '')).strip()
    sessdata = str(payload.get('sessdata', '')).strip() or None
    if not source:
        return web.json_response({"ok": False, "error": "empty source"}, status=400)
    try:
        if source.startswith('http://') or source.startswith('https://'):
            return web.json_response({"ok": True, "url": source, "room_id": None})
        rid = resolve_room_id(source, sessdata=sessdata)
        url = pick_best_hls(rid, sessdata=sessdata)
        return web.json_response({"ok": True, "url": url, "room_id": rid})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_start_dm(req: web.Request) -> web.Response:
    """启动多房间弹幕采集并通过 WebSocket 广播"""
    state: AppState = req.app["state"]
    payload = await req.json()
    sessdata = None
    try:
        sessdata = str(payload.get('sessdata', '')).strip() or None
    except Exception:
        pass
    rooms: List[int] = [resolve_room_id(str(x), sessdata=sessdata) for x in payload.get("rooms", [])]

    # 支持颜色键为URL/ID字符串
    raw_colors = payload.get("colors", {}) or {}
    color_map: Dict[int, str] = {}
    for k, v in raw_colors.items():
        try:
            rid = resolve_room_id(str(k), sessdata=sessdata)
            color_map[rid] = str(v)
        except Exception as e:
            logger.warning(f"Failed to parse color key={k}: {e}")
            continue

    if state.collector:
        await state.collector.stop()

    from app.services.danmaku_service import DanmakuCollector
    state.collector = DanmakuCollector(rooms, color_map=color_map)

    async def broadcast_loop() -> None:
        assert state.collector is not None
        first_dm_logged = False
        while True:
            item: DanmakuItem = await state.collector.queue.get()
            # 仅首次打印样本
            if not first_dm_logged:
                logger.info(f"First DM sample: room={item.room_id} color={item.color} msg={item.msg[:20]}")
                first_dm_logged = True
            msg = json.dumps(item.__dict__, ensure_ascii=False)
            to_remove: List[web.WebSocketResponse] = []
            for client in state.ws_clients:
                try:
                    await client.send_str(msg)
                except Exception:
                    to_remove.append(client)
            for c in to_remove:
                if c in state.ws_clients:
                    state.ws_clients.remove(c)

    # 启动 collector 与广播
    if state.broadcast_task:
        state.broadcast_task.cancel()
    state.broadcast_task = asyncio.create_task(broadcast_loop())
    asyncio.create_task(state.collector.start())
    logger.info(f"Danmaku started rooms={rooms} colors={color_map}")
    return web.json_response({"ok": True})


async def api_stop(req: web.Request) -> web.Response:
    """停止弹幕采集与广播"""
    state: AppState = req.app["state"]
    if state.collector:
        await state.collector.stop()
        state.collector = None
    if state.broadcast_task:
        state.broadcast_task.cancel()
        state.broadcast_task = None
    logger.info("Stopped all services")
    return web.json_response({"ok": True})

