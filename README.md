# CY Player

**Chenying Player · 辰映** — a macOS video player with English and Simplified Chinese interfaces, local playback, and single-video downloads from YouTube and Bilibili.

English | [简体中文](README.zh-CN.md)

![CY Player](docs/player-en.png)

## Features

- Switch **English / 简体中文** using **Language / 语言** at the bottom of the sidebar. The preference is saved automatically; switching preserves playback and download state.
- Open or drag in local videos. Play, pause, seek, adjust volume and playback speed, and enter full screen.
- Select embedded audio and subtitle tracks.
- Paste a YouTube or Bilibili video URL, choose a quality limit and destination, monitor progress, cancel, and play the result.
- One download at a time. Incomplete fragments are kept so yt-dlp can attempt to resume.

Playback uses **PySide6 / Qt Multimedia with FFmpeg**. Downloads use **yt-dlp**, **FFmpeg**, and **Node.js** for YouTube JavaScript challenges. A file extension alone does not guarantee codec support.

## Launch on this Mac

Double-click **CY Player.app** in the supplied project folder. Keep the entire folder together: the top-level app shortcut points to the application in `dist`, while Node.js, settings, caches and downloads remain alongside it. The bundled build targets Apple Silicon and macOS 13 or later.

The `启动播放器.command` launcher is an alternative that runs the source with the project-local Python environment.

Settings are stored in `cache/settings.json`; downloads default to `downloads`. Project dependencies and build files stay in the supplied folder. Operating-system logs and application registration are managed by macOS.

## Run from source

Use Python 3.12 or later:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

For this delivery, the source is in `project` and the data root is its parent. For a normal clone, the source directory is the data root. Set `YINGZHOU_ROOT` to override it; this environment variable is retained for compatibility.

For full YouTube support, place Node.js 20 or later at `runtime/tools/node` under the data root. The local delivery already includes it. FFmpeg is supplied by `imageio-ffmpeg` and is linked as `runtime/tools/ffmpeg` when needed. No global installation is required for the supplied build.

## Shortcuts

| Action | Shortcut |
|---|---|
| Open a video | ⌘O |
| Play / pause | Space |
| Seek backward / forward 5 seconds | ← / → |
| Toggle full screen | F or double-click the video |
| Exit full screen | Esc |

## Source layout

- `app.py`: interface, playback, language switching and download process management.
- `i18n.py`: English / Chinese application text.
- `download_worker.py`: isolated download worker with structured progress messages.
- `core.py`: paths, settings, URL validation and FFmpeg discovery.
- `test_core.py`, `test_i18n.py`: validation, preferences, translated states and live-switch regression tests.
- `build_mac.sh`: local PyInstaller build; output goes to the parent folder's `dist` directory.

Tests can run with `QT_QPA_PLATFORM=offscreen python -m unittest discover -p 'test_*.py'`. Tests use isolated temporary settings. The media test uses the local fixture when available or generates a short one with FFmpeg.

## Current limits

- The first version connects directly and does not change system proxy settings.
- Account sign-in, cookie import, batch playlists, external subtitles and automatic updates are not included.
- Private, paid, region-restricted or anti-bot-protected videos may fail. Browser cookies are never read automatically.
- Video and audio may download separately, so progress can restart for the next stream; merging uses an indeterminate indicator.
- App-owned labels and messages follow the language selector. Native macOS file-dialog controls follow the system language; media titles, paths and upstream diagnostic details retain their original text.
- Site changes can require a yt-dlp update. Successful test links do not guarantee every video will work.
- Save only content you are entitled to download.
- The local app has an ad-hoc signature, not an Apple Developer ID signature or notarization. Distribution to other Macs needs separate preparation.

## GitHub

Publish this source directory. Keep runtime dependencies, caches, build outputs, downloaded videos and personal settings out of the repository.

See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency sources and license information. The project owner has not yet selected a license for this project's original code.
