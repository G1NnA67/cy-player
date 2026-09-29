# Third-party components / 第三方组件

CY Player original source is **GPL-3.0-or-later**; see [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT). Third-party components retain their own notices and terms.

## Current source-built-media version (0.3.1)

| Component | Version, source and terms |
|---|---|
| Python / python-build-standalone | Python 3.12.14, standalone release 20260924; [builder](https://github.com/astral-sh/python-build-standalone/tree/20260924). Companion materials contain the full release metadata, licenses, pinned builder source and runtime dependency sources. |
| PySide6 / Shiboken / Qt | 6.10.3; [versioned source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.3-src/), [licenses and attributions](https://doc.qt.io/qtforpython-6/licenses.html). Original wheels have been checked against PyPI SHA-256 values. |
| Qt playback FFmpeg | 7.1.3, LGPL-2.1-or-later; rebuilt locally from the same pinned source as the CLI, with dav1d software AV1 decoding and unchanged FFmpeg 7.1 ABI names. Shared-library and CLI configurations are recorded separately. |
| Download FFmpeg / ffprobe | 7.1.3, built locally from [official source](https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz). The binary reports LGPL-2.1-or-later; GPL/nonfree switches are disabled. Uses LAME 3.100 and dav1d 1.5.4, with pinned source archives, original license texts and complete build records. |
| LAME / dav1d | LAME MP3 encoder and dav1d AV1 decoder retain their original LGPL and BSD license texts, respectively; these are included with the build materials. |
| yt-dlp / yt-dlp-ejs | 2026.8.19 / 0.8.0; [yt-dlp](https://github.com/yt-dlp/yt-dlp), [ejs](https://github.com/yt-dlp/ejs). Their source distributions and embedded-component notices are retained. |
| Node.js | 24.19.0; [source and checksums](https://nodejs.org/dist/v24.19.0/), full NODE-LICENSE included. |
| Other frozen Python packages | Exact versions are in requirements-lock.txt. Their source distributions and notices are supplied; these include mutagen (GPL-2.0-or-later), certifi (MPL-2.0) and packages under other terms. |
| PyInstaller | 6.22.3; [GPL license with bootloader exception](https://pyinstaller.org/en/stable/license.html), source and license retained. Some PyInstaller Python modules and supporting packages also appear in the bundle. |
| Build-only tools | Meson 1.7.2, Ninja Python package 1.11.1.4, pkgconf 2.4.3; separate source/wheel provenance and notices. Not needed to run the packaged player. |

The imageio-ffmpeg precompiled executable is no longer shipped in this candidate. Older preview ZIPs are historical artifacts with their own component inventories and notices.

The trimmed Qt bundle retains Core, Concurrent, DBus, Gui, Network, Widgets, Svg, Multimedia and MultimediaWidgets, together with the retained image-format/platform/media plugins. The companion materials include the corresponding Qt source modules and module-wide upstream third-party attributions. Those upstream attributions can cover additional platforms or tests that are not in this application.

## Building and replacing components

[tools/README.md](tools/README.md) explains the pinned FFmpeg build, project-local tools and rebuilding the app with modified dynamically linked Qt/PySide6. Download and playback FFmpeg remain separate builds; their configuration records are not interchangeable. No restriction on reverse engineering for debugging modifications to LGPL components is added by CY Player.

The companion source archive includes application source, source inputs, build records, applicable notices and a file-hash manifest. Version-matched Qt wheels and source are upstream release artifacts; we have not independently reproduced every upstream binary byte-for-byte. This is distinct from our FFmpeg helper and playback libraries, which are built locally from the recorded inputs. No Apple Developer ID signature, notarization or another-Mac compatibility certification is implied.

中文：原创代码采用 GPL-3.0-or-later；第三方各自保留许可。当前候选版下载处理工具及播放用 FFmpeg 库已改为本地源码构建，源码、构建参数、记录和许可证随配套材料提供。Qt/Python 等上游组件也保留对应版本源码、发行记录及声明；不声称所有上游二进制都已在本机逐字节重建。历史测试包与本候选版的组件不同，应分别使用其材料。
