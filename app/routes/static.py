from pathlib import Path

from aiohttp import web


async def index(_req: web.Request) -> web.Response:
    """提供前端首页"""
    html = Path("web/index.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")

