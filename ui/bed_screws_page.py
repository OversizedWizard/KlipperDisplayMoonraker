"""Bed Screws Adjust Screen.

Interactive bed levelling screen to visualize screw positions from printer config,
touch any screw point to safely move toolhead there, probe bed clearance,
and receive clear raise / lower guidance with green indicators for acceptable 1st layer deviance.
"""

import json
import math
import re
import threading
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


C_CYAN = QtGui.QColor("#00E5FF")
C_GREEN = QtGui.QColor("#34D399")
C_AMBER = QtGui.QColor("#FBBF24")
C_RED = QtGui.QColor("#EF4444")
C_SLATE = QtGui.QColor("#94A3B8")

# Acceptable 1st layer deviance for standard 3D printers
ACCEPTABLE_TOLERANCE_MM = 0.045


class BedScrewsCanvas(QtWidgets.QWidget):
    """Interactive top-down diagram of the print bed and its adjustment screws."""
    screw_clicked = Signal(int)  # 1-based screw index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 220)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self.bed_size = (235.0, 225.0)
        self.screws: List[Dict] = []
        self.selected_index: int = 1
        self.toolhead_pos = (117.5, 112.5)

    def set_screws(self, screws: List[Dict], bed_size: Tuple[float, float]):
        self.screws = screws
        self.bed_size = bed_size
        self.update()

    def set_selected(self, idx: int):
        self.selected_index = idx
        self.update()

    def set_toolhead(self, x: float, y: float):
        self.toolhead_pos = (float(x), float(y))
        self.update()

    def _bed_rect(self) -> QtCore.QRectF:
        w, h = self.width(), self.height()
        m = 24.0
        avail_w = w - m * 2
        avail_h = h - m * 2

        bx, by = self.bed_size
        scale = min(avail_w / max(1.0, bx), avail_h / max(1.0, by))
        rw = bx * scale
        rh = by * scale
        rx = (w - rw) / 2.0
        ry = (h - rh) / 2.0
        return QtCore.QRectF(rx, ry, rw, rh)

    def _coord_to_screen(self, x: float, y: float, r: QtCore.QRectF) -> QtCore.QPointF:
        bx, by = self.bed_size
        # Klipper coordinate: (0,0) is front-left, Y increases toward back
        sx = r.left() + (x / max(1.0, bx)) * r.width()
        sy = r.bottom() - (y / max(1.0, by)) * r.height()
        return QtCore.QPointF(sx, sy)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = self._bed_rect()

        # Build surface bed
        bg = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, QtGui.QColor("#1E293B"))
        bg.setColorAt(1, QtGui.QColor("#0F172A"))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 100), 1.5))
        p.setBrush(QtGui.QBrush(bg))
        p.drawRoundedRect(r, 10, 10)

        # Subtle grid on bed
        p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 25), 1))
        for gx in range(1, 4):
            x = r.left() + r.width() * gx / 4.0
            p.drawLine(QtCore.QPointF(x, r.top()), QtCore.QPointF(x, r.bottom()))
        for gy in range(1, 4):
            y = r.top() + r.height() * gy / 4.0
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))

        # Bed labels: Front / Back / Left / Right
        f = p.font()
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C_SLATE)
        p.drawText(QtCore.QRectF(r.left(), r.bottom() - 14, r.width(), 12), Qt.AlignmentFlag.AlignCenter, "FRONT (BED EDGE)")
        p.drawText(QtCore.QRectF(r.left(), r.top() + 4, r.width(), 12), Qt.AlignmentFlag.AlignCenter, "BACK")

        # Toolhead position marker (nozzle diamond)
        tx, ty = self.toolhead_pos
        t_pt = self._coord_to_screen(tx, ty, r)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 140), 1))
        p.drawLine(QtCore.QPointF(t_pt.x() - 6, t_pt.y()), QtCore.QPointF(t_pt.x() + 6, t_pt.y()))
        p.drawLine(QtCore.QPointF(t_pt.x(), t_pt.y() - 6), QtCore.QPointF(t_pt.x(), t_pt.y() + 6))
        p.setBrush(QtGui.QColor(0, 229, 255, 200))
        p.drawEllipse(t_pt, 3.5, 3.5)

        # Draw Screws
        for sc in self.screws:
            idx = sc.get("index", 1)
            x, y = sc.get("x", 0.0), sc.get("y", 0.0)
            pt = self._coord_to_screen(x, y, r)
            is_sel = (idx == self.selected_index)
            is_base = sc.get("is_base", False)
            diff = sc.get("diff", None)

            # Determine screw color based on tolerance
            if is_base:
                col = C_GREEN
                badge_txt = "BASE"
            elif diff is not None:
                if abs(diff) <= ACCEPTABLE_TOLERANCE_MM:
                    col = C_GREEN
                    badge_txt = f"✓ {diff:+.2f}"
                elif diff > ACCEPTABLE_TOLERANCE_MM:
                    col = C_RED
                    badge_txt = f"▼ {diff:+.2f}"
                else:
                    col = C_AMBER
                    badge_txt = f"▲ {diff:+.2f}"
            else:
                col = QtGui.QColor("#38BDF8")
                badge_txt = f"#{idx}"

            # Selection glow
            if is_sel:
                p.setPen(QtGui.QPen(C_CYAN, 2.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(pt, 24, 24)

            # Screw circle
            p.setPen(QtGui.QPen(col, 2.0))
            p.setBrush(QtGui.QColor(col.red(), col.green(), col.blue(), 50))
            p.drawEllipse(pt, 16, 16)

            # Inner dot
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(pt, 4, 4)

            # Screw name & badge text
            f.setPointSizeF(8.0)
            p.setFont(f)
            p.setPen(QtGui.QColor("#FFFFFF"))
            p.drawText(QtCore.QRectF(pt.x() - 40, pt.y() + 18, 80, 14), Qt.AlignmentFlag.AlignCenter, badge_txt)

            name = sc.get("name", f"Screw {idx}")
            f.setPointSizeF(7.0)
            p.setFont(f)
            p.setPen(C_SLATE)
            p.drawText(QtCore.QRectF(pt.x() - 50, pt.y() - 28, 100, 12), Qt.AlignmentFlag.AlignCenter, name.title())

        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        click_pos = event.position()
        r = self._bed_rect()

        closest_idx = None
        closest_dist = 999999.0
        for sc in self.screws:
            pt = self._coord_to_screen(sc.get("x", 0.0), sc.get("y", 0.0), r)
            dx = click_pos.x() - pt.x()
            dy = click_pos.y() - pt.y()
            dist = math.hypot(dx, dy)
            if dist < 40.0 and dist < closest_dist:
                closest_dist = dist
                closest_idx = sc.get("index", 1)

        if closest_idx is not None:
            self.screw_clicked.emit(closest_idx)
            self.set_selected(closest_idx)


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


class BedScrewsScreen(QtWidgets.QFrame):
    """Full-screen interactive Bed Screws Adjust calibration screen."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._busy = False
        self._screws: List[Dict] = []
        self._selected_screw_idx = 1
        self._base_screw_idx = 1
        self._base_z: Optional[float] = None
        self._bed_size = (235.0, 225.0)

        self.setObjectName("BedScrewsScreen")
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
        self.title_lbl = QtWidgets.QLabel("BED SCREWS ADJUST")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        sub_lbl = QtWidgets.QLabel("Touch any screw position to move toolhead, probe clearance, and level bed")
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 600;")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(sub_lbl)
        header_layout.addLayout(title_col, 1)

        self.tol_badge = QtWidgets.QLabel("≤ 0.04 mm LEVEL")
        self.tol_badge.setStyleSheet("""
            color: #34D399;
            font-size: 10px;
            font-weight: 800;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid #10B981;
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.tol_badge)

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

        # --- Body: Left (Interactive Bed Grid Canvas) | Right (Selected Screw Controls & Guidance) ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # Left Column: Bed Screws Canvas
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(_s(4, scale))

        self.canvas = BedScrewsCanvas()
        self.canvas.screw_clicked.connect(self._on_screw_selected_from_canvas)
        left_col.addWidget(self.canvas, 1)

        legend_row = QtWidgets.QHBoxLayout()
        legend_row.setSpacing(12)
        for col_str, txt in [("#34D399", "Green = Level (≤ 0.04 mm)"), ("#EF4444", "Red = Lower Screw"), ("#FBBF24", "Amber = Raise Screw")]:
            leg_lbl = QtWidgets.QLabel(f"● {txt}")
            leg_lbl.setStyleSheet(f"color: {col_str}; font-size: 10px; font-weight: 700;")
            legend_row.addWidget(leg_lbl)
        legend_row.addStretch(1)
        left_col.addLayout(legend_row)

        body.addLayout(left_col, 3)

        # Right Column: Selected Screw Telemetry, Raise/Lower Guidance & Actions
        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(6, scale))

        # 1. Selected Screw Box
        sel_box = QtWidgets.QFrame()
        sel_box.setObjectName("SelScrewBox")
        sel_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sel_box.setStyleSheet("""
            QFrame#SelScrewBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        sb_lay = QtWidgets.QVBoxLayout(sel_box)
        sb_lay.setContentsMargins(10, 6, 10, 6)
        sb_lay.setSpacing(2)

        self.screw_title_lbl = QtWidgets.QLabel("SCREW 1: FRONT LEFT")
        self.screw_title_lbl.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 900; letter-spacing: 0.5px;")
        sb_lay.addWidget(self.screw_title_lbl)

        self.screw_coords_lbl = QtWidgets.QLabel("X: 30.0 mm   Y: 30.0 mm")
        self.screw_coords_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 800; font-family: 'Consolas', monospace;")
        sb_lay.addWidget(self.screw_coords_lbl)
        side.addWidget(sel_box)

        # 2. Guidance & Deviation Card
        guidance_box = QtWidgets.QFrame()
        guidance_box.setObjectName("GuidanceBox")
        guidance_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        guidance_box.setStyleSheet("""
            QFrame#GuidanceBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
            }
        """)
        gb_lay = QtWidgets.QVBoxLayout(guidance_box)
        gb_lay.setContentsMargins(10, 8, 10, 8)
        gb_lay.setSpacing(3)

        lbl_dev_hdr = QtWidgets.QLabel("LEVELLING STATUS & DEVIATION")
        lbl_dev_hdr.setStyleSheet(_LBL_HDR)
        gb_lay.addWidget(lbl_dev_hdr)

        self.dev_val_lbl = QtWidgets.QLabel("Reference Base Screw")
        self.dev_val_lbl.setStyleSheet("color: #34D399; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
        gb_lay.addWidget(self.dev_val_lbl)

        self.guidance_note = QtWidgets.QLabel("This is the reference screw. All other screws adjust to match this height.")
        self.guidance_note.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        self.guidance_note.setWordWrap(True)
        gb_lay.addWidget(self.guidance_note)
        side.addWidget(guidance_box)

        # 3. Action Buttons: Move Toolhead, Probe This Screw, Probe All
        self.btn_move = QtWidgets.QPushButton("🎯  Move Toolhead Here")
        self.btn_move.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move.setStyleSheet(_BTN_PRIMARY)
        self.btn_move.clicked.connect(self._on_move_to_selected)
        side.addWidget(self.btn_move)

        self.btn_probe = QtWidgets.QPushButton("🔍  Probe This Screw")
        self.btn_probe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probe.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                border: 1px solid #34D399;
                border-radius: 7px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                min-height: 32px;
                padding: 2px 14px;
            }
            QPushButton:hover { background: #10B981; }
            QPushButton:disabled { background: rgba(30, 41, 59, 0.6); color: #64748B; border-color: rgba(255, 255, 255, 0.1); }
        """)
        self.btn_probe.clicked.connect(self._on_probe_selected)
        side.addWidget(self.btn_probe)

        self.btn_probe_all = QtWidgets.QPushButton("⚡  Probe All Screws (Calculate)")
        self.btn_probe_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probe_all.setStyleSheet(_BTN_GHOST)
        self.btn_probe_all.clicked.connect(self._on_probe_all_screws)
        side.addWidget(self.btn_probe_all)

        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side)
        side_widget.setMinimumWidth(230)
        side_widget.setMaximumWidth(290)
        body.addWidget(side_widget, 2)

        card_layout.addLayout(body, 1)

        # --- Bottom Status Bar ---
        bot = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Reading screw coordinates from printer config...")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bot.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bot.addWidget(self.close_btn)

        card_layout.addLayout(bot)

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(40, self._load_screws_from_config)

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _load_screws_from_config(self):
        mr = self._get_moonraker()
        cfg = mr.config if mr else {}

        # 1. Determine Bed Dimensions
        bx, by = 235.0, 225.0
        if "stepper_x" in cfg:
            bx = float(cfg["stepper_x"].get("position_max", 235.0))
        if "stepper_y" in cfg:
            by = float(cfg["stepper_y"].get("position_max", 225.0))
        self._bed_size = (bx, by)

        # 2. Extract Screw coordinates from screws_tilt_adjust or bed_screws
        sec = cfg.get("screws_tilt_adjust") or cfg.get("bed_screws") or {}
        screws: List[Dict] = []
        for idx in range(1, 10):
            k = f"screw{idx}"
            if k in sec:
                coords = sec[k]
                if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                    sx, sy = float(coords[0]), float(coords[1])
                else:
                    parts = [float(p) for p in str(coords).replace(" ", "").split(",") if p]
                    sx, sy = parts[0], parts[1]
                name = str(sec.get(f"screw{idx}_name", f"Screw {idx}"))
                screws.append({
                    "index": idx,
                    "x": sx,
                    "y": sy,
                    "name": name,
                    "is_base": (idx == 1),
                    "z": None,
                    "diff": 0.0 if idx == 1 else None,
                    "turn": None,
                })

        if not screws:
            # Fallback to standard 4 corners if unconfigured
            screws = [
                {"index": 1, "x": 30.0, "y": 30.0, "name": "front left screw", "is_base": True, "z": None, "diff": 0.0, "turn": None},
                {"index": 2, "x": bx - 30.0, "y": 30.0, "name": "front right screw", "is_base": False, "z": None, "diff": None, "turn": None},
                {"index": 3, "x": bx - 30.0, "y": by - 30.0, "name": "back right screw", "is_base": False, "z": None, "diff": None, "turn": None},
                {"index": 4, "x": 30.0, "y": by - 30.0, "name": "back left screw", "is_base": False, "z": None, "diff": None, "turn": None},
            ]

        self._screws = screws
        self.canvas.set_screws(screws, self._bed_size)
        self._select_screw(1)
        self.status_lbl.setText(f"Loaded {len(screws)} bed screws from config. Bed size: {bx:.0f}x{by:.0f} mm.")

    def _select_screw(self, idx: int):
        self._selected_screw_idx = idx
        self.canvas.set_selected(idx)

        sc = next((s for s in self._screws if s["index"] == idx), None)
        if not sc:
            return

        name = sc.get("name", f"Screw {idx}").upper()
        self.screw_title_lbl.setText(f"SCREW {idx}: {name}")
        self.screw_coords_lbl.setText(f"X: {sc['x']:.1f} mm   Y: {sc['y']:.1f} mm")

        # Update deviation & guidance text
        is_base = sc.get("is_base", False)
        diff = sc.get("diff", None)
        turn = sc.get("turn", "")

        if is_base:
            self.dev_val_lbl.setText("● BASE REFERENCE (0.00 mm)")
            self.dev_val_lbl.setStyleSheet("color: #34D399; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
            self.guidance_note.setText("This is the base reference point. Adjust all other bed screws until they turn GREEN to match.")
        elif diff is not None:
            sign = "+" if diff > 0 else ""
            diff_str = f"{sign}{diff:.3f} mm"

            if abs(diff) <= ACCEPTABLE_TOLERANCE_MM:
                self.dev_val_lbl.setText(f"✓ LEVEL ({diff_str})")
                self.dev_val_lbl.setStyleSheet("color: #34D399; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
                self.guidance_note.setText("✓ EXCELLENT: Height deviation is within acceptable 1st layer tolerance (≤ 0.04 mm). No turn required!")
            elif diff > ACCEPTABLE_TOLERANCE_MM:
                # Bed is too high -> turn to lower
                self.dev_val_lbl.setText(f"▼ TOO HIGH ({diff_str})")
                self.dev_val_lbl.setStyleSheet("color: #EF4444; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
                turn_info = f" ({turn})" if turn else ""
                self.guidance_note.setText(f"LOWER THIS CORNER: Bed is {diff:+.3f} mm too high. Turn screw knob Counter-Clockwise (CCW){turn_info} to lower.")
            else:
                # Bed is too low -> turn to raise
                self.dev_val_lbl.setText(f"▲ TOO LOW ({diff_str})")
                self.dev_val_lbl.setStyleSheet("color: #FBBF24; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
                turn_info = f" ({turn})" if turn else ""
                self.guidance_note.setText(f"RAISE THIS CORNER: Bed is {abs(diff):.3f} mm too low. Turn screw knob Clockwise (CW){turn_info} to raise.")
        else:
            self.dev_val_lbl.setText("Not yet probed (--)")
            self.dev_val_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
            self.guidance_note.setText("Tap 'Move Toolhead Here' and 'Probe This Screw' to measure clearance at this corner.")

    def _on_screw_selected_from_canvas(self, idx: int):
        self._select_screw(idx)
        # Immediately move to touched screw point
        self._on_move_to_selected()

    def _on_move_to_selected(self):
        sc = next((s for s in self._screws if s["index"] == self._selected_screw_idx), None)
        if not sc or self._busy:
            return

        sx, sy = sc["x"], sc["y"]
        self.canvas.set_toolhead(sx, sy)
        self.status_lbl.setText(f"Moving toolhead to Screw {sc['index']} (X{sx:.1f} Y{sy:.1f})...")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            return

        self._busy = True
        self.btn_move.setEnabled(False)

        # Check homed status, lift to safe height, move XY
        gcode = (
            "G90\n"
            "G1 Z10 F1200\n"
            f"G1 X{sx:.1f} Y{sy:.1f} F6000\n"
        )
        if "xyz" not in (mr.homed_axes or "").lower():
            gcode = "G28\n" + gcode

        def _done(ok):
            self._busy = False
            self.btn_move.setEnabled(True)
            if ok:
                self.status_lbl.setText(f"Toolhead positioned at Screw {sc['index']}. Ready to probe.")
            else:
                self.status_lbl.setText("Move failed. Check printer.")

        mr.send_gcode(gcode, on_done=_done, timeout=40.0)

    def _on_probe_selected(self):
        sc = next((s for s in self._screws if s["index"] == self._selected_screw_idx), None)
        if not sc or self._busy:
            return

        self._busy = True
        self.btn_probe.setEnabled(False)
        self.btn_probe.setText("Probing...")
        self.status_lbl.setText(f"Probing bed clearance at Screw {sc['index']}...")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            # Simulation mode
            QtCore.QTimer.singleShot(800, lambda: self._apply_simulated_probe(sc))
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()

        # Send PROBE command followed by safe Z lift
        cmd = "PROBE\nG91\nG1 Z10 F1200\nG90"

        def _after_probe(ok):
            # Parse measured Z from gcode_store
            def _bg():
                measured_z = None
                try:
                    url = f"http://{host}/server/gcode_store?count=25"
                    req = urllib.request.Request(url, headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            for item in reversed(data.get("result", {}).get("gcode_store", [])):
                                if float(item.get("time", 0.0)) < start_t - 1.0:
                                    continue
                                msg = item.get("message", "")
                                m = re.search(r"(?:contact at|Result is)\s+z=\s*([\d\.-]+)", msg, re.IGNORECASE)
                                if m:
                                    measured_z = float(m.group(1))
                                    break
                except Exception:
                    pass

                def _apply():
                    self._busy = False
                    self.btn_probe.setEnabled(True)
                    self.btn_probe.setText("🔍  Probe This Screw")
                    if measured_z is not None:
                        self._record_screw_reading(sc, measured_z)
                    else:
                        self.status_lbl.setText("Probe completed. Reading captured.")

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode(cmd, on_done=_after_probe, timeout=30.0)

    def _apply_simulated_probe(self, sc: Dict):
        self._busy = False
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText("🔍  Probe This Screw")
        sim_val = 0.025 if sc["index"] == 1 else (0.015 if sc["index"] == 2 else 0.120)
        self._record_screw_reading(sc, sim_val)

    def _record_screw_reading(self, sc: Dict, z: float):
        sc["z"] = z
        if sc.get("is_base", False) or self._base_z is None:
            self._base_z = z
            sc["diff"] = 0.0
            self.status_lbl.setText(f"Base screw reference recorded: Z = {z:.3f} mm.")
        else:
            diff = round(z - self._base_z, 4)
            sc["diff"] = diff
            self.status_lbl.setText(f"Screw {sc['index']} measured: diff = {diff:+.3f} mm.")

        self.canvas.update()
        self._select_screw(sc["index"])

    def _on_probe_all_screws(self):
        if self._busy:
            return
        mr = self._get_moonraker()
        self._busy = True
        self.btn_probe_all.setEnabled(False)
        self.btn_probe_all.setText("Measuring All Screws...")
        self.status_lbl.setText("Executing SCREWS_TILT_CALCULATE to probe all screws automatically...")

        if not (mr and mr.connected):
            # Simulation demo
            QtCore.QTimer.singleShot(1500, self._apply_sim_all)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()

        def _done(ok):
            def _bg():
                results = {}
                try:
                    url = f"http://{host}/server/gcode_store?count=60"
                    req = urllib.request.Request(url, headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            for item in data.get("result", {}).get("gcode_store", []):
                                if float(item.get("time", 0.0)) < start_t - 2.0:
                                    continue
                                msg = item.get("message", "").strip()
                                # E.g. front right screw : x=205.0, y=30.0, z=0.08500 : CW 00:04 (diff: 0.04500)
                                m = re.search(
                                    r"([\w\s]+)\s*:\s*x=([\d\.-]+),\s*y=([\d\.-]+),\s*z=([\d\.-]+)\s*:\s*(BASE|([A-Z]+)\s+([\d:]+))(?:\s*\(diff:\s*([\d\.-]+)\))?",
                                    msg,
                                    re.IGNORECASE,
                                )
                                if m:
                                    name_part = m.group(1).strip().lower()
                                    z_val = float(m.group(4))
                                    base_or_turn = m.group(5).strip()
                                    diff_val = float(m.group(8)) if m.group(8) else (0.0 if "BASE" in base_or_turn.upper() else 0.0)
                                    results[name_part] = {
                                        "z": z_val,
                                        "diff": diff_val,
                                        "turn": base_or_turn if "BASE" not in base_or_turn else "",
                                        "is_base": "BASE" in base_or_turn.upper(),
                                    }
                except Exception:
                    pass

                def _apply():
                    self._busy = False
                    self.btn_probe_all.setEnabled(True)
                    self.btn_probe_all.setText("⚡  Probe All Screws (Calculate)")
                    for sc in self._screws:
                        name_key = sc.get("name", "").lower()
                        match = results.get(name_key)
                        if not match:
                            for k, v in results.items():
                                if k in name_key or name_key in k:
                                    match = v
                                    break
                        if match:
                            sc["z"] = match["z"]
                            sc["diff"] = match["diff"]
                            sc["turn"] = match["turn"]
                            if match["is_base"]:
                                sc["is_base"] = True
                                self._base_z = match["z"]

                    self.canvas.update()
                    self._select_screw(self._selected_screw_idx)
                    self.status_lbl.setText("All bed screws probed! Green screws are within acceptable tolerance.")

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode("SCREWS_TILT_CALCULATE", on_done=_done, timeout=180.0)

    def _apply_sim_all(self):
        self._busy = False
        self.btn_probe_all.setEnabled(True)
        self.btn_probe_all.setText("⚡  Probe All Screws (Calculate)")
        if len(self._screws) >= 4:
            self._screws[0].update({"is_base": True, "z": 0.040, "diff": 0.0, "turn": ""})
            self._screws[1].update({"is_base": False, "z": 0.065, "diff": 0.025, "turn": "CW 00:02"})
            self._screws[2].update({"is_base": False, "z": -0.070, "diff": -0.110, "turn": "CCW 00:09"})
            self._screws[3].update({"is_base": False, "z": 0.055, "diff": 0.015, "turn": "CW 00:01"})
        self.canvas.update()
        self._select_screw(self._selected_screw_idx)
        self.status_lbl.setText("Simulated: All screws probed. Green screws are level.")

    def accept(self):
        self.closed.emit()

    def reject(self):
        self.closed.emit()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("screws", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
