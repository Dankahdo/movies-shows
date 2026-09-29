"""Animated tab panels drawn from the show's monitor screens (see the "MAGI Tab Panels" design canvas).

Every panel derives from AnimatedWidget, which only ticks while the widget is on screen, so just the
visible tab animates and nothing runs while the panel area is hidden or in fullscreen.
"""

from __future__ import annotations

import math

import shiboken6

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from nerv_theme import TEXT_DIM, _clamp01, _font, _glow_text

RED_HOT = QColor("#ff4a1a")
RED_CORE = QColor("#ff7a4d")
SIGNAL = QColor("#ff9a1a")
SIGNAL_CORE = QColor("#ffc27a")
MINT = QColor("#3dfcc0")
HARMONIC_GREEN = QColor("#39ff6a")
ON_AIR_RED = QColor("#e8221b")
AMBER_PANEL = QColor("#f39a1f")
AMBER_INK = QColor("#3a1700")
AMBER_LINE = QColor("#b8650c")
BLACK_FILL = QColor(5, 5, 5, 235)

_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignCenter


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = _clamp01(t)
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _ramp(stops: list[QColor], t: float) -> QColor:
    t = _clamp01(t) * (len(stops) - 1)
    i = min(len(stops) - 2, int(t))
    return _mix(stops[i], stops[i + 1], t - i)


def glow_frame(painter: QPainter, rect: QRectF, color: QColor, radius: float = 6.0, fill: QColor = BLACK_FILL) -> None:
    halo = QColor(color)
    halo.setAlpha(60)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(halo, 6))
    painter.drawRoundedRect(rect, radius, radius)
    painter.setBrush(fill)
    painter.setPen(QPen(color, 2))
    painter.drawRoundedRect(rect, radius, radius)


def framed_lines(
    painter: QPainter,
    origin: QPointF,
    lines: list[tuple[str, QFont]],
    color: QColor,
    core: QColor,
    pad: float = 10.0,
    align_right: bool = False,
    divider: bool = False,
) -> QRectF:
    """A glowing rounded frame holding one or more lines of glowing text; returns the frame."""
    metrics = [QFontMetricsF(font) for _, font in lines]
    width = max(m.horizontalAdvance(text) for (text, _), m in zip(lines, metrics)) + pad * 2
    heights = [m.height() for m in metrics]
    height = sum(heights) + pad * 0.8 + (4 if divider else 0)
    x = origin.x() - width if align_right else origin.x()
    rect = QRectF(x, origin.y(), width, height)
    glow_frame(painter, rect, color)
    y = rect.top() + pad * 0.4
    for index, ((text, font), line_h) in enumerate(zip(lines, heights)):
        if divider and index == 1:
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(rect.left() + pad, y + 1), QPointF(rect.right() - pad, y + 1))
            y += 4
        _glow_text(painter, QRectF(rect.left() + pad, y, width - pad * 2, line_h), _LEFT, text, font, color, core)
        y += line_h
    return rect


class AnimatedWidget(QWidget):
    FRAME_MS = 33

    def __init__(self, parent: QWidget | None = None, animated: bool = True) -> None:
        super().__init__(parent)
        self._animated = animated
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)

    def seconds(self) -> float:
        return self._clock.elapsed() / 1000.0

    def is_ticking(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, event) -> None:  # noqa: N802
        if self._animated:
            self._timer.start(self.FRAME_MS)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)


