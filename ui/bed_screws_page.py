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
                col = C_GREEN if sc.get("z") is not None else C_CYAN
                badge_txt = "CENTER (REF)" if sc.get("z") is not None else "CENTER REF"
            elif diff is not None:
                turn = sc.get("turn", "")
                if abs(diff) <= ACCEPTABLE_TOLERANCE_MM:
                    col = C_GREEN
                    badge_txt = f"✓ {diff:+.2f}"
                elif diff > ACCEPTABLE_TOLERANCE_MM:
                    col = C_RED
                    badge_txt = f"▼ {turn}" if turn else f"▼ {diff:+.2f}"
                else:
                    col = C_AMBER
                    badge_txt = f"▲ {turn}" if turn else f"▲ {diff:+.2f}"
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
            f.setPointSizeF(7.5)
            p.setFont(f)
            p.setPen(QtGui.QColor("#FFFFFF"))
            p.drawText(QtCore.QRectF(pt.x() - 55, pt.y() + 18, 110, 14), Qt.AlignmentFlag.AlignCenter, badge_txt)

            name = sc.get("name", f"Screw {idx}")
            f.setPointSizeF(7.0)
            p.setFont(f)
            p.setPen(C_SLATE)
            p.drawText(QtCore.QRectF(pt.x() - 55, pt.y() - 28, 110, 12), Qt.AlignmentFlag.AlignCenter, name.title())

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
        self._top_screws_enabled = False
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

        # 3. Top Screws Mode Toggle (Moves 30mm out of way after probe)
        self.btn_top_screws = QtWidgets.QPushButton()
        self.btn_top_screws.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_top_screws.clicked.connect(self._toggle_top_screws)
        self._update_top_screws_style()
        side.addWidget(self.btn_top_screws)

        # 4. Action Buttons: Move Toolhead, Probe This Screw, Probe All
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

    def _toggle_top_screws(self):
        self._top_screws_enabled = not self._top_screws_enabled
        self._update_top_screws_style()
        if self._top_screws_enabled:
            self.status_lbl.setText("Top Screws Mode: ON. Toolhead will move 30mm out of the way after probing so you can adjust screws.")
        else:
            self.status_lbl.setText("Top Screws Mode: OFF. For under-bed screws (no extra clearance travel needed).")

    def _update_top_screws_style(self):
        if self._top_screws_enabled:
            self.btn_top_screws.setText("🛠  Top Screws: ON (Clear 30mm)")
            self.btn_top_screws.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(2, 132, 199, 0.4), stop:1 rgba(0, 229, 255, 0.4));
                    border: 1.5px solid #00E5FF;
                    border-radius: 7px;
                    color: #00E5FF;
                    font-size: 12px;
                    font-weight: 800;
                    min-height: 30px;
                    padding: 2px 10px;
                }
                QPushButton:hover {
                    background: rgba(0, 229, 255, 0.3);
                }
            """)
        else:
            self.btn_top_screws.setText("🛠  Top Screws: OFF (Under Bed)")
            self.btn_top_screws.setStyleSheet("""
                QPushButton {
                    background: rgba(15, 23, 42, 0.7);
                    border: 1px solid rgba(148, 163, 184, 0.25);
                    border-radius: 7px;
                    color: #94A3B8;
                    font-size: 12px;
                    font-weight: 700;
                    min-height: 30px;
                    padding: 2px 10px;
                }
                QPushButton:hover {
                    border-color: rgba(255, 255, 255, 0.3);
                    color: #FFFFFF;
                }
            """)

    def _get_clearance_pos(self, sc: Dict) -> Tuple[float, float]:
        """Calculate position 30mm out of the way for top screw adjustment.
        If far left side screws move right (+30), if far right move left (-30).
        """
        bx, by = self._bed_size
        sx, sy = float(sc["x"]), float(sc["y"])
        # Far left side (x < bx * 0.35) -> move 30mm to the right (+30)
        # Far right side (x > bx * 0.65) -> move 30mm to the left (-30)
        # Center column -> move 30mm to the right (+30)
        if sx < bx * 0.35:
            target_x = min(bx - 5.0, sx + 30.0)
        elif sx > bx * 0.65:
            target_x = max(5.0, sx - 30.0)
        else:
            target_x = sx + 30.0 if (sx + 30.0 <= bx - 5.0) else sx - 30.0
        return (round(target_x, 2), round(sy, 2))

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
        self._screw_thread = str(sec.get("screw_thread", "CW-M3")).upper()
        self._hop_z = float(sec.get("horizontal_move_z", 10.0))
        self._speed = float(sec.get("speed", 150.0))

        screws: List[Dict] = []
        for idx in range(1, 30):
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
                    "is_base": False,
                    "z": None,
                    "diff": None,
                    "turn": None,
                })

        if not screws:
            # Fallback to standard 4 corners if unconfigured
            screws = [
                {"index": 1, "x": bx / 2.0, "y": by / 2.0, "name": "center screw", "is_base": True, "z": None, "diff": None, "turn": None},
                {"index": 2, "x": 30.0, "y": 30.0, "name": "front left screw", "is_base": False, "z": None, "diff": None, "turn": None},
                {"index": 3, "x": bx - 30.0, "y": 30.0, "name": "front right screw", "is_base": False, "z": None, "diff": None, "turn": None},
                {"index": 4, "x": bx - 30.0, "y": by - 30.0, "name": "back right screw", "is_base": False, "z": None, "diff": None, "turn": None},
                {"index": 5, "x": 30.0, "y": by - 30.0, "name": "back left screw", "is_base": False, "z": None, "diff": None, "turn": None},
            ]

        # Identify Center / Base Reference Screw
        base_screw = None
        for s in screws:
            nm = s.get("name", "").lower()
            if "center" in nm or "centre" in nm or "base" in nm:
                base_screw = s
                break
        if not base_screw and screws:
            cx, cy = bx / 2.0, by / 2.0
            base_screw = min(screws, key=lambda s: (s["x"] - cx)**2 + (s["y"] - cy)**2)
        if not base_screw and screws:
            base_screw = screws[0]

        for s in screws:
            if base_screw and s["index"] == base_screw["index"]:
                s["is_base"] = True
                self._base_screw_idx = s["index"]
            else:
                s["is_base"] = False

        self._screws = screws
        self._base_z = None
        self.canvas.set_screws(screws, self._bed_size)
        self._select_screw(self._base_screw_idx)
        self.status_lbl.setText(f"Loaded {len(screws)} bed screws. Center reference: Screw {self._base_screw_idx} ({base_screw['name']}).")

        # Automatically check if Moonraker already has recent screw tilt results
        if mr and getattr(mr, "connected", False):
            host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
            threading.Thread(target=lambda: self._bg_check_initial_store(host), daemon=True).start()

    def _bg_check_initial_store(self, host: str):
        mr = self._get_moonraker()
        matched = self._fetch_tilt_results_from_store(host)
        if matched:
            def _apply():
                self.canvas.update()
                self._select_screw(self._selected_screw_idx)
                self.status_lbl.setText(f"Loaded {matched} screw tilt calculations from printer.")
            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_apply)
            else:
                QtCore.QTimer.singleShot(0, _apply)

    def _fetch_tilt_results_from_store(self, host: str) -> int:
        """Fetch and apply screws_tilt_calculate results from Moonraker gcode_store."""
        try:
            url = f"http://{host}/server/gcode_store?count=100"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    return 0
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("result", {}).get("gcode_store", [])

            # Regex matching Klipper's screws_tilt_calculate output:
            # // <name> : x=<x>, y=<y>, z=<z> [ : adjust <direction> <HH:MM> ]
            regex = re.compile(
                r"(?://\s*)?([a-zA-Z0-9_\s\(\)]+?)\s*:\s*x=([\d\.-]+),\s*y=([\d\.-]+),\s*z=([\d\.-]+)(?:\s*:\s*(?:adjust\s+)?([A-Z]+)\s+([\d:]+))?",
                re.IGNORECASE,
            )

            parsed = []
            base_z = None

            for it in reversed(items):
                msg = it.get("message", "").strip()
                m = regex.search(msg)
                if m:
                    raw_name = m.group(1).strip()
                    clean_name = re.sub(r"\s*\(base\)", "", raw_name, flags=re.IGNORECASE).strip().lower()
                    x_val = float(m.group(2))
                    y_val = float(m.group(3))
                    z_val = float(m.group(4))
                    turn_dir = m.group(5)
                    turn_time = m.group(6)
                    is_base = "base" in raw_name.lower() or turn_dir is None
                    turn_str = f"{turn_dir.upper()} {turn_time}" if (turn_dir and turn_time) else ""

                    if is_base and base_z is None:
                        base_z = z_val

                    parsed.append({
                        "name": clean_name,
                        "x": x_val,
                        "y": y_val,
                        "z": z_val,
                        "turn": turn_str,
                        "is_base": is_base,
                    })
                elif "means 1 full turn" in msg.lower():
                    break

            if not parsed:
                return 0

            if base_z is None:
                base_item = next((p for p in parsed if p["is_base"]), parsed[-1])
                base_z = base_item["z"]

            self._base_z = base_z
            matched_count = 0
            for p in parsed:
                target = None
                for sc in self._screws:
                    if abs(sc["x"] - p["x"]) <= 15.0 and abs(sc["y"] - p["y"]) <= 15.0:
                        target = sc
                        break
                if not target:
                    target = next(
                        (sc for sc in self._screws if p["name"] in sc["name"].lower() or sc["name"].lower() in p["name"]),
                        None
                    )
                if target:
                    diff = round(p["z"] - base_z, 4)
                    target["z"] = p["z"]
                    target["diff"] = diff
                    target["turn"] = p["turn"] or (self._calc_turn(diff) if not p["is_base"] else "")
                    if p["is_base"]:
                        target["is_base"] = True
                        target["diff"] = 0.0
                        target["turn"] = ""
                    matched_count += 1

            return matched_count
        except Exception:
            return 0

    def _calc_turn(self, diff: float) -> str:
        if abs(diff) <= ACCEPTABLE_TOLERANCE_MM:
            return "LEVEL"
        pitch = 0.5
        th = getattr(self, "_screw_thread", "CW-M3").upper()
        if "M4" in th:
            pitch = 0.7
        elif "M5" in th:
            pitch = 0.8
        elif "M3" in th:
            pitch = 0.5

        is_ccw = "CCW" in th
        # On CW thread, bed too high (diff > 0) -> turn CW to tighten/lower
        turn_dir = ("CCW" if is_ccw else "CW") if diff > 0 else ("CW" if is_ccw else "CCW")
        fraction = abs(diff) / pitch
        hours = int(fraction)
        mins = int(round((fraction - hours) * 60))
        if mins >= 60:
            hours += 1
            mins = 0
        return f"{turn_dir} {hours:02d}:{mins:02d}"

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
            if self._base_z is not None:
                self.dev_val_lbl.setText(f"● CENTER REF (Z = {self._base_z:.3f} mm)")
                self.guidance_note.setText("✓ Center reference locked. Outer screws adjust relative to this point (only 1 reference needed).")
                self.btn_probe.setText("🎯  Re-probe Center Reference")
            else:
                self.dev_val_lbl.setText("● CENTER REF (Not Probed)")
                self.guidance_note.setText("This is the Center Reference point. Probing will automatically measure this center reference first.")
                self.btn_probe.setText("🎯  Probe Center Reference")
            self.dev_val_lbl.setStyleSheet("color: #34D399; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
        else:
            if self._base_z is None:
                self.btn_probe.setText("🔍  Probe (Gets Ref First)")
            else:
                self.btn_probe.setText(f"🔍  Probe Screw {idx}")

            if diff is not None:
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
                    turn_action = f"Turn screw knob {turn}" if turn else "Turn screw knob to lower"
                    self.guidance_note.setText(f"LOWER THIS SCREW: Bed is {diff:+.3f} mm higher than center reference. {turn_action}.")
                else:
                    # Bed is too low -> turn to raise
                    self.dev_val_lbl.setText(f"▲ TOO LOW ({diff_str})")
                    self.dev_val_lbl.setStyleSheet("color: #FBBF24; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
                    turn_action = f"Turn screw knob {turn}" if turn else "Turn screw knob to raise"
                    self.guidance_note.setText(f"RAISE THIS SCREW: Bed is {abs(diff):.3f} mm lower than center reference. {turn_action}.")
            else:
                ref_hint = f"Ref: {self._base_z:.3f} mm" if self._base_z is not None else "Needs Ref First"
                self.dev_val_lbl.setText(f"Not yet probed ({ref_hint})")
                self.dev_val_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
                if self._base_z is not None:
                    self.guidance_note.setText(f"Center reference is locked (Z = {self._base_z:.3f} mm). Tap 'Probe' to measure this screw directly.")
                else:
                    self.guidance_note.setText("Center reference not yet recorded. Probing will automatically get center reference first, then probe this screw.")

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

        base_sc = next((s for s in self._screws if s.get("is_base", False)), self._screws[0])
        needs_ref = (self._base_z is None) and (not sc.get("is_base", False))

        self._busy = True
        self.btn_probe.setEnabled(False)
        self.btn_probe.setText("Probing...")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            # Simulation mode
            QtCore.QTimer.singleShot(800, lambda: self._apply_simulated_probe(sc, base_sc, needs_ref))
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()

        speed_f = int(getattr(self, "_speed", 150.0) * 60)
        hop = int(getattr(self, "_hop_z", 10.0))
        clear_x, clear_y = self._get_clearance_pos(sc)

        has_lc = False
        if mr:
            if hasattr(mr, "has_load_cell"):
                has_lc = mr.has_load_cell()
            if not has_lc and hasattr(mr, "objects"):
                has_lc = any("load_cell" in str(o).lower() for o in mr.objects)

        tare_step = "G4 P250\nLOAD_CELL_TARE\nG4 P100\n" if has_lc else ""

        if needs_ref:
            self.status_lbl.setText(f"Taring probe and measuring Center Reference first ({base_sc['name']}), then Screw {sc['index']}...")
            cmd = (
                f"G90\n"
                f"G1 Z{hop} F1200\n"
                f"G1 X{base_sc['x']:.2f} Y{base_sc['y']:.2f} F{speed_f}\n"
                f"{tare_step}"
                f"PROBE\n"
                f"G91\n"
                f"G1 Z{hop} F1200\n"
                f"G90\n"
                f"G1 X{sc['x']:.2f} Y{sc['y']:.2f} F{speed_f}\n"
                f"{tare_step}"
                f"PROBE\n"
                f"G91\n"
                f"G1 Z{hop} F1200\n"
                f"G90"
            )
            if self._top_screws_enabled:
                cmd += f"\nG1 X{clear_x:.2f} Y{clear_y:.2f} F{speed_f}"
        else:
            if sc.get("is_base", False):
                self.status_lbl.setText(f"Taring probe and measuring Center Reference Screw ({sc['name']})...")
            else:
                self.status_lbl.setText(f"Taring probe and measuring Screw {sc['index']} ({sc['name']}) using locked Center Reference...")
            cmd = (
                f"G90\n"
                f"G1 Z{hop} F1200\n"
                f"G1 X{sc['x']:.2f} Y{sc['y']:.2f} F{speed_f}\n"
                f"{tare_step}"
                f"PROBE\n"
                f"G91\n"
                f"G1 Z{hop} F1200\n"
                f"G90"
            )
            if self._top_screws_enabled:
                cmd += f"\nG1 X{clear_x:.2f} Y{clear_y:.2f} F{speed_f}"

        def _after_probe(ok):
            def _bg():
                readings = []
                try:
                    url = f"http://{host}/server/gcode_store?count=40"
                    req = urllib.request.Request(url, headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            for item in data.get("result", {}).get("gcode_store", []):
                                if float(item.get("time", 0.0)) < start_t - 1.0:
                                    continue
                                msg = item.get("message", "")
                                m = re.search(r"(?:contact at|Result is)\s+z=\s*([\d\.-]+)", msg, re.IGNORECASE)
                                if m:
                                    readings.append(float(m.group(1)))
                except Exception:
                    pass

                def _apply():
                    self._busy = False
                    self.btn_probe.setEnabled(True)
                    if needs_ref and len(readings) >= 2:
                        ref_z = readings[0]
                        target_z = readings[1]
                        self._base_z = ref_z
                        base_sc["z"] = ref_z
                        base_sc["diff"] = 0.0
                        base_sc["turn"] = ""
                        self._record_screw_reading(sc, target_z)
                        self.status_lbl.setText(f"Center Ref locked ({ref_z:.3f} mm). Screw {sc['index']} diff = {sc['diff']:+.3f} mm.")
                    elif sc.get("is_base", False) and len(readings) >= 1:
                        ref_z = readings[-1]
                        self._base_z = ref_z
                        base_sc["z"] = ref_z
                        base_sc["diff"] = 0.0
                        base_sc["turn"] = ""
                        self.status_lbl.setText(f"Center Reference locked at Z = {ref_z:.3f} mm (only 1 reference needed).")
                    elif len(readings) >= 1:
                        target_z = readings[-1]
                        self._record_screw_reading(sc, target_z)
                    else:
                        self.status_lbl.setText("Probe completed.")

                    if self._top_screws_enabled:
                        self.canvas.set_toolhead(clear_x, clear_y)
                        self.status_lbl.setText(f"{self.status_lbl.text()} (Toolhead moved 30mm clear)")
                    else:
                        self.canvas.set_toolhead(sc["x"], sc["y"])

                    self.canvas.update()
                    self._select_screw(self._selected_screw_idx)

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode(cmd, on_done=_after_probe, timeout=45.0)

    def _apply_simulated_probe(self, sc: Dict, base_sc: Dict, needs_ref: bool):
        self._busy = False
        self.btn_probe.setEnabled(True)
        if needs_ref:
            self._base_z = 0.000
            base_sc["z"] = 0.000
            base_sc["diff"] = 0.0
            base_sc["turn"] = ""
            sim_val = 0.035 if sc["index"] == 2 else -0.115
            self._record_screw_reading(sc, sim_val)
            self.status_lbl.setText(f"Center Ref locked (0.000 mm). Screw {sc['index']} diff: {sc['diff']:+.3f} mm.")
        elif sc.get("is_base", False):
            self._base_z = 0.000
            sc["z"] = 0.000
            sc["diff"] = 0.0
            sc["turn"] = ""
            self.status_lbl.setText("Center Reference locked (0.000 mm). Only 1 reference needed!")
        else:
            sim_val = 0.020 if sc["index"] == 3 else 0.090
            self._record_screw_reading(sc, sim_val)

        if self._top_screws_enabled:
            cx, cy = self._get_clearance_pos(sc)
            self.canvas.set_toolhead(cx, cy)
            self.status_lbl.setText(f"{self.status_lbl.text()} (Toolhead moved 30mm clear)")
        else:
            self.canvas.set_toolhead(sc["x"], sc["y"])

        self.canvas.update()
        self._select_screw(self._selected_screw_idx)

    def _record_screw_reading(self, sc: Dict, z: float):
        sc["z"] = z
        if sc.get("is_base", False) or self._base_z is None:
            self._base_z = z
            sc["diff"] = 0.0
            sc["turn"] = ""
            self.status_lbl.setText(f"Center Reference recorded: Z = {z:.3f} mm.")
        else:
            diff = round(z - self._base_z, 4)
            sc["diff"] = diff
            sc["turn"] = self._calc_turn(diff)
            self.status_lbl.setText(f"Screw {sc['index']} measured: diff = {diff:+.3f} mm ({sc['turn']}).")

        self.canvas.update()
        self._select_screw(sc["index"])

    def _on_probe_all_screws(self):
        if self._busy:
            return
        mr = self._get_moonraker()
        self._busy = True
        self.btn_probe_all.setEnabled(False)
        self.btn_probe_all.setText("Measuring All Screws...")
        self.status_lbl.setText("Taring probe before each screw and measuring bed...")

        if not (mr and mr.connected):
            # Simulation demo
            QtCore.QTimer.singleShot(1500, self._apply_sim_all)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()

        has_lc = False
        if mr:
            if hasattr(mr, "has_load_cell"):
                has_lc = mr.has_load_cell()
            if not has_lc and hasattr(mr, "objects"):
                has_lc = any("load_cell" in str(o).lower() for o in mr.objects)

        speed_f = int(getattr(self, "_speed", 150.0) * 60)
        hop = int(getattr(self, "_hop_z", 10.0))

        base_sc = next((s for s in self._screws if s.get("is_base", False)), self._screws[0])
        ordered_screws = [base_sc] + [s for s in self._screws if s["index"] != base_sc["index"]]

        if has_lc:
            tare_step = "G4 P250\nLOAD_CELL_TARE\nG4 P100\n"
            cmd_lines = ["G90", f"G1 Z{hop} F1200"]
            for s in ordered_screws:
                cmd_lines.append(f"G90\nG1 X{s['x']:.2f} Y{s['y']:.2f} F{speed_f}")
                cmd_lines.append(f"{tare_step}PROBE")
                cmd_lines.append(f"G91\nG1 Z{hop} F1200\nG90")

            if self._top_screws_enabled and ordered_screws:
                last_sc = ordered_screws[-1]
                clear_x, clear_y = self._get_clearance_pos(last_sc)
                cmd_lines.append(f"G1 X{clear_x:.2f} Y{clear_y:.2f} F{speed_f}")

            cmd = "\n".join(cmd_lines)
            timeout_s = max(60.0, len(ordered_screws) * 15.0)
        else:
            cmd = "SCREWS_TILT_CALCULATE"
            timeout_s = 300.0

        def _done(ok):
            def _bg():
                time.sleep(0.5)
                readings = []
                try:
                    url = f"http://{host}/server/gcode_store?count=100"
                    req = urllib.request.Request(url, headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            for item in data.get("result", {}).get("gcode_store", []):
                                if float(item.get("time", 0.0)) < start_t - 1.0:
                                    continue
                                msg = item.get("message", "")
                                m = re.search(r"(?:contact at|Result is)\s+z=\s*([\d\.-]+)", msg, re.IGNORECASE)
                                if m:
                                    readings.append(float(m.group(1)))
                except Exception:
                    pass

                def _apply():
                    self._busy = False
                    self.btn_probe_all.setEnabled(True)
                    self.btn_probe_all.setText("⚡  Probe All Screws (Calculate)")
                    if has_lc and len(readings) >= len(ordered_screws):
                        ref_z = readings[0]
                        self._base_z = ref_z
                        base_sc["z"] = ref_z
                        base_sc["diff"] = 0.0
                        base_sc["turn"] = ""
                        for idx, s in enumerate(ordered_screws[1:], start=1):
                            s_z = readings[idx]
                            s["z"] = s_z
                            diff = round(s_z - ref_z, 4)
                            s["diff"] = diff
                            s["turn"] = self._calc_turn(diff)
                        self.status_lbl.setText(f"All {len(ordered_screws)} screws tared & measured! Center Ref Z = {ref_z:.3f} mm.")
                    else:
                        matched = self._fetch_tilt_results_from_store(host)
                        if matched > 0:
                            self.status_lbl.setText(f"All {matched} bed screws calculated! Follow the turn directions on screen.")
                        elif len(readings) > 0:
                            ref_z = readings[0]
                            self._base_z = ref_z
                            base_sc["z"] = ref_z
                            base_sc["diff"] = 0.0
                            base_sc["turn"] = ""
                            for idx, s in enumerate(ordered_screws[1:len(readings)], start=1):
                                s_z = readings[idx]
                                s["z"] = s_z
                                diff = round(s_z - ref_z, 4)
                                s["diff"] = diff
                                s["turn"] = self._calc_turn(diff)
                            self.status_lbl.setText(f"{len(readings)} screws measured with tare. Center Ref Z = {ref_z:.3f} mm.")
                        else:
                            self.status_lbl.setText("Probe calculation completed.")

                    self.canvas.update()
                    self._select_screw(self._selected_screw_idx)

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)
                else:
                    QtCore.QTimer.singleShot(0, _apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode(cmd, on_done=_done, timeout=timeout_s)

    def _apply_sim_all(self):
        self._busy = False
        self.btn_probe_all.setEnabled(True)
        self.btn_probe_all.setText("⚡  Probe All Screws (Calculate)")
        self._base_z = 0.000
        for sc in self._screws:
            if sc.get("is_base", False):
                sc["z"] = 0.000
                sc["diff"] = 0.0
                sc["turn"] = ""
            else:
                idx = sc["index"]
                diff = [-0.015, 0.025, -0.060, 0.030, 0.120, -0.080, 0.010, -0.035, 0.055][(idx - 1) % 9]
                sc["z"] = round(diff, 4)
                sc["diff"] = diff
                sc["turn"] = self._calc_turn(diff)
        self.canvas.update()
        self._select_screw(self._selected_screw_idx)
        self.status_lbl.setText("Simulated: All screws probed with Center Reference. Green screws are level.")

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

