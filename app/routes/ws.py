from aiohttp import web

from state import AppState


async def ws_danmaku(req: web.Request) -> web.WebSocketResponse:
    """WebSocket 弹幕推送端点"""
    state: AppState = req.app["state"]
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    state.ws_clients.append(ws)
    try:
        async for _ in ws:
            pass
    finally:
        if ws in state.ws_clients:
            state.ws_clients.remove(ws)
    return ws