class GlowTitle(QWidget):
    def __init__(self, text: str, pixel_size: int = 26, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._font = _font("cond", pixel_size, bold=True)
        self.setFixedHeight(int(QFontMetricsF(self._font).height()) + 4)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        _glow_text(painter, QRectF(self.rect()), _CENTER, self._text, self._font, RED_HOT, RED_CORE)


# ---------------------------------------------------------------- 01 HOME


class SyncMeterPanel(AnimatedWidget):
    """"Mental toxicity level" style meters: one row of 32 capsules per recently watched video,
    lit up to how far into the episode it was left. Click a row to resume it; scroll for older ones."""

    activated = Signal(str)
    SEGMENTS = 32
    LABEL_W = 112
    TOP = 66
    CAPSULES = [MINT, QColor("#2f7bff"), QColor("#8a3cff")]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._scroll = 0
        self._hover = -1
        self._last_session = "—"
        self._files = 0
        self.setMouseTracking(True)
        self.setMinimumSize(560, 250)

    def set_rows(self, rows: list[dict]) -> None:
        self._rows = rows
        self._scroll = max(0, min(self._scroll, len(rows) - self._layout()[2]))
        self.update()

    def set_readouts(self, last_session: str, files: int) -> None:
        self._last_session, self._files = last_session, files
        self.update()

    def _layout(self) -> tuple[float, float, int]:
        avail = max(1.0, self.height() - self.TOP)
        row_h = max(74.0, min(126.0, avail / 3))
        return float(self.TOP), row_h, max(1, int(avail // row_h))

    def _row_at(self, y: float) -> int:
        top, row_h, count = self._layout()
        if y < top:
            return -1
        index = self._scroll + int((y - top) // row_h)
        return index if index < min(len(self._rows), self._scroll + count) else -1

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.seconds()
        w = float(self.width())
        top, row_h, count = self._layout()

        title_font = _font("cond", 36 if w > 900 else 28, bold=True)
        title = "CONTINUE WATCHING LEVEL"
        title_w = QFontMetricsF(title_font).horizontalAdvance(title)
        _glow_text(painter, QRectF(0, 0, title_w + 8, 42), _LEFT, title, title_font, RED_HOT, RED_CORE)
        read_font = _font("cond", 16, bold=True)
        rx = title_w + 30
        for i, (label, value) in enumerate(
            (("LAST SESSION :", self._last_session), ("LIBRARY INTEGRITY :", f"{self._files} FILES"))
        ):
            _glow_text(painter, QRectF(rx, 4 + i * 18, 150, 18), _LEFT, label, read_font, RED_HOT, RED_CORE)
            _glow_text(painter, QRectF(rx + 150, 4 + i * 18, 200, 18), _LEFT, value, read_font, RED_HOT, RED_CORE)

        meter_x = self.LABEL_W + 14.0
        meter_w = w - meter_x - 4
        mono = _font("mono", 11)
        _glow_text(painter, QRectF(meter_x, 44, 120, 16), _LEFT, "00:00", mono, RED_HOT, RED_CORE)
        more = f"  ·  ROWS {self._scroll + 1}-{min(len(self._rows), self._scroll + count)} OF {len(self._rows)}" if self._rows else ""
        _glow_text(painter, QRectF(meter_x, 44, meter_w, 16), _RIGHT, f"WATCHED FRACTION ▸ 32 SEGMENTS{more}", mono, RED_HOT, RED_CORE)

        if not self._rows:
            _glow_text(painter, QRectF(0, top, w, row_h), _CENTER, "NO RECENT ACTIVITY  //  PLAY SOMETHING FROM THE LIBRARY", _font("cond", 20, bold=True), RED_HOT, RED_CORE)
            return

        for slot, index in enumerate(range(self._scroll, min(len(self._rows), self._scroll + count))):
            self._paint_row(painter, self._rows[index], top + slot * row_h, row_h, meter_x, meter_w, t, index == self._hover)

    def _paint_row(
        self, painter: QPainter, row: dict, y: float, row_h: float, meter_x: float, meter_w: float, t: float, hover: bool
    ) -> None:
        if hover:
            painter.setPen(QPen(QColor(255, 122, 0, 110), 1))
            painter.setBrush(QColor(255, 122, 0, 18))
            painter.drawRect(QRectF(0.5, y + 0.5, self.width() - 1, row_h - 7))

        cond_small = _font("cond", 13, bold=True)
        _glow_text(painter, QRectF(6, y + 2, self.LABEL_W, 16), _LEFT, "SUBJECT", cond_small, RED_HOT, RED_CORE)
        code_font = _font("cond", int(min(56, row_h * 0.46)), bold=True)
        _glow_text(painter, QRectF(6, y + 14, self.LABEL_W, row_h * 0.5), _LEFT, row["code"], code_font, RED_HOT, RED_CORE)
        _glow_text(painter, QRectF(6, y + row_h - 26, self.LABEL_W, 16), _LEFT, row["ep"], cond_small, RED_HOT, RED_CORE)

        mono = _font("mono", 11)
        painter.fillRect(QRectF(meter_x, y + 2, 2, 14), RED_HOT)
        _glow_text(painter, QRectF(meter_x + 8, y + 1, meter_w * 0.75, 16), _LEFT, row["show"], mono, RED_HOT, RED_CORE)
        _glow_text(painter, QRectF(meter_x + meter_w * 0.8, y + 1, 100, 16), _LEFT, "[ CAUTION ]", mono, RED_HOT, RED_CORE)
        _glow_text(painter, QRectF(meter_x, y + 1, meter_w, 16), _RIGHT, "[ NEXT EP ]", mono, RED_HOT, RED_CORE)

        caps_y = y + 20
        caps_h = max(18.0, row_h - 20 - 26)
        n = self.SEGMENTS
        gap = 6.0
        cap_w = (meter_w - gap * (n - 1)) / n
        radius = min(cap_w / 2, 10.0)
        frac = row["frac"]
        lit = max(1 if frac > 0 else 0, round(frac * n))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            rect = QRectF(meter_x + i * (cap_w + gap), caps_y, cap_w, caps_h)
            if i < lit:
                base = _ramp(self.CAPSULES, i / (n - 1))
                pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t / 2.6 - i * 0.23)
                color = base.lighter(100 + int(55 * pulse))
                if i == lit - 1 and frac < 1 and (t % 1.1) > 0.62:
                    color = base.darker(260)
                halo = QColor(base)
                halo.setAlpha(70)
                painter.setBrush(halo)
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
                painter.setBrush(color)
                painter.drawRoundedRect(rect, radius, radius)
            else:
                painter.setBrush(QColor("#0a0e1b"))
                painter.setPen(QPen(QColor("#1c2748"), 1))
                painter.drawRoundedRect(rect, radius, radius)
                painter.setPen(Qt.PenStyle.NoPen)

        # Light sweep travelling along the meter.
        sweep_x = meter_x + (t * 300) % (meter_w + 240) - 120
        gradient = QLinearGradient(sweep_x - 60, 0, sweep_x + 60, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 46))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.save()
        painter.setClipRect(QRectF(meter_x, caps_y - 2, meter_w, caps_h + 4))
        painter.fillRect(QRectF(sweep_x - 60, caps_y - 2, 120, caps_h + 4), gradient)
        painter.restore()

        info_y = caps_y + caps_h + 4
        painter.setFont(mono)
        painter.setPen(MINT)
        time_w = QFontMetricsF(mono).horizontalAdvance(row["time"])
        painter.drawText(QRectF(meter_x, info_y, time_w + 4, 16), _LEFT, row["time"])
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(QRectF(meter_x + time_w + 10, info_y, 20, 16), _LEFT, "//")
        state_colors = {"RESUME ▸": QColor("#ffb000"), "WATCHED": MINT, "START ▸": QColor("#ffb000")}
        painter.setPen(state_colors.get(row["state"], QColor(TEXT_DIM)))
        painter.drawText(QRectF(meter_x + time_w + 34, info_y, 300, 16), _LEFT, row["state"])

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = self._row_at(event.position().y())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        index = self._row_at(event.position().y())
        if event.button() == Qt.MouseButton.LeftButton and index >= 0:
            self.activated.emit(self._rows[index]["path"])
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        count = self._layout()[2]
        step = -1 if event.angleDelta().y() > 0 else 1
        self._scroll = max(0, min(max(0, len(self._rows) - count), self._scroll + step))
        self._hover = self._row_at(event.position().y())
        self.update()


# ---------------------------------------------------------------- 02 LIBRARY


class AmberTitleBar(AnimatedWidget):
    """Title strip of a "multinominal analysis" panel: amber band, dark ink, black data tab."""

    def __init__(self, title: str, tab: str, blink: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent, animated=blink)
        self._title, self._tab, self._blink = title, tab, blink
        self.setFixedHeight(40)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        painter.fillRect(QRectF(0, 0, w, h), AMBER_PANEL)
        painter.fillRect(QRectF(0, h - 2, w, 2), AMBER_LINE)
        painter.setPen(AMBER_INK)
        painter.setFont(_font("cond", 28, bold=True))
        painter.drawText(QRectF(12, 0, w, h - 2), _LEFT, self._title)

        tab_font = _font("cond", 18, bold=True)
        tab_w = QFontMetricsF(tab_font).horizontalAdvance(self._tab) + 46
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#050505"))
        painter.drawPolygon(QPolygonF([QPointF(w - tab_w, 0), QPointF(w, 0), QPointF(w, h - 2), QPointF(w - tab_w + 16, h - 2)]))
        lit = not self._blink or (self.seconds() % 1.2) < 0.7
        painter.setPen(QColor("#7dffb0") if lit else QColor("#2c6b48"))
        painter.setFont(tab_font)
        painter.drawText(QRectF(w - tab_w + 22, 0, tab_w - 26, h - 2), _LEFT, self._tab)


class ScanOverlay(AnimatedWidget):
    """A soft band sweeping down over a list's viewport; transparent to the mouse.

    It is parented to the list, not the viewport: a viewport's children are moved when the rows scroll.
    """

    PERIOD = 4.2

    def __init__(self, viewport: QWidget) -> None:
        super().__init__(viewport.parentWidget())
        self._viewport = viewport
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        viewport.installEventFilter(self)
        self.setGeometry(viewport.geometry())
        self.raise_()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self._viewport.geometry())
        return False

    def paintEvent(self, _event) -> None:  # noqa: N802
        h = float(self.height())
        y = (self.seconds() % self.PERIOD) / self.PERIOD * (h + 80) - 40
        gradient = QLinearGradient(0, y - 18, 0, y + 18)
        gradient.setColorAt(0.0, QColor(90, 36, 0, 0))
        gradient.setColorAt(0.5, QColor(90, 36, 0, 60))
        gradient.setColorAt(1.0, QColor(90, 36, 0, 0))
        QPainter(self).fillRect(QRectF(0, y - 18, self.width(), 36), gradient)


class StickySeriesBar(QFrame):
    """Pins the series you are scrolling through to the top of the library list, so a long expanded
    series can be collapsed from anywhere inside it instead of scrolling all the way back up."""

    HEIGHT = 32

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self.setObjectName("stickySeries")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Collapse this series and jump back to it")
        self._tree = tree
        self._series: QTreeWidgetItem | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(10)
        self._title = QLabel()
        self._title.setObjectName("stickyTitle")
        self._meta = QLabel()
        self._meta.setObjectName("stickyMeta")
        self._button = QPushButton("\u25b4  COLLAPSE")
        self._button.setObjectName("stickyButton")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self.collapse)
        layout.addWidget(self._title)
        layout.addWidget(self._meta)
        layout.addStretch(1)
        layout.addWidget(self._button)

        tree.verticalScrollBar().valueChanged.connect(self.refresh)
        tree.itemExpanded.connect(self.refresh)
        tree.itemCollapsed.connect(self.refresh)
        # Rebuilding the tree deletes its items; re-evaluate once the rebuild has finished.
        tree.model().rowsRemoved.connect(lambda *_: QTimer.singleShot(0, self.refresh))
        tree.model().rowsInserted.connect(lambda *_: QTimer.singleShot(0, self.refresh))
        tree.viewport().installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._place()
        return False

    def _place(self) -> None:
        viewport = self._tree.viewport().geometry()
        self.setGeometry(viewport.x(), viewport.y(), viewport.width(), self.HEIGHT)
        self.raise_()

    def refresh(self, *_args) -> None:
        item = self._tree.itemAt(QPoint(4, 2))
        series = item.parent() if item is not None else None
        if series is None:
            self._series = None
            self.hide()
            return
        self._series = series
        self._title.setText(series.text(0))
        self._meta.setText(f"{series.text(1)}  //  {series.text(2)}")
        self._place()
        self.show()

    def collapse(self) -> None:
        series = self._series
        if series is None or not shiboken6.isValid(series):
            self.refresh()
            return
        self._tree.collapseItem(series)
        self._tree.setCurrentItem(series)
        self._tree.scrollToItem(series, QAbstractItemView.ScrollHint.PositionAtTop)
        self.refresh()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.collapse()
            return
        super().mousePressEvent(event)


