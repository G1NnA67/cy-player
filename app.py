from __future__ import annotations
import json
import codecs
import signal
import os
import sys
from pathlib import Path
from i18n import LANGUAGES, translate
from core import APP_NAME, VERSION, root_dir, prepare_environment, read_settings, write_settings, timestamp, validate_url

# Worker dispatch happens before importing Qt so downloads have no GUI side effects.
if __name__ == "__main__" and "--download-worker" in sys.argv:
    from download_worker import run
    i = sys.argv.index("--download-worker")
    raise SystemExit(run(*sys.argv[i + 1:i + 5]))

from PySide6.QtCore import Qt, QUrl, QProcess, QTimer, Signal, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QStackedWidget, QFileDialog, QSlider, QComboBox, QLineEdit,
    QProgressBar, QMessageBox, QSizePolicy, QStyle, QButtonGroup, QPlainTextEdit, QDialog,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

STYLE = """
QMainWindow, QWidget { background: #101215; color: #ebece9; font-size: 14px; }
QWidget#sidebar { background: #171a1e; border-right: 1px solid #282c31; }
QLabel { background: transparent; }
QLabel#brand { font-size: 19px; font-weight: 700; color: #d3f78b; }
QLabel#heading { font-size: 30px; font-weight: 650; }
QLabel#kicker { color: #9faf93; font-size: 11px; font-weight: 600; }
QLabel#muted { color: #929a9f; font-size: 13px; }
QLabel#section { font-size: 18px; font-weight: 600; }
QLabel#heroIcon { color: #d3f78b; font-size: 62px; }
QWidget#card, QFrame#card { background: #191d22; border: 1px solid #2c3239; border-radius: 16px; }
QWidget#emptyVideo { background: #15191d; border: 1px dashed #3c454c; border-radius: 16px; }
QPushButton { background: #292f35; border: 1px solid #363e45; border-radius: 9px; padding: 10px 17px; color: #e9eeec; }
QPushButton:hover { background: #343d45; border-color: #6a777e; }
QPushButton:pressed { background: #20262c; }
QPushButton:disabled { color: #646d72; background: #20252a; border-color: #2b3035; }
QPushButton#primary { background: #d3f78b; color: #17230c; border: none; font-weight: 650; }
QPushButton#primary:hover { background: #e2ffae; }
QPushButton#primary:disabled { background: #415039; color: #899780; }
QPushButton#nav { text-align: left; background: transparent; border: 0; padding: 13px 16px; color: #9da6ac; }
QPushButton#nav:checked { background: #2a3427; color: #d3f78b; font-weight: 600; }
QPushButton#nav:hover { background: #252b2b; }
QLineEdit, QComboBox, QPlainTextEdit { background: #111519; border: 1px solid #37414a; border-radius: 8px; padding: 10px; selection-background-color: #486c31; }
QLineEdit:focus, QComboBox:focus { border-color: #b0d479; }
QComboBox { min-width: 100px; }
QComboBox QAbstractItemView { background: #252c32; selection-background-color: #3b4d31; }
QSlider::groove:horizontal { height: 5px; background: #343c44; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #c4eb81; border-radius: 2px; }
QSlider::handle:horizontal { width: 13px; background: #d3f78b; margin: -4px 0; border-radius: 6px; }
QProgressBar { background: #2c343c; border: 0; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: #c4eb81; border-radius: 4px; }
QToolTip { background: #303a43; color: #fff; border: 0; padding: 6px; }
"""


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.setCursor(Qt.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


class SeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                   int(event.position().x()), self.width())
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)


class VideoWidget(QVideoWidget):
    doubleClicked = Signal()
    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()


class PlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = prepare_environment()
        self.settings = read_settings()
        language = self.settings.get("language", "en")
        self.language = language if language in LANGUAGES else "en"
        self._text_bindings = {}
        self._progress_event = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "icon.png")))
        self.resize(1140, 790)
        self.setMinimumSize(960, 700)
        self.setAcceptDrops(True)
        self.current_file = None
        self.download_result = None
        self.process = None
        self.worker_buffer = ""
        self.worker_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.active_download_type = "video"
        self.download_done = False
        self.download_cancelled = False
        self.last_worker_error = ""
        self.last_worker_error_key = None
        self.warning_text = ""
        self.error_details = ""
        self.error_details_key = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(float(self.settings.get("volume", .7)))
        self.player.setAudioOutput(self.audio)
        main = QWidget()
        self.setCentralWidget(main)
        layout = QHBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(20, 32, 20, 24)
        side.setSpacing(10)
        side.addWidget(self.make_label("Chenying Player", "brand"))
        side.addWidget(self.make_label("你的桌面放映室", "muted"))
        side.addSpacing(38)
        self.tabs = QButtonGroup(self)
        self.nav_buttons = []
        for i, text in enumerate(("▷    本地播放", "↓    视频下载")):
            nav = QPushButton()
            self.text(nav, text)
            nav.setObjectName("nav")
            nav.setCheckable(True)
            nav.setCursor(Qt.PointingHandCursor)
            self.tabs.addButton(nav, i)
            nav.clicked.connect(lambda checked=False, index=i: self.switch_page(index))
            side.addWidget(nav)
            self.nav_buttons.append(nav)
        side.addStretch()
        side.addWidget(self.make_label("MAC EDITION", "kicker"))
        self.version_label = self.make_label("v{version} · 本地运行", "muted", version=VERSION)
        side.addWidget(self.version_label)
        side.addSpacing(14)
        side.addWidget(label("Language / 语言", "muted"))
        self.language_picker = QComboBox()
        self.language_picker.setObjectName("languagePicker")
        self.language_picker.setAccessibleName("Language / 语言")
        for code, name in LANGUAGES.items():
            self.language_picker.addItem(name, code)
        self.language_picker.setCurrentIndex(self.language_picker.findData(self.language))
        self.language_picker.currentIndexChanged.connect(
            lambda: self.set_language(self.language_picker.currentData()))
        side.addWidget(self.language_picker)
        layout.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.make_player_page()
        self.make_download_page()
        self.player_shortcuts = []
        for key, callback in (("Space", self.toggle_play), ("F", self.toggle_fullscreen),
                              ("Left", lambda: self.seek_by(-5000)),
                              ("Right", lambda: self.seek_by(5000))):
            shortcut = QShortcut(QKeySequence(key), self, activated=callback)
            self.player_shortcuts.append(shortcut)
        self.switch_page(0)
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(self.on_duration)
        self.player.playbackStateChanged.connect(self.on_playback)
        self.player.errorOccurred.connect(self.on_media_error)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.tracksChanged.connect(self.update_tracks)
        QShortcut(QKeySequence.Open, self, activated=self.open_dialog)
        QShortcut(QKeySequence("Escape"), self, activated=self.exit_fullscreen)
        self.set_player_enabled(False)

    def t(self, key, **values):
        return translate(key, self.language, **values)

    def bind_text(self, widget, method, key, **values):
        self._text_bindings[(widget, method)] = (key, values)
        getattr(widget, method)(self.t(key, **values))

    def text(self, widget, key, **values):
        self.bind_text(widget, "setText", key, **values)

    def literal(self, widget, value):
        self._text_bindings.pop((widget, "setText"), None)
        widget.setText(value)

    def make_label(self, key, name=None, wrap=False, **values):
        widget = label("", name, wrap)
        self.text(widget, key, **values)
        return widget

    def make_button(self, key, callback, primary=False):
        widget = button("", callback, primary)
        self.text(widget, key)
        return widget

    def set_language(self, language):
        if language not in LANGUAGES or language == self.language:
            return
        self.language = language
        self.settings["language"] = language
        self.language_picker.blockSignals(True)
        self.language_picker.setCurrentIndex(self.language_picker.findData(language))
        self.language_picker.blockSignals(False)
        for (widget, method), (key, values) in self._text_bindings.items():
            getattr(widget, method)(self.t(key, **values))
        for index, key in enumerate(("视频＋声音", "仅音频（MP3）")):
            self.download_type.setItemText(index, self.t(key))
        for index, key in enumerate(("最高可用画质", "最高 1080p", "最高 720p")):
            self.quality.setItemText(index, self.t(key))
        self.update_tracks()
        if self._progress_event is not None:
            self.render_download_progress(self._progress_event)
        try:
            saved = read_settings()
            saved["language"] = language
            write_settings(saved)
        except OSError as error:
            self.show_notice("语言设置", "语言已切换，但无法保存设置：{message}", message=str(error))

    def show_notice(self, title, message_key, **values):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self.t(title))
        dialog.setText(self.t(message_key, **values))
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.button(QMessageBox.Ok).setText(self.t("确定"))
        dialog.exec()

    def page_layout(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)
        layout.addWidget(self.make_label("CHENYING  /  DESKTOP CINEMA", "kicker"))
        layout.addWidget(self.make_label(title, "heading"))
        layout.addWidget(self.make_label(subtitle, "muted", True))
        self.pages.addWidget(page)
        return page, layout

    def make_player_page(self):
        self.play_page, layout = self.page_layout("好视频，慢慢看。", "打开本地文件，让每一段画面都有自己的时刻。")
        header = QHBoxLayout()
        self.file_title = self.make_label("尚未打开视频", "section")
        self.file_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header.addWidget(self.file_title, 1)
        header.addWidget(self.make_button("＋ 打开视频", self.open_dialog, True))
        layout.addLayout(header)
        self.video_stack = QStackedWidget()
        self.video_stack.setMinimumHeight(270)
        self.empty_video = QWidget()
        self.empty_video.setObjectName("emptyVideo")
        empty = QVBoxLayout(self.empty_video)
        empty.setAlignment(Qt.AlignCenter)
        for widget in (self.make_label("▷", "heroIcon"), self.make_label("把视频拖到这里", "section"),
                       self.make_label("或点击「打开视频」选择文件", "muted")):
            widget.setAlignment(Qt.AlignCenter)
            empty.addWidget(widget)
        empty.addSpacing(16)
        types = self.make_label("MP4  ·  MKV  ·  MOV  ·  WEBM  ·  AVI", "kicker")
        types.setAlignment(Qt.AlignCenter)
        empty.addWidget(types)
        self.video = VideoWidget()
        self.video.setStyleSheet("background: black;")
        self.video.doubleClicked.connect(self.toggle_fullscreen)
        self.player.setVideoOutput(self.video)
        self.video_stack.addWidget(self.empty_video)
        self.video_stack.addWidget(self.video)
        layout.addWidget(self.video_stack, 1)
        self.seek = SeekSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        layout.addWidget(self.seek)
        controls = QHBoxLayout()
        controls.setSpacing(9)
        self.play_button = self.make_button("播放", self.toggle_play, True)
        self.play_button.setMinimumWidth(72)
        controls.addWidget(self.play_button)
        self.time_label = self.make_label("00:00 / 00:00", "muted")
        controls.addWidget(self.time_label)
        controls.addStretch()
        self.rate = QComboBox()
        for rate in (.5, .75, 1., 1.25, 1.5, 2.):
            self.rate.addItem(f"{rate:g}×", rate)
        self.rate.setCurrentIndex(2)
        self.bind_text(self.rate, "setToolTip", "播放速度")
        self.rate.currentIndexChanged.connect(lambda: self.player.setPlaybackRate(self.rate.currentData()))
        controls.addWidget(self.rate)
        controls.addWidget(self.make_label("音量", "muted"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(round(self.audio.volume() * 100))
        self.volume.setFixedWidth(80)
        self.bind_text(self.volume, "setToolTip", "音量")
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        controls.addWidget(self.volume)
        self.fullscreen_button = self.make_button("全屏", self.toggle_fullscreen)
        controls.addWidget(self.fullscreen_button)
        layout.addLayout(controls)
        tracks = QHBoxLayout()
        tracks.addWidget(self.make_label("音轨", "muted"))
        self.audio_tracks = QComboBox()
        self.audio_tracks.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.audio_tracks.activated.connect(lambda: self.player.setActiveAudioTrack(self.audio_tracks.currentData()))
        tracks.addWidget(self.audio_tracks, 1)
        tracks.addWidget(self.make_label("字幕", "muted"))
        self.subtitle_tracks = QComboBox()
        self.subtitle_tracks.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.subtitle_tracks.activated.connect(lambda: self.player.setActiveSubtitleTrack(self.subtitle_tracks.currentData()))
        tracks.addWidget(self.subtitle_tracks, 1)
        layout.addLayout(tracks)
        self.media_status = self.make_label("空格 播放/暂停  ·  ← → 快退/快进  ·  F 全屏  ·  ⌘O 打开", "muted", True)
        layout.addWidget(self.media_status)

    def make_download_page(self):
        _, layout = self.page_layout("想看的，留在本地。", "粘贴 YouTube 或 Bilibili 视频链接，下载完成后直接播放。")
        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(14)
        form.addWidget(self.make_label("视频链接", "section"))
        self.url = QLineEdit()
        self.bind_text(self.url, "setPlaceholderText", "https://www.youtube.com/watch?v=… 或 Bilibili 视频链接")
        self.url.setClearButtonEnabled(True)
        form.addWidget(self.url)
        form.addWidget(self.make_label("保存位置", "muted"))
        row = QHBoxLayout()
        self.folder = QLineEdit(self.settings.get("download_folder", str(self.root / "downloads")))
        self.folder.setReadOnly(True)
        row.addWidget(self.folder, 1)
        self.choose_folder_button = self.make_button("选择…", self.choose_folder)
        row.addWidget(self.choose_folder_button)
        form.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.make_label("下载内容", "muted"))
        self.download_type = QComboBox()
        for key, value in (("视频＋声音", "video"), ("仅音频（MP3）", "audio")):
            self.download_type.addItem(self.t(key), value)
        self.download_type.currentIndexChanged.connect(self.update_download_type)
        row.addWidget(self.download_type)
        self.quality_label = self.make_label("画质", "muted")
        row.addWidget(self.quality_label)
        self.quality = QComboBox()
        for text, data in (("最高可用画质", "best"), ("最高 1080p", "1080"), ("最高 720p", "720")):
            self.quality.addItem(self.t(text), data)
        self.quality.setCurrentIndex(1)
        row.addWidget(self.quality)
        row.addStretch()
        self.start_button = self.make_button("↓ 开始下载", self.start_download, True)
        row.addWidget(self.start_button)
        form.addLayout(row)
        form.addWidget(self.make_label("仅音频保存为 MP3；有独立音轨时不下载画面。", "muted", True))
        layout.addWidget(card)
        status_card = QFrame()
        status_card.setObjectName("card")
        progress_layout = QVBoxLayout(status_card)
        progress_layout.setContentsMargins(22, 22, 22, 22)
        progress_layout.setSpacing(14)
        self.download_title = self.make_label("等待添加视频", "section", True)
        progress_layout.addWidget(self.download_title)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress)
        self.download_status = self.make_label("每次下载一个视频，进度会显示在这里。", "muted", True)
        self.download_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        progress_layout.addWidget(self.download_status)
        buttons = QHBoxLayout()
        self.cancel_button = self.make_button("取消下载", self.cancel_download)
        self.cancel_button.setEnabled(False)
        self.result_button = self.make_button("▷ 播放文件", self.play_download, True)
        self.result_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        self.details_button = self.make_button("查看原因", self.show_download_error)
        self.details_button.setEnabled(False)
        buttons.addWidget(self.details_button)
        buttons.addStretch()
        buttons.addWidget(self.make_button("打开保存文件夹", self.reveal_folder))
        buttons.addWidget(self.result_button)
        progress_layout.addLayout(buttons)
        layout.addWidget(status_card)
        layout.addStretch()
        layout.addWidget(self.make_label("画质取决于视频源及访问权限；部分视频可能需要登录。", "muted", True))

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        for shortcut in self.player_shortcuts:
            shortcut.setEnabled(index == 0)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("打开视频"), self.settings.get("last_folder", str(self.root)),
            self.t("视频文件") + " (*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.ts *.mts *.m2ts *.mpg *.mpeg *.flv *.wmv *.mp3 *.m4a *.ogg *.opus *.wav);;" + self.t("所有文件") + " (*)")
        if path:
            self.open_file(path)

    def open_file(self, path):
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            self.show_notice("无法打开", "这个文件不存在，请重新选择。")
            return
        self.current_file = path
        self.settings["last_folder"] = str(path.parent)
        self.literal(self.file_title, path.name)
        self.file_title.setToolTip(str(path))
        self.text(self.media_status, "正在打开视频…")
        self.video_stack.setCurrentIndex(1)
        self.switch_page(0)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.setPlaybackRate(self.rate.currentData())
        self.set_player_enabled(True)
        self.player.play()

    def set_player_enabled(self, enabled):
        for widget in (self.play_button, self.seek, self.rate, self.fullscreen_button, self.audio_tracks, self.subtitle_tracks):
            widget.setEnabled(enabled)

    def toggle_play(self):
        if not self.current_file:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def on_playback(self, state):
        self.text(self.play_button, "暂停" if state == QMediaPlayer.PlayingState else "播放")

    def on_position(self, value):
        if not self.seek.isSliderDown():
            self.seek.setValue(value)
        self.text(self.time_label, f"{timestamp(value)} / {timestamp(self.player.duration())}")

    def on_duration(self, value):
        self.seek.setRange(0, value)
        self.on_position(self.player.position())

    def on_media_error(self, error, message):
        if error != QMediaPlayer.NoError:
            self.text(self.media_status, "无法播放：{message}。文件可能损坏，或使用了暂不支持的编码。", message=message)
            self.play_button.setEnabled(False)

    def on_media_status(self, status):
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self.text(self.media_status, "空格 播放/暂停  ·  ← → 快退/快进  ·  F 全屏  ·  双击画面 全屏")
        elif status == QMediaPlayer.EndOfMedia:
            self.text(self.media_status, "播放结束。点击「播放」重新观看。")

    def update_tracks(self):
        from PySide6.QtMultimedia import QMediaMetaData
        for combo, tracks, active, subtitle in (
            (self.audio_tracks, self.player.audioTracks(), self.player.activeAudioTrack(), False),
            (self.subtitle_tracks, self.player.subtitleTracks(), self.player.activeSubtitleTrack(), True),
        ):
            combo.clear()
            if subtitle:
                combo.addItem(self.t("关闭字幕"), -1)
            for index, metadata in enumerate(tracks):
                title = metadata.stringValue(QMediaMetaData.Title) or metadata.stringValue(QMediaMetaData.Language)
                combo.addItem(title or self.t("字幕 {number}" if subtitle else "音轨 {number}", number=index + 1), index)
            if not tracks and not subtitle:
                combo.addItem(self.t("无音轨"), -1)
            found = combo.findData(active)
            combo.setCurrentIndex(max(0, found))
            combo.setEnabled(bool(tracks))

    def toggle_fullscreen(self):
        if not self.current_file:
            return
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.sidebar.hide()
            self.text(self.fullscreen_button, "退出全屏")
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.sidebar.show()
            self.text(self.fullscreen_button, "全屏")

    def seek_by(self, amount):
        self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + amount)))

    def keyPressEvent(self, event):
        if self.pages.currentIndex() == 0:
            if event.key() == Qt.Key_Space:
                self.toggle_play()
                return
            if event.key() in (Qt.Key_Left, Qt.Key_Right):
                step = -5000 if event.key() == Qt.Key_Left else 5000
                self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + step)))
                return
            if event.key() == Qt.Key_F:
                self.toggle_fullscreen()
                return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_file(url.toLocalFile())
                event.acceptProposedAction()
                break

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.t("选择保存文件夹"), self.folder.text())
        if folder:
            self.folder.setText(folder)

    def reveal_folder(self):
        folder = Path(self.folder.text())
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def start_download(self):
        if self.process is not None:
            return
        self._progress_event = None
        try:
            url = validate_url(self.url.text())
            folder = Path(self.folder.text()).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            if not os.access(folder, os.W_OK):
                raise ValueError("保存文件夹不可写，请选择其他位置。")
        except (ValueError, OSError) as error:
            self.text(self.download_status, str(error))
            return
        self.active_download_type = self.download_type.currentData()
        self.download_done = False
        self.download_cancelled = False
        self.download_result = None
        self.last_worker_error = ""
        self.last_worker_error_key = None
        self.warning_text = ""
        self.error_details = ""
        self.error_details_key = None
        self.worker_buffer = ""
        self.worker_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.text(self.download_title, "正在连接视频源")
        self.text(self.download_status, "正在读取视频信息…")
        self.progress.setRange(0, 0)
        self.result_button.setEnabled(False)
        self.details_button.setEnabled(False)
        self.set_download_busy(True)
        self.settings["download_folder"] = str(folder)
        process = QProcess(self)
        self.process = process
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self.read_worker)
        process.readyReadStandardError.connect(lambda: self.collect_stderr(process))
        process.finished.connect(self.worker_finished)
        process.errorOccurred.connect(self.worker_error)
        args = ["--download-worker", url, str(folder), self.quality.currentData(), self.active_download_type]
        if not getattr(sys, "frozen", False):
            args.insert(0, str(Path(__file__).resolve()))
        process.setWorkingDirectory(str(self.root))
        process.start(sys.executable, args)

    def set_download_busy(self, busy):
        for widget in (self.start_button, self.url, self.choose_folder_button, self.download_type):
            widget.setEnabled(not busy)
        self.quality.setEnabled(not busy and self.download_type.currentData() == "video")
        self.cancel_button.setEnabled(busy)

    def update_download_type(self):
        video = self.download_type.currentData() == "video"
        self.quality.setEnabled(video and self.process is None)
        self.quality_label.setVisible(video)
        self.quality.setVisible(video)

    def collect_stderr(self, process):
        message = bytes(process.readAllStandardError()).decode("utf-8", "replace").strip()
        if message:
            self.warning_text = message[-1600:]

    def read_worker(self):
        if self.process is None:
            return
        self.worker_buffer += self.worker_decoder.decode(bytes(self.process.readAllStandardOutput()))
        lines = self.worker_buffer.split("\n")
        self.worker_buffer = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            self.handle_worker_event(event)

    def handle_worker_event(self, data):
        event = data.get("event")
        if event in ("status", "processing", "completed", "failed"):
            self._progress_event = None
        if event in ("status", "processing"):
            self.text(self.download_status, data.get("message") or ("正在读取视频信息…" if event == "status" else "正在合并或整理视频…"))
            self.progress.setRange(0, 0)
        elif event == "warning":
            self.warning_text = data.get("message", "")
        elif event == "progress":
            self._progress_event = dict(data)
            self.render_download_progress(data)
        elif event == "completed":
            path = Path(data["path"])
            if not path.is_file():
                self.last_worker_error = "下载程序返回的文件不存在。"
                return
            self.download_done = True
            self.download_result = path
            self.progress.setRange(0, 1000)
            self.progress.setValue(1000)
            self.literal(self.download_title, path.name)
            self.text(self.download_status, "下载完成，音频已保存到所选文件夹。" if data.get("media_type") == "audio" else "下载完成，视频已保存到所选文件夹。")
            self.result_button.setEnabled(True)
        elif event == "failed":
            self.last_worker_error = data.get("message", "未知错误")
            self.last_worker_error_key = data.get("code")

    def render_download_progress(self, data):
        if data.get("title"):
            self.literal(self.download_title, data["title"])
        else:
            self.text(self.download_title, "正在下载")
        percent = data.get("percent")
        if percent is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(round(percent * 10))
        speed = data.get("speed")
        eta = data.get("eta")
        downloaded = (data.get("downloaded") or 0) / 1024**2
        parts = [f"{percent:.1f}%" if percent is not None else self.t("正在下载"), self.t("已下载 {amount} MB", amount=f"{downloaded:.1f}")]
        if speed:
            parts.append(f"{speed / 1024**2:.1f} MB/s")
        if eta is not None:
            parts.append(self.t("剩余 {time}", time=timestamp(eta * 1000)))
        self.literal(self.download_status, "  ·  ".join(parts))

    def worker_error(self, error):
        if error == QProcess.FailedToStart:
            self.last_worker_error = "下载组件启动失败，请检查项目文件是否完整。"
            self.worker_finished(-1, QProcess.CrashExit)

    def worker_finished(self, exit_code, status):
        self.read_worker()
        self._progress_event = None
        process = self.process
        self.process = None
        self.set_download_busy(False)
        if not self.download_done:
            self.progress.setRange(0, 1000)
            self.progress.setValue(0)
            if self.download_cancelled:
                self.text(self.download_title, "下载已取消")
                self.text(self.download_status, "已保留未完成的片段；再次下载相同链接时会尝试续传。")
            else:
                self.text(self.download_title, "下载未完成")
                reason = self.last_worker_error or self.warning_text or "连接中断，请稍后重试。"
                self.error_details = reason
                self.error_details_key = self.last_worker_error_key
                self.details_button.setEnabled(True)
                lower = reason.lower()
                if any(word in lower for word in ("sign in", "login", "cookies", "bot", "登录")):
                    summary = "网站要求登录或验证。第一版尚未接入登录，可换一条公开视频链接重试。"
                elif any(word in lower for word in ("timed out", "timeout", "resolve", "connection", "network")):
                    summary = "连接视频网站失败，请检查网络后重试。"
                elif any(word in lower for word in ("403", "412", "forbidden", "geo", "region")):
                    summary = "网站拒绝了当前请求，可能受到访问权限、地区或风控限制。"
                elif any(word in lower for word in ("unavailable", "not available", "private", "removed")):
                    summary = "这条视频目前不可访问，请换一个链接重试。"
                else:
                    summary = "未能完成下载。可点击「查看原因」检查具体信息，再重试。"
                self.text(self.download_status, self.last_worker_error_key or summary)
        if process:
            process.deleteLater()

    def cancel_download(self):
        self._progress_event = None
        if self.process:
            self.download_cancelled = True
            self.cancel_button.setEnabled(False)
            self.text(self.download_status, "正在取消…")
            process = self.process
            self.stop_process(process)
            def force_stop():
                if self.process is process and process.state() != QProcess.NotRunning:
                    self.stop_process(process, force=True)
            QTimer.singleShot(2000, force_stop)

    def stop_process(self, process, force=False):
        pid = process.processId()
        if pid:
            try:
                os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
                return
            except (ProcessLookupError, PermissionError):
                pass
        process.kill() if force else process.terminate()

    def show_download_error(self):
        if self.error_details:
            dialog = QDialog(self)
            dialog.setWindowTitle(self.t("下载详情"))
            dialog.resize(640, 360)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.addWidget(label(self.download_status.text(), wrap=True))
            details = QPlainTextEdit()
            details.setReadOnly(True)
            details.setPlainText(self.t(self.error_details_key or self.error_details))
            layout.addWidget(details)
            layout.addWidget(button(self.t("确定"), dialog.accept, True))
            dialog.exec()

    def play_download(self):
        if self.download_result:
            self.open_file(self.download_result)

    def closeEvent(self, event):
        if self.process is not None:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(self.t("正在下载标题"))
            dialog.setText(self.t("退出会停止当前下载，确定退出吗？"))
            dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            dialog.button(QMessageBox.Yes).setText(self.t("退出"))
            dialog.button(QMessageBox.No).setText(self.t("取消"))
            dialog.setDefaultButton(QMessageBox.No)
            choice = dialog.exec()
            if choice != QMessageBox.Yes:
                event.ignore()
                return
            self.stop_process(self.process, force=True)
            self.process.waitForFinished(2000)
        self.player.stop()
        self.settings["language"] = self.language
        self.settings["volume"] = self.audio.volume()
        self.settings["download_folder"] = self.folder.text()
        try:
            write_settings(self.settings)
        except OSError:
            pass
        event.accept()


def main():
    prepare_environment()
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setWindowIcon(QIcon(str(Path(__file__).parent / "icon.png")))
    application.setOrganizationName("Yingzhou")
    application.setFont(QFont("PingFang SC", 13))
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    window = PlayerWindow()
    window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        QTimer.singleShot(0, lambda: window.open_file(sys.argv[1]))
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
