import os
from pathlib import Path

from aiohttp import web


def _locate_web_index() -> Path:
    """动态定位 web/index.html，兼容开发环境与 pyfuze 打包后的解压路径"""
    # 优先使用 PYFUZE 环境变量（打包后的 src 目录）
    if "PYFUZE_EXECUTABLE_PATH" in os.environ:
        # 打包后工作目录在 <unzip>/src，web/ 也在 src/web/
        return Path.cwd() / "web" / "index.html"
    # 开发环境：从项目根查找
    root = Path(__file__).resolve().parents[2]  # app/routes/static.py -> 根
    return root / "web" / "index.html"


async def index(_req: web.Request) -> web.Response:
    """提供前端首页"""
    html = _locate_web_index().read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")

