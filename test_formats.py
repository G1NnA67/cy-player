"""Exercise actual yt-dlp selection and remuxing, including cross-format safety."""
import contextlib
import copy
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import yt_dlp
from core import UserFacingError, ffmpeg_executable
from download_worker import format_options, run


class FormatTests(unittest.TestCase):
    def test_source_selection_keeps_audio_and_height_limit(self):
        formats = []
        for height in (720, 1080, 2160):
            for ext, codec in (('mp4', 'avc1'), ('webm', 'vp9')):
                formats.append(dict(format_id=f'{ext}-{height}', ext=ext, vcodec=codec,
                                    acodec='none', height=height, url='https://example.org/video'))
        for ext, codec in (('m4a', 'mp4a'), ('webm', 'opus')):
            formats.append(dict(format_id=f'a-{ext}', ext=ext, vcodec='none', acodec=codec,
                                url='https://example.org/audio'))
        for container in ('mp4', 'mkv', 'webm'):
            for quality, height in (('720', 720), ('1080', 1080), ('best', 2160)):
                with self.subTest(container=container, quality=quality):
                    with yt_dlp.YoutubeDL({'quiet': True, **format_options(quality, 'video', container)}) as ydl:
                        info = ydl.process_ie_result(dict(id='test', title='test', formats=copy.deepcopy(formats)), download=False)
                    self.assertEqual(info['height'], height)
                    streams = info['requested_formats']
                    self.assertEqual(len(streams), 2)
                    self.assertNotEqual(streams[0]['vcodec'], 'none')
                    self.assertNotEqual(streams[1]['acodec'], 'none')
                    if container != 'mkv':
                        self.assertEqual(streams[0]['ext'], container)
                        self.assertEqual(streams[1]['ext'], 'm4a' if container == 'mp4' else 'webm')
        with yt_dlp.YoutubeDL({'quiet': True, **format_options('720', 'audio', 'webm')}) as ydl:
            info = ydl.process_ie_result(dict(id='test', title='test', formats=formats), download=False)
        self.assertEqual(info['vcodec'], 'none')

    def test_invalid_options_and_unavailable_format(self):
        for args in (('4k', 'video', 'mp4'), ('best', 'bad', 'mp4'), ('best', 'video', '../bad')):
            with self.assertRaises(UserFacingError):
                format_options(*args)
        with yt_dlp.YoutubeDL({'quiet': True, **format_options('best', 'video', 'webm')}) as ydl:
            with self.assertRaisesRegex(yt_dlp.utils.ExtractorError, 'Requested format is not available'):
                ydl.process_ie_result(dict(id='test', title='test', extractor='test', formats=[dict(
                    format_id='mp4', ext='mp4', vcodec='avc1', acodec='mp4a',
                    url='https://example.org/video')]), download=False)

    def test_real_remux_preserves_other_formats_and_audio(self):
        ffmpeg = ffmpeg_executable()
        ffprobe = ffmpeg.with_name('ffprobe')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixture = root/'source.mp4'
            subprocess.run([str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10',
                            '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '1', '-c:v', 'mpeg4',
                            '-c:a', 'aac', str(fixture)], check=True)
            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=directory, **kwargs)
                def log_message(self, *args):
                    pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def extract(ydl, url, download=True):
                return ydl.process_ie_result(dict(id='fixture', title='same title', formats=[dict(
                    format_id='combined', url=f'http://127.0.0.1:{server.server_port}/source.mp4',
                    ext='mp4', vcodec='mpeg4', acodec='aac', height=90)]), download=download)
            try:
                hashes = {}
                for container in ('mp4', 'mkv', 'mp4', 'mkv'):
                    output = io.StringIO()
                    with patch('download_worker.os.setsid'), patch.dict(os.environ, {'YINGZHOU_ROOT': directory}), \
                         patch('download_worker.ffmpeg_executable', return_value=ffmpeg), \
                         patch.object(yt_dlp.YoutubeDL, 'extract_info', extract), contextlib.redirect_stdout(output):
                        self.assertEqual(run('https://youtu.be/fixture', str(root/'out'), 'best', 'video', container), 0, output.getvalue())
                    events = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
                    result = Path(next(e['path'] for e in events if e['event'] == 'completed'))
                    self.assertEqual(result.parent, root/'out')
                    self.assertEqual(result.suffix, '.'+container)
                    probe = json.loads(subprocess.check_output([str(ffprobe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(result)]))
                    self.assertIn('mp4' if container == 'mp4' else 'matroska', probe['format']['format_name'])
                    self.assertEqual({s['codec_type'] for s in probe['streams']}, {'video', 'audio'})
                    for existing, digest in hashes.items():
                        self.assertEqual(hashlib.sha256(existing.read_bytes()).hexdigest(), digest)
                    hashes[result] = hashlib.sha256(result.read_bytes()).hexdigest()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
