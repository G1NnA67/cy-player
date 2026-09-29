"""Build the download postprocessor from pinned source, using Apple's existing CLT.

No Homebrew/global installation. Run with --help for the source/output locations.
Temporary compilation uses a path without spaces; final files stay in --output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

SOURCES = {
    'ffmpeg-7.1.3.tar.xz': (
        'https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz',
        'f0bf043299db9e3caacb435a712fc541fbb07df613c4b893e8b77e67baf3adbe'),
    'lame-3.100.tar.gz': (
        'https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz',
        'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e'),
    'dav1d-1.5.4.tar.xz': (
        'https://downloads.videolan.org/pub/videolan/dav1d/1.5.4/dav1d-1.5.4.tar.xz',
        '686616b7c69eb88d44459391ab25cac13b6647a3b288835c5784e71c1514a5c5'),
    'pkgconf-2.4.3.tar.xz': (
        'https://distfiles.ariadne.space/pkgconf/pkgconf-2.4.3.tar.xz',
        '51203d99ed573fa7344bf07ca626f10c7cc094e0846ac4aa0023bd0c83c25a41'),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-tools', type=Path, required=True,
                        help='Project-local pip --target directory containing meson==1.7.2 and ninja==1.11.1.4')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('This recipe targets macOS ARM64.')
    args.sources = args.sources.resolve()
    args.output = args.output.resolve()
    args.build_tools = args.build_tools.resolve()
    ninja = args.build_tools / 'bin/ninja'
    if not ninja.is_file():
        parser.error('Install tools/requirements-build.txt into --build-tools first.')
    args.sources.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'sources': [], 'commands': [], 'patches': [], 'target': 'macOS ARM64 13.5+',
              'scope': 'FFmpeg CLI tools and ABI-compatible shared libraries for Qt playback.'}
    for name, (url, expected) in SOURCES.items():
        archive = args.sources / name
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                archive.write_bytes(response.read())
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Source checksum mismatch: {name}')
        report['sources'].append({'file': name, 'url': url, 'sha256': actual})
    with tempfile.TemporaryDirectory(prefix='cy-media-build-', dir='/private/tmp') as temp:
        work = Path(temp)
        prefix = work / 'install'
        env = os.environ.copy()
        env.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', MACOSX_DEPLOYMENT_TARGET='13.5',
                   CC='/usr/bin/clang', CXX='/usr/bin/clang++',
                   CFLAGS='-O2 -arch arm64 -mmacosx-version-min=13.5',
                   LDFLAGS='-arch arm64 -mmacosx-version-min=13.5', TMPDIR=str(work))
        for key in ['CPATH', 'LIBRARY_PATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'PKG_CONFIG_PATH', 'SDKROOT']:
            env.pop(key, None)
        env['PYTHONPATH'] = str(args.build_tools)
        env['PATH'] = f'{prefix}/bin:{ninja.parent}:' + env['PATH']
        env['PKG_CONFIG_PATH'] = str(prefix / 'lib/pkgconfig')
        def run(command, cwd, name):
            report['commands'].append({'cwd': str(cwd).replace(str(work), '$BUILD'),
                                       'argv': [str(a).replace(str(work), '$BUILD') for a in command]})
            print(name, flush=True)
            with (args.output / (name + '.log')).open('w') as log:
                subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        for name in SOURCES:
            with tarfile.open(args.sources / name) as archive:
                archive.extractall(work, filter='data')
        lame = work / 'lame-3.100'
        ffmpeg = work / 'ffmpeg-7.1.3'
        pkgconf = work / 'pkgconf-2.4.3'
        run(['./configure', f'--prefix={prefix}', '--disable-shared', '--enable-static'], pkgconf, 'pkgconf-configure')
        run(['/usr/bin/make', f'-j{args.jobs}'], pkgconf, 'pkgconf-make')
        run(['/usr/bin/make', 'install'], pkgconf, 'pkgconf-install')
        meson = [sys.executable, '-m', 'mesonbuild.mesonmain']
        davbuild = work / 'dav1d-build'
        run(meson + ['setup', str(davbuild), str(work / 'dav1d-1.5.4'), f'--prefix={prefix}',
                     '--libdir=lib', '--default-library=static', '--buildtype=release',
                     '-Denable_tools=false', '-Denable_tests=false'], work, 'dav1d-configure')
        run([str(ninja), '-C', str(davbuild), f'-j{args.jobs}'], work, 'dav1d-make')
        run([str(ninja), '-C', str(davbuild), 'install'], work, 'dav1d-install')
        run(['./configure', f'--prefix={prefix}', '--build=aarch64-apple-darwin',
             '--disable-shared', '--enable-static', '--disable-frontend', '--disable-decoder',
             '--disable-gtktest', '--disable-nasm'], lame, 'lame-configure')
        run(['/usr/bin/make', f'-j{args.jobs}'], lame, 'lame-make')
        run(['/usr/bin/make', 'install'], lame, 'lame-install')
        ffmpeg_configure = ['./configure', f'--prefix={prefix}', '--cc=/usr/bin/clang', '--arch=arm64',
             '--target-os=darwin', '--disable-autodetect', '--disable-gpl', '--disable-nonfree',
             '--disable-doc', '--disable-debug', '--disable-ffplay', '--disable-shared', '--enable-static',
             '--enable-libmp3lame', '--enable-libdav1d', f'--pkg-config={prefix}/bin/pkgconf',
             '--pkg-config-flags=--static', '--enable-pthreads', '--enable-videotoolbox',
             '--enable-audiotoolbox', '--enable-securetransport', '--enable-zlib',
             f'--extra-cflags=-I{prefix}/include -mmacosx-version-min=13.5',
             f'--extra-ldflags=-L{prefix}/lib -mmacosx-version-min=13.5']
        run(ffmpeg_configure, ffmpeg, 'ffmpeg-configure')
        run(['/usr/bin/make', f'-j{args.jobs}'], ffmpeg, 'ffmpeg-make')
        for name in ['ffmpeg', 'ffprobe']:
            dest = args.output / name
            shutil.copyfile(ffmpeg / name, dest)
            dest.chmod(0o755)
            subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(dest)], check=True)
            report[name] = {'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                            'bytes': dest.stat().st_size,
                            'version': subprocess.check_output([str(dest), '-version'], text=True),
                            'linked_libraries': subprocess.check_output(['/usr/bin/otool', '-L', str(dest)], text=True)}
        for src, name in [(lame / 'COPYING', 'LAME-COPYING'), (lame / 'config.log', 'lame-config.log'),
                          (work / 'dav1d-1.5.4/COPYING', 'dav1d-COPYING'),
                          (ffmpeg / 'COPYING.LGPLv2.1', 'FFmpeg-COPYING.LGPLv2.1'),
                          (ffmpeg / 'LICENSE.md', 'FFmpeg-LICENSE.md'),
                          (ffmpeg / 'ffbuild/config.log', 'ffmpeg-config.log'),
                          (ffmpeg / 'config.h', 'ffmpeg-config.h'),
                          (ffmpeg / 'ffbuild/config.mak', 'ffmpeg-config.mak')]:
            shutil.copyfile(src, args.output / name)
        # Preserve object/library inputs so the static executable can also be relinked.
        with tarfile.open(args.output / 'relink-objects.tar.gz', 'w:gz') as archive:
            for p in sorted(ffmpeg.rglob('*')):
                if p.is_file() and p.suffix in {'.o', '.a'}:
                    archive.add(p, arcname='ffmpeg/' + str(p.relative_to(ffmpeg)))
            archive.add(prefix / 'lib/libmp3lame.a', arcname='lame/libmp3lame.a')
            archive.add(prefix / 'lib/libdav1d.a', arcname='dav1d/libdav1d.a')
        # Reuse the same pinned inputs for Qt's FFmpeg 7.1 ABI. This also gives
        # Macs without AV1 hardware a software decoder inside the player.
        run(['/usr/bin/make', 'distclean'], ffmpeg, 'ffmpeg-shared-clean')
        shared_configure = [a for a in ffmpeg_configure if a not in
                            ['--disable-shared', '--enable-static', '--disable-ffplay']]
        shared_configure += ['--enable-shared', '--disable-static', '--disable-programs',
                             '--install-name-dir=@rpath']
        run(shared_configure, ffmpeg, 'ffmpeg-shared-configure')
        run(['/usr/bin/make', f'-j{args.jobs}'], ffmpeg, 'ffmpeg-shared-make')
        qt_libs = args.output / 'qt-libs'
        qt_libs.mkdir(exist_ok=True)
        report['qt_libraries'] = []
        for lib, major in [('avcodec',61), ('avformat',61), ('avutil',59), ('swresample',5), ('swscale',8)]:
            name = f'lib{lib}.{major}.dylib'
            dest = qt_libs / name
            shutil.copyfile(ffmpeg / ('lib' + lib) / name, dest)
            dest.chmod(0o755)
            subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(dest)], check=True)
            report['qt_libraries'].append({'file': name, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                'bytes': dest.stat().st_size,
                'linked_libraries': subprocess.check_output(['/usr/bin/otool','-L',str(dest)],text=True)})
        for source, name in [('ffbuild/config.log','ffmpeg-shared-config.log'),
                             ('config.h','ffmpeg-shared-config.h'),
                             ('ffbuild/config.mak','ffmpeg-shared-config.mak')]:
            shutil.copyfile(ffmpeg / source, args.output / name)
        report['compiler'] = subprocess.check_output(['/usr/bin/clang', '--version'], text=True)
        report['sdk'] = subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-version'], text=True).strip()
        report['build_tools'] = {'meson': subprocess.check_output(meson + ['--version'], env=env, text=True).strip(),
                                 'ninja': subprocess.check_output([str(ninja), '--version'], text=True).strip(),
                                 'pkgconf': '2.4.3'}
        report['environment'] = {k: env[k] for k in ['PATH', 'MACOSX_DEPLOYMENT_TARGET', 'CC', 'CXX', 'CFLAGS', 'LDFLAGS']}
    (args.output / 'BUILD-RECORD.json').write_text(json.dumps(report, indent=2) + '\n')
    shutil.copyfile(__file__, args.output / 'build_media_tools.py')
    print('Media tools built, signed, and recorded.', flush=True)

if __name__ == '__main__':
    main()
