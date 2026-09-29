"""NERV / MAGI inspired visual theme: palette, Qt stylesheet and decorative widgets."""

from __future__ import annotations

import math
import random
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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

/* ---------- tab panels ---------- */
QFrame#readout { background-color: #0a0504; border: 2px solid #ff4a1a; border-left: 2px solid #ff4a1a; border-radius: 8px; }
QLabel#readoutLabel { color: #ff4a1a; }
QLabel#readoutValue { color: #ff6a2a; font-size: 32px; }
QLabel#resumeHint { color: @text_dim; font-family: "@mono"; font-size: 11px; }
QPushButton:checked { background-color: @orange; color: #000; border-color: @orange; }
QListWidget#queueList::item:selected { background-color: @red; color: #fff; }

QFrame#amberPanel { background-color: #f39a1f; border: none; border-radius: 3px; }
QWidget#amberBody { background-color: #f39a1f; }
QFrame#amberPanel QLabel { color: #3a1700; }
QFrame#amberPanel QLabel#detailTitle { color: #3a1700; font-size: 21px; }
QFrame#amberPanel QLabel#detailMeta { color: #5a2a00; }
QFrame#amberPanel QLabel#fieldLabel { color: #3a1700; font-size: 15px; }
QFrame#amberPanel QLabel#thumbPreview { background-color: #2a1000; border: 2px solid #b8650c; color: #f39a1f; }
QFrame#amberPanel QTextEdit { background-color: rgba(58, 23, 0, 24); color: #3a1700; border: 1px solid #b8650c; }
QFrame#amberPanel QPushButton { background-color: transparent; color: #3a1700; border: 2px solid #3a1700; }
QFrame#amberPanel QPushButton:hover { background-color: rgba(58, 23, 0, 40); color: #3a1700; }
QFrame#amberPanel QPushButton:pressed { background-color: #3a1700; color: #f39a1f; }
QFrame#amberPanel QPushButton[variant="primary"] { background-color: #050505; color: #ffb000; border: 2px solid #050505; }
QFrame#amberPanel QPushButton[variant="primary"]:hover { background-color: #2a1000; color: #ffc040; }
QTreeWidget#amberTree {
    background-color: #f39a1f; alternate-background-color: #ec9116; color: #3a1700; border: none;
    font-family: "@mono"; font-size: 12px;
}
QTreeWidget#amberTree::item:hover { background-color: rgba(58, 23, 0, 34); }
QTreeWidget#amberTree::item:selected { background-color: #3a1700; color: #f39a1f; }
QTreeWidget#amberTree QHeaderView::section {
    background-color: #f39a1f; color: #3a1700; border: none;
    border-bottom: 1px solid #b8650c; border-right: 1px solid #b8650c;
    font-family: "@cond"; font-size: 14px; font-weight: bold;
}

/* Scoped under #stickySeries so the amber panel's dark-ink label/button rules don't win. */
QFrame#stickySeries { background-color: #3a1700; border: none; border-bottom: 2px solid #ff7a00; }
QFrame#stickySeries QLabel#stickyTitle { color: #f39a1f; font-family: "@cond"; font-size: 16px; font-weight: bold; }
QFrame#stickySeries QLabel#stickyMeta { color: #c98a3a; font-family: "@mono"; font-size: 11px; }
QFrame#stickySeries QPushButton#stickyButton {
    background-color: transparent; color: #f39a1f; border: 1px solid #f39a1f;
    padding: 1px 10px; min-height: 16px; font-size: 13px;
}
QFrame#stickySeries QPushButton#stickyButton:hover { background-color: #f39a1f; color: #3a1700; }
QFrame#stickySeries QPushButton#stickyButton:pressed { background-color: #ff7a00; color: #000; }

