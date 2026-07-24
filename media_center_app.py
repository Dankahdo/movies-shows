from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import yt_dlp
from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from broadcast import (
    BASE_DIR,
    DEFAULT_OUTPUT,
    MOVIES_DIR,
    SHOWS_DIR,
    scan_all_shows,
    scan_movies,
    write_m3u,
)
from RipYoutube import resolve_download_url
from timestampSplitter import split_media

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".webm"}
APP_STATE_FILE = BASE_DIR / "app_state.json"
THUMBNAILS_DIR = BASE_DIR / ".thumbnails"
COLLECTION_TAG_PATTERN = re.compile(r"^\(\s*(completed|complete|ip)\s*\)\s*", re.IGNORECASE)


def parse_collection_tag(folder_name: str) -> tuple[str, str]:
    match = COLLECTION_TAG_PATTERN.match(folder_name)
    if not match:
        return "Unspecified", folder_name

    tag = match.group(1).lower()
    clean_name = folder_name[match.end() :].strip() or folder_name
    if tag in {"completed", "complete"}:
        return "Completed", clean_name
    if tag == "ip":
        return "In Progress", clean_name
    return "Unspecified", clean_name


def status_badge_text(status: str) -> str:
    if status == "Completed":
        return "Completed"
    if status == "In Progress":
        return "IP"
    return "Unspecified"


@dataclass
class MediaItem:
    path: Path
    kind: str
    title: str
    group: str
    collection_status: str = "Unspecified"


class AppState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = {
            "recent": [],
            "reviews": {},
            "broadcast_excluded_shows": [],
            "broadcast_excluded_movies": [],
            "settings": {
                "shows_dir": str(SHOWS_DIR),
                "movies_dir": str(MOVIES_DIR),
                "skip_seconds": 5,
                "autoplay": True,
            },
            "broadcast": {
                "output_path": str(DEFAULT_OUTPUT),
                "last_index": 0,
                "last_position_ms": 0,
                "completed_only_default": True,
            },
            "custom_thumbnails": {},
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                self.data.update(content)
        except Exception:
            pass

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")


class MediaCenterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Media Center")
        self.resize(1450, 900)

