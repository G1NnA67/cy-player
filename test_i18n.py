"""Verify live language switching without touching the user's settings or network."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton, QMessageBox
from PySide6.QtMultimedia import QMediaPlayer
from app import PlayerWindow, STYLE
from core import read_settings, write_settings
from i18n import ENGLISH

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parent if PROJECT.name == 'project' else PROJECT
(ROOT/'tmp').mkdir(exist_ok=True)
APPLICATION = QApplication.instance() or QApplication([])
APPLICATION.setStyle('Fusion')
APPLICATION.setStyleSheet(STYLE)
APPLICATION.setFont(QFont('PingFang SC', 13))


def pump(check=lambda: False, seconds=.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        APPLICATION.processEvents()
        if check():
            return True
        time.sleep(.01)
    return check()


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='language-test-')
        self.previous_root = os.environ.get('YINGZHOU_ROOT')
        os.environ['YINGZHOU_ROOT'] = self.temp.name
        self.windows = []

    def window(self):
        w = PlayerWindow()
        self.windows.append(w)
        w.show()
        pump()
        return w

    def tearDown(self):
        for w in self.windows:
            if w.process:
                w.stop_process(w.process, force=True)
                pump(lambda: w.process is None, 2)
            w.close()
        pump()
        if self.previous_root is None:
            os.environ.pop('YINGZHOU_ROOT', None)
        else:
            os.environ['YINGZHOU_ROOT'] = self.previous_root
        self.temp.cleanup()

    def test_switch_persists_and_keeps_form_data_and_settings(self):
        write_settings({'volume':.4, 'custom_setting':'keep me'})
        w = self.window()
        self.assertEqual(w.language, 'en')
        self.assertEqual(w.windowTitle(), 'CY Player')
        self.assertEqual(w.findChild(QLabel,'brand').text(), 'Chenying Player')
        w.switch_page(1)
        w.url.setText('https://youtu.be/example')
        w.quality.setCurrentIndex(2)
        folder = w.folder.text()
        w.language_picker.setCurrentIndex(w.language_picker.findData('zh'))
        self.assertEqual(w.start_button.text(), '↓ 开始下载')
        self.assertEqual(w.volume.toolTip(), '音量')
        self.assertIn('Bilibili 视频链接', w.url.placeholderText())
        self.assertEqual(w.pages.currentIndex(), 1)
        self.assertEqual(w.url.text(), 'https://youtu.be/example')
        self.assertEqual(w.quality.currentData(), '720')
        self.assertEqual(w.folder.text(), folder)
        self.assertEqual(read_settings()['custom_setting'], 'keep me')
        self.assertEqual(read_settings()['language'], 'zh')
        reloaded = self.window()
        self.assertEqual(reloaded.language, 'zh')
        w.set_language('en')
        self.assertEqual(w.start_button.text(), '↓ Download')
        self.assertEqual(w.volume.toolTip(), 'Volume')
        self.assertEqual(w.quality.currentText(), 'Up to 720p')

    def test_audio_selection_worker_arguments_and_completion(self):
        from unittest.mock import patch
        w = self.window()
        w.download_type.setCurrentIndex(1)
        self.assertFalse(w.quality.isEnabled())
        self.assertFalse(w.video_format.isEnabled())
        self.assertTrue(w.video_format.isHidden())
        w.set_language('zh')
        self.assertEqual(w.download_type.currentText(), '仅音频（MP3）')
        w.url.setText('https://youtu.be/example')
        with patch('app.QProcess') as process_type:
            process = process_type.return_value
            w.start_download()
            args = process.start.call_args.args[1]
            self.assertEqual(args[-2:], ['audio', 'mp4'])
            self.assertFalse(w.download_type.isEnabled())
            w.process = None
        w.set_download_busy(False)
        self.assertFalse(w.quality.isEnabled())
        output = Path(self.temp.name)/'audio.mp3'
        output.write_bytes(b'test audio')
        w.handle_worker_event({'event':'completed','path':str(output),'media_type':'audio'})
        self.assertIn('音频已保存', w.download_status.text())
        w.set_language('en')
        self.assertIn('Your audio', w.download_status.text())
        self.assertEqual(w.result_button.text(), '▷ Play File')
        w.download_type.setCurrentIndex(0)
        self.assertTrue(w.quality.isEnabled())

    def test_video_format_persists_and_reaches_worker(self):
        from unittest.mock import patch
        w = self.window()
        self.assertEqual(w.video_format.currentData(), 'mp4')
        w.video_format.setCurrentIndex(w.video_format.findData('webm'))
        w.set_language('zh')
        self.assertEqual(w.video_format.currentData(), 'webm')
        self.assertEqual(w.video_format_label.text(), '视频格式')
        w.url.setText('https://youtu.be/example')
        with patch('app.QProcess') as process_type:
            w.start_download()
            self.assertEqual(process_type.return_value.start.call_args.args[1][-2:], ['video', 'webm'])
            self.assertFalse(w.video_format.isEnabled())
            w.process = None
        w.set_download_busy(False)
        w.handle_worker_event({'event': 'failed', 'message': 'Requested format is not available'})
        w.worker_finished(1, QProcess.NormalExit)
        self.assertIn('换一种格式', w.download_status.text())
        w.set_language('en')
        self.assertIn('Try another format', w.download_status.text())
        w.close()
        self.assertEqual(read_settings()['video_format'], 'webm')
        self.assertEqual(self.window().video_format.currentData(), 'webm')

    def test_static_texts_and_dynamic_error_states(self):
        w = self.window()
        for (_, _), (key, _) in w._text_bindings.items():
            if any('\u4e00' <= char <= '\u9fff' for char in key):
                self.assertIn(key, ENGLISH)
        w.url.setText('https://youtube.com.evil.test/123')
        w.start_download()
        self.assertEqual(w.download_status.text(), 'Please paste a YouTube or Bilibili video link.')
        w.set_language('zh')
        self.assertEqual(w.download_status.text(), '请粘贴 YouTube 或 Bilibili 的视频链接。')
        w.handle_worker_event({'event':'failed','message':'Connection timed out'})
        w.worker_finished(1, QProcess.NormalExit)
        self.assertIn('检查网络',w.download_status.text())
        w.set_language('en')
        self.assertIn('Check your network',w.download_status.text())
        captured = {}
        def inspect_dialog():
            dialog = APPLICATION.activeModalWidget()
            captured['title'] = dialog.windowTitle()
            captured['details'] = dialog.findChild(QPlainTextEdit).toPlainText()
            captured['button'] = dialog.findChild(QPushButton).text()
            dialog.accept()
        QTimer.singleShot(0, inspect_dialog)
        w.show_download_error()
        self.assertEqual(captured, {'title':'Download Details','details':'Connection timed out','button':'OK'})
        w.download_cancelled = True
        w.worker_finished(1,QProcess.NormalExit)
        w.set_language('zh')
        self.assertEqual(w.download_title.text(), '下载已取消')

    def test_download_progress_retranslates_without_restarting_process(self):
        import sys
        w = self.window()
        process = QProcess(w)
        w.process = process
        process.finished.connect(w.worker_finished)
        process.start(sys.executable,['-c','import os,time; os.setsid(); time.sleep(10)'])
        self.assertTrue(process.waitForStarted(3000))
        pump(seconds=.15)
        pid = process.processId()
        w.set_download_busy(True)
        w.handle_worker_event({'event':'progress','title':'测试视频 {original}', 'percent':42.5,
                               'downloaded':1048576,'speed':524288,'eta':9})
        w.set_language('zh')
        self.assertIn('已下载 1.0 MB',w.download_status.text())
        self.assertEqual(w.progress.value(),425)
        self.assertEqual(w.download_title.text(),'测试视频 {original}')
        self.assertEqual(process.processId(),pid)
        self.assertEqual(process.state(),QProcess.Running)
        self.assertFalse(w.start_button.isEnabled())
        w.set_language('en')
        self.assertIn('1.0 MB downloaded',w.download_status.text())
        self.assertIn('00:09 remaining',w.download_status.text())
        w.handle_worker_event({'event':'processing'})
        w.set_language('zh')
        self.assertEqual(w.download_status.text(),'正在合并或整理视频…')
        w.cancel_download()
        self.assertTrue(pump(lambda: w.process is None,3))
        w.set_language('en')
        self.assertEqual(w.download_title.text(),'Download cancelled')

    def test_video_state_and_completed_filename_survive_switch(self):
        fixture = ROOT/'tests/fixtures/播放测试.mkv'
        if not fixture.exists():
            import subprocess
            from unittest.mock import patch
            from core import ffmpeg_executable
            fixture = Path(self.temp.name)/'fixture.mkv'
            subtitles = Path(self.temp.name)/'fixture.srt'
            subtitles.write_text('1\n00:00:00,000 --> 00:00:04,000\nSubtitle test\n')
            with patch('core.root_dir', return_value=ROOT):
                ffmpeg = ffmpeg_executable()
            subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i',
                            'testsrc2=size=320x180:rate=24','-i',str(subtitles),'-t','5',
                            '-c:v','mpeg4','-c:s','srt',str(fixture)],check=True)
        w = self.window()
        w.audio.setVolume(0)
        frames=[]
        w.video.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
        w.open_file(fixture)
        self.assertTrue(pump(lambda: any(frames) and w.player.position()>200,8))
        player = w.player
        w.set_language('zh')
        self.assertIs(w.player,player)
        self.assertEqual(w.player.playbackState(),QMediaPlayer.PlayingState)
        self.assertEqual(w.play_button.text(),'暂停')
        w.player.pause(); w.player.setPosition(2000); pump(seconds=.15)
        w.player.setActiveSubtitleTrack(0)
        w.rate.setCurrentIndex(4)
        position=w.player.position()
        w.set_language('en')
        self.assertEqual(w.player.playbackState(),QMediaPlayer.PausedState)
        self.assertEqual(w.player.position(),position)
        self.assertEqual(w.player.playbackRate(),1.5)
        self.assertEqual(w.player.activeSubtitleTrack(),0)
        self.assertEqual(w.file_title.text(),fixture.name)
        self.assertEqual(w.subtitle_tracks.currentData(),0)
        w.handle_worker_event({'event':'completed','path':str(fixture)})
        w.set_language('zh')
        self.assertEqual(w.download_title.text(),fixture.name)
        self.assertTrue(w.result_button.isEnabled())
        self.assertIn('下载完成',w.download_status.text())

    def test_save_failure_keeps_switch_working_and_shows_localized_notice(self):
        from unittest.mock import patch
        w = self.window()
        captured = {}
        def inspect_notice():
            dialog = APPLICATION.activeModalWidget()
            captured['button'] = dialog.button(QMessageBox.Ok).text()
            captured['message'] = dialog.text()
            dialog.accept()
        QTimer.singleShot(0, inspect_notice)
        with patch('app.write_settings', side_effect=OSError('read-only folder')):
            w.set_language('zh')
        self.assertEqual(w.language, 'zh')
        self.assertEqual(captured['button'], '确定')
        self.assertIn('无法保存设置', captured['message'])

    def test_unsupported_saved_language_falls_back_to_english(self):
        write_settings({'language':'unsupported'})
        w=self.window()
        self.assertEqual(w.language,'en')
        self.assertEqual(w.language_picker.currentData(),'en')


if __name__ == '__main__':
    unittest.main()
