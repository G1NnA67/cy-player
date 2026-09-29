import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from core import validate_url, timestamp, ffmpeg_executable

class CoreTests(unittest.TestCase):
    def test_allowed_sites_and_short_links(self):
        for url in ("https://www.youtube.com/watch?v=test", "https://youtu.be/test",
                    "https://www.bilibili.com/video/BV123", "https://b23.tv/abc"):
            self.assertEqual(validate_url("  " + url + "  "), url)

    def test_deceptive_hosts_and_credentials_rejected(self):
        for url in ("file:///etc/passwd", "https://youtube.com.evil.test/video",
                    "https://youtube.com@evil.test", "https://user:secret@youtube.com/a",
                    "https://bilibili.com:9999/test", "https://[bad", "hello",
                    "https://youtube.com/playlist?list=123", "https://www.youtube.com/@channel",
                    "https://space.bilibili.com/123"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_timestamps(self):
        self.assertEqual(timestamp(0), "00:00")
        self.assertEqual(timestamp(65000), "01:05")
        self.assertEqual(timestamp(3601000), "1:00:01")
        self.assertEqual(timestamp(-100), "00:00")

    def test_source_ffmpeg_ignores_old_runtime_link(self):
        with tempfile.TemporaryDirectory() as temp, patch('core.root_dir', return_value=Path(temp)):
            root = Path(temp)
            (root / 'runtime/tools').mkdir(parents=True)
            legacy = root / 'runtime/tools/ffmpeg'
            legacy.symlink_to('/missing-old-imageio-binary')
            with self.assertRaises(FileNotFoundError):
                ffmpeg_executable()
            tool = root / 'runtime/media-tools/ffmpeg'
            tool.parent.mkdir()
            tool.write_bytes(b'test fixture')
            self.assertEqual(ffmpeg_executable(), tool)
            self.assertTrue(legacy.is_symlink())

    def test_frozen_ffmpeg_comes_from_current_bundle(self):
        with tempfile.TemporaryDirectory() as temp, patch('core.sys.frozen', True, create=True), patch('core.sys._MEIPASS', temp, create=True):
            tool = Path(temp) / 'media-tools/ffmpeg'
            tool.parent.mkdir()
            tool.write_bytes(b'test fixture')
            self.assertEqual(ffmpeg_executable(), tool)

if __name__ == "__main__":
    unittest.main()
