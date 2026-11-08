"""Probe Accuracy screen.

Runs Klipper PROBE_ACCURACY at the bed centre with a live nozzle-tap animation,
plots every sample as it arrives and shows range / std-dev / average results.
"""

import json
import math
import random
import re
import statistics
import threading
import urllib.request

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


C_CYAN = QtGui.QColor("#00E5FF")
C_GREEN = QtGui.QColor("#34D399")
C_AMBER = QtGui.QColor("#FBBF24")
C_RED = QtGui.QColor("#EF4444")
C_SLATE = QtGui.QColor("#94A3B8")

RE_SAMPLE = re.compile(r"probe:?.*(?:is|contact at)\s+z=\s*(-?[\d.]+)", re.IGNORECASE)
RE_RESULT = re.compile(
    r"maximum\s+(-?[\d.]+),\s*minimum\s+(-?[\d.]+),\s*range\s+(-?[\d.]+),\s*average\s+(-?[\d.]+),"
    r"\s*median\s+(-?[\d.]+),\s*standard deviation\s+(-?[\d.]+)")


def verdict(std: float):
    """Quality rating from standard deviation (mm)."""
    if std <= 0.0025:
        return "EXCELLENT", C_GREEN
    if std <= 0.005:
        return "GOOD", C_GREEN
    if std <= 0.01:
        return "FAIR", C_AMBER
    return "POOR", C_RED


