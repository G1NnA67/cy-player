import unittest
from core import validate_url, timestamp

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

if __name__ == "__main__":
    unittest.main()
