"""NERV / MAGI inspired visual theme: palette, Qt stylesheet and decorative widgets."""

from __future__ import annotations

import math
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

BLACK = "#050505"
PANEL = "#0b0907"
PANEL_ALT = "#110d09"
FIELD = "#0d0b09"
LINE = "#3b2511"
ORANGE = "#ff7a00"
ORANGE_HOT = "#ffa040"
ORANGE_DIM = "#8a4300"
RED = "#e8221b"
GREEN = "#39ff6a"
GREEN_DIM = "#1c6b35"
AMBER = "#ffb000"
TEXT = "#f3e9dc"
TEXT_DIM = "#8f7f6c"
DISABLED = "#4a3a2a"

STATUS_COLORS = {"Completed": GREEN, "In Progress": AMBER, "Unspecified": TEXT_DIM}

FONTS = {"sans": "Segoe UI", "cond": "Segoe UI", "mono": "Consolas", "serif": "Times New Roman"}

_FONT_CANDIDATES = {
    "sans": ["Bahnschrift", "Segoe UI", "Arial"],
    "cond": ["Bahnschrift Condensed", "Bahnschrift SemiCondensed", "Arial Narrow", "Segoe UI"],
    "mono": ["Cascadia Mono", "Consolas", "Courier New"],
    "serif": ["Times New Roman", "Georgia", "Serif"],
}

