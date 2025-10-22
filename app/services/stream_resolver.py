import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


def get_room_id(url_or_id: str) -> int:
    match = re.search(r'live\.bilibili\.com/(\d+)', url_or_id)
    if match:
        return int(match.group(1))
    elif url_or_id.isdigit():
        return int(url_or_id)
    else:
        raise ValueError("无效的直播间链接或ID")


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15,
                   retries: int = 3, backoff: float = 0.6) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for i in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))
    raise RuntimeError(f"请求失败: {last_err}")


def _build_headers(room_id: int, sessdata: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://live.bilibili.com/{room_id}",
        "Origin": "https://live.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    token = sessdata or os.getenv("BILI_SESSDATA") or ""
    token = token.strip()
    if token:
        headers["Cookie"] = f"SESSDATA={token}"
    return headers


def resolve_room_id(source: str, sessdata: Optional[str] = None) -> int:
    """
    将用户输入的房间（URL/短号/长号）解析为真实 room_id。
    优先调用 room_init 接口获取真实ID，失败则回退 get_room_id。
    """
    try:
        short_or_long = get_room_id(source)
    except Exception:
        raise
    api = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={short_or_long}"
    headers = _build_headers(short_or_long, sessdata)
    try:
        data = _http_get_json(api, headers=headers)
        if data.get('code') == 0 and data.get('data') and data['data'].get('room_id'):
            return int(data['data']['room_id'])
    except Exception:
        pass
    return int(short_or_long)


def _extract_candidates(api_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    try:
        streams = api_data["data"]["playurl_info"]["playurl"]["stream"]
    except Exception:
        return candidates

    for stream in streams or []:
        protocol_name = stream.get("protocol_name") or ""
        for fmt in stream.get("format", []) or []:
            format_name = fmt.get("format_name") or ""
            for codec in fmt.get("codec", []) or []:
                codec_name = codec.get("codec_name") or ""
                base_url = codec.get("base_url") or ""
                url_infos = codec.get("url_info", []) or []
                if not base_url or not url_infos:
                    continue
                ui0 = url_infos[0]
                host = ui0.get("host") or ""
                extra = ui0.get("extra") or ""
                if not host:
                    continue
                full_url = f"{host}{base_url}{extra}"
                candidates.append({
                    "protocol": protocol_name,
                    "format": format_name,
                    "codec": codec_name,
                    "url": full_url,
                })
    return candidates


def _select_best(candidates: List[Dict[str, Any]],
                 prefer_protocol: str = "http_hls",
                 prefer_formats: Optional[List[str]] = None,
                 prefer_codecs: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None
    if prefer_formats is None:
        prefer_formats = ["ts", "fmp4", "flv"]
    if prefer_codecs is None:
        prefer_codecs = ["avc", "h264", "hevc", "av1"]

    def score(c: Dict[str, Any]) -> Tuple[int, int, int]:
        p = 0 if prefer_protocol and prefer_protocol in (c.get("protocol") or "") else 1
        try:
            f = prefer_formats.index((c.get("format") or "").lower())
        except ValueError:
            f = len(prefer_formats)
        codec_l = (c.get("codec") or "").lower()
        if codec_l == "h264":
            codec_l = "avc"
        try:
            k = prefer_codecs.index(codec_l)
        except ValueError:
            k = len(prefer_codecs)
        return (p, f, k)

    return sorted(candidates, key=score)[0]


def get_live_streams(room_id: int, qn: int = 25000, sessdata: Optional[str] = None) -> List[Dict[str, Any]]:
    api = (
        "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
        f"?room_id={room_id}"
        f"&no_playurl=0&mask=1&qn={qn}"
        "&platform=web&protocol=0,1&format=0,1,2&codec=0,1,2&dolby=5&panorama=1&hdr_type=0,1"
    )
    headers = _build_headers(room_id, sessdata)
    data = _http_get_json(api, headers=headers)
    return _extract_candidates(data)


def pick_best_hls(room_id: int, sessdata: Optional[str] = None) -> str:
    prefer_qn = [25000, 20000, 10000, 8000, 400, 250, 150, 80]
    last_err: Optional[Exception] = None
    for qn in prefer_qn:
        try:
            candidates = get_live_streams(room_id, qn=qn, sessdata=sessdata)
            best = _select_best(candidates, prefer_protocol="http_hls")
            if best and best.get("url"):
                return best["url"]
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"未找到可用的直播流候选（最后错误: {last_err}）")