QFrame#harmonicsForm { background-color: rgba(5, 5, 5, 228); border: 1px solid @green_dim; }
QLabel#harmonicsTitle { color: @green; font-family: "@cond"; font-size: 18px; font-weight: bold; }
QLabel#keyCapGreen {
    color: #02130a; background-color: @green; padding: 1px 6px;
    font-family: "@mono"; font-size: 12px; font-weight: bold;
}
QLabel#keyAction { color: #d8ffe4; font-size: 14px; }

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


class ScopeBackdrop:
    """Looping oscilloscope picture for the header: a glowing magenta sine band that turns into a
    red/blue lattice on its falling slope, over a dense grid with cream rails, a ruler and crosshairs.

    Each wave is rendered once as a seamless one-wavelength tile and then only scrolled, so a
    frame costs a few pixmap blits.
    """

    CREAM = QColor("#f3e3d3")
    MAGENTA = QColor("#ff2bd6")
    VIOLET = QColor("#8a3cff")
    LATTICE_RED = QColor("#ff1f5a")
    LATTICE_BLUE = QColor("#5a2bff")
    BACKGROUND = QColor("#0e050b")

    # (wavelength px, amplitude/height, band thickness/height, colour, opacity, speed px/s)
    WAVES = (
        (780, 0.18, 0.22, VIOLET, 0.45, -22.0),
        (520, 0.24, 0.40, MAGENTA, 0.85, 48.0),
    )
    SCAN_SPEED = 90.0

    def __init__(self) -> None:
        self._size = QSize()
        self._dpr = 1.0
        self._static: QPixmap | None = None
        self._rails: QPixmap | None = None
        self._tiles: list[QPixmap] = []

    def _pixmap(self, width: int, height: int) -> QPixmap:
        pixmap = QPixmap(max(1, int(width * self._dpr)), max(1, int(height * self._dpr)))
        pixmap.setDevicePixelRatio(self._dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def _ensure(self, size: QSize, dpr: float) -> None:
        if size == self._size and dpr == self._dpr and self._static is not None:
            return
        self._size, self._dpr = QSize(size), dpr
        w, h = size.width(), size.height()

        # Background grid, drawn under the waves.
        self._static = self._pixmap(w, h)
        painter = QPainter(self._static)
        painter.fillRect(QRectF(0, 0, w, h), self.BACKGROUND)
        painter.setPen(QPen(QColor(255, 43, 214, 30), 1))
        for x in range(0, w, 6):
            painter.drawLine(x, 0, x, h)
        painter.setPen(QPen(QColor(255, 43, 214, 16), 1))
        for y in range(0, h, 12):
            painter.drawLine(0, y, w, y)
        painter.end()

        # Rails, ruler, crosshairs and the fixed ladder, drawn over the waves.
        self._rails = self._pixmap(w, h)
        painter = QPainter(self._rails)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QColor(self.CREAM)
        glow.setAlpha(60)
        bottom = h - 14
        for y, thickness in ((3, 3), (bottom, 2)):
            painter.fillRect(QRectF(0, y - 2, w, thickness + 4), glow)
            painter.fillRect(QRectF(0, y, w, thickness), self.CREAM)
        painter.setPen(QPen(self.CREAM, 1))
        for x in range(0, w, 8):
            tall = x % 64 == 0
            painter.drawLine(QPointF(x + 0.5, bottom + 4), QPointF(x + 0.5, h - (1 if tall else 7)))
        self._crosshairs(painter, w, h)
        self._ladder(painter, w * 0.5, h, 150)
        painter.end()

        self._tiles = [self._wave_tile(*wave[:5], h) for wave in self.WAVES]

    def _crosshairs(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QPen(self.CREAM, 2))
        arm = 6
        # Stop short of the clock on the right.
        for x in range(130, w - 320, 260):
            for y in (h * 0.26, h * 0.66):
                painter.drawLine(QPointF(x - arm, y), QPointF(x + arm, y))
                painter.drawLine(QPointF(x, y - arm), QPointF(x, y + arm))

    def _ladder(self, painter: QPainter, x: float, h: int, alpha: int) -> None:
        cream = QColor(self.CREAM)
        cream.setAlpha(alpha)
        painter.setPen(QPen(cream, 2))
        for y in range(9, h - 16, 5):
            painter.drawLine(QPointF(x - 5, y), QPointF(x + 5, y))
        glow = QColor(self.CREAM)
        glow.setAlpha(alpha // 5)
        painter.fillRect(QRectF(x - 9, 6, 18, h - 22), glow)

    def _wave_tile(
        self, wavelength: int, amp_ratio: float, thick_ratio: float, color: QColor, opacity: float, h: int
    ) -> QPixmap:
        tile = self._pixmap(wavelength, h)
        painter = QPainter(tile)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(opacity)
        mid = (h - 14) / 2 + 2
        amp = h * amp_ratio
        thick = h * thick_ratio
        k = 2 * math.pi / wavelength

        def centre(x: float) -> float:
            return mid + amp * math.sin(k * x)

        def curve(offset: float) -> QPainterPath:
            path = QPainterPath(QPointF(-8, centre(-8) + offset))
            for x in range(-4, wavelength + 12, 4):
                path.lineTo(x, centre(x) + offset)
            return path

        # Soft halo, then the fine strands that make up the band.
        halo = QColor(color)
        halo.setAlpha(45)
        painter.setPen(QPen(halo, thick + 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawPath(curve(0))
        strands = 12
        for i in range(strands):
            offset = -thick / 2 + thick * i / (strands - 1)
            strand = QColor(color)
            strand.setAlpha(150 if i in (0, strands - 1) else 95)
            painter.setPen(QPen(strand, 1.6))
            painter.drawPath(curve(offset))

        # Crosshatch lattice, strongest where the band falls (screen y increasing).
        step, run = 12, 22
        for x in range(-run - step, wavelength + run + step, step):
            weight = max(0.0, math.cos(k * (x + run / 2))) ** 1.5
            if weight < 0.05:
                continue
            top_a, bottom_a = centre(x) - thick / 2, centre(x) + thick / 2
            top_b, bottom_b = centre(x + run) - thick / 2, centre(x + run) + thick / 2
            red = QColor(self.LATTICE_RED)
            red.setAlpha(int(190 * weight))
            painter.setPen(QPen(red, 1.3))
            painter.drawLine(QPointF(x, top_a), QPointF(x + run, bottom_b))
            blue = QColor(self.LATTICE_BLUE)
            blue.setAlpha(int(170 * weight))
            painter.setPen(QPen(blue, 1.3))
            painter.drawLine(QPointF(x + run, top_b), QPointF(x, bottom_a))
        painter.end()
        return tile

    def paint(self, painter: QPainter, size: QSize, dpr: float, seconds: float, scrims: list[tuple[float, float]]) -> None:
        self._ensure(size, dpr)
        w, h = size.width(), size.height()
        painter.drawPixmap(0, 0, self._static)

        for tile, (wavelength, *_rest, speed) in zip(self._tiles, self.WAVES):
            offset = int(seconds * speed) % wavelength
            x = -offset
            while x < w:
                painter.drawPixmap(x, 0, tile)
                x += wavelength

        painter.drawPixmap(0, 0, self._rails)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._ladder(painter, (seconds * self.SCAN_SPEED) % (w + 40) - 20, h, 230)

        # Darken behind text so the title and clock stay legible over the moving waves.
        for start, end in scrims:
            gradient = QLinearGradient(start, 0, end, 0)
            gradient.setColorAt(0.0, QColor(0, 0, 0, 185))
            gradient.setColorAt(0.65, QColor(0, 0, 0, 150))
            gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(min(start, end), 0, abs(end - start), h - 15), gradient)


class NervHeader(QFrame):
    FRAME_MS = 33

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        self.setMinimumHeight(96)
        self._backdrop = ScopeBackdrop()
        self._clock_elapsed = QElapsedTimer()
        self._clock_elapsed.start()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 22)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self._title = TitleCard("MAGI MEDIA SYSTEM", 32)
        titles.addWidget(self._title)
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

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self.update)

    def _tick(self) -> None:
        self.clock.setText(datetime.now().strftime("%Y.%m.%d  %H:%M:%S"))

    # Only animate while on screen (the header is hidden in fullscreen).
    def showEvent(self, event) -> None:  # noqa: N802
        self._frame_timer.start(self.FRAME_MS)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._frame_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        title_end = float(self._title.geometry().right() + 70)
        clock_start = float(self.clock.geometry().left() - 60)
        self._backdrop.paint(
            painter,
            self.size(),
            self.devicePixelRatioF(),
            self._clock_elapsed.elapsed() / 1000.0,
            [(0.0, title_end), (float(self.width()), clock_start)],
        )


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

    def __init__(
        self,
        maximum: int = 5,
        parent: QWidget | None = None,
        on: str = ORANGE,
        off_fill: str = PANEL_ALT,
        off_border: str = ORANGE_DIM,
        text: str = GREEN,
    ) -> None:
        super().__init__(parent)
        self._colors = {"on": QColor(on), "off_fill": QColor(off_fill), "off_border": QColor(off_border), "text": QColor(text)}
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
            painter.setBrush(self._colors["on"] if lit else self._colors["off_fill"])
            painter.setPen(QPen(self._colors["on"] if lit else self._colors["off_border"], 1.5))
            painter.drawPolygon(poly)
        painter.setPen(self._colors["text"] if self._value else self._colors["off_border"])
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


def _lerp_rect(a: QRectF, b: QRectF, t: float) -> QRectF:
    return QRectF(
        a.x() + (b.x() - a.x()) * t,
        a.y() + (b.y() - a.y()) * t,
        a.width() + (b.width() - a.width()) * t,
        a.height() + (b.height() - a.height()) * t,
    )


class ReticleTabBar(QTabBar):
    """Tab bar whose targeting brackets slide from the old tab to the new one."""

    DURATION_MS = 220
    BRACKET = 7

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._from_rect = QRectF()
        self._to_index = -1
        self._t = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_step)
        self.currentChanged.connect(self._on_current_changed)

    def _reticle_rect(self) -> QRectF:
        if self._to_index < 0:
            return QRectF()
        target = QRectF(self.tabRect(self._to_index))
        if self._from_rect.isNull() or self._t >= 1.0:
            return target
        return _lerp_rect(self._from_rect, target, self._t)

    def _on_current_changed(self, index: int) -> None:
        # Start from wherever the reticle is drawn right now, so rapid switching stays smooth.
        self._from_rect = self._reticle_rect()
        self._to_index = index
        self._t = 1.0 if self._from_rect.isNull() else 0.0
        self._anim.stop()
        if self._t < 1.0:
            self._anim.start()
        self.update()

    def _on_step(self, value: float) -> None:
        self._t = float(value)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        rect = self._reticle_rect()
        if rect.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._t < 1.0 and not self._from_rect.isNull():
            # Motion streak between where the reticle left and where it is now.
            streak = self._from_rect.united(rect)
            streak.setTop(streak.bottom() - 3)
            painter.fillRect(streak, QColor(255, 122, 0, int(160 * (1.0 - self._t))))

        r = rect.adjusted(2, 2, -3, -2)
        b = self.BRACKET
        painter.setPen(QPen(QColor(TEXT), 2))
        for x, y, sx, sy in (
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ):
            painter.drawLine(QPointF(x, y), QPointF(x + sx * b, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + sy * b))


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _smoothstep(value: float) -> float:
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