class ProbeTapAnimation(QtWidgets.QWidget):
    """Side view of the toolhead tapping the bed. Only moves down & up when probing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self._stroke_t = 0.0
        self._is_tapping = False
        self._flash = 0.0
        self._ripples = []
        self._done = 0
        self._total = 10
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(20)  # 50 FPS
        self._timer.timeout.connect(self._step)

    def start(self, total: int):
        """Reset state for a new test run; remains stationary at top until taps occur."""
        self._total = total
        self._done = 0
        self._is_tapping = False
        self._stroke_t = 0.0
        self._flash = 0.0
        self._ripples = []
        self._timer.stop()
        self.update()

    def stop(self):
        self._is_tapping = False
        self._timer.stop()
        self.update()

    def trigger_tap(self, done: int):
        """Execute exactly one downward probe tap stroke and lift back up."""
        self._done = done
        self._is_tapping = True
        self._stroke_t = 0.0
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def contact(self, done: int):
        """Compatibility alias for trigger_tap."""
        self.trigger_tap(done)

    def _step(self):
        need_timer = False

        if self._is_tapping:
            prev = self._stroke_t
            self._stroke_t += 0.045  # ~450ms for complete down-tap-lift stroke
            if prev < 0.5 <= self._stroke_t:
                self._flash = 1.0
                self._ripples.append(0.0)
            if self._stroke_t >= 1.0:
                self._stroke_t = 0.0
                self._is_tapping = False
            else:
                need_timer = True

        if self._flash > 0:
            self._flash = max(0.0, self._flash - 0.06)
            need_timer = True

        if self._ripples:
            self._ripples = [r + 0.05 for r in self._ripples if r < 1.0]
            if self._ripples:
                need_timer = True

        if not need_timer and not self._is_tapping:
            self._timer.stop()

        self.update()

    def _nozzle_y(self, top, bed_y):
        rest_y = bed_y - 34
        if not self._is_tapping:
            return rest_y
        # stroke_t: 0.0 (top) -> 0.5 (bed contact) -> 1.0 (top)
        d = 0.5 - 0.5 * math.cos(self._stroke_t * 2 * math.pi)
        return rest_y + d * 30

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bed_y = h - 18
        cx = w * 0.30

        # bed
        g = QtGui.QLinearGradient(0, bed_y, 0, bed_y + 10)
        g.setColorAt(0, QtGui.QColor(0, 229, 255, 160))
        g.setColorAt(1, QtGui.QColor(15, 23, 42, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(g))
        p.drawRect(QtCore.QRectF(12, bed_y, w * 0.6 - 12, 10))
        p.setPen(QtGui.QPen(C_CYAN, 2))
        p.drawLine(QtCore.QPointF(12, bed_y), QtCore.QPointF(w * 0.6, bed_y))

        # ripples at contact point
        for r in self._ripples:
            a = int(200 * (1 - r))
            p.setPen(QtGui.QPen(QtGui.QColor(52, 211, 153, a), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QtCore.QPointF(cx, bed_y), 6 + r * 50, 2 + r * 8)

        # toolhead
        ny = self._nozzle_y(0, bed_y)
        body = QtCore.QRectF(cx - 26, ny - 46, 52, 34)
        bg = QtGui.QLinearGradient(body.topLeft(), body.bottomLeft())
        bg.setColorAt(0, QtGui.QColor("#334155"))
        bg.setColorAt(1, QtGui.QColor("#1E293B"))
        p.setBrush(QtGui.QBrush(bg))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 120), 1.2))
        p.drawRoundedRect(body, 6, 6)
        # load-cell strip on toolhead, glows on contact
        lc = QtGui.QColor(52, 211, 153, int(80 + 175 * self._flash))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(lc)
        p.drawRoundedRect(QtCore.QRectF(cx - 18, ny - 40, 36, 5), 2, 2)
        # heater block + nozzle
        p.setBrush(QtGui.QColor("#64748B"))
        p.drawRect(QtCore.QRectF(cx - 12, ny - 12, 24, 8))
        noz = QtGui.QPolygonF([QtCore.QPointF(cx - 7, ny - 4), QtCore.QPointF(cx + 7, ny - 4), QtCore.QPointF(cx, ny + 4)])
        p.setBrush(QtGui.QColor("#D4A017"))
        p.drawPolygon(noz)
        if self._flash > 0:
            p.setBrush(QtGui.QColor(52, 211, 153, int(160 * self._flash)))
            p.drawEllipse(QtCore.QPointF(cx, bed_y), 10 * self._flash + 3, 3)

        # counter
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(20)
        p.setFont(f)
        p.setPen(QtGui.QColor("#FFFFFF"))
        tr = QtCore.QRectF(w * 0.62, 6, w * 0.38 - 8, h * 0.55)
        p.drawText(tr, Qt.AlignmentFlag.AlignCenter, f"{self._done}/{self._total}")
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(C_SLATE)
        p.drawText(QtCore.QRectF(w * 0.62, h * 0.55, w * 0.38 - 8, 16), Qt.AlignmentFlag.AlignCenter,
                   "PROBING..." if self._is_tapping else ("SAMPLES" if self._done else "READY"))
        p.end()


class AccuracyChart(QtWidgets.QWidget):
    """Plots each probe Z sample with average line and ±1σ band."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self._samples = []
        self._total = 10

    def reset(self, total: int):
        self._samples = []
        self._total = max(1, total)
        self.update()

    def add(self, z: float):
        self._samples.append(z)
        self.update()

    def set_samples(self, zs):
        self._samples = list(zs)
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = QtCore.QRectF(46, 10, self.width() - 56, self.height() - 30)

        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 90), 1))
        p.setBrush(QtGui.QColor(15, 23, 42, 200))
        p.drawRoundedRect(r.adjusted(-6, -6, 6, 6), 8, 8)

        f = p.font()
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)

        zs = self._samples
        if not zs:
            p.setPen(C_SLATE)
            f.setPointSizeF(10)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Samples will plot here")
            p.end()
            return

        avg = sum(zs) / len(zs)
        sd = statistics.pstdev(zs) if len(zs) > 1 else 0.0
        lo, hi = min(zs), max(zs)
        pad = max((hi - lo) * 0.25, 0.002)
        y0, y1 = lo - pad, hi + pad

        def ymap(z):
            return r.bottom() - (z - y0) / (y1 - y0) * r.height()

        def xmap(i):
            n = max(self._total, len(zs))
            return r.left() + (r.width() * (i + 0.5) / n)

        # ±1σ band
        if sd > 0:
            band = QtCore.QRectF(r.left(), ymap(avg + sd), r.width(), ymap(avg - sd) - ymap(avg + sd))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 229, 255, 28))
            p.drawRect(band.intersected(r))

        # gridlines + labels
        for k in range(5):
            z = y0 + (y1 - y0) * k / 4
            y = ymap(z)
            p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 35), 1))
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))
            p.setPen(C_SLATE)
            p.drawText(QtCore.QRectF(0, y - 7, 42, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{z:.3f}")

        # average line
        p.setPen(QtGui.QPen(C_CYAN, 1.3, Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(r.left(), ymap(avg)), QtCore.QPointF(r.right(), ymap(avg)))

        # connecting line
        path = QtGui.QPainterPath()
        for i, z in enumerate(zs):
            pt = QtCore.QPointF(xmap(i), ymap(z))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QtGui.QPen(QtGui.QColor(125, 211, 252, 150), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # points coloured by distance from average
        for i, z in enumerate(zs):
            dev = abs(z - avg)
            col = C_GREEN if sd == 0 or dev <= sd else (C_AMBER if dev <= 2 * sd else C_RED)
            pt = QtCore.QPointF(xmap(i), ymap(z))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(col.red(), col.green(), col.blue(), 60))
            p.drawEllipse(pt, 7, 7)
            p.setBrush(col)
            p.drawEllipse(pt, 3.5, 3.5)

        # x labels
        p.setPen(C_SLATE)
        n = max(self._total, len(zs))
        step = 1 if n <= 12 else max(1, n // 10)
        for i in range(0, n, step):
            p.drawText(QtCore.QRectF(xmap(i) - 12, r.bottom() + 6, 24, 12), Qt.AlignmentFlag.AlignCenter, str(i + 1))
        p.setPen(C_CYAN)
        p.drawText(QtCore.QRectF(r.right() - 120, r.top() + 2, 116, 12), Qt.AlignmentFlag.AlignRight,
                   f"avg {avg:.4f}  \u03C3 {sd:.4f}")
        p.end()



_BTN_PRIMARY = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 7px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 32px;
    padding: 2px 14px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #38BDF8);
    border-color: #FFFFFF;
}
QPushButton:pressed { background: #0284C7; }
QPushButton:disabled {
    background: rgba(30, 41, 59, 0.6);
    border-color: rgba(255, 255, 255, 0.1);
    color: #64748B;
}
"""

_BTN_GHOST = """
QPushButton {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 6px;
    color: #CBD5E1;
    font-size: 11px;
    font-weight: 700;
    min-height: 26px;
    padding: 2px 10px;
}
QPushButton:hover {
    background: rgba(51, 65, 85, 0.9);
    border-color: rgba(255, 255, 255, 0.35);
    color: #FFFFFF;
}
QPushButton:pressed { background: #0284C7; color: #FFFFFF; }
QPushButton:disabled { color: #475569; }
"""

_LBL_HDR = "color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;"


class ProbeAccuracyScreen(QtWidgets.QFrame):
    """Full-screen in-window Probe Accuracy test with live tap animation & chart."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._samples_count = 10
        self._is_running = False
        self._samples_collected = []
        self._last_gcode_index = 0

        self.setObjectName("ProbeAccuracyScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Main Card container
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet("""
            QFrame#DialogCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141C2E, stop:1 #0B0F19);
                border: 1px solid rgba(0, 229, 255, 120);
                border-radius: 14px;
            }
            QLabel { border: none; background: transparent; }
        """)
        outer.addWidget(self.card)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setSpacing(_s(8, scale))

        # --- Header ---
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(_s(8, scale))

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.icon_label)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)

        self.title_lbl = QtWidgets.QLabel("PROBE ACCURACY TEST")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        title_col.addWidget(self.title_lbl)

        header_layout.addLayout(title_col, 1)

        # Verdict / rating badge
        self.verdict_badge = QtWidgets.QLabel("READY TO TEST")
        self.verdict_badge.setStyleSheet("""
            color: #7DD3FC;
            font-size: 10px;
            font-weight: 800;
            background: rgba(0, 229, 255, 0.12);
            border: 1px solid rgba(0, 229, 255, 0.4);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.verdict_badge)

        self.close_x = QtWidgets.QPushButton("\u2715")
        self.close_x.setObjectName("DialogCloseX")
        self.close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_x.setFixedSize(26, 26)
        self.close_x.setStyleSheet("""
            QPushButton#DialogCloseX {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 13px;
                color: #94A3B8;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#DialogCloseX:hover {
                background: rgba(239, 68, 68, 0.3);
                border-color: #EF4444;
                color: #FFFFFF;
            }
        """)
        self.close_x.clicked.connect(self.reject)
        header_layout.addWidget(self.close_x)

        card_layout.addLayout(header_layout)

        # --- Body: Left (Tap Animation + Live Chart) | Right (Controls + Stats) ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # Left Column
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(_s(6, scale))

        # Animation box
        self.tap_anim = ProbeTapAnimation()
        left_col.addWidget(self.tap_anim, 2)

        # Live chart
        self.chart = AccuracyChart()
        left_col.addWidget(self.chart, 3)

        body.addLayout(left_col, 3)

        # Right Column
        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(8, scale))

        # Sample Count Selector
        lbl_samples = QtWidgets.QLabel("SAMPLE COUNT")
        lbl_samples.setStyleSheet(_LBL_HDR)
        side.addWidget(lbl_samples)

        sample_btn_layout = QtWidgets.QHBoxLayout()
        sample_btn_layout.setSpacing(4)
        self.sample_btns = {}
        for count in (5, 10, 20):
            btn = QtWidgets.QPushButton(f"{count}")
            btn.setCheckable(True)
            btn.setChecked(count == self._samples_count)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 41, 59, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 6px;
                    color: #94A3B8;
                    font-size: 12px;
                    font-weight: 800;
                    padding: 4px 10px;
                    min-height: 24px;
                }
                QPushButton:hover { border-color: #00E5FF; color: #FFFFFF; }
                QPushButton:checked {
                    background: rgba(0, 229, 255, 0.2);
                    border: 1.5px solid #00E5FF;
                    color: #00E5FF;
                }
            """)
            btn.clicked.connect(lambda _=False, c=count: self._set_sample_count(c))
            sample_btn_layout.addWidget(btn)
            self.sample_btns[count] = btn
        side.addLayout(sample_btn_layout)

        # Statistics Card
        stats_box = QtWidgets.QFrame()
        stats_box.setObjectName("StatsBox")
        stats_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        stats_box.setStyleSheet("""
            QFrame#StatsBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        sg = QtWidgets.QGridLayout(stats_box)
        sg.setContentsMargins(10, 8, 10, 8)
        sg.setHorizontalSpacing(10)
        sg.setVerticalSpacing(4)

        self.stat_labels = {}
        fields = [
            ("STD DEV", "std", "#34D399"),
            ("RANGE", "range", "#7DD3FC"),
            ("AVERAGE", "avg", "#FBBF24"),
            ("MEDIAN", "median", "#CBD5E1"),
            ("MIN", "min", "#60A5FA"),
            ("MAX", "max", "#F87171"),
        ]
        for idx, (label_txt, key, colr) in enumerate(fields):
            row = idx // 2
            col = (idx % 2) * 2
            hdr = QtWidgets.QLabel(label_txt)
            hdr.setStyleSheet(_LBL_HDR)
            val = QtWidgets.QLabel("---")
            val.setStyleSheet(f"color: {colr}; font-size: 13px; font-weight: 900; font-family: 'Consolas', monospace;")
            sg.addWidget(hdr, row * 2, col)
            sg.addWidget(val, row * 2 + 1, col)
            self.stat_labels[key] = val

        side.addWidget(stats_box)

        # Action Buttons
        self.start_btn = QtWidgets.QPushButton("\u25B6  Start Accuracy Test")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(_BTN_PRIMARY)
        self.start_btn.clicked.connect(self._on_start_test)
        side.addWidget(self.start_btn)

        side.addStretch(1)

        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side)
        side_widget.setMinimumWidth(190)
        side_widget.setMaximumWidth(280)
        body.addWidget(side_widget, 2)

        card_layout.addLayout(body, 1)

        # --- Bottom Status Bar ---
        bottom_row = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Ready. Tap Start Accuracy Test to probe bed repeatability.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bottom_row.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(self.close_btn)

        card_layout.addLayout(bottom_row)

        # Polling timer for real-time sample capture from Klipper
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(300)
        self._poll_timer.timeout.connect(self._poll_samples)

        self.apply_scale(scale)

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _set_sample_count(self, count: int):
        if self._is_running:
            return
        self._samples_count = count
        for c, btn in self.sample_btns.items():
            btn.setChecked(c == count)
        self.chart.reset(count)

    def _set_busy(self, running: bool):
        self._is_running = running
        self.start_btn.setEnabled(not running)
        for btn in self.sample_btns.values():
            btn.setEnabled(not running)
        if running:
            self.start_btn.setText("Probing Accuracy...")
            self.verdict_badge.setText("TEST IN PROGRESS")
            self.verdict_badge.setStyleSheet("""
                color: #00E5FF; font-size: 10px; font-weight: 800;
                background: rgba(0, 229, 255, 0.15);
                border: 1px solid rgba(0, 229, 255, 0.5); border-radius: 4px; padding: 2px 8px;
            """)
        else:
            self.start_btn.setText("\u25B6  Start Accuracy Test")

    def _on_start_test(self):
        if self._is_running:
            return

        import time
        self._test_start_time = time.time()
        self._samples_collected = []
        self.chart.reset(self._samples_count)
        self.tap_anim.start(self._samples_count)
        self._set_busy(True)
        self.status_lbl.setText(f"Starting PROBE_ACCURACY ({self._samples_count} samples)...")

        for lbl in self.stat_labels.values():
            lbl.setText("---")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._start_simulation()
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _check_home():
            homed = ""
            if mr and hasattr(mr, "homed_axes") and mr.homed_axes:
                homed = mr.homed_axes
            try:
                url = f"http://{host}/printer/objects/query?toolhead=homed_axes"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        homed = data.get("result", {}).get("status", {}).get("toolhead", {}).get("homed_axes", homed)
            except Exception:
                pass

            is_homed = all(a in str(homed).lower() for a in "xyz")

            def _proceed():
                _mr = self._get_moonraker() if hasattr(self, "_get_moonraker") else None
                _tare = _mr.tare_gcode() if (_mr and hasattr(_mr, "tare_gcode")) else ""
                if not is_homed:
                    cmd = f"G28\n{_tare}PROBE_ACCURACY SAMPLES={self._samples_count}"
                    self.start_btn.setText("Homing (G28)...")
                    self.verdict_badge.setText("HOMING (G28)")
                    self.status_lbl.setText(f"Axes not homed. Homing (G28) first, then testing accuracy...")
                else:
                    cmd = f"{_tare}PROBE_ACCURACY SAMPLES={self._samples_count}"
                    self.start_btn.setText("Probing Accuracy...")
                    self.verdict_badge.setText("TEST IN PROGRESS")
                    self.status_lbl.setText(f"Running PROBE_ACCURACY ({self._samples_count} samples)...")

                self.verdict_badge.setStyleSheet("""
                    color: #00E5FF; font-size: 10px; font-weight: 800;
                    background: rgba(0, 229, 255, 0.15);
                    border: 1px solid rgba(0, 229, 255, 0.5); border-radius: 4px; padding: 2px 8px;
                """)
                self._poll_timer.start()
                mr.send_gcode(cmd, on_done=self._on_test_done, timeout=240.0)

            if hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_proceed)
            else:
                QtCore.QTimer.singleShot(0, _proceed)

        threading.Thread(target=_check_home, daemon=True).start()

    def _poll_samples(self):
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            return
        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _bg():
            found_samples = []
            final_res = None
            try:
                url = f"http://{host}/server/gcode_store?count=100"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        store = data.get("result", {}).get("gcode_store", [])

                        # Find start index of current test run
                        start_time = getattr(self, "_test_start_time", 0.0)
                        start_idx = 0
                        for i, item in enumerate(store):
                            msg = item.get("message", "")
                            item_t = float(item.get("time", 0.0))
                            if "PROBE_ACCURACY" in msg and item_t >= start_time - 5.0:
                                start_idx = i

                        for item in store[start_idx:]:
                            msg = item.get("message", "")
                            m = RE_SAMPLE.search(msg)
                            if m:
                                z = float(m.group(1))
                                found_samples.append(z)
                            m_res = RE_RESULT.search(msg)
                            if m_res:
                                final_res = {
                                    "max": float(m_res.group(1)),
                                    "min": float(m_res.group(2)),
                                    "range": float(m_res.group(3)),
                                    "avg": float(m_res.group(4)),
                                    "median": float(m_res.group(5)),
                                    "std": float(m_res.group(6)),
                                }
            except Exception:
                pass

            def _update():
                if len(found_samples) > len(self._samples_collected):
                    new_count = len(found_samples)
                    self._samples_collected = found_samples
                    self.chart.set_samples(found_samples)
                    self.tap_anim.trigger_tap(new_count)
                    self.start_btn.setText("Probing Accuracy...")
                    self.verdict_badge.setText("TEST IN PROGRESS")
                    self.status_lbl.setText(f"Collected sample {new_count} of {self._samples_count} (Z = {found_samples[-1]:+.4f} mm)...")
                if final_res:
                    self._apply_results(final_res)

            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_update)
            else:
                QtCore.QTimer.singleShot(0, _update)

        threading.Thread(target=_bg, daemon=True).start()

    def _on_test_done(self, ok: bool):
        self._poll_timer.stop()
        self.tap_anim.stop()
        self._set_busy(False)
        if not ok:
            self.status_lbl.setText("Probe accuracy test failed or cancelled.")
            self.verdict_badge.setText("TEST FAILED")
            self.verdict_badge.setStyleSheet("""
                color: #EF4444; font-size: 10px; font-weight: 800;
                background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.5);
                border-radius: 4px; padding: 2px 8px;
            """)
            return

        # Ensure counter reflects 100% completion
        self.tap_anim._done = self._samples_count
        self.tap_anim.update()

        # Run one final poll to ensure any lingering sample or results message is processed
        self._poll_samples()

        if self._samples_collected:
            zs = self._samples_collected
            calc_res = {
                "max": max(zs),
                "min": min(zs),
                "range": max(zs) - min(zs),
                "avg": sum(zs) / len(zs),
                "median": statistics.median(zs),
                "std": statistics.pstdev(zs) if len(zs) > 1 else 0.0,
            }
            self._apply_results(calc_res)

    def _apply_results(self, res: dict):
        # Guarantee counter shows full count when results arrive
        self.tap_anim._done = self._samples_count
        self.tap_anim.update()
        self.stat_labels["std"].setText(f"{res['std']:.4f} mm")
        self.stat_labels["range"].setText(f"{res['range']:.4f} mm")
        self.stat_labels["avg"].setText(f"{res['avg']:.4f} mm")
        self.stat_labels["median"].setText(f"{res['median']:.4f} mm")
        self.stat_labels["min"].setText(f"{res['min']:.4f} mm")
        self.stat_labels["max"].setText(f"{res['max']:.4f} mm")

        v_text, v_colr = verdict(res["std"])
        self.verdict_badge.setText(f"{v_text} (\u03C3 = {res['std']:.4f} mm)")
        self.verdict_badge.setStyleSheet(f"""
            color: {v_colr.name()}; font-size: 10px; font-weight: 800;
            background: rgba({v_colr.red()}, {v_colr.green()}, {v_colr.blue()}, 0.15);
            border: 1px solid {v_colr.name()}; border-radius: 4px; padding: 2px 8px;
        """)
        self.status_lbl.setText(f"\u2713 Probe Accuracy complete: Range = {res['range']:.4f} mm, StdDev = {res['std']:.4f} mm")

    def _start_simulation(self):
        """Simulate realistic probe accuracy samples when running offline."""
        self._set_busy(True)
        self.tap_anim.start(self._samples_count)
        self.chart.reset(self._samples_count)
        base_z = -0.1500
        step_ms = 450
        samples = []

        def _step(idx):
            if not self._is_running:
                return
            noise = random.gauss(0, 0.0016)
            z = round(base_z + noise, 4)
            samples.append(z)
            self._samples_collected = samples
            self.chart.add(z)
            self.tap_anim.contact(len(samples))
            self.status_lbl.setText(f"Sample {len(samples)}/{self._samples_count} (Simulated)...")

            if len(samples) < self._samples_count:
                QtCore.QTimer.singleShot(step_ms, lambda: _step(idx + 1))
            else:
                self.tap_anim.stop()
                self._set_busy(False)
                res = {
                    "max": max(samples),
                    "min": min(samples),
                    "range": max(samples) - min(samples),
                    "avg": sum(samples) / len(samples),
                    "median": statistics.median(samples),
                    "std": statistics.pstdev(samples),
                }
                self._apply_results(res)

        QtCore.QTimer.singleShot(step_ms, lambda: _step(1))

    def _cleanup(self):
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        self.tap_anim.stop()

    def accept(self):
        self._cleanup()
        self.closed.emit()

    def reject(self):
        self._cleanup()
        self.closed.emit()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("probe", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
