"""Shared paths and validation. No network or UI work at import time."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

APP_NAME = "CY Player"
VERSION = "0.3.0"


def root_dir() -> Path:
    configured = os.environ.get("YINGZHOU_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        # dist/CY Player.app/Contents/MacOS/CY Player
        return Path(sys.executable).resolve().parents[4]
    source = Path(__file__).resolve().parent
    return source.parent if source.name == "project" else source


def prepare_environment() -> Path:
    root = root_dir()
    for name in ("cache", "tmp", "downloads", "runtime/tools"):
        (root / name).mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(root / "tmp")
    os.environ["XDG_CACHE_HOME"] = str(root / "cache")
    os.environ["PYTHONPYCACHEPREFIX"] = str(root / "cache/pycache")
    os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
    return root


class UserFacingError(ValueError):
    def __init__(self, message_key):
        self.message_key = message_key
        super().__init__(message_key)


def validate_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise UserFacingError("链接格式不正确，请粘贴完整的视频链接。")
    allowed = ("youtube.com", "youtu.be", "bilibili.com", "b23.tv")
    if (parsed.scheme not in ("https", "http") or parsed.username or parsed.password
            or port not in (None, 80, 443)
            or not any(host == site or host.endswith("." + site) for site in allowed)):
        raise UserFacingError("请粘贴 YouTube 或 Bilibili 的视频链接。")
    path = parsed.path.rstrip("/")
    if host == "youtu.be" or host.endswith(".youtu.be") or host == "b23.tv":
        is_video = bool(path.strip("/"))
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        is_video = ((path == "/watch" and bool(parse_qs(parsed.query).get("v", [""])[0]))
                    or any(path.startswith(prefix) and len(path) > len(prefix)
                           for prefix in ("/shorts/", "/live/", "/embed/")))
    else:
        is_video = path.startswith("/video/") and len(path) > len("/video/")
    if not is_video:
        raise UserFacingError("第一版只下载单条视频，请使用视频播放页链接，不要使用频道或播放列表链接。")
    return value


def read_settings() -> dict:
    try:
        data = json.loads((root_dir() / "cache/settings.json").read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_settings(settings: dict) -> None:
    path = root_dir() / "cache/settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), "utf-8")
    temp.replace(path)


def ffmpeg_executable() -> Path:
    """Give yt-dlp a conventional ffmpeg filename; never install globally."""
    import imageio_ffmpeg
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    target = root_dir() / "runtime/tools/ffmpeg"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() and not target.exists():
        target.unlink()
    if not target.exists():
        try:
            target.symlink_to(source)
        except FileExistsError:
            pass  # Another worker may have prepared it concurrently.
    return target


def timestamp(ms: int) -> str:
    seconds = max(0, int(ms)) // 1000
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
