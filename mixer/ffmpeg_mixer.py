import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional


def which_ffmpeg() -> str:
    """
    查找 ffmpeg 可执行文件。优先使用环境变量 FFMPEG_PATH，否则查 PATH。
    """
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("未找到 ffmpeg，请安装并加入 PATH，或设置 FFMPEG_PATH 环境变量")
    return found


class FFmpegMixer:
    def __init__(
        self,
        video_url: str,
        audio_url: str,
        output: str = "out/mixed/playlist.m3u8",
        output_type: str = "hls",  # hls 或 rtmp
        low_latency: bool = True,
        transcode_video: bool = False,
        audio_bitrate: str = "160k",
        hls_time: int = 2,
        hls_list_size: int = 6,
        delete_segments: bool = True,
    ) -> None:
        self.video_url = video_url
        self.audio_url = audio_url
        self.output = output
        self.output_type = output_type
        self.low_latency = low_latency
        self.transcode_video = transcode_video
        self.audio_bitrate = audio_bitrate
        self.hls_time = hls_time
        self.hls_list_size = hls_list_size
        self.delete_segments = delete_segments

        self._proc: Optional[subprocess.Popen] = None
        self._watcher: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    def _ensure_output_dir(self) -> None:
        if self.output_type == "hls":
            m3u8_path = Path(self.output)
            m3u8_dir = m3u8_path.parent
            m3u8_dir.mkdir(parents=True, exist_ok=True)

    def _build_cmd(self) -> List[str]:
        ffmpeg_bin = which_ffmpeg()
        cmd: List[str] = [ffmpeg_bin, "-loglevel", "info"]

        # 输入优化：尽可能降低缓冲，提升实时性
        # 为每个输入添加队列，避免阻塞
        input_common = [
            "-rw_timeout", "15000000",  # 15s
            "-thread_queue_size", "1024",
        ]
        if self.low_latency:
            # 尽可能少缓存
            input_common += ["-fflags", "nobuffer"]

        # 针对B站HLS添加UA/Referer等HTTP头，并启用网络重连
        header_opts = [
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "-headers", "Referer: https://live.bilibili.com/\r\nOrigin: https://live.bilibili.com\r\n",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_on_network_error", "1",
            "-http_persistent", "1",
        ]

        cmd += input_common + header_opts + ["-i", self.video_url]
        cmd += input_common + header_opts + ["-i", self.audio_url]

        # 映射：0号输入的视频 + 1号输入的音频
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]

        # 编码器：视频尽量copy，音频统一aac
        if self.transcode_video:
            cmd += [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-tune", "zerolatency",
                "-pix_fmt", "yuv420p",
                "-g", "48",
                "-keyint_min", "48",
                "-sc_threshold", "0",
                "-x264-params", "keyint=48:min-keyint=48:scenecut=0",
            ]
        else:
            cmd += ["-c:v", "copy"]

        cmd += [
            "-c:a", "aac",
            "-b:a", self.audio_bitrate,
            "-ar", "48000",
            "-ac", "2",
        ]

        if self.low_latency:
            cmd += ["-flush_packets", "1", "-max_delay", "0"]

        if self.output_type == "hls":
            self._ensure_output_dir()
            hls_flags = ["independent_segments"]
            if self.delete_segments:
                hls_flags.append("delete_segments")
            if self.low_latency:
                # 非LL-HLS的轻量低延迟参数
                cmd += ["-use_wallclock_as_timestamps", "1"]
            cmd += [
                "-f", "hls",
                "-hls_time", str(self.hls_time),
                "-hls_list_size", str(self.hls_list_size),
                "-hls_flags", "+".join(hls_flags),
                self.output,
            ]
        elif self.output_type == "rtmp":
            # 输出FLV容器以便推流
            cmd += ["-f", "flv", self.output]
        else:
            raise ValueError(f"不支持的输出类型: {self.output_type}")

        return cmd

    def start(self, auto_restart: bool = True, restart_backoff: float = 1.0, max_backoff: float = 30.0) -> None:
        """
        启动 ffmpeg 进程；当异常退出时可选自动重启。
        """
        self._stop_flag.clear()

        def run_loop() -> None:
            backoff = restart_backoff
            while not self._stop_flag.is_set():
                cmd = self._build_cmd()
                creationflags = 0
                if sys.platform.startswith("win"):
                    # 隐藏多余窗口（可选）
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                try:
                    # 准备日志
                    log_dir = Path(self.output).parent if self.output_type == "hls" else Path("out")
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_path = log_dir / "ffmpeg-mix.log"
                    log_fp = open(log_path, "a", encoding="utf-8", errors="ignore")

                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        creationflags=creationflags,
                        text=True,
                        encoding="utf-8",
                        errors="ignore",
                    )
                except Exception:
                    # 启动失败，按退避重试
                    time.sleep(backoff)
                    backoff = min(max_backoff, backoff * 2)
                    continue

                # 读取输出并等待退出
                try:
                    assert self._proc is not None
                    for line in self._proc.stdout or []:
                        try:
                            log_fp.write(line)
                        except Exception:
                            pass
                        if self._stop_flag.is_set():
                            break
                        # 将关键报错打印到控制台，便于快速定位
                        if (
                            "Error" in line
                            or "HTTP error" in line
                            or "403" in line
                            or "404" in line
                        ):
                            print(line.rstrip())
                    self._proc.wait()
                finally:
                    self._proc = None
                    try:
                        log_fp.flush()
                        log_fp.close()
                    except Exception:
                        pass

                if not auto_restart or self._stop_flag.is_set():
                    break
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 2)

        self._watcher = threading.Thread(target=run_loop, name="ffmpeg-mix", daemon=True)
        self._watcher.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_flag.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                t0 = time.time()
                while time.time() - t0 < timeout:
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if self._proc.poll() is None:
                    self._proc.kill()
            finally:
                self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


def start_mix(
    video_url: str,
    audio_url: str,
    output: str = "out/mixed/playlist.m3u8",
    output_type: str = "hls",
    low_latency: bool = True,
    transcode_video: bool = False,
) -> FFmpegMixer:
    mixer = FFmpegMixer(
        video_url=video_url,
        audio_url=audio_url,
        output=output,
        output_type=output_type,
        low_latency=low_latency,
        transcode_video=transcode_video,
    )
    mixer.start()
    return mixer