def _glow_text(painter: QPainter, rect: QRectF, flags, text: str, font: QFont, color: QColor, core: QColor) -> None:
    """Text with a soft bloom, like the show's CRT readouts."""
    painter.setFont(font)
    halo = QColor(color)
    halo.setAlpha(70)
    painter.setPen(halo)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        painter.drawText(rect.translated(dx, dy), flags, text)
    painter.setPen(core)
    painter.drawText(rect, flags, text)


class _TabTransition(QWidget):
    """Base overlay for tab changes: holds the outgoing page snapshot and drives progress 0 → 1.

    Each element of a transition gets a start delay; in its local time it first covers the
    outgoing page (0 → 0.5) and then uncovers the incoming page (0.5 → 1).
    """

    DURATION_MS = 420
    SPAN = 0.45

    def __init__(self, host: QWidget, snapshot: QPixmap, direction: int, label: str) -> None:
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(host.rect())
        self._snapshot = snapshot
        # Moving to a higher tab sweeps right-to-left, so the new page enters from the right.
        self._dir = 1 if direction >= 0 else -1
        self._label = label
        self._p = 0.0
        self._done = False
        self._setup()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_step)
        self._anim.finished.connect(self.finish)

        self.show()
        self.raise_()
        self._anim.start()

    def _setup(self) -> None:
        pass

    def _on_step(self, value: float) -> None:
        self._p = float(value)
        self.update()

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._anim.stop()
        self.hide()
        self.deleteLater()

    def _order(self, x: float) -> float:
        """0 for the side the sweep starts from, 1 for the far side."""
        norm = _clamp01(x / max(1.0, float(self.width())))
        return 1.0 - norm if self._dir > 0 else norm

    def _local(self, delay: float) -> float:
        return _clamp01((self._p - delay) / self.SPAN)


