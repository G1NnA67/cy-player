# 第三方组件

本项目调用或随本机开发环境提供以下组件。组件许可不因本项目而改变。正式对外分发安装包时，需要保留适用的许可证、版权信息及对应来源/源码获取信息。

| 组件 | 来源及许可信息 |
|---|---|
| Python | https://www.python.org/psf/license/ |
| python-build-standalone | https://github.com/astral-sh/python-build-standalone |
| PySide6 / Qt | https://doc.qt.io/qtforpython-6/licenses.html |
| Qt Multimedia / FFmpeg | https://doc.qt.io/qt-6/qtmultimedia-index.html#licenses-and-attributions |
| yt-dlp | https://github.com/yt-dlp/yt-dlp#license |
| yt-dlp-ejs | https://github.com/yt-dlp/ejs |
| imageio-ffmpeg / bundled FFmpeg | https://github.com/imageio/imageio-ffmpeg |
| Node.js | https://github.com/nodejs/node/blob/main/LICENSE |
| PyInstaller（构建工具） | https://pyinstaller.org/en/stable/license.html |

Python 包的 dist-info / license 文件保留在本地 runtime/python 中。Node.js 的许可副本在 runtime/tools/NODE-LICENSE。FFmpeg 二进制来源于 imageio-ffmpeg 的 macOS ARM64 wheel；请以该具体构建的 `ffmpeg -L` 输出为准，不假设所有 FFmpeg 构建都采用同一种许可。
