"""PID Heater Autotune screen.

Interactive calibration screen to run PID_CALIBRATE for extruder or heated bed,
plot live thermal oscillation curves, display calculated Kp / Ki / Kd gains,
and permanently save the new PID parameters to printer.cfg via SAVE_CONFIG.
"""

import json
import re
import threading
import time
import urllib.request
from typing import Optional, List, Tuple

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


C_CYAN = QtGui.QColor("#00E5FF")
C_GREEN = QtGui.QColor("#34D399")
C_AMBER = QtGui.QColor("#FBBF24")
C_RED = QtGui.QColor("#EF4444")
C_SLATE = QtGui.QColor("#94A3B8")


class PidThermalChart(QtWidgets.QWidget):
    """Real-time thermal oscillation chart for PID autotuning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self._history: List[Tuple[float, float]] = []  # (rel_time_sec, temp_c)
        self._target_temp: float = 210.0
        self._start_time: float = time.time()
        self._max_points: int = 400

    def reset(self, target_temp: float):
        self._target_temp = float(target_temp)
        self._history = []
        self._start_time = time.time()
        self.update()

    def add_sample(self, temp: float):
        t = time.time() - self._start_time
        self._history.append((t, float(temp)))
        if len(self._history) > self._max_points:
            self._history.pop(0)
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = QtCore.QRectF(44, 10, w - 54, h - 26)

        # Background box
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 60), 1))
        p.setBrush(QtGui.QColor(15, 23, 42, 220))
        p.drawRoundedRect(r, 8, 8)

        f = p.font()
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)

        if not self._history:
            p.setPen(C_SLATE)
            f.setPointSizeF(10)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Thermal autotune curve will plot here")
            p.end()
            return

        temps = [pt[1] for pt in self._history]
        min_t = min(temps + [self._target_temp - 5.0])
        max_t = max(temps + [self._target_temp + 5.0])
        pad = max((max_t - min_t) * 0.15, 4.0)
        y0, y1 = min_t - pad, max_t + pad

        def ymap(temp: float) -> float:
            ratio = (temp - y0) / max(1.0, (y1 - y0))
            return r.bottom() - ratio * r.height()

        t_min = self._history[0][0]
        t_max = max(self._history[-1][0], t_min + 10.0)

        def xmap(t: float) -> float:
            ratio = (t - t_min) / max(1.0, (t_max - t_min))
            return r.left() + ratio * r.width()

        # Grid lines & temperature labels
        for k in range(5):
            t_val = y0 + (y1 - y0) * k / 4.0
            y = ymap(t_val)
            p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 30), 1))
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))
            p.setPen(C_SLATE)
            p.drawText(QtCore.QRectF(0, y - 6, 40, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{t_val:.0f}°")

        # Target temperature line (amber dashed)
        target_y = ymap(self._target_temp)
        p.setPen(QtGui.QPen(C_AMBER, 1.3, Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(r.left(), target_y), QtCore.QPointF(r.right(), target_y))
        p.setPen(C_AMBER)
        p.drawText(QtCore.QRectF(r.right() - 85, target_y - 14, 80, 12), Qt.AlignmentFlag.AlignRight, f"Target {self._target_temp:.0f}°C")

        # Temperature curve path
        path = QtGui.QPainterPath()
        for idx, (t, val) in enumerate(self._history):
            pt = QtCore.QPointF(xmap(t), ymap(val))
            if idx == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)

        # Gradient area under curve
        fill_path = QtGui.QPainterPath(path)
        fill_path.lineTo(xmap(self._history[-1][0]), r.bottom())
        fill_path.lineTo(xmap(self._history[0][0]), r.bottom())
        fill_path.closeSubpath()

        g = QtGui.QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, QtGui.QColor(0, 229, 255, 60))
        g.setColorAt(1, QtGui.QColor(0, 229, 255, 5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(g))
        p.drawPath(fill_path)

        # Outline
        p.setPen(QtGui.QPen(C_CYAN, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Latest dot
        latest_pt = QtCore.QPointF(xmap(self._history[-1][0]), ymap(self._history[-1][1]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 229, 255, 80))
        p.drawEllipse(latest_pt, 7, 7)
        p.setBrush(C_CYAN)
        p.drawEllipse(latest_pt, 3.5, 3.5)

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

_BTN_SAVE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);
    border: 1px solid #34D399;
    border-radius: 7px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 32px;
    padding: 2px 14px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #10B981);
    border-color: #6EE7B7;
}
QPushButton:pressed { background: #047857; }
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


class PidTuneScreen(QtWidgets.QFrame):
    """Full-screen in-window PID autotune screen with live temperature chart, gains, and save."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._heater = "extruder"  # "extruder" or "heater_bed"
        self._target_temp = 210.0
        self._fan_speed_pct = 45
        self._is_tuning = False
        self._last_gcode_time = time.time()
        self._stored_pid = {"Kp": None, "Ki": None, "Kd": None}
        self._new_pid = {"Kp": None, "Ki": None, "Kd": None}

        self.setObjectName("PidTuneScreen")
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
        self.title_lbl = QtWidgets.QLabel("PID HEATER CALIBRATION")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        sub_lbl = QtWidgets.QLabel("Automated PID autotune cycles to eliminate temperature fluctuations")
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 600;")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(sub_lbl)
        header_layout.addLayout(title_col, 1)

        self.heater_badge = QtWidgets.QLabel("[EXTRUDER]")
        self.heater_badge.setStyleSheet("""
            color: #00E5FF;
            font-size: 10px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
            background: rgba(0, 229, 255, 0.15);
            border: 1px solid rgba(0, 229, 255, 0.4);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.heater_badge)

        self.close_x = QtWidgets.QPushButton("✕")
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

        # --- Body: Left (Thermal Chart & Live Temperature) | Right (Controls & Results) ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # Left Column
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(_s(6, scale))

        self.chart = PidThermalChart()
        left_col.addWidget(self.chart, 1)

        # Live Temperature & Cycle Readout Card
        temp_box = QtWidgets.QFrame()
        temp_box.setObjectName("TempBox")
        temp_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        temp_box.setStyleSheet("""
            QFrame#TempBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.30);
                border-radius: 8px;
            }
        """)
        tb_layout = QtWidgets.QHBoxLayout(temp_box)
        tb_layout.setContentsMargins(12, 6, 12, 6)

        tb_left = QtWidgets.QVBoxLayout()
        tb_left.setSpacing(1)
        tb_title = QtWidgets.QLabel("CURRENT TEMPERATURE")
        tb_title.setStyleSheet(_LBL_HDR)
        self.live_temp_lbl = QtWidgets.QLabel("24.0°C / 210°C")
        self.live_temp_lbl.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: 900; font-family: 'Consolas', monospace;")
        tb_left.addWidget(tb_title)
        tb_left.addWidget(self.live_temp_lbl)
        tb_layout.addLayout(tb_left, 1)

        self.status_pill = QtWidgets.QLabel("IDLE")
        self.status_pill.setStyleSheet("""
            color: #94A3B8;
            background: rgba(148, 163, 184, 0.15);
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        tb_layout.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        left_col.addWidget(temp_box)
        body.addLayout(left_col, 3)

        # Right Column: Controls & PID Gains
        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(6, scale))

        # 1. Heater Selector
        lbl_h = QtWidgets.QLabel("SELECT HEATER")
        lbl_h.setStyleSheet(_LBL_HDR)
        side.addWidget(lbl_h)

        h_row = QtWidgets.QHBoxLayout()
        h_row.setSpacing(6)
        self.btn_extruder = QtWidgets.QPushButton("♨ Nozzle (Extruder)")
        self.btn_extruder.setCheckable(True)
        self.btn_extruder.setChecked(True)
        self.btn_extruder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_extruder.clicked.connect(lambda: self._set_heater("extruder"))

        self.btn_bed = QtWidgets.QPushButton("🛏 Heated Bed")
        self.btn_bed.setCheckable(True)
        self.btn_bed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bed.clicked.connect(lambda: self._set_heater("heater_bed"))

        for b in (self.btn_extruder, self.btn_bed):
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 41, 59, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 6px;
                    color: #94A3B8;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 4px 8px;
                    min-height: 24px;
                }
                QPushButton:hover { border-color: #00E5FF; color: #FFFFFF; }
                QPushButton:checked {
                    background: rgba(0, 229, 255, 0.2);
                    border: 1.5px solid #00E5FF;
                    color: #00E5FF;
                }
            """)
            h_row.addWidget(b, 1)
        side.addLayout(h_row)

        # 2. Target Temperature Selector & Fine Adjust
        lbl_tgt = QtWidgets.QLabel("TARGET TEMPERATURE")
        lbl_tgt.setStyleSheet(_LBL_HDR)
        side.addWidget(lbl_tgt)

        tgt_row = QtWidgets.QHBoxLayout()
        tgt_row.setSpacing(4)
        self.btn_minus5 = QtWidgets.QPushButton("-5°")
        self.btn_minus5.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus5.setStyleSheet(_BTN_GHOST)
        self.btn_minus5.clicked.connect(lambda: self._adjust_target(-5))
        tgt_row.addWidget(self.btn_minus5)

        self.target_display = QtWidgets.QLabel("210°C")
        self.target_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_display.setStyleSheet("color: #00E5FF; font-size: 16px; font-weight: 900; font-family: 'Consolas', monospace;")
        tgt_row.addWidget(self.target_display, 1)

        self.btn_plus5 = QtWidgets.QPushButton("+5°")
        self.btn_plus5.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus5.setStyleSheet(_BTN_GHOST)
        self.btn_plus5.clicked.connect(lambda: self._adjust_target(+5))
        tgt_row.addWidget(self.btn_plus5)
        side.addLayout(tgt_row)

        # Preset target buttons
        self.preset_row = QtWidgets.QHBoxLayout()
        self.preset_row.setSpacing(4)
        self.preset_btns = []
        side.addLayout(self.preset_row)
        self._update_presets()

        # 3. PID Gains Card (Stored vs New Calculated)
        pid_box = QtWidgets.QFrame()
        pid_box.setObjectName("PidGainsBox")
        pid_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pid_box.setStyleSheet("""
            QFrame#PidGainsBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        pg_lay = QtWidgets.QVBoxLayout(pid_box)
        pg_lay.setContentsMargins(10, 6, 10, 6)
        pg_lay.setSpacing(4)

        pg_hdr = QtWidgets.QHBoxLayout()
        lbl_pid_title = QtWidgets.QLabel("PID GAINS")
        lbl_pid_title.setStyleSheet(_LBL_HDR)
        pg_hdr.addWidget(lbl_pid_title)
        pg_hdr.addStretch(1)
        self.gain_status_lbl = QtWidgets.QLabel("STORED")
        self.gain_status_lbl.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 800;")
        pg_hdr.addWidget(self.gain_status_lbl)
        pg_lay.addLayout(pg_hdr)

        grid_gains = QtWidgets.QGridLayout()
        grid_gains.setHorizontalSpacing(8)
        grid_gains.setVerticalSpacing(2)

        self.lbl_kp = QtWidgets.QLabel("Kp: --")
        self.lbl_ki = QtWidgets.QLabel("Ki: --")
        self.lbl_kd = QtWidgets.QLabel("Kd: --")
        for idx, (lbl, col) in enumerate([(self.lbl_kp, "#00E5FF"), (self.lbl_ki, "#34D399"), (self.lbl_kd, "#FBBF24")]):
            lbl.setStyleSheet(f"color: {col}; font-size: 13px; font-weight: 900; font-family: 'Consolas', monospace;")
            grid_gains.addWidget(lbl, 0, idx)

        pg_lay.addLayout(grid_gains)
        side.addWidget(pid_box)

        # 4. Action Buttons: Run PID & Save Results
        self.btn_run = QtWidgets.QPushButton("▶  Start PID Autotune")
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setStyleSheet(_BTN_PRIMARY)
        self.btn_run.clicked.connect(self._on_run_clicked)
        side.addWidget(self.btn_run)

        self.btn_save = QtWidgets.QPushButton("💾  Save Results (SAVE_CONFIG)")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet(_BTN_SAVE)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._on_save_clicked)
        side.addWidget(self.btn_save)

        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side)
        side_widget.setMinimumWidth(220)
        side_widget.setMaximumWidth(280)
        body.addWidget(side_widget, 2)

        card_layout.addLayout(body, 1)

        # --- Bottom Status Bar ---
        bot = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Select heater and target temp, then tap Start PID Autotune.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bot.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bot.addWidget(self.close_btn)

        card_layout.addLayout(bot)

        # Polling timer for real-time temps & gcode store updates
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start()

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(50, self._load_stored_pid)

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _set_heater(self, heater: str):
        if self._is_tuning:
            return
        self._heater = heater
        self.btn_extruder.setChecked(heater == "extruder")
        self.btn_bed.setChecked(heater == "heater_bed")
        self.heater_badge.setText("[EXTRUDER]" if heater == "extruder" else "[HEATER_BED]")
        self._target_temp = 210.0 if heater == "extruder" else 60.0
        self.target_display.setText(f"{self._target_temp:.0f}°C")
        self._update_presets()
        self._load_stored_pid()
        self.chart.reset(self._target_temp)

    def _update_presets(self):
        while self.preset_row.count():
            item = self.preset_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.preset_btns = []

        presets = [200, 210, 220, 245] if self._heater == "extruder" else [55, 60, 70, 85]
        for val in presets:
            b = QtWidgets.QPushButton(f"{val}°")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_BTN_GHOST)
            b.clicked.connect(lambda _=False, v=val: self._set_target(v))
            self.preset_row.addWidget(b)
            self.preset_btns.append(b)

    def _set_target(self, val: float):
        if self._is_tuning:
            return
        self._target_temp = float(val)
        self.target_display.setText(f"{self._target_temp:.0f}°C")
        self.chart.reset(self._target_temp)

    def _adjust_target(self, delta: float):
        if self._is_tuning:
            return
        new_val = max(30.0, min(300.0, self._target_temp + delta))
        self._set_target(new_val)

    def _load_stored_pid(self):
        mr = self._get_moonraker()
        if not mr:
            return
        cfg = mr.config or {}
        sec = cfg.get(self._heater, {})
        kp = sec.get("pid_kp") or sec.get("pid_Kp")
        ki = sec.get("pid_ki") or sec.get("pid_Ki")
        kd = sec.get("pid_kd") or sec.get("pid_Kd")
        if kp and ki and kd:
            self._stored_pid = {"Kp": float(kp), "Ki": float(ki), "Kd": float(kd)}
            self.lbl_kp.setText(f"Kp: {float(kp):.3f}")
            self.lbl_ki.setText(f"Ki: {float(ki):.3f}")
            self.lbl_kd.setText(f"Kd: {float(kd):.3f}")
            self.gain_status_lbl.setText("STORED IN CONFIG")
            self.gain_status_lbl.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 800;")

    def _poll_status(self):
        mr = self._get_moonraker()
        if not mr:
            return

        # Update live temperature
        if self._heater == "extruder":
            c = mr.nozzle_temp
            t = self._target_temp if self._is_tuning else mr.nozzle_target
        else:
            c = mr.bed_temp
            t = self._target_temp if self._is_tuning else mr.bed_target

        self.live_temp_lbl.setText(f"{c:.1f}°C / {self._target_temp:.0f}°C")
        if self._is_tuning:
            self.chart.add_sample(c)

        if not self._is_tuning:
            return

        # Poll gcode store to capture tuning progress and final calculated gains
        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _bg():
            try:
                url = f"http://{host}/server/gcode_store?count=40"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.2) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        items = data.get("result", {}).get("gcode_store", [])
                        for it in items:
                            t_msg = float(it.get("time", 0.0))
                            if t_msg <= self._last_gcode_time:
                                continue
                            msg = it.get("message", "")
                            # Check cycle progress
                            m_cyc = re.search(r"cycle\s+(\d+)", msg, re.IGNORECASE)
                            if m_cyc:
                                c_num = m_cyc.group(1)
                                if hasattr(mr, "_dispatch_signal"):
                                    mr._dispatch_signal.emit(lambda: self._set_cycle_progress(c_num))
                            # Check final PID parameters
                            m_pid = re.search(r"pid_Kp=([\d\.]+)\s+pid_Ki=([\d\.]+)\s+pid_Kd=([\d\.]+)", msg, re.IGNORECASE)
                            if m_pid:
                                kp = float(m_pid.group(1))
                                ki = float(m_pid.group(2))
                                kd = float(m_pid.group(3))
                                if hasattr(mr, "_dispatch_signal"):
                                    mr._dispatch_signal.emit(lambda: self._on_pid_finished(kp, ki, kd))
                                return
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _set_cycle_progress(self, cycle_num: str):
        self.status_pill.setText(f"CYCLE {cycle_num}")
        self.status_pill.setStyleSheet("""
            color: #00E5FF;
            background: rgba(0, 229, 255, 0.20);
            border: 1px solid #00E5FF;
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        self.status_lbl.setText(f"Tuning {self._heater} around {self._target_temp:.0f}°C • Autotune cycle {cycle_num}...")

    def _on_run_clicked(self):
        if self._is_tuning:
            # Cancel tuning
            self._is_tuning = False
            self.btn_run.setText("▶  Start PID Autotune")
            self.btn_run.setStyleSheet(_BTN_PRIMARY)
            self.status_pill.setText("CANCELLED")
            self.status_pill.setStyleSheet("""
                color: #EF4444;
                background: rgba(239, 68, 68, 0.15);
                border: 1px solid #EF4444;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 800;
            """)
            self.status_lbl.setText("PID autotuning stopped.")
            mr = self._get_moonraker()
            if mr and mr.connected:
                mr.send_gcode(f"SET_HEATER_TEMPERATURE HEATER={self._heater} TARGET=0")
            return

        self._is_tuning = True
        self._last_gcode_time = time.time()
        self.chart.reset(self._target_temp)
        self.btn_run.setText("⏹  Cancel Autotune")
        self.btn_run.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.25);
                border: 1px solid #EF4444;
                border-radius: 7px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                min-height: 32px;
                padding: 2px 14px;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.45); }
        """)
        self.btn_save.setEnabled(False)
        self.status_pill.setText("HEATING")
        self.status_pill.setStyleSheet("""
            color: #F59E0B;
            background: rgba(245, 158, 11, 0.20);
            border: 1px solid #F59E0B;
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        self.status_lbl.setText(f"Starting PID_CALIBRATE HEATER={self._heater} TARGET={self._target_temp:.0f}...")

        mr = self._get_moonraker()
        cmd = f"PID_CALIBRATE HEATER={self._heater} TARGET={self._target_temp:.0f}"
        if mr and mr.connected:
            mr.send_gcode(cmd, timeout=300.0)
        else:
            # Simulation demo
            QtCore.QTimer.singleShot(3500, lambda: self._on_pid_finished(32.415, 5.120, 51.330))

    def _on_pid_finished(self, kp: float, ki: float, kd: float):
        self._is_tuning = False
        self._new_pid = {"Kp": kp, "Ki": ki, "Kd": kd}
        self.lbl_kp.setText(f"Kp: {kp:.3f}")
        self.lbl_ki.setText(f"Ki: {ki:.3f}")
        self.lbl_kd.setText(f"Kd: {kd:.3f}")

        self.gain_status_lbl.setText("NEW TUNED GAINS")
        self.gain_status_lbl.setStyleSheet("color: #34D399; font-size: 9px; font-weight: 900;")

        self.btn_run.setText("▶  Start PID Autotune")
        self.btn_run.setStyleSheet(_BTN_PRIMARY)
        self.btn_save.setEnabled(True)

        self.status_pill.setText("✓ COMPLETE")
        self.status_pill.setStyleSheet("""
            color: #34D399;
            background: rgba(16, 185, 129, 0.20);
            border: 1px solid #10B981;
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        self.status_lbl.setText(f"PID autotune complete! New gains: Kp={kp:.3f}, Ki={ki:.3f}, Kd={kd:.3f}. Tap Save Results.")

    def _on_save_clicked(self):
        self.btn_save.setEnabled(False)
        self.btn_save.setText("Saving to printer.cfg...")
        self.status_lbl.setText("Sending SAVE_CONFIG to write new PID gains to printer.cfg and restart firmware...")

        mr = self._get_moonraker()
        if mr and mr.connected:
            def _done(ok):
                self.btn_save.setText("✓ Saved & Restarted!")
                self.status_lbl.setText("New PID settings saved successfully to printer.cfg.")
                QtCore.QTimer.singleShot(2500, self.accept)
            mr.send_gcode("SAVE_CONFIG", on_done=_done, timeout=25.0)
        else:
            QtCore.QTimer.singleShot(1200, lambda: [
                self.btn_save.setText("✓ Saved (simulated)!"),
                QtCore.QTimer.singleShot(1500, self.accept)
            ])

    def accept(self):
        if hasattr(self, "_timer") and self._timer.isActive():
            self._timer.stop()
        self.closed.emit()

    def reject(self):
        if hasattr(self, "_timer") and self._timer.isActive():
            self._timer.stop()
        self.closed.emit()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("nozzle", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