# ---------------------------------------------------------------- 03 BROADCAST


class ProgramDirectionGraph(AnimatedWidget):
    """"Entry plug emergency direction system" graph: stepped bands flowing across a red ruled grid,
    with the playhead at the broadcast's position in its queue."""

    CYCLE = 5.0
    STOPS = [QColor("#ffb000"), QColor("#ff5a1a"), QColor("#e0287a"), QColor("#8a3cff"), QColor("#3a7bff")]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._total = 0
        self._index = -1
        self._on_air = False
        self.setMinimumSize(420, 240)

    def set_program(self, total: int, index: int, on_air: bool) -> None:
        self._total, self._index, self._on_air = total, index, on_air
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.seconds()
        w, h = float(self.width()), float(self.height())
        left, top, bottom = 40.0, 22.0, h - 22.0
        mono = _font("mono", 11)

        # Ruled grid.
        for y in (top, bottom):
            painter.fillRect(QRectF(left, y - 1, w - left, 2), RED_HOT)
        painter.fillRect(QRectF(left - 1, 0, 2, h), RED_HOT)
        span = (w - left - 24) / 10
        for i in range(11):
            x = left + 16 + i * span
            label = f"{8 + i:02d}"
            painter.fillRect(QRectF(x, top - 6, 2, 12), RED_HOT)
            painter.fillRect(QRectF(x, bottom - 6, 2, 12), RED_HOT)
            _glow_text(painter, QRectF(x - 12, 0, 26, 16), _CENTER, label, mono, RED_HOT, RED_CORE)
            _glow_text(painter, QRectF(x - 12, bottom + 6, 26, 16), _CENTER, label, mono, RED_HOT, RED_CORE)
        mid = (top + bottom) / 2
        level_step = (bottom - top - 20) / 12
        for i, value in enumerate(range(8, -5, -1)):
            y = top + 10 + i * level_step
            painter.fillRect(QRectF(left - 8, y - 1, 16, 2), RED_HOT)
            text = "±0" if value == 0 else f"{value:+d}"
            _glow_text(painter, QRectF(0, y - 8, left - 10, 16), _RIGHT, text, mono, RED_HOT, RED_CORE)

        # Stepped bands build out, hold, then fade, on a loop.
        phase = t % self.CYCLE
        step_w = (w - left - 60) / 10
        # Climb/fall per step, sized so the outermost steps stay between the rulers.
        rise = max(4.0, min((bottom - top) * 0.07, ((bottom - top) / 2 - 70) / 9))
        blocks = [(left + 8, mid - 22, step_w * 1.4, 44, 0.0, 0.0)]
        for i in range(9):
            x = left + 8 + step_w * (1.2 + i)
            delay = (i + 1) * 0.16
            blocks.append((x, mid - 42 - i * rise - (i % 2) * 6, step_w * 1.35, 44 + (i % 3) * 8, delay, (i + 1) / 10))
            blocks.append((x, mid + 16 + i * rise * 1.15 + (i % 2) * 8, step_w * 1.35, 38 + ((i + 1) % 3) * 8, delay + 0.08, (i + 1) / 10))
        painter.save()
        painter.setClipRect(QRectF(left + 1, top + 1, w - left - 1, bottom - top - 2))
        for x, y, bw, bh, delay, tone in blocks:
            local = phase - delay
            if local <= 0:
                continue
            grow = 1 - (1 - _clamp01(local / 0.5)) ** 3
            fade = 1 - _clamp01((phase - (self.CYCLE - 0.7)) / 0.7)
            gradient = QLinearGradient(x, 0, x + bw, 0)
            if tone == 0.0:
                gradient.setColorAt(0, QColor("#ffb000"))
                gradient.setColorAt(1, QColor("#ff5a1a"))
            else:
                gradient.setColorAt(0, _ramp(self.STOPS, tone))
                gradient.setColorAt(1, _ramp(self.STOPS, min(1.0, tone + 0.1)))
            painter.setOpacity(0.9 * fade)
            painter.fillRect(QRectF(x, y, bw * grow, bh), gradient)
        painter.restore()
        painter.setOpacity(1.0)

        # Playhead: the broadcast's place in its queue, or an idle scan while nothing is on air.
        if self._total > 0 and self._index >= 0:
            px = left + 8 + (w - left - 16) * (self._index + 0.5) / self._total
            label = f"CH {self._index + 1:03d} / {self._total:03d}"
        else:
            px = left + 8 + ((t / self.CYCLE) % 1.0) * (w - left - 16)
            label = ""
        glow = 0.55 + 0.45 * math.sin(t * 4) if self._on_air else 0.55
        painter.fillRect(QRectF(px - 1, top + 1, 2, bottom - top - 2), QColor(243, 233, 220, int(200 * glow)))
        painter.fillRect(QRectF(px - 5, top + 1, 10, bottom - top - 2), QColor(243, 233, 220, int(40 * glow)))
        if label:
            _glow_text(painter, QRectF(px + 6, bottom - 24, 150, 16), _LEFT, label, mono, RED_HOT, RED_CORE)

        framed_lines(
            painter,
            QPointF(left + 16, top + 14),
            [("BROADCAST : CH-01", _font("cond", 28, bold=True)), ("PROGRAM DIRECTION SYSTEM", _font("cond", 15, bold=True))],
            RED_HOT,
            RED_CORE,
            divider=True,
        )
        legend_y = bottom - 44
        for i, (text, color) in enumerate(
            (("■ SERIES ROTATION", "#ffb000"), ("■ MOVIE SLOT", "#e0287a"), ("■ LOOP RETURN", "#3a7bff"))
        ):
            painter.setPen(QColor(color))
            painter.setFont(mono)
            painter.drawText(QRectF(left + 16 + i * 150, legend_y, 150, 16), _LEFT, text)


