# Building and replacing the media tools

The download worker uses our own FFmpeg 7.1.3 build with LAME 3.100 for MP3 and dav1d 1.5.4 for software AV1 decoding. It no longer uses the precompiled imageio-ffmpeg executable. The same pinned sources also build FFmpeg shared libraries for Qt playback, so AV1 has a software decoder on Macs without AV1 hardware support.

The recipe pins source archive SHA-256 values, disables automatic discovery of optional external libraries, and records commands, compiler/SDK versions, configuration files, license texts and output hashes. It uses Apple's existing Command Line Tools, Meson 1.7.2, Ninja 1.11.1.4 and source-built pkgconf 2.4.3. Nothing is installed globally.

## Fresh source checkout on an Apple Silicon Mac

Use Python 3.12+ and an already installed Apple Command Line Tools toolchain. In a normal clone, run from the source root:

```sh
python3 -m pip install --target runtime/build-tools --cache-dir cache/pip -r tools/requirements-build.txt
python3 tools/build_media_tools.py --sources cache/media-sources --output runtime/media-tools --build-tools runtime/build-tools
```

For the local delivery's `project/` directory, use `../cache/media-sources`, `../runtime/media-tools` and `../runtime/build-tools` instead. You can point `--sources` at the companion source materials' `sources/` folder to reuse the exact downloaded archives. The `build-tools/` subfolder of those materials also contains the pinned Meson/Ninja wheels for an offline pip installation.

Compilation uses a temporary path under `/private/tmp` because upstream makefiles do not reliably support paths containing spaces. The directory is removed when the build exits. Source archives, final tools, logs and rebuild records stay at the paths you supply.

`ffmpeg` and `ffprobe` use system frameworks and system zlib dynamically. FFmpeg, LAME and dav1d are built from the pinned inputs. The source archives are unmodified; no source patch is applied. `relink-objects.tar.gz` also preserves the compiled FFmpeg objects/static libraries and external static libraries. The script can rebuild them with modifications; first change the applicable source archive checksum intentionally when using your own modified source.

This is a documented rebuild procedure, not a claim of bit-for-bit reproducibility across different compilers, SDKs or build paths. The actual compiler/SDK and command lines for the delivered tools are in `BUILD-RECORD.json`.

## Application build

The delivery layout is `project/`, `runtime/python/`, `runtime/media-tools/` and `dist/` under one parent. Install `requirements-dev.txt` into the project-local Python runtime, then run `build_mac.sh`. Set `CY_BUILD_DIST` to an absolute separate destination when testing a replacement. The script bundles both tools, places the five matching source-built FFmpeg shared libraries in the build output, and then applies the final ad-hoc signature. Qt frameworks, bindings and plugins remain the upstream 6.10.3 build. The FFmpeg 7.1 ABI names are preserved.

The current preview targets macOS 13.5+ and ARM64. Creating a build for a different CPU or OS requires a matching toolchain and testing.

For source-mode AV1 playback, start Python with the matching libraries available to the dynamic loader (use `../runtime` in the delivery's `project/` layout):

```sh
DYLD_LIBRARY_PATH="$PWD/runtime/media-tools/qt-libs" python3 app.py
```

A normal source launch without that setting uses the installed PySide6 wheel's media libraries. Packaged applications use the rebuilt libraries automatically.

## Modified components and library replacement

The source tree, original-source LICENSE/COPYRIGHT, pinned Python package sources, Qt/PySide6 sources, runtime sources and notices are supplied as companion materials. Qt/PySide6 are dynamically linked components. To use a compatible modified Qt/PySide6, build/install its matching bindings into the project-local Python environment and rebuild this application with `build_mac.sh`. Preserve module names, Qt 6 ABI compatibility and needed platform/media plugins. Upstream `coin_build_instructions.py` and the versioned PySide source archive provide its build tooling. Rebuilding Qt/PySide itself requires additional upstream build prerequisites; those are not installed by our FFmpeg recipe.

For testing, work on a copy, retain your own modified source and rebuild records, and re-sign your rebuilt app after modification. The build script signs that new copy. Do not edit a signed application and then expect its old signature to remain valid. No Gatekeeper or quarantine disabling is part of this workflow.

## Licenses

CY Player's original code is GPL-3.0-or-later. Our FFmpeg binary reports LGPL-2.1-or-later; LAME and dav1d retain their own licenses. The complete source/configuration and notice materials must accompany distribution as appropriate; rebuilding a helper does not change licenses of the rest of the application. See `THIRD_PARTY.md` and the source-materials README.
