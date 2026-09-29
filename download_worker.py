"""A separate process keeps downloads and FFmpeg work off the GUI thread."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from core import root_dir, prepare_environment, validate_url, ffmpeg_executable, UserFacingError


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


class QuietLogger:
    def debug(self, message):
        pass
    def warning(self, message):
        emit("warning", message=str(message))
    def error(self, message):
        pass


def format_options(quality: str, media_type: str, video_format: str) -> dict:
    if quality not in ("best", "1080", "720"):
        raise UserFacingError("无效的画质选项。")
    if media_type not in ("video", "audio"):
        raise UserFacingError("无效的下载类型。")
    if video_format not in ("mp4", "mkv", "webm"):
        raise UserFacingError("无效的视频格式。")
    if media_type == "audio":
        return {
            "format": "bestaudio/best", "final_ext": "mp3",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }
    height = "" if quality == "best" else f"[height<={quality}]"
    if video_format == "mkv":
        selector = f"bv*{height}+ba/b{height}"
    else:
        audio_ext = "m4a" if video_format == "mp4" else "webm"
        selector = f"bv{height}[ext={video_format}]+ba[ext={audio_ext}]/b{height}[ext={video_format}]"
    return {
        "format": selector, "merge_output_format": video_format, "final_ext": video_format,
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": video_format}],
    }


def run(url: str, destination: str, quality: str, media_type: str = "video", video_format: str = "mkv") -> int:
    prepare_environment()
    try:
        os.setsid()  # Cancel the worker and any FFmpeg child together.
    except OSError:
        pass
    try:
        url = validate_url(url)
        folder = Path(destination).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        selected = format_options(quality, media_type, video_format)
        import yt_dlp
        from accelerated_http import accelerated_downloads
        from yt_dlp.postprocessor.common import PostProcessor
        final_files = []

        class CompletedFile(PostProcessor):
            def run(self, info):
                path = Path(info["filepath"]).resolve()
                if path.is_file() and path.suffix.lower() == "." + selected["final_ext"]:
                    final_files.append(str(path))
                return [], info

        last_update = [0.0]
        def progress(data):
            status = data.get("status")
            if status == "finished":
                emit("processing", message="正在转换为 MP3…" if media_type == "audio" else "正在合并或整理视频…")
                return
            if status != "downloading":
                return
            now = time.monotonic()
            if now - last_update[0] < .2:
                return
            last_update[0] = now
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            info = data.get("info_dict") or {}
            emit("progress", title=info.get("title", ""),
                 percent=min(100, downloaded / total * 100) if total else None,
                 downloaded=downloaded, total=total,
                 speed=data.get("speed"), eta=data.get("eta"))

        options = {
            **selected,
            # Separate intermediates so remuxing never deletes another format's completed file.
            "paths": {"home": str(folder), "temp": str(folder / ".cy-downloads" / ("audio" if media_type == "audio" else video_format))},
            "outtmpl": {"default": "%(title).140B [%(id)s]" + (" audio" if media_type == "audio" else " " + video_format.upper()) + ".%(ext)s"},
            "noplaylist": True,
            "playlistend": 1,
            "quiet": True,
            "proxy": "",  # Do not inherit a stale macOS system proxy.
            "no_warnings": False,
            "noprogress": True,
            "logger": QuietLogger(),
            "progress_hooks": [progress],
            "ffmpeg_location": str(ffmpeg_executable()),
            "cachedir": str(root_dir() / "cache/yt-dlp"),
            "socket_timeout": 20,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "skip_unavailable_fragments": False,
            "cy_status": lambda message: emit("status", message=message),
            "overwrites": False,
            "continuedl": True,
        }
        node = root_dir() / "runtime/tools/node"
        if node.is_file():
            options["js_runtimes"] = {"node": {"path": str(node)}}
        emit("status", message="正在读取视频信息…")
        with accelerated_downloads(), yt_dlp.YoutubeDL(options) as downloader:
            downloader.add_post_processor(CompletedFile(), when="after_move")
            downloader.extract_info(url, download=True)
        if not final_files:
            raise UserFacingError("未找到完整的下载文件，请检查链接是否指向单个视频。")
        emit("completed", path=final_files[-1], media_type=media_type)
        return 0
    except Exception as error:
        emit("failed", message=str(error).removeprefix("ERROR: "), code=getattr(error, "message_key", None))
        return 1


if __name__ == "__main__":
    raise SystemExit(run(*sys.argv[1:6]))
