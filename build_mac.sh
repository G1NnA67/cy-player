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
  --hidden-import download_worker --hidden-import accelerated_http --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick \
  --exclude-module tkinter app.py

"$ROOT/runtime/python/bin/python3" - "$ROOT" <<'PYMETA'
from pathlib import Path
import plistlib,sys
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'project'))
from core import VERSION
p=root/'dist/CY Player.app/Contents/Info.plist'
d=plistlib.loads(p.read_bytes());d.update(CFBundleShortVersionString=VERSION,CFBundleVersion=VERSION,LSMinimumSystemVersion='13.5');p.write_bytes(plistlib.dumps(d))
PYMETA
/usr/bin/xattr -dr com.apple.FinderInfo "$ROOT/dist/CY Player.app"
/usr/bin/codesign --force --deep --sign - "$ROOT/dist/CY Player.app"