_STYLESHEET = """
* { outline: none; }
QWidget {
    background-color: @black; color: @text;
    font-family: "@sans"; font-size: 13px;
    selection-background-color: @orange; selection-color: #000;
}
QToolTip {
    background-color: #000; color: @orange; border: 1px solid @orange;
    padding: 4px 6px; font-family: "@mono"; font-size: 12px;
}
QLabel { background: transparent; }

/* ---------- header / chrome ---------- */
QFrame#header { background-color: #000; border: none; }
QLabel#headerSub { color: @orange; font-family: "@mono"; font-size: 11px; }
QLabel#headerCaption { color: @text_dim; font-family: "@mono"; font-size: 10px; }
QLabel#clock { color: @green; font-family: "@mono"; font-size: 18px; font-weight: bold; }

QStatusBar {
    background-color: #000; color: @green; border-top: 1px solid @line;
    font-family: "@mono"; font-size: 12px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: @text_dim; font-family: "@mono"; font-size: 11px; padding: 0 8px; }

/* ---------- monitor ---------- */
QFrame#monitorPanel { background-color: @panel; border: 1px solid @line; }
QFrame#monitor { background-color: #000; border: 1px solid @line; }
QWidget#monitorHeader { background: transparent; }
QLabel#monitorTitle { color: @orange; font-family: "@cond"; font-size: 14px; font-weight: bold; }
QLabel#queuePos { color: @green; font-family: "@mono"; font-size: 13px; font-weight: bold; }
QLabel#modeBadge {
    color: #000; background-color: @orange; padding: 1px 8px;
    font-family: "@cond"; font-size: 12px; font-weight: bold;
}
QLabel#modeBadge[mode="broadcast"] { background-color: @red; color: #fff; }
QLabel#modeBadge[mode="idle"] { background-color: #1d1510; color: @text_dim; }

QFrame#controlBar { background-color: @panel; border: none; border-top: 1px solid @line; }
QLabel#nowPlaying { color: @amber; font-family: "@cond"; font-size: 17px; font-weight: bold; }
QLabel#nowPlayingMeta { color: @text_dim; font-family: "@mono"; font-size: 11px; }
QLabel#timecode { color: @green; font-family: "@mono"; font-size: 20px; font-weight: bold; }
QLabel#timecodeCaption { color: @green_dim; font-family: "@mono"; font-size: 10px; }

/* ---------- section headers / readouts ---------- */
QFrame#sectionBar { background-color: @orange; border: none; }
QFrame#sectionLine { background-color: @line; border: none; }
QLabel#sectionTitle { color: @orange; font-family: "@cond"; font-size: 17px; font-weight: bold; }
QLabel#sectionCode { color: @text_dim; font-family: "@mono"; font-size: 11px; }

QFrame#readout { background-color: @panel; border: 1px solid @line; border-left: 3px solid @orange; }
QLabel#readoutLabel { color: @orange; font-family: "@cond"; font-size: 12px; font-weight: bold; }
QLabel#readoutValue { color: @green; font-family: "@mono"; font-size: 26px; font-weight: bold; }

QFrame#detailPanel { background-color: @panel; border: 1px solid @line; }
QLabel#detailTitle { color: @amber; font-family: "@cond"; font-size: 20px; font-weight: bold; }
QLabel#detailMeta { color: @text_dim; font-family: "@mono"; font-size: 11px; }
QLabel#thumbPreview { background-color: #000; border: 1px solid @line; color: @orange_dim; font-family: "@mono"; }
QLabel#fieldLabel { color: @orange; font-family: "@cond"; font-size: 13px; font-weight: bold; }
QLabel#hint { color: @text_dim; font-family: "@mono"; font-size: 11px; }
QLabel#statusLine { color: @green; font-family: "@mono"; font-size: 12px; }
QLabel#keyCap {
    color: #000; background-color: @orange; padding: 1px 6px;
    font-family: "@mono"; font-size: 12px; font-weight: bold;
}

/* ---------- group boxes ---------- */
QGroupBox {
    font-family: "@cond"; font-size: 13px; font-weight: bold;
    background-color: @panel; border: 1px solid @line; border-top: 2px solid @orange;
    margin-top: 24px; padding: 14px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left; left: 0px; top: 2px;
    padding: 2px 10px; background-color: @orange; color: #000;
    font-family: "@cond"; font-size: 13px; font-weight: bold;
}

/* ---------- tabs ---------- */
QTabWidget::pane { border: 1px solid @line; border-top: 2px solid @orange; background-color: @black; top: -1px; }
QTabBar { background: transparent; }
QTabBar::tab {
    background-color: @panel; color: @orange_dim; border: 1px solid @line; border-bottom: none;
    padding: 7px 22px; margin-right: 2px; min-width: 80px;
    font-family: "@cond"; font-size: 15px; font-weight: bold;
}
QTabBar::tab:hover { color: @orange; border-color: @orange_dim; }
QTabBar::tab:selected { background-color: @orange; color: #000; border-color: @orange; }

/* ---------- buttons ---------- */
QPushButton {
    background-color: transparent; color: @orange; border: 1px solid @orange_dim;
    padding: 6px 14px; min-height: 18px;
    font-family: "@cond"; font-size: 14px; font-weight: bold;
}
QPushButton:hover { border-color: @orange; background-color: rgba(255, 122, 0, 36); color: @orange_hot; }
QPushButton:pressed { background-color: @orange; color: #000; }
QPushButton:disabled { color: @disabled; border-color: #2a1e14; background-color: transparent; }
QPushButton[variant="primary"] { background-color: @orange; color: #000; border: 1px solid @orange; }
QPushButton[variant="primary"]:hover { background-color: @orange_hot; border-color: @orange_hot; }
QPushButton[variant="primary"]:pressed { background-color: #c85f00; }
QPushButton[variant="primary"]:disabled { background-color: #2a1e14; color: @disabled; border-color: #2a1e14; }
QPushButton[variant="danger"] { color: @red; border-color: #6a1410; }
QPushButton[variant="danger"]:hover { border-color: @red; background-color: rgba(232, 34, 27, 40); color: #ff5a50; }
QPushButton[variant="transport"] { font-size: 16px; padding: 6px 10px; min-width: 40px; }
QPushButton[variant="small"] { font-size: 12px; padding: 2px 8px; min-height: 14px; }

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: @field; color: @amber; border: 1px solid @line;
    padding: 5px 7px; font-family: "@mono"; font-size: 12px;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover, QTextEdit:hover { border-color: @orange_dim; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: @orange; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: url(@arrow_down); width: 9px; height: 6px; }
QSpinBox { padding-right: 22px; }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border; width: 20px; background-color: #1a120a; border: none; border-left: 1px solid @line;
}
QSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: rgba(255, 122, 0, 70); }
QSpinBox::up-arrow { image: url(@arrow_up); width: 9px; height: 6px; }
QSpinBox::down-arrow { image: url(@arrow_down); width: 9px; height: 6px; }
QComboBox QAbstractItemView {
    background-color: @field; color: @text; border: 1px solid @orange;
    selection-background-color: @orange; selection-color: #000;
}
QPlainTextEdit#terminal {
    background-color: #020402; color: @green; border: 1px solid @green_dim;
    font-family: "@mono"; font-size: 12px;
}

/* ---------- lists / trees ---------- */
QTreeWidget, QListWidget {
    background-color: @panel; alternate-background-color: @panel_alt;
    border: 1px solid @line; color: @text; font-size: 13px;
}
QListWidget#queueList { font-family: "@mono"; font-size: 12px; }
QTreeView::item, QListView::item { padding: 3px 4px; border: none; }
QTreeView::item:hover, QListView::item:hover { background-color: rgba(255, 122, 0, 30); }
QTreeView::item:selected, QListView::item:selected { background-color: @orange; color: #000; }
QHeaderView::section {
    background-color: #000; color: @orange; border: none;
    border-bottom: 1px solid @orange; border-right: 1px solid @line; padding: 5px 8px;
    font-family: "@cond"; font-size: 13px; font-weight: bold;
}
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator, QListView::indicator {
    width: 12px; height: 12px; border: 1px solid @orange; background-color: #000;
}
QCheckBox::indicator:hover, QListView::indicator:hover { background-color: rgba(255, 122, 0, 60); }
QCheckBox::indicator:checked, QListView::indicator:checked { background-color: @orange; image: none; }

/* ---------- sliders ---------- */
QSlider { background: transparent; }
QSlider::groove:horizontal { height: 6px; background-color: #140f0b; border: 1px solid @line; }
QSlider::sub-page:horizontal { background-color: @orange; border: 1px solid @orange; }
QSlider::add-page:horizontal { background-color: #140f0b; border: 1px solid @line; }
QSlider::handle:horizontal { background-color: @text; border: 1px solid @orange; width: 6px; margin: -6px 0; }
QSlider::handle:horizontal:hover { background-color: @orange_hot; }
QSlider#seekBar::groove:horizontal { height: 8px; }
QSlider#seekBar::handle:horizontal { width: 8px; margin: -7px 0; }

/* ---------- scrollbars / splitters ---------- */
QScrollBar:vertical { background-color: #000; width: 10px; margin: 0; border-left: 1px solid @line; }
QScrollBar:horizontal { background-color: #000; height: 10px; margin: 0; border-top: 1px solid @line; }
QScrollBar::handle:vertical { background-color: @orange_dim; min-height: 30px; }
QScrollBar::handle:horizontal { background-color: @orange_dim; min-width: 30px; }
QScrollBar::handle:hover { background-color: @orange; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QSplitter::handle { background-color: @line; }
QSplitter::handle:hover { background-color: @orange; }
QSplitter::handle:vertical { height: 4px; }
QSplitter::handle:horizontal { width: 4px; }
"""


