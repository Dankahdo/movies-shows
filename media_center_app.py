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

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyleOptionSlider,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

import nerv_theme as theme
from nerv_theme import (
    HazardStripe,
    MonitorFrame,
    NervHeader,
    NoSignalScreen,
    RatingBar,
    ReadoutTile,
    SectionHeader,
    repolish,
)

from broadcast import (
    BASE_DIR,
    DATA_DIR,
    DEFAULT_OUTPUT,
    MOVIES_DIR,
    OUTPUT_DIR,
    SHOWS_DIR,
    scan_all_shows,
    scan_movies,
    write_m3u,
)
from RipYoutube import download_with_fallback, resolve_download_url
from timestampSplitter import split_media

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv", ".webm"}
APP_STATE_FILE = DATA_DIR / "app_state.json"
THUMBNAILS_DIR = DATA_DIR / ".thumbnails"
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
        return "COMPLETE"
    if status == "In Progress":
        return "IN PROGRESS"
    return "UNTAGGED"


def friendly_timestamp(iso_text: str) -> str:
    try:
        stamp = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text
    days = (datetime.now().date() - stamp.date()).days
    if days == 0:
        return f"TODAY {stamp:%H:%M}"
    if days == 1:
        return f"YESTERDAY {stamp:%H:%M}"
    return f"{stamp:%Y.%m.%d %H:%M}"


def make_button(text: str, variant: str | None = None, tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setProperty("variant", variant)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def make_label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")


class SeekSlider(QSlider):
    """Clicking the track jumps the handle straight to that spot (and keeps dragging),
    instead of QSlider's default page-step toward the click."""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            style = self.style()
            handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
            click = event.position().toPoint()
            if not handle.contains(click):
                groove = style.subControlRect(
                    QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self
                )
                span = max(1, groove.width() - handle.width())
                offset = click.x() - groove.x() - handle.width() // 2
                self.setSliderPosition(
                    QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), offset, span)
                )
        # The handle now sits under the cursor, so the base class starts a normal drag:
        # sliderPressed -> sliderMoved... -> sliderReleased, which performs the seek.
        super().mousePressEvent(event)


class MediaCenterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MAGI // Local Media Center")
        self.resize(1450, 940)
        self.setMinimumSize(1100, 720)

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
        self.audio_output.setVolume(int(self.state.data.get("settings", {}).get("volume", 80)) / 100)
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
        self._update_now_playing()

    def _build_ui(self) -> None:
        root = QWidget()
        self.root_layout = QVBoxLayout(root)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.header = NervHeader()
        self.header_stripe = HazardStripe(6)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(10, 10, 10, 6)

        self.monitor_panel = self._build_monitor_panel()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.home_tab = self._build_home_tab()
        self.library_tab = self._build_library_tab()
        self.broadcast_tab = self._build_broadcast_tab()
        self.tools_tab = self._build_tools_tab()
        self.settings_tab = self._build_settings_tab()

        self.tabs.addTab(self.home_tab, "01  HOME")
        self.tabs.addTab(self.library_tab, "02  LIBRARY")
        self.tabs.addTab(self.broadcast_tab, "03  BROADCAST")
        self.tabs.addTab(self.tools_tab, "04  TOOLS")
        self.tabs.addTab(self.settings_tab, "05  SYSTEM")

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.monitor_panel)
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([520, 360])
        self.body_layout.addWidget(self.main_splitter)

        self.root_layout.addWidget(self.header)
        self.root_layout.addWidget(self.header_stripe)
        self.root_layout.addWidget(body, stretch=1)
        self.setCentralWidget(root)

        self.statusBar().setSizeGripEnabled(False)
        hints = make_label("SPACE play/pause  ·  ←/→ skip  ·  F fullscreen  ·  ESC exit", "hint")
        self.statusBar().addPermanentWidget(hints)
        self._notify("MAGI SYSTEM ONLINE")

        refresh_action = QAction("Refresh Library", self)
        refresh_action.triggered.connect(self.refresh_library)
        self.addAction(refresh_action)

    def _build_monitor_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("monitorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        self.monitor_header = QWidget()
        self.monitor_header.setObjectName("monitorHeader")
        mh = QHBoxLayout(self.monitor_header)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(10)
        self.mode_badge = make_label("STANDBY", "modeBadge")
        self.mode_badge.setProperty("mode", "idle")
        self.queue_pos_label = make_label("", "queuePos")
        mh.addWidget(make_label("MAIN MONITOR", "monitorTitle"))
        mh.addWidget(self.mode_badge)
        mh.addStretch(1)
        mh.addWidget(self.queue_pos_label)

        self.monitor_frame = MonitorFrame()
        frame_layout = QVBoxLayout(self.monitor_frame)
        frame_layout.setContentsMargins(4, 4, 4, 4)
        self.monitor_stack = QStackedWidget()
        self.no_signal = NoSignalScreen()
        self.video_widget.setStyleSheet("background-color: #000;")
        self.monitor_stack.addWidget(self.no_signal)
        self.monitor_stack.addWidget(self.video_widget)
        frame_layout.addWidget(self.monitor_stack)

        self.control_bar = self._build_control_bar()

        layout.addWidget(self.monitor_header)
        layout.addWidget(self.monitor_frame, stretch=1)
        layout.addWidget(self.control_bar)

        self.controls_opacity_effect = QGraphicsOpacityEffect(self.control_bar)
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setGraphicsEffect(self.controls_opacity_effect)

        self.controls_fade_animation = QPropertyAnimation(self.controls_opacity_effect, b"opacity", self)
        self.controls_fade_animation.setDuration(260)
        self.controls_fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.controls_fade_animation.finished.connect(self._on_controls_fade_finished)

        self.setMouseTracking(True)
        for widget in (self.video_widget, self.no_signal, self.control_bar):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

        return panel

    def _build_control_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("controlBar")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(4, 8, 4, 2)
        layout.setSpacing(8)

        self.progress = SeekSlider(Qt.Orientation.Horizontal)
        # Arrow keys belong to the window's skip handling, not the slider.
        self.progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress.setObjectName("seekBar")
        self.progress.setRange(0, 1000)
        self.progress.setSingleStep(1)
        self.progress.setPageStep(50)
        self.progress.setToolTip("Drag to seek")
        self.progress.sliderPressed.connect(self._on_seek_start)
        self.progress.sliderReleased.connect(self._on_seek_end)
        self.progress.sliderMoved.connect(self._on_seek_preview)
        self.progress.actionTriggered.connect(self._on_seek_action)

        row = QHBoxLayout()
        row.setSpacing(6)

        self.prev_button = make_button("◀◀", "transport", "Previous in queue")
        self.play_pause_button = make_button("▶  PLAY", "primary", "Play / pause (Space)")
        self.play_pause_button.setMinimumWidth(110)
        self.next_button = make_button("▶▶", "transport", "Next in queue")

        now_playing = QVBoxLayout()
        now_playing.setSpacing(0)
        self.now_playing_label = make_label("NO SIGNAL", "nowPlaying")
        self.now_playing_meta = make_label("NOTHING LOADED", "nowPlayingMeta")
        now_playing.addWidget(self.now_playing_label)
        now_playing.addWidget(self.now_playing_meta)

        timecode = QVBoxLayout()
        timecode.setSpacing(0)
        timecode.addWidget(make_label("ELAPSED / TOTAL", "timecodeCaption"), alignment=Qt.AlignmentFlag.AlignRight)
        self.position_label = make_label("00:00 / 00:00", "timecode")
        timecode.addWidget(self.position_label, alignment=Qt.AlignmentFlag.AlignRight)

        self.mute_button = make_button("VOL", "small", "Mute / unmute")
        self.mute_button.setCheckable(True)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setValue(round(self.audio_output.volume() * 100))
        self.volume_slider.setToolTip("Volume")

        self.tabs_toggle_button = make_button("▾  PANEL", None, "Hide / show the lower panel")
        self.fullscreen_button = make_button("⛶  FULL", None, "Fullscreen (F / F11)")

        row.addWidget(self.prev_button)
        row.addWidget(self.play_pause_button)
        row.addWidget(self.next_button)
        row.addSpacing(10)
        row.addLayout(now_playing, stretch=1)
        row.addLayout(timecode)
        row.addSpacing(14)
        row.addWidget(self.mute_button)
        row.addWidget(self.volume_slider)
        row.addSpacing(14)
        row.addWidget(self.tabs_toggle_button)
        row.addWidget(self.fullscreen_button)

        layout.addWidget(self.progress)
        layout.addLayout(row)

        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.next_button.clicked.connect(self.play_next)
        self.prev_button.clicked.connect(self.play_previous)
        self.tabs_toggle_button.clicked.connect(self.toggle_tabs_panel)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.mute_button.toggled.connect(self._on_mute_toggled)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        return bar

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

        # Text fields consume a plain Space themselves, so this only fires outside of typing.
        self.shortcut_play_pause = QShortcut(QKeySequence("Space"), self)
        self.shortcut_play_pause.setContext(Qt.ApplicationShortcut)
        self.shortcut_play_pause.activated.connect(self.toggle_play_pause)

    def eventFilter(self, watched, event) -> bool:
        if self.isFullScreen() and event.type() in (QEvent.Type.MouseMove, QEvent.Type.Enter):
            self._show_controls_temporarily()
        return super().eventFilter(watched, event)

    def _notify(self, message: str, timeout_ms: int = 6000) -> None:
        self.statusBar().showMessage(f">  {message}", timeout_ms)

    def _build_home_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_series = ReadoutTile("SERIES")
        self.tile_episodes = ReadoutTile("EPISODES")
        self.tile_movies = ReadoutTile("MOVIES")
        self.tile_queue = ReadoutTile("BROADCAST QUEUE")
        for tile in (self.tile_series, self.tile_episodes, self.tile_movies, self.tile_queue):
            tiles.addWidget(tile, stretch=1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        resume_last = make_button("▶  CONTINUE LAST WATCHED", "primary", "Resume the series you watched most recently")
        resume_broadcast = make_button("◉  RESUME BROADCAST", None, "Continue the saved broadcast playlist")
        resume_last.clicked.connect(self._play_last_recent)
        resume_broadcast.clicked.connect(self.play_generated_playlist)
        actions.addWidget(resume_last)
        actions.addWidget(resume_broadcast)
        tiles.addLayout(actions)

        self.recent_header = SectionHeader("RECENT ACTIVITY LOG", "DOUBLE-CLICK TO RESUME")
        self.recent_list = QListWidget()
        self.recent_list.setIconSize(QSize(96, 54))
        self.recent_list.setAlternatingRowColors(True)
        self.recent_list.itemDoubleClicked.connect(self._play_recent_item)

        layout.addLayout(tiles)
        layout.addWidget(self.recent_header)
        layout.addWidget(self.recent_list, stretch=1)
        return tab

    def _build_library_tab(self) -> QWidget:
        tab = QWidget()
        main = QVBoxLayout(tab)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("SEARCH  //  title, series or filename")
        self.search_box.setClearButtonEnabled(True)
        self.filter_box = QComboBox()
        self.filter_box.addItems(["All", "Movies", "Shows"])
        self.collection_filter_box = QComboBox()
        self.collection_filter_box.addItems(["All Status", "Completed", "In Progress", "Unspecified"])
        refresh_btn = make_button("⟳  RESCAN", None, "Rescan the shows and movies folders")

        toolbar.addWidget(self.search_box, stretch=1)
        toolbar.addWidget(make_label("TYPE", "fieldLabel"))
        toolbar.addWidget(self.filter_box)
        toolbar.addWidget(make_label("STATUS", "fieldLabel"))
        toolbar.addWidget(self.collection_filter_box)
        toolbar.addWidget(refresh_btn)

        splitter = QSplitter()
        self.library_tree = QTreeWidget()
        self.library_tree.setHeaderLabels(["TITLE", "TYPE / STATUS", "LOCATION"])
        self.library_tree.setIconSize(QSize(48, 27))
        self.library_tree.setAlternatingRowColors(True)
        self.library_tree.setColumnWidth(0, 420)
        self.library_tree.setColumnWidth(1, 120)
        self.library_tree.itemSelectionChanged.connect(self._on_library_selection)
        self.library_tree.itemDoubleClicked.connect(self._play_selected_library_item)

        right = QFrame()
        right.setObjectName("detailPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 12)
        right_layout.setSpacing(8)

        self.thumb_preview = make_label("NO IMAGE", "thumbPreview")
        self.thumb_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_preview.setFixedHeight(150)
        self.selected_title = make_label("SELECT A DATA FILE", "detailTitle")
        self.selected_title.setWordWrap(True)
        self.selected_meta = make_label("", "detailMeta")
        self.selected_meta.setWordWrap(True)
        self.rating_bar = RatingBar()
        self.note_box = QTextEdit()
        self.note_box.setPlaceholderText("Field notes / review...")

        play_now = make_button("▶  PLAY", "primary", "Play this file; shows continue through the series")
        save_review = make_button("SAVE REVIEW")
        set_thumbnail = make_button("SET IMAGE", None, "Choose a custom thumbnail for this series / folder")
        buttons = QHBoxLayout()
        buttons.addWidget(play_now, stretch=1)
        buttons.addWidget(save_review)
        buttons.addWidget(set_thumbnail)

        right_layout.addWidget(SectionHeader("DATA FILE"))
        right_layout.addWidget(self.thumb_preview)
        right_layout.addWidget(self.selected_title)
        right_layout.addWidget(self.selected_meta)
        right_layout.addWidget(make_label("RATING", "fieldLabel"))
        right_layout.addWidget(self.rating_bar)
        right_layout.addWidget(make_label("NOTES", "fieldLabel"))
        right_layout.addWidget(self.note_box, stretch=1)
        right_layout.addLayout(buttons)

        splitter.addWidget(self.library_tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main.addLayout(toolbar)
        main.addWidget(splitter, stretch=1)

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
        outer = QHBoxLayout(tab)
        outer.setContentsMargins(12, 4, 12, 12)
        splitter = QSplitter()

        left = QWidget()
        layout = QVBoxLayout(left)
        layout.setContentsMargins(0, 0, 0, 0)

        settings_box = QGroupBox("BROADCAST GENERATION")
        settings_layout = QGridLayout(settings_box)
        settings_layout.setHorizontalSpacing(10)

        self.bc_include_movies = QCheckBox("Interleave movies")
        self.bc_include_movies.setChecked(True)

        broadcast_state = self.state.data.get("broadcast", {})
        self.bc_completed_only_default = QCheckBox("Only COMPLETE series by default")
        self.bc_completed_only_default.setChecked(bool(broadcast_state.get("completed_only_default", True)))

        self.bc_movie_every = QSpinBox()
        self.bc_movie_every.setRange(1, 100)
        self.bc_movie_every.setValue(8)
        self.bc_movie_every.setSuffix(" episodes")
        self.bc_movie_every.setMaximumWidth(160)

        self.bc_output = QLineEdit(str(broadcast_state.get("output_path", str(DEFAULT_OUTPUT))))
        output_btn = make_button("BROWSE")

        self.bc_generate_btn = make_button("◉  GENERATE + GO ON AIR", "primary", "Build a new playlist and start it")
        self.bc_play_btn = make_button("▶  PLAY SAVED", None, "Resume the playlist already saved to the M3U")

        settings_layout.addWidget(self.bc_include_movies, 0, 0)
        settings_layout.addWidget(self.bc_completed_only_default, 0, 1, 1, 2)
        settings_layout.addWidget(make_label("MOVIE EVERY", "fieldLabel"), 1, 0)
        settings_layout.addWidget(self.bc_movie_every, 1, 1, 1, 2)
        settings_layout.addWidget(make_label("OUTPUT M3U", "fieldLabel"), 2, 0)
        settings_layout.addWidget(self.bc_output, 2, 1)
        settings_layout.addWidget(output_btn, 2, 2)
        settings_layout.addWidget(
            make_label("Every episode of each included show is used. Broadcast playback loops forever.", "hint"),
            3, 0, 1, 3,
        )
        generate_row = QHBoxLayout()
        generate_row.addWidget(self.bc_generate_btn, stretch=1)
        generate_row.addWidget(self.bc_play_btn)
        settings_layout.addLayout(generate_row, 4, 0, 1, 3)

        list_box = QGroupBox("INCLUDE / EXCLUDE")
        list_layout = QHBoxLayout(list_box)
        self.bc_show_list = QListWidget()
        self.bc_movie_list = QListWidget()
        list_layout.addWidget(self._wrap_labeled_widget("SHOWS", self.bc_show_list))
        list_layout.addWidget(self._wrap_labeled_widget("MOVIES", self.bc_movie_list))

        layout.addWidget(settings_box)
        layout.addWidget(list_box, stretch=1)

        right = QWidget()
        queue_layout = QVBoxLayout(right)
        queue_layout.setContentsMargins(0, 8, 0, 0)
        self.bc_queue_header = SectionHeader("BROADCAST QUEUE", "EMPTY")
        self.bc_queue_list = QListWidget()
        self.bc_queue_list.setObjectName("queueList")
        self.bc_queue_list.setAlternatingRowColors(True)
        self.bc_queue_list.setIconSize(QSize(40, 22))
        self.bc_queue_list.itemDoubleClicked.connect(self.play_selected_broadcast_item)
        queue_actions = QHBoxLayout()
        self.bc_jump_btn = make_button("▶  PLAY SELECTED")
        self.bc_refresh_btn = make_button("LOAD FROM M3U")
        self.bc_status = make_label("", "statusLine")
        queue_actions.addWidget(self.bc_jump_btn)
        queue_actions.addWidget(self.bc_refresh_btn)
        queue_actions.addWidget(self.bc_status, stretch=1)

        queue_layout.addWidget(self.bc_queue_header)
        queue_layout.addWidget(self.bc_queue_list, stretch=1)
        queue_layout.addLayout(queue_actions)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter)

        output_btn.clicked.connect(self._browse_broadcast_output)
        self.bc_generate_btn.clicked.connect(self.generate_broadcast)
        self.bc_play_btn.clicked.connect(self.play_generated_playlist)
        self.bc_completed_only_default.stateChanged.connect(self._on_broadcast_default_filter_changed)
        self.bc_jump_btn.clicked.connect(self.play_selected_broadcast_item)
        self.bc_refresh_btn.clicked.connect(self.load_broadcast_queue_from_file)
        return tab

    def _build_tools_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 4, 12, 12)

        yt_box = QGroupBox("YOUTUBE RIP")
        yt_layout = QGridLayout(yt_box)

        self.yt_url = QLineEdit()
        self.yt_url.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.yt_output = QLineEdit(str(OUTPUT_DIR / "downloads"))
        yt_output_btn = make_button("BROWSE")
        self.yt_single = QCheckBox("Single video only")
        self.yt_run_btn = make_button("⤓  DOWNLOAD", "primary")

        yt_layout.addWidget(make_label("URL", "fieldLabel"), 0, 0)
        yt_layout.addWidget(self.yt_url, 0, 1, 1, 2)
        yt_layout.addWidget(make_label("OUTPUT", "fieldLabel"), 1, 0)
        yt_layout.addWidget(self.yt_output, 1, 1)
        yt_layout.addWidget(yt_output_btn, 1, 2)
        yt_layout.addWidget(self.yt_single, 2, 1)
        yt_layout.addWidget(self.yt_run_btn, 2, 2)
        yt_layout.setRowStretch(3, 1)

        split_box = QGroupBox("TIMESTAMP SPLITTER")
        split_layout = QGridLayout(split_box)

        self.ts_input = QLineEdit()
        self.ts_marks = QLineEdit(str(BASE_DIR / "timestamps.txt"))
        self.ts_output = QLineEdit(str(OUTPUT_DIR / "split_output"))
        self.ts_ffmpeg_bin = QLineEdit("")
        self.ts_ffmpeg_bin.setPlaceholderText("optional — uses PATH")
        self.ts_reencode = QCheckBox("Re-encode")
        self.ts_run_btn = make_button("✂  SPLIT", "primary")

        ts_input_btn = make_button("BROWSE")
        ts_marks_btn = make_button("BROWSE")
        ts_output_btn = make_button("BROWSE")
        ts_ffmpeg_btn = make_button("BROWSE")

        for row, (label, field, button) in enumerate(
            [
                ("INPUT", self.ts_input, ts_input_btn),
                ("TIMESTAMPS", self.ts_marks, ts_marks_btn),
                ("OUTPUT", self.ts_output, ts_output_btn),
                ("FFMPEG BIN", self.ts_ffmpeg_bin, ts_ffmpeg_btn),
            ]
        ):
            split_layout.addWidget(make_label(label, "fieldLabel"), row, 0)
            split_layout.addWidget(field, row, 1)
            split_layout.addWidget(button, row, 2)

        split_layout.addWidget(self.ts_reencode, 4, 1)
        split_layout.addWidget(self.ts_run_btn, 4, 2)

        self.tools_log = QPlainTextEdit()
        self.tools_log.setObjectName("terminal")
        self.tools_log.setReadOnly(True)
        self.tools_log.setPlaceholderText("> awaiting tasks_")

        yt_output_btn.clicked.connect(lambda: self._browse_dir_into(self.yt_output))
        self.yt_run_btn.clicked.connect(self.run_youtube_download)

        ts_input_btn.clicked.connect(lambda: self._browse_file_into(self.ts_input))
        ts_marks_btn.clicked.connect(lambda: self._browse_file_into(self.ts_marks))
        ts_output_btn.clicked.connect(lambda: self._browse_dir_into(self.ts_output))
        ts_ffmpeg_btn.clicked.connect(lambda: self._browse_dir_into(self.ts_ffmpeg_bin))
        self.ts_run_btn.clicked.connect(self.run_timestamp_splitter)

        boxes = QHBoxLayout()
        boxes.addWidget(yt_box, stretch=1)
        boxes.addWidget(split_box, stretch=1)
        layout.addLayout(boxes)
        layout.addWidget(SectionHeader("TERMINAL", "TASK OUTPUT"))
        layout.addWidget(self.tools_log, stretch=1)
        return tab

    def _log(self, message: str) -> None:
        self.tools_log.appendPlainText(f"[{datetime.now():%H:%M:%S}] > {message}")

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        outer = QHBoxLayout(tab)
        outer.setContentsMargins(12, 4, 12, 12)

        settings = self.state.data.get("settings", {})

        config_box = QGroupBox("SYSTEM CONFIGURATION")
        layout = QFormLayout(config_box)
        layout.setVerticalSpacing(10)

        self.set_shows_dir = QLineEdit(settings.get("shows_dir", str(SHOWS_DIR)))
        self.set_movies_dir = QLineEdit(settings.get("movies_dir", str(MOVIES_DIR)))
        self.set_skip_seconds = QSpinBox()
        self.set_skip_seconds.setRange(1, 60)
        self.set_skip_seconds.setSuffix(" s")
        self.set_skip_seconds.setMaximumWidth(120)
        self.set_skip_seconds.setValue(int(settings.get("skip_seconds", 5)))
        self.set_autoplay = QCheckBox("Autoplay next item")
        self.set_autoplay.setChecked(bool(settings.get("autoplay", True)))

        shows_browse = make_button("BROWSE")
        movies_browse = make_button("BROWSE")
        save_button = make_button("SAVE CONFIGURATION", "primary")

        shows_line = self._with_button(self.set_shows_dir, shows_browse)
        movies_line = self._with_button(self.set_movies_dir, movies_browse)

        shows_browse.clicked.connect(lambda: self._browse_dir_into(self.set_shows_dir))
        movies_browse.clicked.connect(lambda: self._browse_dir_into(self.set_movies_dir))
        save_button.clicked.connect(self.save_settings)

        layout.addRow(make_label("SHOWS FOLDER", "fieldLabel"), shows_line)
        layout.addRow(make_label("MOVIES FOLDER", "fieldLabel"), movies_line)
        layout.addRow(make_label("ARROW-KEY SKIP", "fieldLabel"), self.set_skip_seconds)
        layout.addRow("", self.set_autoplay)
        layout.addRow("", save_button)

        keys_box = QGroupBox("CONTROL REFERENCE")
        keys = QGridLayout(keys_box)
        keys.setVerticalSpacing(8)
        for row, (key, action) in enumerate(
            [
                ("SPACE", "Play / pause"),
                ("← / →", "Skip back / forward"),
                ("F · F11", "Toggle fullscreen"),
                ("ESC", "Exit fullscreen"),
            ]
        ):
            keys.addWidget(make_label(key, "keyCap"), row, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            keys.addWidget(QLabel(action), row, 1)
        keys.setColumnStretch(1, 1)
        keys.setRowStretch(4, 1)

        outer.addWidget(config_box, stretch=3)
        outer.addWidget(keys_box, stretch=1, alignment=Qt.AlignmentFlag.AlignTop)
        return tab

    def _with_button(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        box = QWidget()
        l = QHBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(line_edit)
        l.addWidget(button)
        return box

    def _wrap_labeled_widget(self, label: str, widget: QListWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(make_label(label, "fieldLabel"))
        top.addStretch(1)
        all_btn = make_button("ALL", "small", f"Include every entry in {label.lower()}")
        none_btn = make_button("NONE", "small", f"Exclude every entry in {label.lower()}")
        all_btn.clicked.connect(lambda: self._set_all_checked(widget, Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all_checked(widget, Qt.Unchecked))
        top.addWidget(all_btn)
        top.addWidget(none_btn)
        layout.addLayout(top)
        layout.addWidget(widget)
        return box

    def _set_all_checked(self, widget: QListWidget, state: Qt.CheckState) -> None:
        for i in range(widget.count()):
            widget.item(i).setCheckState(state)

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
            self.play_pause_button.setText("❚❚  PAUSE")
        else:
            self.play_pause_button.setText("▶  PLAY")
        self._update_magi()

    def _on_volume_changed(self, value: int) -> None:
        self.audio_output.setVolume(value / 100)
        self.state.data.setdefault("settings", {})["volume"] = value
        if value and self.mute_button.isChecked():
            self.mute_button.setChecked(False)

    def _on_mute_toggled(self, muted: bool) -> None:
        self.audio_output.setMuted(muted)
        self.mute_button.setText("MUTE" if muted else "VOL")
        self.mute_button.setProperty("variant", "danger" if muted else "small")
        repolish(self.mute_button)

    def _update_magi(self) -> None:
        lights = self.header.lights

        if self.media_items:
            lights["library"].set_state(f"{len(self.media_items)} FILES", "ok")
        else:
            lights["library"].set_state("NO DATA", "alert")

        on_air = self.current_queue_kind == "broadcast" and self.current_queue == self.broadcast_queue
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if on_air and playing:
            lights["broadcast"].set_state("ON AIR", "alert")
        elif self.broadcast_queue:
            lights["broadcast"].set_state(f"QUEUE {len(self.broadcast_queue)}", "busy")
        else:
            lights["broadcast"].set_state("STANDBY", "idle")

        if playing:
            lights["player"].set_state("PLAYING", "ok")
        elif self.current_queue:
            lights["player"].set_state("PAUSED", "busy")
        else:
            lights["player"].set_state("NO SIGNAL", "idle")

    def _update_now_playing(self) -> None:
        if not self.current_queue or not (0 <= self.current_index < len(self.current_queue)):
            self.now_playing_label.setText("NO SIGNAL")
            self.now_playing_meta.setText("NOTHING LOADED")
            self.queue_pos_label.setText("")
            mode, badge = "idle", "STANDBY"
        else:
            path = self.current_queue[self.current_index]
            media = self._media_item_for_path(path)
            self.now_playing_label.setText(path.stem)
            if media:
                status, clean_group = parse_collection_tag(media.group)
                self.now_playing_meta.setText(f"{clean_group.upper()}  //  {media.kind.upper()}")
            else:
                self.now_playing_meta.setText(str(path.parent))
            total = len(self.current_queue)
            prefix = "CH" if self.current_queue_kind == "broadcast" else "EP"
            self.queue_pos_label.setText(f"{prefix} {self.current_index + 1:03d} / {total:03d}" if total > 1 else "")
            if self.current_queue_kind == "broadcast":
                mode, badge = "broadcast", "◉ BROADCAST"
            elif total > 1:
                mode, badge = "manual", "SERIES"
            else:
                mode, badge = "manual", "SINGLE"
        self.mode_badge.setText(badge)
        self.mode_badge.setProperty("mode", mode)
        repolish(self.mode_badge)
        self._update_magi()

    def toggle_tabs_panel(self) -> None:
        tabs_visible = self.tabs.isVisible()
        self.tabs.setVisible(not tabs_visible)
        self.tabs_toggle_button.setText("▴  PANEL" if tabs_visible else "▾  PANEL")

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

    def _thumbnail_path_for_media(self, media: MediaItem) -> Path | None:
        key = self._thumbnail_key(media)
        custom = self.state.data.get("custom_thumbnails", {}).get(key)
        if custom and Path(custom).exists():
            return Path(custom)

        source_video = self.group_first_media.get(key)
        if source_video and source_video.exists():
            auto_thumb = self._ensure_auto_thumbnail_for_key(key, source_video)
            if auto_thumb and auto_thumb.exists():
                return auto_thumb
        return None

    def _icon_for_media_item(self, media: MediaItem) -> QIcon:
        thumb = self._thumbnail_path_for_media(media)
        if thumb:
            return QIcon(str(thumb))
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _show_thumbnail_preview(self, media: MediaItem | None) -> None:
        thumb = self._thumbnail_path_for_media(media) if media else None
        pixmap = QPixmap(str(thumb)) if thumb else QPixmap()
        if pixmap.isNull():
            self.thumb_preview.setPixmap(QPixmap())
            self.thumb_preview.setText("NO IMAGE")
            return
        self.thumb_preview.setPixmap(
            pixmap.scaled(
                self.thumb_preview.width() - 2,
                self.thumb_preview.height() - 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

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
        self._show_thumbnail_preview(media)
        self._notify(f"CUSTOM IMAGE SET FOR {parse_collection_tag(media.group)[1].upper()}")
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
        self._update_library_readouts()
        self._update_magi()
        self._notify(f"LIBRARY SCAN COMPLETE  //  {len(self.media_items)} FILES")

    def _update_library_readouts(self) -> None:
        shows = [m for m in self.media_items if m.kind == "Show"]
        self.tile_series.set_value(f"{len({m.group for m in shows}):03d}")
        self.tile_episodes.set_value(f"{len(shows):04d}")
        self.tile_movies.set_value(f"{len(self.media_items) - len(shows):03d}")
        self.tile_queue.set_value(f"{len(self.broadcast_queue):04d}")

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

        for group_name in sorted(grouped, key=lambda name: parse_collection_tag(name)[1].lower()):
            status, clean_group_name = parse_collection_tag(group_name)
            count = len(grouped[group_name])
            parent = QTreeWidgetItem([clean_group_name, status_badge_text(status), f"{count} file{'s' if count != 1 else ''}"])
            parent.setForeground(1, QBrush(QColor(theme.STATUS_COLORS.get(status, theme.TEXT_DIM))))
            parent.setForeground(2, QBrush(QColor(theme.TEXT_DIM)))
            title_font = parent.font(0)
            title_font.setBold(True)
            parent.setFont(0, title_font)
            group_icon_set = False
            self.library_tree.addTopLevelItem(parent)
            for media in sorted(grouped[group_name], key=lambda m: self._natural_text_key(m.title)):
                child = QTreeWidgetItem([media.title, media.kind.upper(), str(media.path)])
                child.setForeground(1, QBrush(QColor(theme.ORANGE_DIM)))
                child.setForeground(2, QBrush(QColor(theme.TEXT_DIM)))
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

        status, clean_group = parse_collection_tag(media.group)
        self.selected_title.setText(media.title)
        self.selected_meta.setText(
            f"{clean_group.upper()}  //  {media.kind.upper()}  //  {status_badge_text(status)}\n{media.path.name}"
        )
        self._show_thumbnail_preview(media)
        review = self.state.data.get("reviews", {}).get(path_str, {})
        self.rating_bar.setValue(int(review.get("rating", 0)))
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
            "rating": self.rating_bar.value(),
            "note": self.note_box.toPlainText().strip(),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        self.state.save()
        self._notify(f"REVIEW SAVED  //  {Path(path_str).stem}")

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
        # Resume within the whole series so autoplay carries on to the next episode.
        media = self.media_lookup.get(str(path))
        if media:
            queue, start_index = self._series_queue_for_media(media)
            self.play_paths(queue, start_index=start_index, loop=False)
        else:
            self.play_paths([path], start_index=0, loop=False)

    def _play_last_recent(self) -> None:
        if self.recent_list.count() == 0:
            self._notify("NO RECENT ACTIVITY TO RESUME")
            return
        self._play_recent_item(self.recent_list.item(0))

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
        self.monitor_stack.setCurrentWidget(self.video_widget)
        self._update_now_playing()
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
        self.bc_queue_header.set_code(f"{len(paths)} ITEMS" if paths else "EMPTY")
        self.tile_queue.set_value(f"{len(paths):04d}")
        for idx, path in enumerate(paths, start=1):
            label = f"{idx:04d}  {path.stem}"
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

    def _on_seek_action(self, _action: int) -> None:
        # Mouse-wheel / page steps change the slider without a press/release pair;
        # drags are left to _on_seek_end.
        if not self.progress.isSliderDown():
            self._seek_to_slider_value(self.progress.sliderPosition())

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
        self._set_chrome_visible(False)
        self.showFullScreen()
        self.fullscreen_button.setText("⛶  EXIT")
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setVisible(True)
        self._show_controls_temporarily()

    def exit_fullscreen(self) -> None:
        self.controls_hide_timer.stop()
        if self.isFullScreen():
            self.showNormal()
            self.tabs.setVisible(True)
            self.tabs_toggle_button.setText("▾  PANEL")
        self._set_chrome_visible(True)
        self.controls_fade_animation.stop()
        self.controls_opacity_effect.setOpacity(1.0)
        self.control_bar.setVisible(True)
        self.fullscreen_button.setText("⛶  FULL")

    def _set_chrome_visible(self, visible: bool) -> None:
        """Header, stripe, frame borders and status bar give way to the picture in fullscreen."""
        for widget in (self.header, self.header_stripe, self.monitor_header, self.statusBar()):
            widget.setVisible(visible)
        margin = 10 if visible else 0
        self.body_layout.setContentsMargins(margin, margin, margin, 6 if visible else 0)

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
            played = friendly_timestamp(row.get("last_played", ""))
            media = self._media_item_for_path(Path(path))
            if media:
                group = parse_collection_tag(media.group)[1].upper()
                subtitle = f"{group}  //  {media.kind.upper()}  //  {played}"
            else:
                subtitle = played
            item = QListWidgetItem(f"{Path(path).stem}\n{subtitle}")
            if media:
                item.setIcon(self._icon_for_media_item(media))
            if not Path(path).exists():
                item.setForeground(QBrush(QColor(theme.DISABLED)))
                item.setToolTip("File no longer exists")
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
            item = QListWidgetItem(f"{clean_name}  ·  {status_badge_text(status)}")
            item.setForeground(QBrush(QColor(theme.STATUS_COLORS.get(status, theme.TEXT_DIM))))
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
        output_dir = Path(self.yt_output.text().strip() or str(OUTPUT_DIR / "downloads"))
        single = self.yt_single.isChecked()

        if not url:
            QMessageBox.warning(self, "YouTube", "Please provide a URL.")
            return

        self.yt_run_btn.setEnabled(False)
        self._log("Starting download...")

        def job() -> None:
            output_dir.mkdir(parents=True, exist_ok=True)
            download_url = resolve_download_url(url, single)
            download_with_fallback(download_url=download_url, output_dir=output_dir, single=single)

        def done(message: str, ok: bool) -> None:
            self.yt_run_btn.setEnabled(True)
            if ok:
                self._log("YouTube download completed.")
            else:
                self._log("YouTube download failed:\n" + message)

        self._threaded(job, done)

    def run_timestamp_splitter(self) -> None:
        input_file = Path(self.ts_input.text().strip())
        marks_file = Path(self.ts_marks.text().strip())
        output_dir = Path(self.ts_output.text().strip() or str(OUTPUT_DIR / "split_output"))
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
        self._log("Starting timestamp split...")

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
                self._log("Timestamp split completed.")
            else:
                self._log("Timestamp split failed:\n" + message)

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
        self._notify("CONFIGURATION SAVED")

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
    theme.apply_theme(app)
    window = MediaCenterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
