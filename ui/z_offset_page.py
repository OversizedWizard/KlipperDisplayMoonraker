"""Z-Offset Calibration Screen.

In-window touch screen to view stored probe / load-cell Z-offset from Klipper config,
move to probe area and home for paper friction testing, adjust clearance with touch increment buttons,
and permanently save the new offset to printer.cfg.
"""

import json
import math
import threading
import urllib.request
from typing import Tuple

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


C_CYAN = QtGui.QColor("#00E5FF")
C_GREEN = QtGui.QColor("#34D399")
C_AMBER = QtGui.QColor("#FBBF24")
C_RED = QtGui.QColor("#EF4444")
C_SLATE = QtGui.QColor("#94A3B8")


class ZOffsetVisualCanvas(QtWidgets.QWidget):
    """Visual diagram showing nozzle clearance and first-layer squish relative to bed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 140)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self._stored_z = -0.200
        self._target_z = -0.200
        self._delta = 0.0

    def set_values(self, stored_z: float, target_z: float, delta: float = 0.0):
        self._stored_z = stored_z
        self._target_z = target_z
        self._delta = delta
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bed_y = max(110, int(h * 0.65))
        cx = w * 0.40

        # Bed surface
        bg = QtGui.QLinearGradient(0, bed_y, 0, bed_y + 16)
        bg.setColorAt(0, QtGui.QColor(0, 229, 255, 140))
        bg.setColorAt(1, QtGui.QColor(15, 23, 42, 220))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(bg))
        p.drawRoundedRect(QtCore.QRectF(14, bed_y, w - 28, 14), 4, 4)
        p.setPen(QtGui.QPen(C_CYAN, 2))
        p.drawLine(QtCore.QPointF(14, bed_y), QtCore.QPointF(w - 14, bed_y))

        # Bed label
        f = p.font()
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C_SLATE)
        p.drawText(QtCore.QRectF(18, bed_y + 2, 100, 12), Qt.AlignmentFlag.AlignLeft, "BUILD SURFACE")

        # Visual clearance displacement (-0.5mm to +0.5mm mapped to -22px to +22px)
        clamped_delta = max(-0.4, min(0.4, self._delta))
        disp_px = clamped_delta * 75.0  # positive = higher, negative = lower
        nozzle_tip_y = (bed_y - 10) - disp_px

        # Filament squish extrusion bead on bed
        bead_w = max(14.0, 32.0 - disp_px * 0.6)
        bead_h = max(3.0, 7.0 - disp_px * 0.3)
        bead_r = QtCore.QRectF(cx - bead_w / 2, bed_y - bead_h, bead_w, bead_h)
        b_grad = QtGui.QLinearGradient(bead_r.topLeft(), bead_r.bottomLeft())
        b_grad.setColorAt(0, QtGui.QColor("#F59E0B"))
        b_grad.setColorAt(1, QtGui.QColor("#D97706"))
        p.setBrush(QtGui.QBrush(b_grad))
        p.setPen(QtGui.QPen(QtGui.QColor("#FBBF24"), 1))
        p.drawRoundedRect(bead_r, bead_h / 2, bead_h / 2)

        # Brass Nozzle + Heater Block
        ny = nozzle_tip_y
        # Heater block
        p.setBrush(QtGui.QColor("#475569"))
        p.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1.2))
        p.drawRoundedRect(QtCore.QRectF(cx - 22, ny - 42, 44, 22), 4, 4)

        # Brass cone
        cone = QtGui.QPolygonF([
            QtCore.QPointF(cx - 13, ny - 20),
            QtCore.QPointF(cx + 13, ny - 20),
            QtCore.QPointF(cx + 3, ny),
            QtCore.QPointF(cx - 3, ny),
        ])
        c_grad = QtGui.QLinearGradient(cx - 13, ny - 20, cx + 13, ny)
        c_grad.setColorAt(0, QtGui.QColor("#EAB308"))
        c_grad.setColorAt(1, QtGui.QColor("#CA8A04"))
        p.setBrush(QtGui.QBrush(c_grad))
        p.setPen(QtGui.QPen(QtGui.QColor("#FACC15"), 1))
        p.drawPolygon(cone)

        # Dimension Arrow line on the right
        ax = cx + 50
        p.setPen(QtGui.QPen(C_CYAN, 1.5, Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(ax, ny), QtCore.QPointF(ax, bed_y))
        # Arrow heads
        p.setPen(QtGui.QPen(C_CYAN, 2))
        p.drawLine(QtCore.QPointF(ax - 3, ny + 4), QtCore.QPointF(ax, ny))
        p.drawLine(QtCore.QPointF(ax + 3, ny + 4), QtCore.QPointF(ax, ny))
        p.drawLine(QtCore.QPointF(ax - 3, bed_y - 4), QtCore.QPointF(ax, bed_y))
        p.drawLine(QtCore.QPointF(ax + 3, bed_y - 4), QtCore.QPointF(ax, bed_y))

        # Dimension Text
        f.setPointSizeF(9.0)
        p.setFont(f)
        p.setPen(QtGui.QColor("#FFFFFF"))
        sign = "+" if self._delta > 0 else ""
        delta_txt = f"{sign}{self._delta:.3f} mm" if abs(self._delta) > 1e-4 else "0.000 mm"
        p.drawText(QtCore.QRectF(ax + 8, (ny + bed_y) / 2 - 10, 110, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"Δ {delta_txt}")

        # Clearance note at top
        f.setPointSizeF(8)
        p.setFont(f)
        if self._delta > 0.001:
            p.setPen(C_CYAN)
            note = f"↑ RAISED (+{self._delta:.3f} mm) • More clearance / less friction"
        elif self._delta < -0.001:
            p.setPen(C_AMBER)
            note = f"↓ LOWERED ({self._delta:.3f} mm) • More squish / more friction"
        else:
            p.setPen(C_GREEN)
            note = "✓ Stored zero baseline • Nominal bed clearance"
        p.drawText(QtCore.QRectF(14, 8, w - 28, 16), Qt.AlignmentFlag.AlignLeft, note)

        p.end()


_BTN_PRIMARY = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 7px;
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 800;
    min-height: 32px;
    padding: 2px 12px;
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
    min-height: 28px;
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

_BTN_ADJUST = """
QPushButton {
    background: rgba(15, 23, 42, 0.9);
    border: 1.5px solid rgba(0, 229, 255, 0.45);
    border-radius: 8px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 36px;
    padding: 4px 12px;
}
QPushButton:hover {
    background: rgba(0, 229, 255, 0.2);
    border-color: #00E5FF;
}
QPushButton:pressed {
    background: #0284C7;
}
QPushButton:disabled {
    border-color: rgba(255, 255, 255, 0.1);
    color: #64748B;
}
"""

_LBL_HDR = "color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;"


class ZOffsetScreen(QtWidgets.QFrame):
    """Full-screen in-window view to inspect and adjust stored probe Z-offset."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._probe_section = "load_cell_probe"
        self._stored_z = -0.200
        self._target_z = -0.200
        self._clearance_delta = 0.0
        self._step_size = 0.010
        self._busy = False
        self._confirm_save = False
        self._at_paper_pos = False
        self._is_homed = False
        self._probe_x = 117.5
        self._probe_y = 112.5

        self.setObjectName("ZOffsetScreen")
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

        self.title_lbl = QtWidgets.QLabel("Z-OFFSET CALIBRATION")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        title_col.addWidget(self.title_lbl)

        header_layout.addLayout(title_col, 1)

        # Probe Section badge
        self.section_badge = QtWidgets.QLabel("[LOAD_CELL_PROBE]")
        self.section_badge.setStyleSheet("""
            color: #00E5FF;
            font-size: 10px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
            background: rgba(0, 229, 255, 0.15);
            border: 1px solid rgba(0, 229, 255, 0.4);
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header_layout.addWidget(self.section_badge)

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

        # --- Body: Left (Squish Diagram & Paper Test) | Right (Digital Readout & Step Buttons) ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # Left Column: Canvas + Paper Friction Test Control Box
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(_s(6, scale))

        self.canvas = ZOffsetVisualCanvas()
        left_col.addWidget(self.canvas, 1)

        # --- Dedicated Paper Friction Test Box ---
        paper_box = QtWidgets.QFrame()
        paper_box.setObjectName("PaperBox")
        paper_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        paper_box.setStyleSheet("""
            QFrame#PaperBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: 8px;
            }
        """)
        pb_layout = QtWidgets.QVBoxLayout(paper_box)
        pb_layout.setContentsMargins(10, 8, 10, 8)
        pb_layout.setSpacing(6)

        # Header row of Paper Test
        pb_hdr = QtWidgets.QHBoxLayout()
        pb_title = QtWidgets.QLabel("📄 PAPER FRICTION TEST")
        pb_title.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        pb_hdr.addWidget(pb_title)
        pb_hdr.addStretch(1)

        self.probe_pos_badge = QtWidgets.QLabel(f"Probe: X{self._probe_x:.1f} Y{self._probe_y:.1f}")
        self.probe_pos_badge.setStyleSheet("""
            color: #94A3B8; font-size: 10px; font-weight: 700; font-family: 'Consolas', monospace;
            background: rgba(148, 163, 184, 0.12); border-radius: 3px; padding: 2px 6px;
        """)
        pb_hdr.addWidget(self.probe_pos_badge)

        self.paper_level_badge = QtWidgets.QLabel("Z: Standby")
        self.paper_level_badge.setStyleSheet("""
            color: #94A3B8; font-size: 10px; font-weight: 800; font-family: 'Consolas', monospace;
            background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 3px; padding: 2px 6px;
        """)
        pb_hdr.addWidget(self.paper_level_badge)
        pb_layout.addLayout(pb_hdr)

        # Buttons row: Move to probe area & Level | Lift
        pb_btn_row = QtWidgets.QHBoxLayout()
        pb_btn_row.setSpacing(6)

        self.paper_btn = QtWidgets.QPushButton("🎯  Move to Probe Area && Level")
        self.paper_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paper_btn.setStyleSheet(_BTN_PRIMARY)
        self.paper_btn.setToolTip("Home if not homed, center over probe area, and lower to Z=0.0 for paper drag check")
        self.paper_btn.clicked.connect(self._on_move_to_probe_area)
        pb_btn_row.addWidget(self.paper_btn, 2)

        self.lift_btn = QtWidgets.QPushButton("⬆  Lift (Z=10)")
        self.lift_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lift_btn.setStyleSheet(_BTN_GHOST)
        self.lift_btn.setToolTip("Safely lift nozzle 10mm above bed")
        self.lift_btn.clicked.connect(self._on_lift_nozzle)
        pb_btn_row.addWidget(self.lift_btn, 1)

        pb_layout.addLayout(pb_btn_row)

        self.paper_status = QtWidgets.QLabel("Tap button to home & position nozzle at Z=0.0 mm for paper friction check.")
        self.paper_status.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 600;")
        self.paper_status.setWordWrap(True)
        pb_layout.addWidget(self.paper_status)

        left_col.addWidget(paper_box)
        body.addLayout(left_col, 3)

        # Right Column: Controls
        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(6, scale))

        # Card 1: Stored value in config
        stored_box = QtWidgets.QFrame()
        stored_box.setObjectName("StoredBox")
        stored_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        stored_box.setStyleSheet("""
            QFrame#StoredBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(148, 163, 184, 0.3);
                border-radius: 8px;
            }
        """)
        sb_layout = QtWidgets.QHBoxLayout(stored_box)
        sb_layout.setContentsMargins(10, 6, 10, 6)

        sb_col = QtWidgets.QVBoxLayout()
        sb_col.setSpacing(1)
        sb_title = QtWidgets.QLabel("STORED CONFIG VALUE")
        sb_title.setStyleSheet(_LBL_HDR)
        sb_col.addWidget(sb_title)
        self.stored_lbl = QtWidgets.QLabel("-0.200 mm")
        self.stored_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 800; font-family: 'Consolas', monospace;")
        sb_col.addWidget(self.stored_lbl)
        sb_layout.addLayout(sb_col, 1)

        self.reset_btn = QtWidgets.QPushButton("Reset")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(_BTN_GHOST)
        self.reset_btn.setToolTip("Reset target offset back to stored config value")
        self.reset_btn.clicked.connect(self._on_reset)
        sb_layout.addWidget(self.reset_btn)
        side.addWidget(stored_box)

        # Card 2: Target Offset Readout & Delta
        target_box = QtWidgets.QFrame()
        target_box.setObjectName("TargetBox")
        target_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        target_box.setStyleSheet("""
            QFrame#TargetBox {
                background: rgba(0, 229, 255, 0.08);
                border: 1px solid rgba(0, 229, 255, 0.45);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        tb_layout = QtWidgets.QVBoxLayout(target_box)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(2)

        tb_hdr = QtWidgets.QLabel("TARGET PROBE Z-OFFSET")
        tb_hdr.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        tb_layout.addWidget(tb_hdr)

        tb_row = QtWidgets.QHBoxLayout()
        self.target_lbl = QtWidgets.QLabel("-0.200 mm")
        self.target_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-size: 24px;
            font-weight: 900;
            font-family: 'Consolas', monospace;
        """)
        tb_row.addWidget(self.target_lbl)

        self.delta_badge = QtWidgets.QLabel("Δ 0.000")
        self.delta_badge.setStyleSheet("""
            color: #34D399;
            font-size: 11px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
            background: rgba(52, 211, 153, 0.15);
            border: 1px solid rgba(52, 211, 153, 0.4);
            border-radius: 4px;
            padding: 2px 6px;
        """)
        tb_row.addWidget(self.delta_badge)
        tb_row.addStretch(1)
        tb_layout.addLayout(tb_row)
        side.addWidget(target_box)

        # Step Size Selector
        step_hdr = QtWidgets.QLabel("INCREMENT STEP SIZE")
        step_hdr.setStyleSheet(_LBL_HDR)
        side.addWidget(step_hdr)

        step_row = QtWidgets.QHBoxLayout()
        step_row.setSpacing(4)
        self.step_btns = {}
        for s_val in (0.005, 0.010, 0.050, 0.100):
            lbl_txt = f"{s_val:g}mm"
            btn = QtWidgets.QPushButton(lbl_txt)
            btn.setCheckable(True)
            btn.setChecked(abs(s_val - self._step_size) < 1e-6)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 41, 59, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 6px;
                    color: #94A3B8;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 3px 6px;
                    min-height: 22px;
                }
                QPushButton:hover { border-color: #00E5FF; color: #FFFFFF; }
                QPushButton:checked {
                    background: rgba(0, 229, 255, 0.2);
                    border: 1.5px solid #00E5FF;
                    color: #00E5FF;
                }
            """)
            btn.clicked.connect(lambda _=False, v=s_val: self._set_step_size(v))
            step_row.addWidget(btn)
            self.step_btns[s_val] = btn
        side.addLayout(step_row)

        # Jog / Increment Buttons (Up / Down)
        jog_row = QtWidgets.QHBoxLayout()
        jog_row.setSpacing(6)

        self.up_btn = QtWidgets.QPushButton("▲  UP (+)")
        self.up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.up_btn.setStyleSheet(_BTN_ADJUST)
        self.up_btn.setToolTip("Raise nozzle farther from bed (less friction / squish)")
        self.up_btn.clicked.connect(lambda: self._adjust_offset(+self._step_size))
        jog_row.addWidget(self.up_btn, 1)

        self.down_btn = QtWidgets.QPushButton("▼  DOWN (-)")
        self.down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.down_btn.setStyleSheet(_BTN_ADJUST)
        self.down_btn.setToolTip("Lower nozzle closer to bed (more friction / squish)")
        self.down_btn.clicked.connect(lambda: self._adjust_offset(-self._step_size))
        jog_row.addWidget(self.down_btn, 1)

        side.addLayout(jog_row)

        # Save Button
        self.save_btn = QtWidgets.QPushButton("💾  Save to Config (SAVE_CONFIG)")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(_BTN_SAVE)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save_config)
        side.addWidget(self.save_btn)

        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side)
        side_widget.setMinimumWidth(260)
        side_widget.setMaximumWidth(340)
        body.addWidget(side_widget, 2)

        card_layout.addLayout(body, 1)

        # --- Bottom Status Bar ---
        bottom_row = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Reading probe z_offset from Klipper config...")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bottom_row.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bottom_row.addWidget(self.close_btn)

        card_layout.addLayout(bottom_row)

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(40, self.refresh)

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _host(self, mr):
        return mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

    def _ui(self, mr, fn):
        if mr is not None and hasattr(mr, "_dispatch_signal"):
            mr._dispatch_signal.emit(fn)
        else:
            QtCore.QTimer.singleShot(0, fn)

    def _set_step_size(self, val: float):
        self._step_size = val
        for s_val, btn in self.step_btns.items():
            btn.setChecked(abs(s_val - val) < 1e-6)

    def refresh(self):
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._probe_section = "load_cell_probe"
            self._stored_z = -0.200
            self._target_z = -0.200
            self._clearance_delta = 0.0
            self._update_display()
            self.status_lbl.setText("Printer offline (simulated z_offset = -0.200 mm).")
            return

        host = self._host(mr)

        def _bg():
            sec = "load_cell_probe"
            val = -0.200
            px = 117.5
            py = 112.5
            try:
                url = f"http://{host}/printer/objects/query?configfile=settings&toolhead"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        st = data.get("result", {}).get("status", {})
                        cfg = (st.get("configfile", {}) or {}).get("settings", {}) or {}
                        for probe_name in ("load_cell_probe", "probe", "bltouch", "smart_effector", "beacon"):
                            if probe_name in cfg and "z_offset" in cfg[probe_name]:
                                sec = probe_name
                                val = float(cfg[probe_name]["z_offset"])
                                break
                        safe = cfg.get("safe_z_home", {})
                        if "home_xy_position" in safe:
                            pos = safe["home_xy_position"]
                            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                                px = float(pos[0])
                                py = float(pos[1])
                        elif "stepper_x" in cfg and "stepper_y" in cfg:
                            px = float(cfg["stepper_x"].get("position_max", 235)) / 2.0
                            py = float(cfg["stepper_y"].get("position_max", 225)) / 2.0
            except Exception:
                pass

            def _apply():
                self._probe_section = sec
                self._stored_z = val
                self._target_z = val
                self._clearance_delta = 0.0
                self._probe_x = px
                self._probe_y = py
                self.probe_pos_badge.setText(f"Probe: X{px:.1f} Y{py:.1f}")
                self._update_display()
                self.status_lbl.setText(f"Loaded {sec} z_offset = {val:+.3f} mm from printer.cfg.")

            self._ui(mr, _apply)

        threading.Thread(target=_bg, daemon=True).start()

    def _update_display(self):
        self.section_badge.setText(f"[{self._probe_section.upper()}]")
        self.stored_lbl.setText(f"{self._stored_z:+.3f} mm")
        self.target_lbl.setText(f"{self._target_z:+.3f} mm")

        delta = self._clearance_delta
        sign = "+" if delta > 0 else ""
        self.delta_badge.setText(f"Δ {sign}{delta:.3f}")

        if abs(delta) < 1e-4:
            self.delta_badge.setStyleSheet("""
                color: #34D399; font-size: 11px; font-weight: 800; font-family: 'Consolas', monospace;
                background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4);
                border-radius: 4px; padding: 2px 6px;
            """)
            self.save_btn.setEnabled(False)
        else:
            self.delta_badge.setStyleSheet("""
                color: #FBBF24; font-size: 11px; font-weight: 800; font-family: 'Consolas', monospace;
                background: rgba(251, 191, 36, 0.15); border: 1px solid rgba(251, 191, 36, 0.5);
                border-radius: 4px; padding: 2px 6px;
            """)
            self.save_btn.setEnabled(not self._busy)

        self.canvas.set_values(self._stored_z, self._target_z, self._clearance_delta)

    def _adjust_offset(self, step: float):
        if self._busy:
            return
        self._clearance_delta = round(self._clearance_delta + step, 4)
        # In Klipper: new_probe_z_offset = stored_z - clearance_delta (where +clearance raises nozzle)
        self._target_z = round(self._stored_z - self._clearance_delta, 4)
        self._update_display()

        sign = "+" if self._clearance_delta > 0 else ""
        delta_str = f"{sign}{self._clearance_delta:.3f} mm"

        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.adjust_z_offset(step)
            if self._at_paper_pos:
                self.status_lbl.setText(f"Jogged Z by {step:+.3f} mm (Δ {delta_str}). Test paper friction.")
                self.paper_status.setText(f"Live jog applied ({step:+.3f} mm). Slide paper to feel friction.")
            else:
                self.status_lbl.setText(f"Target offset: {self._target_z:+.3f} mm (Δ {delta_str}). Tap Save to apply.")
        else:
            self.status_lbl.setText(f"Target offset: {self._target_z:+.3f} mm (Δ {delta_str}). Tap Save to apply.")

        # Immediately reflect new Z location on Home screen & Print screen
        win = self.window()
        pages = getattr(win, "pages", {}) if win else {}
        hp = pages.get("home")
        if hp and hasattr(hp, "_coords") and hasattr(hp, "axis_cards"):
            hp._coords["Z"] = round(float(hp._coords.get("Z", 0.0)) + step, 4)
            is_h = ("z" in getattr(hp, "_homed", "")) if (mr and mr.connected) else True
            hp.axis_cards["Z"].set_position(hp._coords["Z"], is_h)
        pp = pages.get("printing")
        if pp and hasattr(pp, "update_z_babystep"):
            b_cnt = getattr(mr, "babystep_count", 0) if mr else round(self._clearance_delta / max(self._step_size, 0.001))
            pp.update_z_babystep(self._clearance_delta, base_z=self._stored_z, step_count=b_cnt)

    def _on_reset(self):
        if self._busy:
            return
        self._clearance_delta = 0.0
        self._target_z = self._stored_z
        self._confirm_save = False
        self._update_display()

        mr = self._get_moonraker()
        if self._at_paper_pos and mr and mr.connected:
            mr.send_gcode("SET_GCODE_OFFSET Z=0 MOVE=1 MOVE_SPEED=5")
            self.paper_status.setText("Reset Z offset to 0. Nozzle returned to nominal Z=0.0 mm.")
        self.status_lbl.setText(f"Reset target z_offset to stored value ({self._stored_z:+.3f} mm).")

    def _on_move_to_probe_area(self):
        """Move to safe probe area, homing first only if not already homed, then descend to Z=0.0."""
        if self._busy:
            return

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._at_paper_pos = True
            self.paper_status.setText(f"Simulated: At probe center (X{self._probe_x:.1f} Y{self._probe_y:.1f}) at Z=0.00 mm. Slide paper to test.")
            self.status_lbl.setText("Simulated paper test position (Z=0.0 mm).")
            self.paper_level_badge.setText("Z: 0.00 mm")
            self.paper_level_badge.setStyleSheet("""
                color: #00E5FF; font-size: 10px; font-weight: 800; font-family: 'Consolas', monospace;
                background: rgba(0, 229, 255, 0.2); border: 1px solid #00E5FF;
                border-radius: 3px; padding: 2px 6px;
            """)
            return

        self._busy = True
        self.paper_btn.setEnabled(False)
        self.paper_btn.setText("⏳ Positioning...")
        self.status_lbl.setText("Checking homing status...")
        self.paper_status.setText("Checking printer homing status...")

        host = self._host(mr)

        def _bg():
            # Check if toolhead is already homed
            homed_axes = ""
            try:
                url = f"http://{host}/printer/objects/query?toolhead"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        d = json.loads(resp.read().decode("utf-8"))
                        th = d.get("result", {}).get("status", {}).get("toolhead", {})
                        homed_axes = th.get("homed_axes", "")
            except Exception:
                pass

            already_homed = ('x' in homed_axes and 'y' in homed_axes and 'z' in homed_axes)

            gcode_lines = []
            if not already_homed:
                # Home first if not already homed
                gcode_lines.append("G28")

            # Absolute positioning, safe Z hop, move to probe area XY, then lower to Z=0.0
            gcode_lines.extend([
                "G90",
                "G1 Z10 F1200",
                f"G1 X{self._probe_x:.1f} Y{self._probe_y:.1f} F6000",
                "G1 Z0.0 F300",
            ])
            full_gcode = "\n".join(gcode_lines)

            def _start_send():
                if not already_homed:
                    self.status_lbl.setText(f"Homing printer (G28) and positioning at probe area (X{self._probe_x:.1f} Y{self._probe_y:.1f} Z0.0)...")
                    self.paper_status.setText("Homing axes, then moving to probe center at Z=0.0 mm...")
                else:
                    self.status_lbl.setText(f"Already homed. Moving directly to probe area (X{self._probe_x:.1f} Y{self._probe_y:.1f} Z0.0)...")
                    self.paper_status.setText("Moving directly to probe center at Z=0.0 mm...")

                mr.send_gcode(full_gcode, on_done=lambda ok: self._ui(mr, lambda: self._on_probe_pos_arrived(ok)), timeout=60.0)

            self._ui(mr, _start_send)

        threading.Thread(target=_bg, daemon=True).start()

    def _on_probe_pos_arrived(self, ok: bool):
        self._busy = False
        self.paper_btn.setEnabled(True)
        self.paper_btn.setText("🎯  Move to Probe Area && Level")
        if ok:
            self._at_paper_pos = True
            self.paper_level_badge.setText("Z: 0.00 mm")
            self.paper_level_badge.setStyleSheet("""
                color: #00E5FF; font-size: 10px; font-weight: 800; font-family: 'Consolas', monospace;
                background: rgba(0, 229, 255, 0.2); border: 1px solid #00E5FF;
                border-radius: 3px; padding: 2px 6px;
            """)
            self.paper_status.setText("✅ Nozzle at probe level (Z=0.0 mm). Slide paper underneath & use UP/DOWN to adjust.")
            self.status_lbl.setText(f"Positioned at probe area (X{self._probe_x:.1f} Y{self._probe_y:.1f} Z0.0). Slide paper to test friction.")
        else:
            self.paper_status.setText("⚠️ Failed to position nozzle. Check printer / Klipper status.")
            self.status_lbl.setText("Failed to move to probe area.")

    def _on_lift_nozzle(self):
        """Safely lift nozzle 10mm above the bed."""
        if self._busy:
            return
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._at_paper_pos = False
            self.paper_level_badge.setText("Z: +10.0 mm")
            self.paper_level_badge.setStyleSheet("""
                color: #94A3B8; font-size: 10px; font-weight: 700; font-family: 'Consolas', monospace;
                background: rgba(148, 163, 184, 0.12); border-radius: 3px; padding: 2px 6px;
            """)
            self.paper_status.setText("Simulated: Nozzle lifted to safe clearance (Z=10.0 mm).")
            self.status_lbl.setText("Nozzle lifted to Z=10.0 mm.")
            return

        self._busy = True
        self.lift_btn.setEnabled(False)
        self.paper_status.setText("Lifting nozzle to Z=10.0 mm...")
        self.status_lbl.setText("Raising nozzle (G90 G1 Z10)...")

        def _done(ok: bool):
            self._busy = False
            self.lift_btn.setEnabled(True)
            self._at_paper_pos = False
            if ok:
                self.paper_level_badge.setText("Z: +10.0 mm")
                self.paper_level_badge.setStyleSheet("""
                    color: #94A3B8; font-size: 10px; font-weight: 700; font-family: 'Consolas', monospace;
                    background: rgba(148, 163, 184, 0.12); border-radius: 3px; padding: 2px 6px;
                """)
                self.paper_status.setText("Nozzle safely parked at Z=10.0 mm.")
                self.status_lbl.setText("Nozzle raised to Z=10.0 mm.")
            else:
                self.status_lbl.setText("Lift command failed.")

        mr.send_gcode("G90\nG1 Z10 F1200", on_done=lambda ok: self._ui(mr, lambda: _done(ok)), timeout=10.0)

    def _on_save_config(self):
        if self._busy or abs(self._clearance_delta) < 1e-4:
            return

        # Two-tap armed confirmation
        if not self._confirm_save:
            self._confirm_save = True
            self.save_btn.setText("⚠️  Tap Again to Confirm (Restart)")
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F59E0B, stop:1 #D97706);
                    border: 1.5px solid #FCD34D; border-radius: 7px; color: #FFFFFF;
                    font-size: 12px; font-weight: 900; min-height: 32px; padding: 2px 10px;
                }
            """)
            self.status_lbl.setText("Confirm: Saving will apply offset and restart Klipper (SAVE_CONFIG).")
            QtCore.QTimer.singleShot(4500, self._disarm_save)
            return

        self._confirm_save = False
        self._busy = True
        self.save_btn.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.paper_btn.setEnabled(False)
        self.lift_btn.setEnabled(False)

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._stored_z = self._target_z
            self._clearance_delta = 0.0
            self._busy = False
            self.up_btn.setEnabled(True)
            self.down_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
            self.paper_btn.setEnabled(True)
            self.lift_btn.setEnabled(True)
            self._disarm_save()
            self._update_display()
            self.status_lbl.setText(f"✓ Saved new z_offset = {self._stored_z:+.3f} mm (simulated).")
            return

        # Ensure gcode offset matches our clearance adjustment, then apply to probe and SAVE_CONFIG
        cmd = (
            f"SET_GCODE_OFFSET Z={self._clearance_delta:+.4f} MOVE=0\n"
            f"Z_OFFSET_APPLY_PROBE\n"
            f"SAVE_CONFIG"
        )

        self.status_lbl.setText(f"Applying z_offset ({self._target_z:+.3f} mm) and saving config...")
        mr.send_gcode(cmd, on_done=self._after_save_restart, timeout=30.0)

    def _disarm_save(self):
        self._confirm_save = False
        self.save_btn.setText("💾  Save to Config (SAVE_CONFIG)")
        self.save_btn.setStyleSheet(_BTN_SAVE)

    def _after_save_restart(self, ok: bool):
        self.status_lbl.setText("Klipper restarting to apply new z_offset in printer.cfg...")
        mr = self._get_moonraker()
        host = self._host(mr) if mr else "127.0.0.1:7125"
        self._restart_tries = 0

        def _poll():
            self._restart_tries += 1
            ready = False
            try:
                url = f"http://{host}/printer/info"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        ready = (data.get("result", {}).get("state") == "ready")
            except Exception:
                pass

            if ready:
                def _fin():
                    self._busy = False
                    self.up_btn.setEnabled(True)
                    self.down_btn.setEnabled(True)
                    self.reset_btn.setEnabled(True)
                    self.paper_btn.setEnabled(True)
                    self.lift_btn.setEnabled(True)
                    self._disarm_save()
                    self.refresh()
                self._ui(mr, _fin)
            elif self._restart_tries < 30:
                threading.Timer(1.0, _poll).start()
            else:
                def _timeout():
                    self._busy = False
                    self.up_btn.setEnabled(True)
                    self.down_btn.setEnabled(True)
                    self.reset_btn.setEnabled(True)
                    self.paper_btn.setEnabled(True)
                    self.lift_btn.setEnabled(True)
                    self._disarm_save()
                    self.status_lbl.setText("Klipper restart timeout. Check printer.")
                self._ui(mr, _timeout)

        threading.Timer(2.0, _poll).start()

    def accept(self):
        self._safety_park()
        self.closed.emit()

    def reject(self):
        self._safety_park()
        self.closed.emit()

    def _safety_park(self):
        # If closing while nozzle is resting at paper test position, lift to safe height
        if self._at_paper_pos:
            mr = self._get_moonraker()
            if mr and mr.connected:
                mr.send_gcode("G90\nG1 Z10 F1200")
            self._at_paper_pos = False

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("zoffset", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