def _resolve_fonts() -> None:
    available = set(QFontDatabase.families())
    for role, candidates in _FONT_CANDIDATES.items():
        FONTS[role] = next((family for family in candidates if family in available), candidates[-1])


def _write_arrow_images() -> dict[str, str]:
    """QSS needs image files for arrows once combo/spin boxes are restyled, so paint them on startup."""
    folder = Path(tempfile.gettempdir()) / "magi_media_theme"
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, points in {
        "arrow_down": [QPointF(0, 0), QPointF(9, 0), QPointF(4.5, 6)],
        "arrow_up": [QPointF(0, 6), QPointF(9, 6), QPointF(4.5, 0)],
    }.items():
        pixmap = QPixmap(9, 6)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ORANGE))
        painter.drawPolygon(QPolygonF(points))
        painter.end()
        target = folder / f"{name}.png"
        pixmap.save(str(target))
        paths[name] = target.as_posix()
    return paths


def build_stylesheet() -> str:
    tokens = {
        **_write_arrow_images(),
        "black": BLACK,
        "panel_alt": PANEL_ALT,
        "panel": PANEL,
        "field": FIELD,
        "line": LINE,
        "orange_hot": ORANGE_HOT,
        "orange_dim": ORANGE_DIM,
        "orange": ORANGE,
        "red": RED,
        "green_dim": GREEN_DIM,
        "green": GREEN,
        "amber": AMBER,
        "text_dim": TEXT_DIM,
        "text": TEXT,
        "disabled": DISABLED,
        **FONTS,
    }
    sheet = _STYLESHEET
    # Longest tokens first so "@orange_dim" is not clobbered by "@orange".
    for name in sorted(tokens, key=len, reverse=True):
        sheet = sheet.replace(f"@{name}", tokens[name])
    return sheet


