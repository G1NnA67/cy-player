#!/bin/zsh
set -eu
ROOT="${0:A:h:h}"
export YINGZHOU_ROOT="$ROOT"
DIST="${CY_BUILD_DIST:-$ROOT/dist}"
export TMPDIR="$ROOT/tmp"
export XDG_CACHE_HOME="$ROOT/cache"
export PYTHONPYCACHEPREFIX="$ROOT/cache/pycache"
export PYINSTALLER_CONFIG_DIR="$ROOT/cache/pyinstaller"
cd "$ROOT/project"
for TOOL in ffmpeg ffprobe; do
  if [[ ! -x "$ROOT/runtime/media-tools/$TOOL" ]]; then
    print -u2 "Missing $TOOL: run tools/build_media_tools.py first (see README.md)."
    exit 1
  fi
done
for LIB in libavcodec.61.dylib libavformat.61.dylib libavutil.59.dylib libswresample.5.dylib libswscale.8.dylib; do
  if [[ ! -f "$ROOT/runtime/media-tools/qt-libs/$LIB" ]]; then
    print -u2 "Missing playback library $LIB: run tools/build_media_tools.py first."
    exit 1
  fi
done
"$ROOT/runtime/python/bin/python3" -m PyInstaller --noconfirm --windowed --name "CY Player" \
  --add-data "$ROOT/project/icon.png:." --icon "$ROOT/project/AppIcon.icns" \
  --add-binary "$ROOT/runtime/media-tools/ffmpeg:media-tools" \
  --add-binary "$ROOT/runtime/media-tools/ffprobe:media-tools" \
  --osx-bundle-identifier local.yingzhou.player \
  --additional-hooks-dir "$ROOT/project/build_hooks" \
  --distpath "$DIST" --workpath "$ROOT/tmp/build" --specpath "$ROOT/tmp" \
  --collect-all yt_dlp_ejs --collect-submodules yt_dlp --exclude-module imageio_ffmpeg \
  --hidden-import download_worker --hidden-import accelerated_http --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtWebEngineQuick \
  --exclude-module tkinter app.py

# Populate this build output before its final signature.
# Qt 6.10.3 expects the FFmpeg 7.1 library ABI; our matching build adds dav1d.
for LIB in libavcodec.61.dylib libavformat.61.dylib libavutil.59.dylib libswresample.5.dylib libswscale.8.dylib; do
  /bin/cp -X "$ROOT/runtime/media-tools/qt-libs/$LIB" "$DIST/CY Player.app/Contents/Frameworks/$LIB"
done

"$ROOT/runtime/python/bin/python3" - "$ROOT" "$DIST" <<'PYMETA'
from pathlib import Path
import plistlib,sys
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'project'))
from core import VERSION
p=Path(sys.argv[2])/'CY Player.app/Contents/Info.plist'
d=plistlib.loads(p.read_bytes());d.update(CFBundleShortVersionString=VERSION,CFBundleVersion=VERSION,LSMinimumSystemVersion='13.5');p.write_bytes(plistlib.dumps(d))
PYMETA
/usr/bin/xattr -dr com.apple.FinderInfo "$DIST/CY Player.app"
/usr/bin/codesign --force --deep --sign - "$DIST/CY Player.app"
