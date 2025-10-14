import argparse
import json
import webbrowser
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="混合直播 CLI")
    parser.add_argument('--audio', required=True, help='音频来源：房间URL/ID或直接m3u8')
    parser.add_argument('--video', required=True, help='视频来源：房间URL/ID或直接m3u8')
    parser.add_argument('--rooms', nargs='*', default=[], help='参与弹幕的房间：URL或ID，空则仅audio/video两房间')
    parser.add_argument('--colors', nargs='*', default=[], help='房间颜色映射，格式 roomId=#RRGGBB')
    parser.add_argument('--server', default='http://127.0.0.1:8090', help='后端服务地址')
    parser.add_argument('--open', action='store_true', help='启动后打开网页播放器')
    args = parser.parse_args()

    # 启动混流
    r = requests.post(f"{args.server}/api/mix", json={
        "audio": args.audio,
        "video": args.video,
        "output_type": "hls",
        "low_latency": True,
        "transcode_video": False,
    })
    r.raise_for_status()
    print("mix started:", r.json())

    # 组织弹幕房间/颜色
    rooms = list(args.rooms)
    if not rooms:
        rooms = [args.audio, args.video]
    colors = {}
    for kv in args.colors:
        if '=' in kv:
            k, v = kv.split('=', 1)
            colors[k] = v

    r = requests.post(f"{args.server}/api/danmaku/start", json={
        "rooms": rooms,
        "colors": colors,
    })
    r.raise_for_status()
    print("danmaku started")

    if args.open:
        url = f"{args.server}/?src=/out/mixed/playlist.m3u8"
        webbrowser.open(url)


if __name__ == '__main__':
    main()