class SyncCascade(_TabTransition):
    """Columns of glowing slanted bars cascade on and off, with orange circuit traces and SYNC tags."""

    COL_W = 132
    ROW_H = 40
    BAR_T = 13
    RISE = 24
    MINT = QColor("#3dfcc0")
    TRACE = QColor("#e07a1f")

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        ncols = int(w // self.COL_W) + 1
        nrows = int(h // self.ROW_H) + 2
        max_delay = 1.0 - self.SPAN
        label_font = _font("mono", 9)
        tag_font = _font("cond", 11, bold=True)

        for c in range(ncols):
            x0 = c * self.COL_W
            lp = self._local(self._order(x0 + self.COL_W / 2) * max_delay)
            column = QRectF(x0, 0, self.COL_W, h)

            if lp < 0.5:
                painter.save()
                painter.setClipRect(column)
                painter.drawPixmap(QPointF(0, 0), self._snapshot)
                painter.restore()
            if lp <= 0.0 or lp >= 1.0:
                continue

            envelope = math.sin(math.pi * lp)
            painter.fillRect(column, QColor(0, 0, 0, int(215 * envelope)))

            # Circuit trace down the column.
            trace = QColor(self.TRACE)
            trace.setAlpha(int(220 * envelope))
            painter.setPen(QPen(trace, 1))
            trace_x = x0 + 8
            painter.drawLine(QPointF(trace_x, 0), QPointF(trace_x, h))

            # Rows light top-down, then clear top-down.
            lit_until = _smoothstep(lp / 0.5) if lp < 0.5 else 1.0
            cleared_until = 0.0 if lp < 0.5 else _smoothstep((lp - 0.5) / 0.5)
            stagger = (self.ROW_H / 2) if c % 2 else 0.0
            bx0, bx1 = x0 + 62, x0 + self.COL_W - 6

            for i in range(nrows):
                frac = i / nrows
                if frac >= lit_until or frac < cleared_until:
                    continue
                y = i * self.ROW_H + stagger - self.ROW_H
                bar = QPolygonF(
                    [
                        QPointF(bx0, y + self.RISE + self.BAR_T),
                        QPointF(bx0, y + self.RISE),
                        QPointF(bx1, y),
                        QPointF(bx1, y + self.BAR_T),
                    ]
                )
                halo = QColor(self.MINT)
                halo.setAlpha(60)
                painter.setPen(QPen(halo, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.setBrush(self.MINT)
                painter.drawPolygon(bar)

                mid_y = y + self.RISE + self.BAR_T / 2
                painter.setPen(QPen(trace, 1))
                painter.drawLine(QPointF(trace_x, mid_y), QPointF(bx0 - 4, mid_y))
                painter.setFont(label_font)
                painter.drawText(QPointF(x0 + 12, mid_y - 3), f"MT-{1350 + c * 20 + i:05d}")

            if envelope > 0.35:
                tag = QRectF(bx0 - 2, 6, 62, 17)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#0f5c47"))
                painter.drawRoundedRect(tag, 3, 3)
                painter.setPen(self.MINT)
                painter.setFont(tag_font)
                painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, "SYNC")

        # Destination readout.
        painter.setOpacity(_clamp01(math.sin(math.pi * self._p) * 1.8))
        font = _font("cond", 15, bold=True)
        text = f"SYNC  ▸  {self._label}"
        box = QRectF(14, h - 44, QFontMetricsF(font).horizontalAdvance(text) + 28, 30)
        painter.setBrush(QColor(0, 0, 0, 230))
        painter.setPen(QPen(self.MINT, 2))
        painter.drawRoundedRect(box, 4, 4)
        _glow_text(painter, box, Qt.AlignmentFlag.AlignCenter, text, font, self.MINT, QColor("#c8ffee"))


class ATFieldBurst(_TabTransition):
    """Orange honeycomb cells bloom across the pane with A.T. FIELD warning panels."""

    RADIUS = 24.0
    SPAN = 0.4
    HOT = QColor("#ff6a1a")

    def _setup(self) -> None:
        rng = random.Random()
        r = self.RADIUS
        dx, dy = math.sqrt(3) * r, 1.5 * r
        self._cells: list[tuple[float, float, float, float]] = []
        row = 0
        y = 0.0
        while y < self.height() + r:
            x = (dx / 2) if row % 2 else 0.0
            while x < self.width() + dx:
                self._cells.append((x, y, rng.random(), 0.62 + 0.38 * rng.random()))
                x += dx
            y += dy
            row += 1

        # Offscreen copy of the outgoing page; revealed cells are erased from it each frame
        # (far cheaper than clipping to hundreds of hexagons).
        self._buffer = QImage(self._snapshot.size(), QImage.Format.Format_ARGB32_Premultiplied)
        self._buffer.setDevicePixelRatio(self._snapshot.devicePixelRatio())

    # Pointy-top unit hexagon, matching the reference honeycomb.
    _UNIT_HEX = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(30, 390, 60)]

    @classmethod
    def _hex(cls, cx: float, cy: float, radius: float) -> QPolygonF:
        return QPolygonF([QPointF(cx + radius * ux, cy + radius * uy) for ux, uy in cls._UNIT_HEX])

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        max_delay = 1.0 - self.SPAN
        r = self.RADIUS

        buffer_painter = QPainter(self._buffer)
        buffer_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        buffer_painter.drawPixmap(QPointF(0, 0), self._snapshot)
        buffer_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        buffer_painter.setPen(Qt.PenStyle.NoPen)
        buffer_painter.setBrush(QColor("#000"))

        active = []
        for cx, cy, jitter, shade in self._cells:
            # Mostly a wave, with a ragged leading edge like the reference.
            delay = (self._order(cx) * 0.8 + jitter * 0.2) * max_delay
            lp = self._local(delay)
            if lp >= 0.5:
                buffer_painter.drawPolygon(self._hex(cx, cy, r + 1.0))
            if 0.0 < lp < 1.0:
                active.append((cx, cy, shade, lp))
        buffer_painter.end()
        painter.drawImage(QPointF(0, 0), self._buffer)

        painter.setPen(Qt.PenStyle.NoPen)
        for cx, cy, shade, lp in active:
            envelope = math.sin(math.pi * lp)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setBrush(QColor(0, 0, 0, int(220 * envelope)))
            painter.drawPolygon(self._hex(cx, cy, r + 0.8))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            scale = _smoothstep(min(lp, 1.0 - lp) * 2.0)
            cell = QColor(
                int(self.HOT.red() * shade), int(self.HOT.green() * shade), int(self.HOT.blue() * shade)
            )
            painter.setBrush(cell)
            painter.drawPolygon(self._hex(cx, cy, r * 0.88 * scale))
            painter.setBrush(QColor(255, 170, 110, int(90 * shade)))
            painter.drawPolygon(self._hex(cx, cy, r * 0.5 * scale))

        self._paint_panels(painter)

    def _panel(self, painter: QPainter, rect: QRectF) -> None:
        glow = QColor(self.HOT)
        glow.setAlpha(60)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(glow, 7))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setBrush(QColor(0, 0, 0, 225))
        painter.setPen(QPen(self.HOT, 2))
        painter.drawRoundedRect(rect, 7, 7)

    def _paint_panels(self, painter: QPainter) -> None:
        painter.setOpacity(_clamp01(math.sin(math.pi * self._p) * 1.8))
        w, h = float(self.width()), float(self.height())
        core = QColor("#ffc48a")
        big = _font("cond", 26, bold=True)
        mid = _font("cond", 19, bold=True)
        small = _font("mono", 10, bold=True)
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # Warning panel on the side the field arrives from.
        lines = ["SECTOR TRANSFER", f"TO {self._label}"]
        width = max(QFontMetricsF(big).horizontalAdvance(t) for t in lines) + 32
        x = w - width - 24 if self._dir > 0 else 24.0
        box = QRectF(x, 20, width, 76)
        self._panel(painter, box)
        _glow_text(painter, QRectF(x + 16, 26, width - 32, 32), left, lines[0], big, self.HOT, core)
        _glow_text(painter, QRectF(x + 16, 58, width - 32, 32), left, lines[1], big, self.HOT, core)

        # Status panel, bottom corner opposite the warning.
        rows = [
            (self._label, mid),
            ("A.T.FIELD IN OPERATION", mid),
            ("FIELD STRENGTH AT ABSOLUTE LIMIT", small),
        ]
        width = max(QFontMetricsF(f).horizontalAdvance(t) for t, f in rows) + 28
        x = 24.0 if self._dir > 0 else w - width - 24
        box = QRectF(x, h - 104, width, 84)
        self._panel(painter, box)
        y = box.top() + 6
        for text, font in rows:
            line_h = 26 if font is mid else 20
            _glow_text(painter, QRectF(x + 14, y, width - 28, line_h), left, text, font, self.HOT, core)
            y += line_h


class NervTabWidget(QTabWidget):
    """QTabWidget with the reticle tab bar; page changes alternate between SYNC and A.T. FIELD transitions."""

    TRANSITIONS = (SyncCascade, ATFieldBurst)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabBar(ReticleTabBar())
        self._prev_index = -1
        self._transition_count = 0
        self._transition: _TabTransition | None = None
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, index: int) -> None:
        prev, self._prev_index = self._prev_index, index
        if self._transition is not None:
            self._transition.finish()
            self._transition = None
        if prev < 0 or index < 0 or prev == index or not self.isVisible():
            return
        old_page, new_page = self.widget(prev), self.widget(index)
        if old_page is None or new_page is None:
            return
        snapshot = old_page.grab()
        transition_cls = self.TRANSITIONS[self._transition_count % len(self.TRANSITIONS)]
        self._transition_count += 1
        self._transition = transition_cls(new_page.parentWidget(), snapshot, index - prev, self.tabText(index))
