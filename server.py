import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 将 vendored 的 blivedm 包根路径加入 sys.path，确保可导入 blivedm
_vendor_path = (Path(__file__).resolve().parent / "blivedm").as_posix()
if _vendor_path not in sys.path:
    sys.path.insert(0, _vendor_path)

from aiohttp import web

from bili_live_parser import get_room_id, pick_best_hls
from danmaku.collector import DanmakuCollector, DanmakuItem
from mixer.ffmpeg_mixer import FFmpegMixer


class AppState:
    def __init__(self) -> None:
        self.mixer: Optional[FFmpegMixer] = None
        self.collector: Optional[DanmakuCollector] = None
        self.ws_clients: List[web.WebSocketResponse] = []
        self.broadcast_task: Optional[asyncio.Task] = None
        # DPlayer 兼容弹幕内存池：id -> [[time, type, color, author, text], ...]
        self.dplayer_pool: Dict[str, List[list]] = {}

    def append_dplayer(self, pool_id: str, author: str, text: str, color_hex: str = "#ffffff",
                       dm_type: int = 0, at_time: float = 0.0, max_size: int = 1000) -> None:
        def to_color_int(hex_str: str) -> int:
            s = (hex_str or "#ffffff").lstrip('#')
            try:
                return int(s, 16)
            except Exception:
                return 0xffffff
        arr = [float(at_time), int(dm_type), to_color_int(color_hex), str(author or ''), str(text or '')]
        buf = self.dplayer_pool.setdefault(pool_id, [])
        buf.append(arr)
        if len(buf) > max_size:
            del buf[:-max_size]


async def index(_req: web.Request) -> web.Response:
    html = Path("web/index.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def static_out(req: web.Request) -> web.FileResponse:
    # 代理 out/mixed 下的 HLS 产物
    rel = req.match_info.get('path')
    file_path = Path("out/mixed").joinpath(rel)
    return web.FileResponse(file_path)


async def ws_danmaku(req: web.Request) -> web.WebSocketResponse:
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


async def api_mix(req: web.Request) -> web.Response:
    state: AppState = req.app["state"]
    payload = await req.json()
    audio = str(payload.get("audio"))  # room id or url
    video = str(payload.get("video"))
    output_type = payload.get("output_type", "hls")
    low_latency = bool(payload.get("low_latency", True))
    transcode_video = bool(payload.get("transcode_video", False))

    def resolve(u: str) -> str:
        if u.startswith("http://") or u.startswith("https://"):
            return u
        rid = get_room_id(u)
        return pick_best_hls(rid)

    audio_url = resolve(audio)
    video_url = resolve(video)

    if state.mixer:
        state.mixer.stop()
    state.mixer = FFmpegMixer(
        video_url=video_url,
        audio_url=audio_url,
        output="out/mixed/playlist.m3u8" if output_type == "hls" else payload.get("rtmp", ""),
        output_type=output_type,
        low_latency=low_latency,
        transcode_video=transcode_video,
    )
    state.mixer.start()
    return web.json_response({"ok": True, "audio": audio_url, "video": video_url})


async def api_start_dm(req: web.Request) -> web.Response:
    state: AppState = req.app["state"]
    payload = await req.json()
    rooms: List[int] = [get_room_id(str(x)) for x in payload.get("rooms", [])]
    # 支持颜色键为URL/ID字符串
    raw_colors = payload.get("colors", {}) or {}
    color_map: Dict[int, str] = {}
    for k, v in raw_colors.items():
        try:
            rid = get_room_id(str(k))
            color_map[rid] = str(v)
        except Exception:
            continue

    if state.collector:
        await state.collector.stop()

    state.collector = DanmakuCollector(rooms, color_map=color_map)

    async def broadcast_loop() -> None:
        assert state.collector is not None
        while True:
            item: DanmakuItem = await state.collector.queue.get()
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
            # 同步写入 DPlayer 内存池，供首次加载拉取历史
            text = f"[{item.room_id}] {item.uname}: {item.msg}"
            state.append_dplayer(
                pool_id="mixed-live-local",
                author=item.uname,
                text=text,
                color_hex=item.color,
                dm_type=0,
                at_time=0.0,
            )

    # 启动 collector 与广播
    if state.broadcast_task:
        state.broadcast_task.cancel()
    state.broadcast_task = asyncio.create_task(broadcast_loop())
    asyncio.create_task(state.collector.start())
    return web.json_response({"ok": True})


async def api_stop(req: web.Request) -> web.Response:
    state: AppState = req.app["state"]
    if state.mixer:
        state.mixer.stop()
        state.mixer = None
    if state.collector:
        await state.collector.stop()
        state.collector = None
    if state.broadcast_task:
        state.broadcast_task.cancel()
        state.broadcast_task = None
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    app = web.Application()
    app["state"] = AppState()
    # 确保静态HLS输出目录存在
    out_dir = Path('out/mixed')
    out_dir.mkdir(parents=True, exist_ok=True)
    app.router.add_get('/', index)
    app.router.add_get('/ws/danmaku', ws_danmaku)
    app.router.add_post('/api/mix', api_mix)
    app.router.add_post('/api/danmaku/start', api_start_dm)
    app.router.add_post('/api/stop', api_stop)
    # 静态代理 out/mixed 目录
    app.router.add_static('/out/mixed/', path=str(out_dir.absolute()), show_index=True)
    # DPlayer 兼容弹幕 API（简单内存实现）
    async def api_dplayer_get(req: web.Request) -> web.Response:
        pool_id = req.query.get('id', 'mixed-live-local')
        try:
            max_len = int(req.query.get('max', '1000'))
        except Exception:
            max_len = 1000
        data = (app["state"].dplayer_pool.get(pool_id, []) or [])[-max_len:]
        return web.json_response({"code": 0, "data": data})

    async def api_dplayer_post(req: web.Request) -> web.Response:
        body = await req.json()
        pool_id = str(body.get('id', 'mixed-live-local'))
        author = str(body.get('author', 'user'))
        text = str(body.get('text', ''))
        color = str(body.get('color', '#ffffff'))
        try:
            dm_type = int(body.get('type', 0))
        except Exception:
            dm_type = 0
        try:
            at_time = float(body.get('time', 0))
        except Exception:
            at_time = 0.0
        app["state"].append_dplayer(pool_id, author, text, color, dm_type, at_time)
        return web.json_response({"code": 0, "data": {}})

    app.router.add_get('/api/dplayer', api_dplayer_get)
    app.router.add_post('/api/dplayer', api_dplayer_post)
    return app


if __name__ == '__main__':
    web.run_app(create_app(), host='127.0.0.1', port=8090)


