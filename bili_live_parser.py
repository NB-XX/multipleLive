import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import pyperclip

def get_room_id(url_or_id: str) -> int:
    """
    从URL或纯数字中提取B站直播间ID
    """
    match = re.search(r'live\.bilibili\.com/(\d+)', url_or_id)
    if match:
        return int(match.group(1))
    elif url_or_id.isdigit():
        return int(url_or_id)
    else:
        raise ValueError("无效的直播间链接或ID")

def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 8,
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
                # 选择第一个可用的host/extra构建完整URL
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
        # HLS优先TS，再次为FMP4
        prefer_formats = ["ts", "fmp4", "flv"]
    if prefer_codecs is None:
        # 浏览器/解码兼容性：H.264(avc) > HEVC(hevc) > AV1(av1)
        prefer_codecs = ["avc", "h264", "hevc", "av1"]

    def score(c: Dict[str, Any]) -> Tuple[int, int, int]:
        p = 0 if prefer_protocol and prefer_protocol in (c.get("protocol") or "") else 1
        try:
            f = prefer_formats.index((c.get("format") or "").lower())
        except ValueError:
            f = len(prefer_formats)
        # codec_name 可能是 h264/avc/hevc
        codec_l = (c.get("codec") or "").lower()
        # 统一到短名
        if codec_l == "h264":
            codec_l = "avc"
        try:
            k = prefer_codecs.index(codec_l)
        except ValueError:
            k = len(prefer_codecs)
        return (p, f, k)

    return sorted(candidates, key=score)[0]


def get_live_streams(room_id: int, qn: int = 10000) -> List[Dict[str, Any]]:
    """
    返回直播流候选（协议/格式/编解码/URL）
    """
    api = (
        "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
        f"?room_id={room_id}&protocol=0,1&format=0,1,2&codec=0,1"
        f"&qn={qn}&platform=web&ptype=8&dolby=5&panorama=1"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    data = _http_get_json(api, headers=headers)
    return _extract_candidates(data)


def pick_best_hls(room_id: int) -> str:
    candidates = get_live_streams(room_id)
    best = _select_best(candidates, prefer_protocol="http_hls")
    if not best:
        raise RuntimeError("未找到可用的直播流候选")
    return best["url"]


def get_live_stream_url(room_id: int) -> str:
    """
    获取最优HLS播放地址（回溯兼容）
    """
    return pick_best_hls(room_id)

def main():
    print("=== Bilibili 直播流解析 (Python版) ===")
    url_or_id = input("请输入直播间链接或ID：").strip()

    try:
        room_id = get_room_id(url_or_id)
        stream_url = get_live_stream_url(room_id)
        print(f"\n✅ 解析成功：\n{stream_url}\n")

        # 自动复制到剪贴板（Windows/macOS/Linux都支持）
        pyperclip.copy(stream_url)
        print("📋 已复制到剪贴板！")

    except Exception as e:
        print(f"❌ 出错了：{e}")

if __name__ == "__main__":
    main()
