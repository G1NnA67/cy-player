#!/bin/zsh
set -eu
ROOT="${0:A:h:h}"
export YINGZHOU_ROOT="$ROOT"
export TMPDIR="$ROOT/tmp"
export XDG_CACHE_HOME="$ROOT/cache"
export PYTHONPYCACHEPREFIX="$ROOT/cache/pycache"
export PYINSTALLER_CONFIG_DIR="$ROOT/cache/pyinstaller"
cd "$ROOT/project"
"$ROOT/runtime/python/bin/python3" -m PyInstaller --noconfirm --windowed --name "CY Player" \
  --add-data "$ROOT/project/icon.png:." --icon "$ROOT/project/AppIcon.icns" \
  --osx-bundle-identifier local.yingzhou.player \
  --distpath "$ROOT/dist" --workpath "$ROOT/tmp/build" --specpath "$ROOT/tmp" \
  --collect-all imageio_ffmpeg --collect-all yt_dlp_ejs --collect-submodules yt_dlp \
  --hidden-import download_worker --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick \
  --exclude-module tkinter app.py