        self.state = AppState(APP_STATE_FILE)
        self.media_items: list[MediaItem] = []
        self.media_lookup: dict[str, MediaItem] = {}
        self.group_first_media: dict[str, Path] = {}
        self.thumbnail_attempted_keys: set[str] = set()
        self.current_queue: list[Path] = []
        self.current_index = -1
        self.loop_queue = True
        self.current_queue_kind = "manual"
        self.is_seeking = False
        self.broadcast_queue: list[Path] = []
        self.pending_restore_position_ms: int | None = None

        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setSingleShot(True)
        self.controls_hide_timer.timeout.connect(self._fade_out_controls)
        self.controls_target_visible = True

        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)

        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._install_shortcuts()

        self._build_ui()
        self.refresh_library()
        self.refresh_broadcast_lists()
        self.refresh_recent_view()
        self.restore_broadcast_session()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)

        player_box = QGroupBox("Player")
        player_layout = QVBoxLayout(player_box)
        player_layout.addWidget(self.video_widget, stretch=1)

        self.control_bar = QWidget()
        control_bar_layout = QVBoxLayout(self.control_bar)
        control_bar_layout.setContentsMargins(0, 0, 0, 0)
        control_bar_layout.setSpacing(6)

        controls = QHBoxLayout()
        self.play_pause_button = QPushButton("Play")
        self.next_button = QPushButton("Next")
        self.prev_button = QPushButton("Previous")
        self.tabs_toggle_button = QPushButton("Hide Tabs")
        self.fullscreen_button = QPushButton("Fullscreen")
        self.position_label = QLabel("00:00 / 00:00")
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.setSingleStep(1)
        self.progress.setPageStep(50)
        self.progress.setToolTip("Drag to seek")

        self.tabs_toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        controls.addWidget(self.play_pause_button)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.tabs_toggle_button)
        controls.addWidget(self.fullscreen_button)
        controls.addWidget(self.position_label)

        control_bar_layout.addLayout(controls)
        control_bar_layout.addWidget(self.progress)
        player_layout.addWidget(self.control_bar)

        self.controls_opacity_effect = QGraphicsOpacityEffect(self.control_bar)
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setGraphicsEffect(self.controls_opacity_effect)

        self.controls_fade_animation = QPropertyAnimation(self.controls_opacity_effect, b"opacity", self)
        self.controls_fade_animation.setDuration(260)
        self.controls_fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.controls_fade_animation.finished.connect(self._on_controls_fade_finished)

        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.next_button.clicked.connect(self.play_next)
        self.prev_button.clicked.connect(self.play_previous)
        self.tabs_toggle_button.clicked.connect(self.toggle_tabs_panel)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.progress.sliderPressed.connect(self._on_seek_start)
        self.progress.sliderReleased.connect(self._on_seek_end)
        self.progress.sliderMoved.connect(self._on_seek_preview)

        self.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)
        self.control_bar.setMouseTracking(True)
        self.video_widget.installEventFilter(self)
        self.control_bar.installEventFilter(self)

        self.tabs = QTabWidget()
        self.home_tab = self._build_home_tab()
        self.library_tab = self._build_library_tab()
        self.broadcast_tab = self._build_broadcast_tab()
        self.tools_tab = self._build_tools_tab()
        self.settings_tab = self._build_settings_tab()

        self.tabs.addTab(self.home_tab, "Home")
        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.broadcast_tab, "Broadcast")
        self.tabs.addTab(self.tools_tab, "Tools")
        self.tabs.addTab(self.settings_tab, "Settings")

        root_layout.addWidget(player_box, stretch=3)
        root_layout.addWidget(self.tabs, stretch=2)

        self.setCentralWidget(root)

        refresh_action = QAction("Refresh Library", self)
        refresh_action.triggered.connect(self.refresh_library)
        self.addAction(refresh_action)

    def _install_shortcuts(self) -> None:
        self.shortcut_toggle_f11 = QShortcut(QKeySequence("F11"), self)
        self.shortcut_toggle_f11.setContext(Qt.ApplicationShortcut)
        self.shortcut_toggle_f11.activated.connect(self.toggle_fullscreen)

        self.shortcut_toggle_f = QShortcut(QKeySequence("F"), self)
        self.shortcut_toggle_f.setContext(Qt.ApplicationShortcut)
        self.shortcut_toggle_f.activated.connect(self.toggle_fullscreen)

        self.shortcut_exit_esc = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_exit_esc.setContext(Qt.ApplicationShortcut)
        self.shortcut_exit_esc.activated.connect(self.exit_fullscreen)

    def eventFilter(self, watched, event) -> bool:
        if self.isFullScreen() and event.type() in (QEvent.Type.MouseMove, QEvent.Type.Enter):
            self._show_controls_temporarily()
        return super().eventFilter(watched, event)

    def _build_home_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QLabel("Recently Viewed")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._play_recent_item)

        layout.addWidget(header)
        layout.addWidget(self.recent_list)
        return tab

    def _build_library_tab(self) -> QWidget:
        tab = QWidget()
        main = QVBoxLayout(tab)

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search title, series, or filename")
        self.filter_box = QComboBox()
        self.filter_box.addItems(["All", "Movies", "Shows"])
        self.collection_filter_box = QComboBox()
        self.collection_filter_box.addItems(["All Status", "Completed", "In Progress", "Unspecified"])
        refresh_btn = QPushButton("Refresh")

        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self.search_box, stretch=1)
        toolbar.addWidget(QLabel("Filter:"))
        toolbar.addWidget(self.filter_box)
        toolbar.addWidget(QLabel("Collection:"))
        toolbar.addWidget(self.collection_filter_box)
        toolbar.addWidget(refresh_btn)

        splitter = QSplitter()
        self.library_tree = QTreeWidget()
        self.library_tree.setHeaderLabels(["Title", "Type", "Location"])
        self.library_tree.itemSelectionChanged.connect(self._on_library_selection)
        self.library_tree.itemDoubleClicked.connect(self._play_selected_library_item)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.selected_title = QLabel("Select an item")
        self.rating_spin = QSpinBox()
        self.rating_spin.setRange(0, 5)
        self.rating_spin.setToolTip("0 means unrated")
        self.note_box = QTextEdit()
        self.note_box.setPlaceholderText("Your review/notes...")

        save_review = QPushButton("Save Review")
        play_now = QPushButton("Play Selected")
        set_thumbnail = QPushButton("Set Custom Image")

        review_form = QFormLayout()
        review_form.addRow("Title", self.selected_title)
        review_form.addRow("Rating (0-5)", self.rating_spin)
        review_form.addRow("Notes", self.note_box)

        right_layout.addLayout(review_form)
        right_layout.addWidget(save_review)
        right_layout.addWidget(set_thumbnail)
        right_layout.addWidget(play_now)
        right_layout.addStretch(1)

        splitter.addWidget(self.library_tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main.addLayout(toolbar)
        main.addWidget(splitter)

        self.search_box.textChanged.connect(self.populate_library_tree)
        self.filter_box.currentIndexChanged.connect(self.populate_library_tree)
        self.collection_filter_box.currentIndexChanged.connect(self.populate_library_tree)
        refresh_btn.clicked.connect(self.refresh_library)
        save_review.clicked.connect(self.save_current_review)
        set_thumbnail.clicked.connect(self.set_custom_thumbnail_for_selected)
        play_now.clicked.connect(self._play_selected_library_item)

        return tab

    def _build_broadcast_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        settings_box = QGroupBox("Broadcast Generation")
        settings_layout = QGridLayout(settings_box)

        self.bc_include_movies = QCheckBox("Interleave movies")
        self.bc_include_movies.setChecked(True)

        broadcast_state = self.state.data.get("broadcast", {})
        self.bc_completed_only_default = QCheckBox("Include only Completed by default")
        self.bc_completed_only_default.setChecked(bool(broadcast_state.get("completed_only_default", True)))

        self.bc_movie_every = QSpinBox()
        self.bc_movie_every.setRange(1, 100)
        self.bc_movie_every.setValue(8)

        self.bc_output = QLineEdit(str(broadcast_state.get("output_path", str(DEFAULT_OUTPUT))))
        output_btn = QPushButton("Browse")

        settings_layout.addWidget(
            QLabel("Broadcast always includes every episode from included shows."), 0, 0, 1, 3
        )
        settings_layout.addWidget(self.bc_include_movies, 1, 0, 1, 2)
        settings_layout.addWidget(self.bc_completed_only_default, 1, 2)

        settings_layout.addWidget(QLabel("Movie every N episodes"), 2, 0)
        settings_layout.addWidget(self.bc_movie_every, 2, 1)

        settings_layout.addWidget(QLabel("Output M3U"), 3, 0)
        settings_layout.addWidget(self.bc_output, 3, 1)
        settings_layout.addWidget(output_btn, 3, 2)

        settings_layout.addWidget(QLabel("Playback loops forever when started from this tab."), 4, 0, 1, 3)

        list_box = QGroupBox("Include / Exclude")
        list_layout = QHBoxLayout(list_box)

        self.bc_show_list = QListWidget()
        self.bc_movie_list = QListWidget()
        list_layout.addWidget(self._wrap_labeled_widget("Shows", self.bc_show_list))
        list_layout.addWidget(self._wrap_labeled_widget("Movies", self.bc_movie_list))

        action_bar = QHBoxLayout()
        self.bc_generate_btn = QPushButton("Generate Broadcast Playlist")
        self.bc_play_btn = QPushButton("Play Generated Playlist")
        self.bc_status = QLabel("")

        action_bar.addWidget(self.bc_generate_btn)
        action_bar.addWidget(self.bc_play_btn)
        action_bar.addWidget(self.bc_status, stretch=1)

        output_btn.clicked.connect(self._browse_broadcast_output)
        self.bc_generate_btn.clicked.connect(self.generate_broadcast)
        self.bc_play_btn.clicked.connect(self.play_generated_playlist)
        self.bc_completed_only_default.stateChanged.connect(self._on_broadcast_default_filter_changed)

        queue_box = QGroupBox("Broadcast Queue")
        queue_layout = QVBoxLayout(queue_box)
        self.bc_queue_list = QListWidget()
        self.bc_queue_list.setAlternatingRowColors(True)
        self.bc_queue_list.itemDoubleClicked.connect(self.play_selected_broadcast_item)
        queue_actions = QHBoxLayout()
        self.bc_jump_btn = QPushButton("Play Selected")
        self.bc_refresh_btn = QPushButton("Load Queue From M3U")
        queue_actions.addWidget(self.bc_jump_btn)
        queue_actions.addWidget(self.bc_refresh_btn)
        queue_actions.addStretch(1)

        queue_layout.addWidget(self.bc_queue_list)
        queue_layout.addLayout(queue_actions)

        self.bc_jump_btn.clicked.connect(self.play_selected_broadcast_item)
        self.bc_refresh_btn.clicked.connect(self.load_broadcast_queue_from_file)

        layout.addWidget(settings_box)
        layout.addWidget(list_box, stretch=1)
        layout.addWidget(queue_box, stretch=2)
        layout.addLayout(action_bar)
        return tab

    def _build_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        yt_box = QGroupBox("YouTube Rip")
        yt_layout = QGridLayout(yt_box)

        self.yt_url = QLineEdit()
        self.yt_output = QLineEdit(str(BASE_DIR / "downloads"))
        yt_output_btn = QPushButton("Browse")
        self.yt_single = QCheckBox("Single video only")
        self.yt_run_btn = QPushButton("Download")

        yt_layout.addWidget(QLabel("URL"), 0, 0)
        yt_layout.addWidget(self.yt_url, 0, 1, 1, 2)
        yt_layout.addWidget(QLabel("Output directory"), 1, 0)
        yt_layout.addWidget(self.yt_output, 1, 1)
        yt_layout.addWidget(yt_output_btn, 1, 2)
        yt_layout.addWidget(self.yt_single, 2, 1)
        yt_layout.addWidget(self.yt_run_btn, 2, 2)

        split_box = QGroupBox("Timestamp Splitter")
        split_layout = QGridLayout(split_box)

        self.ts_input = QLineEdit()
        self.ts_marks = QLineEdit(str(BASE_DIR / "timestamps.txt"))
        self.ts_output = QLineEdit(str(BASE_DIR / "split_output"))
        self.ts_ffmpeg_bin = QLineEdit("")
        self.ts_reencode = QCheckBox("Re-encode")
        self.ts_run_btn = QPushButton("Split")

        ts_input_btn = QPushButton("Browse")
        ts_marks_btn = QPushButton("Browse")
        ts_output_btn = QPushButton("Browse")
        ts_ffmpeg_btn = QPushButton("Browse")

        split_layout.addWidget(QLabel("Input media"), 0, 0)
        split_layout.addWidget(self.ts_input, 0, 1)
        split_layout.addWidget(ts_input_btn, 0, 2)

        split_layout.addWidget(QLabel("Timestamp file"), 1, 0)
        split_layout.addWidget(self.ts_marks, 1, 1)
        split_layout.addWidget(ts_marks_btn, 1, 2)

        split_layout.addWidget(QLabel("Output directory"), 2, 0)
        split_layout.addWidget(self.ts_output, 2, 1)
        split_layout.addWidget(ts_output_btn, 2, 2)

        split_layout.addWidget(QLabel("FFmpeg bin (optional)"), 3, 0)
        split_layout.addWidget(self.ts_ffmpeg_bin, 3, 1)
        split_layout.addWidget(ts_ffmpeg_btn, 3, 2)

        split_layout.addWidget(self.ts_reencode, 4, 1)
        split_layout.addWidget(self.ts_run_btn, 4, 2)

        self.tools_log = QPlainTextEdit()
        self.tools_log.setReadOnly(True)

        yt_output_btn.clicked.connect(lambda: self._browse_dir_into(self.yt_output))
        self.yt_run_btn.clicked.connect(self.run_youtube_download)

        ts_input_btn.clicked.connect(lambda: self._browse_file_into(self.ts_input))
        ts_marks_btn.clicked.connect(lambda: self._browse_file_into(self.ts_marks))
        ts_output_btn.clicked.connect(lambda: self._browse_dir_into(self.ts_output))
        ts_ffmpeg_btn.clicked.connect(lambda: self._browse_dir_into(self.ts_ffmpeg_bin))
        self.ts_run_btn.clicked.connect(self.run_timestamp_splitter)

        layout.addWidget(yt_box)
        layout.addWidget(split_box)
        layout.addWidget(self.tools_log, stretch=1)
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)

        settings = self.state.data.get("settings", {})

        self.set_shows_dir = QLineEdit(settings.get("shows_dir", str(SHOWS_DIR)))
        self.set_movies_dir = QLineEdit(settings.get("movies_dir", str(MOVIES_DIR)))
        self.set_skip_seconds = QSpinBox()
        self.set_skip_seconds.setRange(1, 60)
        self.set_skip_seconds.setValue(int(settings.get("skip_seconds", 5)))
        self.set_autoplay = QCheckBox("Autoplay next item")
        self.set_autoplay.setChecked(bool(settings.get("autoplay", True)))

        shows_browse = QPushButton("Browse")
        movies_browse = QPushButton("Browse")
        save_button = QPushButton("Save Settings")

        shows_line = self._with_button(self.set_shows_dir, shows_browse)
        movies_line = self._with_button(self.set_movies_dir, movies_browse)

        shows_browse.clicked.connect(lambda: self._browse_dir_into(self.set_shows_dir))
        movies_browse.clicked.connect(lambda: self._browse_dir_into(self.set_movies_dir))
        save_button.clicked.connect(self.save_settings)

        layout.addRow("Shows folder", shows_line)
        layout.addRow("Movies folder", movies_line)
        layout.addRow("Arrow key skip (seconds)", self.set_skip_seconds)
        layout.addRow("", self.set_autoplay)
        layout.addRow("", save_button)

        return tab

    def _with_button(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        l = QHBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(line_edit)
        l.addWidget(button)
        return box

    def _wrap_labeled_widget(self, label: str, widget: QWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(widget)
        return box

    def _browse_dir_into(self, line_edit: QLineEdit) -> None:
        current = line_edit.text().strip() or str(BASE_DIR)
        selected = QFileDialog.getExistingDirectory(self, "Select Directory", current)
        if selected:
            line_edit.setText(selected)

    def _browse_file_into(self, line_edit: QLineEdit) -> None:
        current = line_edit.text().strip() or str(BASE_DIR)
        file_name, _ = QFileDialog.getOpenFileName(self, "Select File", current)
        if file_name:
            line_edit.setText(file_name)

    def _browse_broadcast_output(self) -> None:
        current = self.bc_output.text().strip() or str(DEFAULT_OUTPUT)
        file_name, _ = QFileDialog.getSaveFileName(self, "Select M3U Output", current, "M3U Files (*.m3u)")
        if file_name:
            self.bc_output.setText(file_name)

    def _on_broadcast_default_filter_changed(self) -> None:
        broadcast_state = self.state.data.setdefault("broadcast", {})
        broadcast_state["completed_only_default"] = self.bc_completed_only_default.isChecked()
        self.state.save()
        self.refresh_broadcast_lists()

    def toggle_play_pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_button.setText("Pause")
        else:
            self.play_pause_button.setText("Play")

    def toggle_tabs_panel(self) -> None:
        tabs_visible = self.tabs.isVisible()
        self.tabs.setVisible(not tabs_visible)
        if tabs_visible:
            self.tabs_toggle_button.setText("Show Tabs")
            self.tabs_toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        else:
            self.tabs_toggle_button.setText("Hide Tabs")
            self.tabs_toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))

    def _thumbnail_key(self, media: MediaItem) -> str:
        return f"{media.kind}:{media.group}"

    def _safe_thumbnail_name(self, key: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)

    def _ensure_auto_thumbnail_for_key(self, key: str, source_video: Path) -> Path | None:
        if key in self.thumbnail_attempted_keys:
            candidate = THUMBNAILS_DIR / f"{self._safe_thumbnail_name(key)}.jpg"
            return candidate if candidate.exists() else None

        self.thumbnail_attempted_keys.add(key)
        if shutil.which("ffmpeg") is None:
            return None

        THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = THUMBNAILS_DIR / f"{self._safe_thumbnail_name(key)}.jpg"
        if output_path.exists():
            return output_path

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    "00:00:05",
                    "-i",
                    str(source_video),
                    "-frames:v",
                    "1",
                    str(output_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if output_path.exists():
                return output_path
        except Exception:
            return None
        return None

    def _icon_for_media_item(self, media: MediaItem) -> QIcon:
        key = self._thumbnail_key(media)
        custom = self.state.data.get("custom_thumbnails", {}).get(key)
        if custom and Path(custom).exists():
            return QIcon(custom)

        source_video = self.group_first_media.get(key)
        if source_video and source_video.exists():
            auto_thumb = self._ensure_auto_thumbnail_for_key(key, source_video)
            if auto_thumb and auto_thumb.exists():
                return QIcon(str(auto_thumb))

        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _media_item_for_path(self, path: Path) -> MediaItem | None:
        existing = self.media_lookup.get(str(path))
        if existing:
            return existing

        settings = self.state.data.get("settings", {})
        shows_dir = Path(settings.get("shows_dir", str(SHOWS_DIR)))
        movies_dir = Path(settings.get("movies_dir", str(MOVIES_DIR)))

        try:
            rel_show = path.relative_to(shows_dir)
            if len(rel_show.parts) >= 2:
                status, _ = parse_collection_tag(rel_show.parts[0])
                return MediaItem(
                    path=path,
                    kind="Show",
                    title=path.stem,
                    group=rel_show.parts[0],
                    collection_status=status,
                )
        except Exception:
            pass

        try:
            rel_movie = path.relative_to(movies_dir)
            group = rel_movie.parts[0] if len(rel_movie.parts) > 1 else movies_dir.name
            status, _ = parse_collection_tag(group)
            return MediaItem(
                path=path,
                kind="Movie",
                title=path.stem,
                group=group,
                collection_status=status,
            )
        except Exception:
            pass

        return None

    def set_custom_thumbnail_for_selected(self) -> None:
        items = self.library_tree.selectedItems()
        if not items:
            QMessageBox.information(self, "Custom Image", "Select a library item first.")
            return

        path_str = items[0].data(0, Qt.UserRole)
        if not path_str:
            QMessageBox.information(self, "Custom Image", "Select a library item first.")
            return

        media = self._find_media_by_path(path_str)
        if not media:
            QMessageBox.information(self, "Custom Image", "Selected media not found.")
            return

        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Thumbnail Image",
            str(BASE_DIR),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not image_path:
            return

        key = self._thumbnail_key(media)
        self.state.data.setdefault("custom_thumbnails", {})[key] = image_path
        self.state.save()
        self.populate_library_tree()
        self.refresh_recent_view()
        self._set_broadcast_queue_view(self.broadcast_queue)

    def _threaded(self, fn: Callable[[], None], done: Callable[[str, bool], None]) -> None:
        def runner() -> None:
            try:
                fn()
                self._invoke_in_ui(lambda: done("Completed", True))
            except Exception:
                message = traceback.format_exc()
                self._invoke_in_ui(lambda: done(message, False))

        threading.Thread(target=runner, daemon=True).start()

    def _invoke_in_ui(self, callback: Callable[[], None]) -> None:
        QApplication.instance().postEvent(self, _CallbackEvent(callback))

    def customEvent(self, event) -> None:  # noqa: N802
        if isinstance(event, _CallbackEvent):
            event.callback()
            return
        super().customEvent(event)

    def refresh_library(self) -> None:
        shows_dir = Path(self.state.data.get("settings", {}).get("shows_dir", str(SHOWS_DIR)))
        movies_dir = Path(self.state.data.get("settings", {}).get("movies_dir", str(MOVIES_DIR)))

        self.media_items = []
        self.media_lookup = {}
        self.group_first_media = {}

        if movies_dir.exists():
            for root, _, files in os.walk(movies_dir):
                group_name = Path(root).name
                collection_status, _ = parse_collection_tag(group_name)
                for name in files:
                    path = Path(root) / name
                    if path.suffix.lower() in VIDEO_EXTENSIONS:
                        self.media_items.append(
                            MediaItem(
                                path=path,
                                kind="Movie",
                                title=path.stem,
                                group=group_name,
                                collection_status=collection_status,
                            )
                        )

        if shows_dir.exists():
            for show_folder in sorted([p for p in shows_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                collection_status, _ = parse_collection_tag(show_folder.name)
                for root, _, files in os.walk(show_folder):
                    for name in files:
                        path = Path(root) / name
                        if path.suffix.lower() in VIDEO_EXTENSIONS:
                            self.media_items.append(
                                MediaItem(
                                    path=path,
                                    kind="Show",
                                    title=path.stem,
                                    group=show_folder.name,
                                    collection_status=collection_status,
                                )
                            )

        self.media_items.sort(key=lambda m: str(m.path).lower())
        for media in self.media_items:
            self.media_lookup[str(media.path)] = media
            key = self._thumbnail_key(media)
            if key not in self.group_first_media:
                self.group_first_media[key] = media.path

        self.populate_library_tree()
        self.refresh_broadcast_lists()

    def populate_library_tree(self) -> None:
        query = self.search_box.text().strip().lower()
        filter_value = self.filter_box.currentText()
        status_filter = self.collection_filter_box.currentText()

        self.library_tree.clear()

        grouped: dict[str, list[MediaItem]] = {}
        for item in self.media_items:
            if filter_value == "Movies" and item.kind != "Movie":
                continue
            if filter_value == "Shows" and item.kind != "Show":
                continue

            if status_filter != "All Status" and item.collection_status != status_filter:
                continue

            searchable = f"{item.title} {item.group} {item.path.name}".lower()
            if query and query not in searchable:
                continue

            grouped.setdefault(item.group, []).append(item)

        for group_name in sorted(grouped):
            status, clean_group_name = parse_collection_tag(group_name)
            parent_label = f"{clean_group_name} [{status_badge_text(status)}]"
            parent = QTreeWidgetItem([parent_label, "", ""])
            group_icon_set = False
            self.library_tree.addTopLevelItem(parent)
            for media in sorted(grouped[group_name], key=lambda m: m.title.lower()):
                child = QTreeWidgetItem([media.title, media.kind, str(media.path)])
                icon = self._icon_for_media_item(media)
                child.setIcon(0, icon)
                child.setData(0, Qt.UserRole, str(media.path))
                parent.addChild(child)
                if not group_icon_set:
                    parent.setIcon(0, icon)
                    group_icon_set = True
            parent.setExpanded(False)

        self._focus_current_library_item()

    def _find_media_by_path(self, path_str: str) -> MediaItem | None:
        for item in self.media_items:
            if str(item.path) == path_str:
                return item
        return None

    def _natural_text_key(self, text: str) -> list:
        parts = re.split(r"(\d+)", text)
        return [int(p) if p.isdigit() else p.lower() for p in parts]

    def _series_queue_for_media(self, media: MediaItem) -> tuple[list[Path], int]:
        if media.kind != "Show":
            return [media.path], 0

        series_items = [m for m in self.media_items if m.kind == "Show" and m.group == media.group]
        series_items.sort(key=lambda m: self._natural_text_key(str(m.path)))

        queue = [m.path for m in series_items]
        selected_path = str(media.path)
        start_index = next((i for i, p in enumerate(queue) if str(p) == selected_path), 0)
        return queue, start_index

    def _on_library_selection(self) -> None:
        items = self.library_tree.selectedItems()
        if not items:
            return
        path_str = items[0].data(0, Qt.UserRole)
        if not path_str:
            return

        media = self._find_media_by_path(path_str)
        if not media:
            return

        self.selected_title.setText(media.title)
        review = self.state.data.get("reviews", {}).get(path_str, {})
        self.rating_spin.setValue(int(review.get("rating", 0)))
        self.note_box.setPlainText(review.get("note", ""))

    def save_current_review(self) -> None:
        items = self.library_tree.selectedItems()
        if not items:
            QMessageBox.information(self, "Review", "Select a media item first.")
            return

        path_str = items[0].data(0, Qt.UserRole)
        if not path_str:
            QMessageBox.information(self, "Review", "Select a media item first.")
            return

        self.state.data.setdefault("reviews", {})[path_str] = {
            "rating": self.rating_spin.value(),
            "note": self.note_box.toPlainText().strip(),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        self.state.save()
        QMessageBox.information(self, "Review", "Review saved.")

    def _play_selected_library_item(self) -> None:
        items = self.library_tree.selectedItems()
        if not items:
            return
        path_str = items[0].data(0, Qt.UserRole)
        if not path_str:
            return

        media = self._find_media_by_path(path_str)
        if not media:
            return

        queue, start_index = self._series_queue_for_media(media)
        self.play_paths(queue, start_index=start_index, loop=False)

    def _play_recent_item(self, item: QListWidgetItem) -> None:
        path_str = item.data(Qt.UserRole)
        if not path_str:
            return
        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "Missing File", f"File not found:\n{path}")
            return
        self.play_paths([path], start_index=0, loop=False)

    def play_paths(
        self,
        paths: list[Path],
        start_index: int = 0,
        loop: bool = True,
        queue_kind: str = "manual",
        autoplay: bool = True,
        add_recent: bool = True,
    ) -> None:
        valid_paths = [p for p in paths if p.exists()]
        if not valid_paths:
            QMessageBox.warning(self, "Playback", "No playable files were found.")
            return

        self.current_queue = valid_paths
        self.current_index = max(0, min(start_index, len(valid_paths) - 1))
        self.loop_queue = loop
        self.current_queue_kind = queue_kind
        self._play_current_index(autoplay=autoplay, add_recent=add_recent)

    def _play_current_index(self, autoplay: bool = True, add_recent: bool = True) -> None:
        if self.current_index < 0 or self.current_index >= len(self.current_queue):
            return

        current_path = self.current_queue[self.current_index]
        self.player.setSource(QUrl.fromLocalFile(str(current_path)))
        if autoplay:
            self.player.play()
        else:
            self.player.pause()
        if add_recent:
            self._add_recent(current_path)
        self._update_broadcast_queue_highlight()
        self._focus_current_library_item()

    def play_next(self) -> None:
        if not self.current_queue:
            return
        if self.current_index + 1 < len(self.current_queue):
            self.current_index += 1
            self._play_current_index()
            return
        if self.loop_queue and self.current_queue:
            self.current_index = 0
            self._play_current_index()

    def play_previous(self) -> None:
        if not self.current_queue:
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._play_current_index()
        elif self.loop_queue and self.current_queue:
            self.current_index = len(self.current_queue) - 1
            self._play_current_index()

    def _set_broadcast_queue_view(self, paths: list[Path]) -> None:
        self.broadcast_queue = paths[:]
        self.bc_queue_list.clear()
        for idx, path in enumerate(paths, start=1):
            label = f"{idx:04d}  |  {path.name}"
            item = QListWidgetItem(label)
            media = self._media_item_for_path(path)
            if media:
                item.setIcon(self._icon_for_media_item(media))
            item.setData(Qt.UserRole, str(path))
            self.bc_queue_list.addItem(item)
        self._update_broadcast_queue_highlight()

    def _update_broadcast_queue_highlight(self) -> None:
        if not self.broadcast_queue:
            return
        if self.current_queue != self.broadcast_queue:
            self.bc_queue_list.clearSelection()
            return
        if self.current_index < 0 or self.current_index >= self.bc_queue_list.count():
            return

        self.bc_queue_list.setCurrentRow(self.current_index)
        self.bc_queue_list.scrollToItem(self.bc_queue_list.item(self.current_index))

    def _focus_current_library_item(self) -> None:
        if not self.current_queue or self.current_index < 0 or self.current_index >= len(self.current_queue):
            return

        target_path = str(self.current_queue[self.current_index])
        iterator = QTreeWidgetItemIterator(self.library_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0 and item.data(0, Qt.UserRole) == target_path:
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
                self.library_tree.setCurrentItem(item)
                self.library_tree.scrollToItem(item)
                return
            iterator += 1

    def play_selected_broadcast_item(self) -> None:
        if not self.broadcast_queue:
            QMessageBox.information(self, "Broadcast Queue", "No broadcast queue loaded yet.")
            return

        row = self.bc_queue_list.currentRow()
        if row < 0 or row >= len(self.broadcast_queue):
            QMessageBox.information(self, "Broadcast Queue", "Select an item in the queue first.")
            return

        self.play_paths(self.broadcast_queue, start_index=row, loop=True, queue_kind="broadcast")
        self._persist_broadcast_resume_state()

    def _read_m3u_playlist_paths(self, playlist_file: Path) -> list[Path]:
        playlist_paths: list[Path] = []
        for line in playlist_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            playlist_paths.append(Path(line))
        return playlist_paths

    def _persist_broadcast_resume_state(self) -> None:
        broadcast_state = self.state.data.setdefault("broadcast", {})
        broadcast_state["output_path"] = self.bc_output.text().strip() or str(DEFAULT_OUTPUT)
        broadcast_state["completed_only_default"] = self.bc_completed_only_default.isChecked()

        if self.broadcast_queue:
            resolved_index = 0
            if self.current_queue and 0 <= self.current_index < len(self.current_queue):
                current_path = self.current_queue[self.current_index]
                if current_path in self.broadcast_queue:
                    resolved_index = self.broadcast_queue.index(current_path)
            broadcast_state["last_index"] = int(resolved_index)
            broadcast_state["last_position_ms"] = int(max(0, self.player.position()))
        else:
            broadcast_state["last_index"] = 0
            broadcast_state["last_position_ms"] = 0

        self.state.save()

    def restore_broadcast_session(self) -> None:
        output = Path(self.bc_output.text().strip() or str(DEFAULT_OUTPUT))
        if not output.exists():
            return

        playlist_paths = self._read_m3u_playlist_paths(output)
        if not playlist_paths:
            return

        broadcast_state = self.state.data.get("broadcast", {})
        last_index = int(broadcast_state.get("last_index", 0))
        last_position_ms = int(broadcast_state.get("last_position_ms", 0))

        last_index = max(0, min(last_index, len(playlist_paths) - 1))

        self._set_broadcast_queue_view(playlist_paths)
        self.pending_restore_position_ms = max(0, last_position_ms)
        self.play_paths(
            playlist_paths,
            start_index=last_index,
            loop=True,
            queue_kind="broadcast",
            autoplay=False,
            add_recent=False,
        )
        self.bc_status.setText(f"Restored broadcast session: item {last_index + 1}/{len(playlist_paths)}")

    def load_broadcast_queue_from_file(self) -> None:
        output = Path(self.bc_output.text().strip() or str(DEFAULT_OUTPUT))
        if not output.exists():
            QMessageBox.warning(self, "Broadcast Queue", f"Playlist file does not exist:\n{output}")
            return

        playlist_paths = self._read_m3u_playlist_paths(output)

        self._set_broadcast_queue_view(playlist_paths)
        self.bc_status.setText(f"Loaded queue from file: {len(playlist_paths)} items")
        self._persist_broadcast_resume_state()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self.pending_restore_position_ms is not None and status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.player.setPosition(max(0, int(self.pending_restore_position_ms)))
            self.pending_restore_position_ms = None

        autoplay = bool(self.state.data.get("settings", {}).get("autoplay", True))
        if autoplay and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_next()

    def _on_position_changed(self, ms: int) -> None:
        duration = self.player.duration()
        if duration > 0:
            if not self.is_seeking:
                self.progress.setValue(int(ms * 1000 / duration))
            self.position_label.setText(f"{self._fmt_time(ms)} / {self._fmt_time(duration)}")
        else:
            self.progress.setValue(0)
            self.position_label.setText("00:00 / 00:00")

    def _on_duration_changed(self, _ms: int) -> None:
        self._on_position_changed(self.player.position())

    def _fmt_time(self, ms: int) -> str:
        sec = max(0, int(ms / 1000))
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _seek_to_slider_value(self, slider_value: int) -> None:
        duration = self.player.duration()
        if duration <= 0:
            return
        position = int((slider_value / 1000.0) * duration)
        self.player.setPosition(position)

    def _on_seek_start(self) -> None:
        self.is_seeking = True

    def _on_seek_preview(self, slider_value: int) -> None:
        duration = self.player.duration()
        if duration <= 0:
            return
        preview_position = int((slider_value / 1000.0) * duration)
        self.position_label.setText(f"{self._fmt_time(preview_position)} / {self._fmt_time(duration)}")

    def _on_seek_end(self) -> None:
        self._seek_to_slider_value(self.progress.value())
        self.is_seeking = False

    def _on_controls_fade_finished(self) -> None:
        if not self.controls_target_visible:
            self.control_bar.setVisible(False)

    def _animate_controls_visibility(self, visible: bool) -> None:
        self.controls_target_visible = visible
        self.controls_fade_animation.stop()

        if visible:
            if not self.control_bar.isVisible():
                self.control_bar.setVisible(True)
            start_opacity = self.controls_opacity_effect.opacity()
            self.controls_fade_animation.setStartValue(start_opacity)
            self.controls_fade_animation.setEndValue(1.0)
            self.controls_fade_animation.start()
            return

        if not self.control_bar.isVisible():
            return
        start_opacity = self.controls_opacity_effect.opacity()
        self.controls_fade_animation.setStartValue(start_opacity)
        self.controls_fade_animation.setEndValue(0.0)
        self.controls_fade_animation.start()

    def _show_controls_temporarily(self) -> None:
        if not self.isFullScreen():
            return
        self._animate_controls_visibility(True)
        self.controls_hide_timer.start(2500)

    def _fade_out_controls(self) -> None:
        if not self.isFullScreen():
            return
        if self.progress.isSliderDown():
            self.controls_hide_timer.start(1500)
            return
        self._animate_controls_visibility(False)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return

        # Keep player controls available in fullscreen by fullscreening the app window,
        # not just the raw video surface.
        self.tabs.setVisible(False)
        self.showFullScreen()
        self.fullscreen_button.setText("Exit Fullscreen")
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setVisible(True)
        self._show_controls_temporarily()

    def exit_fullscreen(self) -> None:
        self.controls_hide_timer.stop()
        if self.isFullScreen():
            self.showNormal()
            self.tabs.setVisible(True)
        self.controls_fade_animation.stop()
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setVisible(True)
        self.fullscreen_button.setText("Fullscreen")

    def _add_recent(self, path: Path) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        recent = self.state.data.setdefault("recent", [])

        recent = [row for row in recent if row.get("path") != str(path)]
        recent.insert(0, {"path": str(path), "last_played": now})
        self.state.data["recent"] = recent[:50]
        self.state.save()
        self.refresh_recent_view()

    def refresh_recent_view(self) -> None:
        self.recent_list.clear()
        for row in self.state.data.get("recent", []):
            path = row.get("path", "")
            played = row.get("last_played", "")
            label = f"{Path(path).name}   |   {played}"
            item = QListWidgetItem(label)
            media = self._media_item_for_path(Path(path))
            if media:
                item.setIcon(self._icon_for_media_item(media))
            item.setData(Qt.UserRole, path)
            self.recent_list.addItem(item)

    def refresh_broadcast_lists(self) -> None:
        self.bc_show_list.clear()
        self.bc_movie_list.clear()

        settings = self.state.data.get("settings", {})
        shows_dir = Path(settings.get("shows_dir", str(SHOWS_DIR)))
        movies_dir = Path(settings.get("movies_dir", str(MOVIES_DIR)))

        shows = scan_all_shows(shows_dir)
        movies = scan_movies(movies_dir)

        excluded_shows = set(self.state.data.get("broadcast_excluded_shows", []))
        excluded_movies = set(self.state.data.get("broadcast_excluded_movies", []))
        completed_only_default = self.bc_completed_only_default.isChecked()

        for show_name in sorted(shows):
            status, clean_name = parse_collection_tag(show_name)
            item = QListWidgetItem(f"{clean_name} [{status_badge_text(status)}]")
            item.setData(Qt.UserRole, show_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            default_unchecked = completed_only_default and status != "Completed"
            item.setCheckState(Qt.Unchecked if show_name in excluded_shows or default_unchecked else Qt.Checked)
            self.bc_show_list.addItem(item)

        for movie in movies:
            movie_key = str(movie)
            item = QListWidgetItem(movie.name)
            item.setData(Qt.UserRole, movie_key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if movie_key in excluded_movies else Qt.Checked)
            self.bc_movie_list.addItem(item)

    def _collect_broadcast_inclusions(self) -> tuple[set[str], set[str]]:
        excluded_shows: set[str] = set()
        excluded_movies: set[str] = set()

        for i in range(self.bc_show_list.count()):
            item = self.bc_show_list.item(i)
            if item.checkState() != Qt.Checked:
                raw_show_name = item.data(Qt.UserRole) or item.text()
                excluded_shows.add(raw_show_name)

        for i in range(self.bc_movie_list.count()):
            item = self.bc_movie_list.item(i)
            movie_key = item.data(Qt.UserRole)
            if movie_key and item.checkState() != Qt.Checked:
                excluded_movies.add(movie_key)

        self.state.data["broadcast_excluded_shows"] = sorted(excluded_shows)
        self.state.data["broadcast_excluded_movies"] = sorted(excluded_movies)
        self.state.save()
        return excluded_shows, excluded_movies

    def _build_full_broadcast_playlist(
        self,
        filtered_shows: dict[str, list[Path]],
        filtered_movies: list[Path],
        include_movies: bool,
        movie_every: int,
    ) -> list[Path]:
        # Build a full-cycle queue that contains every included episode exactly once.
        show_names = sorted(filtered_shows.keys(), key=str.lower)
        episode_indexes = {name: 0 for name in show_names}
        playlist: list[Path] = []
        episodes_added = 0

        movie_index = 0
        movies_count = len(filtered_movies)

        while True:
            added_this_cycle = False
            for show_name in show_names:
                idx = episode_indexes[show_name]
                episodes = filtered_shows[show_name]
                if idx >= len(episodes):
                    continue

                playlist.append(episodes[idx])
                episode_indexes[show_name] = idx + 1
                episodes_added += 1
                added_this_cycle = True

                if include_movies and movies_count > 0 and episodes_added % movie_every == 0:
                    playlist.append(filtered_movies[movie_index % movies_count])
                    movie_index += 1

            if not added_this_cycle:
                break

        return playlist

    def generate_broadcast(self) -> None:
        excluded_shows, excluded_movies = self._collect_broadcast_inclusions()
        settings = self.state.data.get("settings", {})
        shows_dir = Path(settings.get("shows_dir", str(SHOWS_DIR)))
        movies_dir = Path(settings.get("movies_dir", str(MOVIES_DIR)))

        output = Path(self.bc_output.text().strip() or str(DEFAULT_OUTPUT))
        include_movies = self.bc_include_movies.isChecked()
        movie_every = self.bc_movie_every.value()

        try:
            shows = scan_all_shows(shows_dir)
            filtered_shows = {name: eps for name, eps in shows.items() if name not in excluded_shows}

            movies = scan_movies(movies_dir)
            filtered_movies = [m for m in movies if str(m) not in excluded_movies]

            if not filtered_shows:
                QMessageBox.warning(self, "Broadcast", "No included shows found for broadcast.")
                return

            playlist = self._build_full_broadcast_playlist(
                filtered_shows=filtered_shows,
                filtered_movies=filtered_movies,
                include_movies=include_movies,
                movie_every=movie_every,
            )
            if not playlist:
                QMessageBox.information(self, "Broadcast", "No playlist generated.")
                return

            write_m3u(playlist, output)
            self.bc_status.setText(f"Full broadcast generated: {output.name} ({len(playlist)} items)")
            self._set_broadcast_queue_view(playlist)
            self.play_paths(playlist, start_index=0, loop=True, queue_kind="broadcast")
            self._persist_broadcast_resume_state()

        except Exception as exc:
            QMessageBox.critical(self, "Broadcast Error", str(exc))

    def play_generated_playlist(self) -> None:
        output = Path(self.bc_output.text().strip() or str(DEFAULT_OUTPUT))
        if not output.exists():
            QMessageBox.warning(self, "Broadcast", f"Playlist file does not exist:\n{output}")
            return

        playlist_paths = self._read_m3u_playlist_paths(output)

        self._set_broadcast_queue_view(playlist_paths)
        if not playlist_paths:
            QMessageBox.information(self, "Broadcast", "Playlist is empty.")
            return

        start_index = int(self.state.data.get("broadcast", {}).get("last_index", 0))
        start_index = max(0, min(start_index, len(playlist_paths) - 1))
        self.play_paths(playlist_paths, start_index=start_index, loop=True, queue_kind="broadcast")
        self._persist_broadcast_resume_state()

    def run_youtube_download(self) -> None:
        url = self.yt_url.text().strip()
        output_dir = Path(self.yt_output.text().strip() or str(BASE_DIR / "downloads"))
        single = self.yt_single.isChecked()

        if not url:
            QMessageBox.warning(self, "YouTube", "Please provide a URL.")
            return

        self.yt_run_btn.setEnabled(False)
        self.tools_log.appendPlainText("Starting download...")

        def job() -> None:
            output_dir.mkdir(parents=True, exist_ok=True)
            download_url = resolve_download_url(url, single)
            ydl_opts = {
                "outtmpl": str(output_dir / "%(playlist_title|uploader)s" / "%(title)s.%(ext)s"),
                "format": "best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "noplaylist": single,
                "ignoreerrors": True,
                "restrictfilenames": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_url])

        def done(message: str, ok: bool) -> None:
            self.yt_run_btn.setEnabled(True)
            if ok:
                self.tools_log.appendPlainText("YouTube download completed.")
            else:
                self.tools_log.appendPlainText("YouTube download failed:\n" + message)

        self._threaded(job, done)

    def run_timestamp_splitter(self) -> None:
        input_file = Path(self.ts_input.text().strip())
        marks_file = Path(self.ts_marks.text().strip())
        output_dir = Path(self.ts_output.text().strip() or str(BASE_DIR / "split_output"))
        ffmpeg_bin_text = self.ts_ffmpeg_bin.text().strip()
        ffmpeg_bin = Path(ffmpeg_bin_text) if ffmpeg_bin_text else None
        reencode = self.ts_reencode.isChecked()

        if not input_file.exists():
            QMessageBox.warning(self, "Timestamp Splitter", "Input media file not found.")
            return
        if not marks_file.exists():
            QMessageBox.warning(self, "Timestamp Splitter", "Timestamp file not found.")
            return

        self.ts_run_btn.setEnabled(False)
        self.tools_log.appendPlainText("Starting timestamp split...")

        def job() -> None:
            split_media(
                input_file=input_file,
                timestamp_file=marks_file,
                output_dir=output_dir,
                reencode=reencode,
                ffmpeg_bin=ffmpeg_bin,
            )

        def done(message: str, ok: bool) -> None:
            self.ts_run_btn.setEnabled(True)
            if ok:
                self.tools_log.appendPlainText("Timestamp split completed.")
            else:
                self.tools_log.appendPlainText("Timestamp split failed:\n" + message)

        self._threaded(job, done)

    def save_settings(self) -> None:
        settings = self.state.data.setdefault("settings", {})
        settings["shows_dir"] = self.set_shows_dir.text().strip() or str(SHOWS_DIR)
        settings["movies_dir"] = self.set_movies_dir.text().strip() or str(MOVIES_DIR)
        settings["skip_seconds"] = self.set_skip_seconds.value()
        settings["autoplay"] = self.set_autoplay.isChecked()
        self.state.save()

        self.refresh_library()
        self.refresh_broadcast_lists()
        QMessageBox.information(self, "Settings", "Settings saved.")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist_broadcast_resume_state()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        skip_seconds = int(self.state.data.get("settings", {}).get("skip_seconds", 5))
        skip_ms = skip_seconds * 1000

        if event.key() == Qt.Key_Right:
            self.player.setPosition(self.player.position() + skip_ms)
            return
        if event.key() == Qt.Key_Left:
            self.player.setPosition(max(0, self.player.position() - skip_ms))
            return
        if event.key() in (Qt.Key_F, Qt.Key_F11):
            self.toggle_fullscreen()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.exit_fullscreen()
            return

        super().keyPressEvent(event)

class _CallbackEvent(QEvent):
    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__(QEvent.Type(QEvent.registerEventType()))
        self.callback = callback


def main() -> int:
    app = QApplication([])
    window = MediaCenterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