class BlinkBadge(AnimatedWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setFixedSize(92, 22)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = QRectF(self.rect())
        if self._active:
            lit = (self.seconds() % 1.0) < 0.6
            painter.fillRect(rect, ON_AIR_RED if lit else ON_AIR_RED.darker(220))
            painter.setPen(QColor("#ffffff"))
            text = "◉ ON AIR"
        else:
            painter.fillRect(rect, QColor("#1d1510"))
            painter.setPen(QColor(TEXT_DIM))
            text = "STANDBY"
        painter.setFont(_font("cond", 14, bold=True))
        painter.drawText(rect, _CENTER, text)


# ---------------------------------------------------------------- 04 TOOLS


class TaskMonitor(AnimatedWidget):
    """"Energy observational data" band: a green stepped histogram with orange ladders and framed
    status tags. The bars run hotter while a download or split is in progress."""

    HEIGHTS = [58, 58, 74, 74, 92, 92, 70, 110, 110, 86, 86, 64, 64, 120, 120, 96, 72, 72, 88, 88, 104, 104, 80, 80]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = {"yt": "STANDBY", "split": "STANDBY", "ffmpeg": "SYSTEM PATH", "output": ""}
        self.setMinimumHeight(170)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(800, 170)

    def set_status(self, **status: str) -> None:
        self._status.update(status)
        self.update()

    def _busy(self) -> bool:
        return "ACTIVE" in (self._status["yt"], self._status["split"])

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.seconds()
        w, h = float(self.width()), float(self.height())
        busy = self._busy()

        rail_y = 36.0
        dash = QPen(QColor("#8a4300"), 2)
        dash.setDashPattern([4, 3])
        painter.setPen(dash)
        painter.drawLine(QPointF(0, rail_y), QPointF(w, rail_y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(SIGNAL)
        x = 20.0
        while x < w:
            painter.drawPolygon(QPolygonF([QPointF(x + 4, rail_y - 6), QPointF(x + 7, rail_y - 6), QPointF(x + 3, rail_y + 6), QPointF(x, rail_y + 6)]))
            x += 48

        base_y = h - 30
        band_h = base_y - rail_y - 26
        columns = max(12, int(w // 28))
        col_w = w / columns
        amplitude, speed = (0.3, 2.2) if busy else (0.13, 1.0)
        for i in range(columns):
            cx = i * col_w
            if i % 16 == 0:
                alpha = int(255 * (0.55 + 0.45 * math.sin(t * 3.9 + i)))
                for r in range(5):
                    painter.fillRect(QRectF(cx + 1, base_y - 8 - r * 10, col_w - 2, 6), QColor(255, 154, 26, alpha))
                continue
            ratio = self.HEIGHTS[i % len(self.HEIGHTS)] / 124
            wobble = 1 + amplitude * math.sin(2 * math.pi * t * speed / 3.2 - (i % 7) * 0.9)
            bar_h = max(8.0, min(band_h, band_h * ratio * wobble))
            gradient = QLinearGradient(0, base_y - bar_h, 0, base_y)
            gradient.setColorAt(0.0, HARMONIC_GREEN)
            gradient.setColorAt(0.7, QColor("#13a37a"))
            gradient.setColorAt(1.0, QColor("#0c6f5c"))
            painter.fillRect(QRectF(cx + 1, base_y - bar_h, col_w - 2, bar_h), gradient)

        painter.fillRect(QRectF(0, base_y + 2, w, 2), SIGNAL)
        for i in range(int(w // 24) + 1):
            major = i % 5 == 0
            painter.fillRect(QRectF(i * 24, base_y + 5, 2, 8 if major else 5), SIGNAL)

        head = _font("cond", 20, bold=True)
        tag = _font("cond", 15, bold=True)
        framed_lines(painter, QPointF(0, 0), [("TASK OBSERVATIONAL DATA", head)], SIGNAL, SIGNAL_CORE, pad=8)
        y = 0.0
        blink_off = (t % 1.2) >= 0.7
        for key, label, font in (("yt", "YOUTUBE RIP", head), ("split", "SPLITTER", tag), ("ffmpeg", "FFMPEG", tag)):
            value = self._status[key]
            if value == "ACTIVE" and blink_off:
                value = " " * len(value)
            rect = framed_lines(painter, QPointF(w - 1, y), [(f"{label} : {value}", font)], SIGNAL, SIGNAL_CORE, pad=8, align_right=True)
            y = rect.bottom() + 4
        output = QFontMetricsF(tag).elidedText(self._status["output"], Qt.TextElideMode.ElideMiddle, w * 0.5)
        framed_lines(painter, QPointF(0, h - 24), [(f"OUTPUT POINT : {output} : POINT 00", tag)], SIGNAL, SIGNAL_CORE, pad=6)
        framed_lines(painter, QPointF(w - 1, h - 24), [("OBSERVED BY MAGI", tag)], SIGNAL, SIGNAL_CORE, pad=6, align_right=True)


# ---------------------------------------------------------------- 05 SYSTEM


class HarmonicsBackdrop(AnimatedWidget):
    """"Harmonics simulation graph display" behind the settings: green ± crosshair axes, flowing
    harmonic traces, a sweep line and a pattern badge that reads GREEN when everything is saved."""

    TOP_MARGIN = 78

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._saved = True

    def set_saved(self, saved: bool) -> None:
        self._saved = saved
        self.update()

    def origin(self) -> QPointF:
        return QPointF(max(560.0, self.width() * 0.66), max(self.TOP_MARGIN + 150.0, self.height() * 0.64))

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.seconds()
        w, h = float(self.width()), float(self.height())
        o = self.origin()
        mono = _font("mono", 11)

        # Harmonic traces flowing along the axis.
        for amp, period, phase, alpha, width in ((h * 0.26, 520.0, 0.0, 70, 2.0), (h * 0.15, 340.0, 1.4, 46, 1.5)):
            pen = QPen(QColor(57, 255, 106, alpha), width)
            pen.setDashPattern([7, 5])
            pen.setDashOffset(-t * 12)
            painter.setPen(pen)
            points = [
                QPointF(x, o.y() + amp * math.sin(phase + t * 0.6 + x / period * 2 * math.pi)) for x in range(0, int(w) + 8, 8)
            ]
            painter.drawPolyline(QPolygonF(points))

        sweep_x = (t / 6.0 % 1.0) * w
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(57, 255, 106, 0))
        gradient.setColorAt(0.5, QColor(57, 255, 106, 150))
        gradient.setColorAt(1.0, QColor(57, 255, 106, 0))
        painter.fillRect(QRectF(sweep_x, 0, 2, h), gradient)

        # Crosshair axes with ± scales.
        painter.fillRect(QRectF(0, o.y() - 1, w, 2), HARMONIC_GREEN)
        painter.fillRect(QRectF(o.x() - 1, 0, 2, h), HARMONIC_GREEN)
        x_step, y_step = 72.0, 34.0
        x = o.x() - math.floor(o.x() / 12) * 12
        while x < w:
            major = abs((x - o.x()) % x_step) < 0.5
            size = 9 if major else 5
            painter.fillRect(QRectF(x, o.y() - size, 1, size * 2), HARMONIC_GREEN)
            x += 12
        neg = ["-C", "-B", "-A", "-9", "-8", "-7", "-6", "-5", "-4", "-3", "-2", "-1"]
        for i in range(1, 13):
            px = o.x() - i * x_step
            if px > 10:
                _glow_text(painter, QRectF(px - 14, o.y() - 28, 28, 16), _CENTER, neg[-i], mono, HARMONIC_GREEN, QColor("#c8ffd8"))
        i = 1
        while o.x() + i * x_step < w - 10:
            px = o.x() + i * x_step
            _glow_text(painter, QRectF(px - 14, o.y() - 28, 28, 16), _CENTER, f"+{i}", mono, HARMONIC_GREEN, QColor("#c8ffd8"))
            i += 1
        _glow_text(painter, QRectF(o.x() + 6, o.y() + 6, 30, 16), _LEFT, "±0", mono, HARMONIC_GREEN, QColor("#c8ffd8"))
        y = o.y() - math.floor(o.y() / 10) * 10
        while y < h:
            major = abs((y - o.y()) % 40) < 0.5
            size = 9 if major else 5
            painter.fillRect(QRectF(o.x() - size, y, size * 2, 1), HARMONIC_GREEN)
            y += 10
        up = ["+1", "+2", "+3", "+4", "+5", "+6", "+7", "+8", "+9", "+A"]
        for i, text in enumerate(up, start=1):
            py = o.y() - i * y_step
            if py > 8:
                _glow_text(painter, QRectF(o.x() + 14, py - 8, 30, 16), _LEFT, text, mono, HARMONIC_GREEN, QColor("#c8ffd8"))
        for i in range(1, 8):
            py = o.y() + i * y_step
            if py < h - 8:
                _glow_text(painter, QRectF(o.x() + 14, py - 8, 30, 16), _LEFT, f"-{i}", mono, HARMONIC_GREEN, QColor("#c8ffd8"))

        # Title card and plug readout.
        title = framed_lines(
            painter,
            QPointF(12, 10),
            [("MAGI HARMONICS", _font("cond", 24, bold=True)), ("SYSTEM CONFIGURATION DISPLAY", _font("cond", 24, bold=True))],
            RED_HOT,
            RED_CORE,
            pad=10,
        )
        info = _font("cond", 15, bold=True)
        for i, line in enumerate(("CONFIG PLUG 1", "STATE FILE : data/app_state.json", "SUBJECT : LOCAL OPERATOR")):
            _glow_text(painter, QRectF(title.right() + 18, 12 + i * 18, 320, 18), _LEFT, line, info, RED_HOT, RED_CORE)

        # Pattern badge, breathing.
        breathe = 0.5 + 0.5 * math.sin(t * 2.6)
        color = QColor(RED_HOT) if self._saved else QColor("#ffb000")
        halo = QColor(color)
        halo.setAlpha(int(50 + 120 * breathe))
        big, small = _font("cond", 26, bold=True), _font("cond", 20, bold=True)
        lines = [("CONFIG PATTERN", small), ("GREEN" if self._saved else "ORANGE  //  UNSAVED", big)]
        width = max(QFontMetricsF(f).horizontalAdvance(s) for s, f in lines) + 32
        rect = QRectF(w - width - 16, h - 72, width, 60)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(halo, 10))
        painter.drawRoundedRect(rect, 6, 6)
        framed_lines(painter, rect.topLeft(), lines, color, RED_CORE if self._saved else QColor("#ffe0a0"), pad=16)
