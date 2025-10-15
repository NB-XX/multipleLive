import logging
import sys
from pathlib import Path

from aiohttp import web

# 将 vendored 的依赖加入 sys.path
root_dir = Path(__file__).resolve().parents[1]
vendor_path = (root_dir / "vendor").as_posix()
legacy_blivedm_path = (root_dir / "blivedm").as_posix()
for p in (vendor_path, legacy_blivedm_path):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.routes.api import api_resolve, api_start_dm, api_stop  # noqa: E402
from app.routes.static import index  # noqa: E402
from app.routes.ws import ws_danmaku  # noqa: E402
from app.state import AppState  # noqa: E402


def create_app() -> web.Application:
    """创建并配置 aiohttp 应用"""
    app = web.Application()
    app["state"] = AppState()

    # 路由注册
    app.router.add_get('/', index)
    app.router.add_get('/ws/danmaku', ws_danmaku)
    app.router.add_post('/api/resolve', api_resolve)
    app.router.add_post('/api/danmaku/start', api_start_dm)
    app.router.add_post('/api/stop', api_stop)

    return app


def configure_logging() -> None:
    """配置彩色日志与过滤"""
    class ColorFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': '\x1b[38;5;245m',
            'INFO': '\x1b[38;5;39m',
            'WARNING': '\x1b[38;5;214m',
            'ERROR': '\x1b[38;5;203m',
            'CRITICAL': '\x1b[38;5;199m',
        }
        RESET = '\x1b[0m'

        def format(self, record: logging.LogRecord) -> str:
            color = self.COLORS.get(record.levelname, '')
            msg = super().format(record)
            return f"{color}{msg}{self.RESET}"

    logging.basicConfig(level=logging.INFO, force=True)
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter(fmt='%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S'))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)

    # 降低第三方噪声
    logging.getLogger('blivedm').setLevel(logging.ERROR)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.server').setLevel(logging.INFO)
    logging.getLogger('multiplelive').setLevel(logging.INFO)


if __name__ == '__main__':
    configure_logging()
    logging.info('MultipleLive server starting on http://127.0.0.1:8090')
    web.run_app(create_app(), host='127.0.0.1', port=8090)