def apply_theme(app: QApplication) -> None:
    _resolve_fonts()
    app.setStyle("Fusion")

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: BLACK,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: FIELD,
        QPalette.ColorRole.AlternateBase: PANEL_ALT,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: PANEL,
        QPalette.ColorRole.ButtonText: ORANGE,
        QPalette.ColorRole.Highlight: ORANGE,
        QPalette.ColorRole.HighlightedText: "#000000",
        QPalette.ColorRole.ToolTipBase: "#000000",
        QPalette.ColorRole.ToolTipText: ORANGE,
        QPalette.ColorRole.PlaceholderText: TEXT_DIM,
        QPalette.ColorRole.Link: ORANGE,
        QPalette.ColorRole.BrightText: RED,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    app.setPalette(palette)

    app.setFont(QFont(FONTS["sans"], 10))
    app.setStyleSheet(build_stylesheet())


def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property used in a selector changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def hexagon(cx: float, cy: float, radius: float) -> QPolygonF:
    return QPolygonF(
        [QPointF(cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    )


def _font(role: str, pixel_size: int, bold: bool = False) -> QFont:
    font = QFont(FONTS[role])
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    return font


class HazardStripe(QWidget):
    def __init__(self, height: int = 6, color: str = ORANGE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(BLACK))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        h = self.height()
        x = -2 * h
        while x < self.width() + h:
            painter.drawPolygon(
                QPolygonF([QPointF(x, h), QPointF(x + h, 0), QPointF(x + 2 * h, 0), QPointF(x + h, h)])
            )
            x += 3 * h


class HexEmblem(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 48)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        painter.setPen(QPen(QColor(ORANGE), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(hexagon(cx, cy, 22))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(RED))
        painter.drawPolygon(hexagon(cx, cy, 16))
        painter.setPen(QColor("#000"))
        painter.setFont(_font("serif", 20, bold=True))
        painter.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignCenter, "M")


class TitleCard(QWidget):
    """Heavy serif text squeezed horizontally, like the show's title cards."""

    def __init__(
        self, text: str, pixel_size: int = 30, color: str = TEXT, squeeze: float = 0.74, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self._squeeze = squeeze
        self._font = _font("serif", pixel_size, bold=True)
        metrics = QFontMetricsF(self._font)
        self._size = QSize(int(metrics.horizontalAdvance(text) * squeeze) + 4, int(metrics.height()))
        self.setFixedSize(self._size)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._size

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        painter.setPen(self._color)
        painter.scale(self._squeeze, 1.0)
        painter.drawText(QPointF(0, QFontMetricsF(self._font).ascent()), self._text)


class MagiLight(QWidget):
    LEVELS = {
        "ok": ("#23c45a", "#000000"),
        "busy": (ORANGE, "#000000"),
        "alert": (RED, "#ffffff"),
        "idle": ("#1d1510", TEXT_DIM),
    }

    def __init__(self, name: str, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._role = role
        self._text = "INIT"
        self._level = "idle"
        self.setFixedSize(124, 40)
        self.setToolTip(f"{name} — {role}")

    def set_state(self, text: str, level: str) -> None:
        if (text, level) == (self._text, self._level):
            return
        self._text, self._level = text, level
        self.setToolTip(f"{self._name} — {self._role}: {text}")
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        fill, fg = self.LEVELS.get(self._level, self.LEVELS["idle"])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        cut = 9
        shape = QPolygonF(
            [
                QPointF(r.left(), r.top()),
                QPointF(r.right() - cut, r.top()),
                QPointF(r.right(), r.top() + cut),
                QPointF(r.right(), r.bottom()),
                QPointF(r.left() + cut, r.bottom()),
                QPointF(r.left(), r.bottom() - cut),
            ]
        )
        painter.setBrush(QColor(fill))
        painter.setPen(QPen(QColor(ORANGE_DIM if self._level == "idle" else fill), 1))
        painter.drawPolygon(shape)

        painter.setPen(QColor(fg))
        painter.setFont(_font("cond", 11, bold=True))
        painter.drawText(QRectF(9, 2, r.width() - 18, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._name)
        painter.setFont(_font("mono", 12, bold=True))
        painter.drawText(QRectF(9, 18, r.width() - 18, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._text)


class NervHeader(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(TitleCard("MAGI MEDIA SYSTEM", 32))
        subtitle = QLabel("LOCAL ARCHIVE TERMINAL  //  第3新東京市")
        subtitle.setObjectName("headerSub")
        titles.addWidget(subtitle)

        layout.addWidget(HexEmblem())
        layout.addLayout(titles)
        layout.addStretch(1)

        self.lights = {
            "library": MagiLight("MELCHIOR·1", "library scan"),
            "broadcast": MagiLight("BALTHASAR·2", "broadcast queue"),
            "player": MagiLight("CASPER·3", "playback"),
        }
        for light in self.lights.values():
            layout.addWidget(light)

        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        caption = QLabel("LOCAL TIME")
        caption.setObjectName("headerCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(caption)
        clock_box.addWidget(self.clock)
        layout.addSpacing(8)
        layout.addLayout(clock_box)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start(1000)
        self._tick()

    def _tick(self) -> None:
        self.clock.setText(datetime.now().strftime("%Y.%m.%d  %H:%M:%S"))


class SectionHeader(QWidget):
    def __init__(self, title: str, code: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        bar = QFrame()
        bar.setObjectName("sectionBar")
        bar.setFixedSize(4, 18)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        line = QFrame()
        line.setObjectName("sectionLine")
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.code_label = QLabel(code)
        self.code_label.setObjectName("sectionCode")

        layout.addWidget(bar)
        layout.addWidget(self.title_label)
        layout.addWidget(line, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.code_label)

    def set_code(self, text: str) -> None:
        self.code_label.setText(text)


class ReadoutTile(QFrame):
    def __init__(self, label: str, value: str = "---", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("readout")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        caption = QLabel(label)
        caption.setObjectName("readoutLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("readoutValue")
        layout.addWidget(caption)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class RatingBar(QWidget):
    """Five skewed segments, like a sync-ratio gauge. Clicking the lit top segment clears it."""

    valueChanged = Signal(int)

    SEGMENT_W = 26
    GAP = 4
    SKEW = 6

    def __init__(self, maximum: int = 5, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0
        self._max = maximum
        self.setFixedHeight(22)
        self.setMinimumWidth(maximum * (self.SEGMENT_W + self.GAP) + 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click a segment to rate. Click the highest lit segment again to clear.")

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:  # noqa: N802
        value = max(0, min(self._max, int(value)))
        if value == self._value:
            return
        self._value = value
        self.update()
        self.valueChanged.emit(value)

    def _segments(self) -> list[QPolygonF]:
        h = self.height() - 1
        polys = []
        for i in range(self._max):
            x = i * (self.SEGMENT_W + self.GAP)
            polys.append(
                QPolygonF(
                    [
                        QPointF(x + self.SKEW, 0),
                        QPointF(x + self.SEGMENT_W + self.SKEW, 0),
                        QPointF(x + self.SEGMENT_W, h),
                        QPointF(x, h),
                    ]
                )
            )
        return polys

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, poly in enumerate(self._segments()):
            lit = i < self._value
            painter.setBrush(QColor(ORANGE if lit else PANEL_ALT))
            painter.setPen(QPen(QColor(ORANGE if lit else ORANGE_DIM), 1))
            painter.drawPolygon(poly)
        painter.setPen(QColor(GREEN if self._value else TEXT_DIM))
        painter.setFont(_font("mono", 12, bold=True))
        text_x = self._max * (self.SEGMENT_W + self.GAP) + 8
        label = f"{self._value}/{self._max}" if self._value else "UNRATED"
        painter.drawText(QRectF(text_x, 0, 90, self.height()), Qt.AlignmentFlag.AlignVCenter, label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        for i, poly in enumerate(self._segments()):
            if poly.containsPoint(event.position(), Qt.FillRule.OddEvenFill):
                self.setValue(0 if i + 1 == self._value else i + 1)
                return
        super().mousePressEvent(event)


class NoSignalScreen(QWidget):
    """Idle picture shown on the monitor before anything is loaded."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#000"))

        # Faint honeycomb grid.
        radius = 26.0
        dx = radius * 1.5
        dy = radius * math.sqrt(3)
        painter.setPen(QPen(QColor(255, 122, 0, 26), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        col = 0
        x = 0.0
        while x < self.width() + radius:
            y = (dy / 2) if col % 2 else 0.0
            while y < self.height() + radius:
                painter.drawPolygon(hexagon(x, y, radius))
                y += dy
            x += dx
            col += 1

        cx, cy = self.width() / 2, self.height() / 2
        painter.setPen(QPen(QColor(RED), 2))
        painter.setBrush(QColor(232, 34, 27, 30))
        painter.drawPolygon(hexagon(cx, cy - 18, 52))

        title_font = _font("serif", 46, bold=True)
        metrics = QFontMetricsF(title_font)
        squeeze = 0.74
        text = "NO SIGNAL"
        width = metrics.horizontalAdvance(text) * squeeze
        painter.save()
        painter.translate(cx - width / 2, cy - 18 + metrics.ascent() / 2 - 4)
        painter.scale(squeeze, 1.0)
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT))
        painter.drawText(QPointF(0, 0), text)
        painter.restore()

        painter.setFont(_font("mono", 12))
        painter.setPen(QColor(ORANGE))
        painter.drawText(
            QRectF(0, cy + 44, self.width(), 20),
            Qt.AlignmentFlag.AlignHCenter,
            "SELECT A FILE IN THE LIBRARY  //  OR RESUME BROADCAST",
        )
        painter.setPen(QColor(TEXT_DIM))
        painter.setFont(_font("mono", 11))
        painter.drawText(QRectF(12, 8, 400, 18), Qt.AlignmentFlag.AlignLeft, "MONITOR-01  //  STANDBY")


class MonitorFrame(QFrame):
    """Black frame with orange corner brackets around the video surface."""

    BRACKET = 18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitor")

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor(ORANGE), 2))
        r = self.rect().adjusted(1, 1, -2, -2)
        b = self.BRACKET
        for (x, y, sx, sy) in (
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ):
            painter.drawLine(x, y, x + sx * b, y)
            painter.drawLine(x, y, x, y + sy * b)
