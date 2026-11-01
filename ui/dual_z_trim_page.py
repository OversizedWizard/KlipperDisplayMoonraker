"""Manual Dual Z Lead Screw Trim Screen.

For printers with dual Z lead screws / motors that do not use independent stepper drivers
(i.e. no [z_tilt] or [quad_gantry_level]), this screen probes the Left side as a fixed reference,
probes the Right side to measure tilt deviation (ΔZ), and guides the user with real-time
animations on how much to manually turn the right Z motor/coupler (CW raises bed, CCW lowers bed).
"""

import json
import math
import re
import threading
import time
import urllib.request
from typing import Optional, Tuple

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


C_CYAN = QtGui.QColor("#00E5FF")
C_GREEN = QtGui.QColor("#34D399")
C_AMBER = QtGui.QColor("#FBBF24")
C_RED = QtGui.QColor("#EF4444")
C_SLATE = QtGui.QColor("#94A3B8")

# Acceptable Z alignment tolerance between left & right lead screws
ACCEPTABLE_TOLERANCE_MM = 0.035


class DualZTrimCanvas(QtWidgets.QWidget):
    """Animated visualizer showing:
    1. Left: Gantry / Bed cross-section with Left (Reference) and Right (Adjustable) Z lead screws,
       tilting bed/gantry beam, and animated probing toolhead.
    2. Right: Animated Stepper Motor / Lead Screw Coupler Knob turning CW or CCW with directional
       arrows and degree / clock-minute turn guidance.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 230)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self.left_z: Optional[float] = None
        self.right_z: Optional[float] = None
        self.diff_z: Optional[float] = None
        self.lead_mm: float = 8.0

        # Probing state: "idle", "probing_left", "probing_right", "done"
        self.probe_state: str = "idle"
        self.toolhead_x_norm: float = 0.5  # 0.18 = left, 0.82 = right, 0.5 = parked center
        self._target_x_norm: float = 0.5
        self._nozzle_z_anim: float = 0.0

        # Animation phase for motor rotation & arrows
        self._anim_angle: float = 0.0
        self._pulse_phase: float = 0.0

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)  # ~33 FPS smooth animation
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_readings(self, left_z: Optional[float], right_z: Optional[float], lead_mm: float = 8.0):
        self.left_z = left_z
        self.right_z = right_z
        self.lead_mm = max(0.5, float(lead_mm))
        if left_z is not None and right_z is not None:
            self.diff_z = round(right_z - left_z, 4)
        else:
            self.diff_z = None
        self.update()

    def set_probe_state(self, state: str):
        self.probe_state = state
        if state == "probing_left":
            self._target_x_norm = 0.18
        elif state == "probing_right":
            self._target_x_norm = 0.82
        else:
            self._target_x_norm = 0.50
        self.update()

    def _tick(self):
        self._pulse_phase = (self._pulse_phase + 0.09) % (math.pi * 2.0)

        # Smooth horizontal toolhead interpolation
        dx = self._target_x_norm - self.toolhead_x_norm
        if abs(dx) > 0.005:
            self.toolhead_x_norm += dx * 0.18
        else:
            self.toolhead_x_norm = self._target_x_norm

        # Vertical probe bobbing during active probing
        if self.probe_state in ("probing_left", "probing_right"):
            self._nozzle_z_anim = (math.sin(self._pulse_phase * 2.2) + 1.0) * 0.5
        else:
            self._nozzle_z_anim *= 0.8

        # Rotate motor coupler in required direction when out of tolerance
        if self.diff_z is not None and abs(self.diff_z) > ACCEPTABLE_TOLERANCE_MM:
            # diff_z < 0 means Right side is LOWER -> Turn CW to raise bed
            # diff_z > 0 means Right side is HIGHER -> Turn CCW to lower bed
            step = 2.6 if self.diff_z < 0 else -2.6
            self._anim_angle = (self._anim_angle + step) % 360.0

        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Outer dark glass container
        rect = QtCore.QRectF(4, 4, w - 8, h - 8)
        bg = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        bg.setColorAt(0.0, QtGui.QColor("#162032"))
        bg.setColorAt(1.0, QtGui.QColor("#0B111E"))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 75), 1.2))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 12, 12)

        # Split canvas: Top/Left 58% = Gantry & Bed diagram, Right 42% = Animated Motor Trim Dial
        split_x = rect.left() + rect.width() * 0.57

        # Vertical divider
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 22), 1.0, Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(split_x, rect.top() + 10), QtCore.QPointF(split_x, rect.bottom() - 10))

        gantry_rect = QtCore.QRectF(rect.left() + 8, rect.top() + 8, (split_x - rect.left()) - 14, rect.height() - 16)
        motor_rect = QtCore.QRectF(split_x + 6, rect.top() + 8, (rect.right() - split_x) - 14, rect.height() - 16)

        self._draw_gantry_section(p, gantry_rect)
        self._draw_motor_dial_section(p, motor_rect)

    def _draw_gantry_section(self, p: QtGui.QPainter, r: QtCore.QRectF):
        # Section Header
        f = p.font()
        f.setPointSizeF(8.0)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C_SLATE)
        p.drawText(QtCore.QRectF(r.left(), r.top(), r.width(), 16), Qt.AlignmentFlag.AlignCenter, "DUAL Z GANTRY & BED TILT")

        left_rod_x = r.left() + r.width() * 0.18
        right_rod_x = r.left() + r.width() * 0.82
        top_y = r.top() + 26
        bot_y = r.bottom() - 32
        rod_h = bot_y - top_y

        # Draw Left & Right Lead Screws with thread lines
        for rx, label, is_right in [(left_rod_x, "LEFT (REF)", False), (right_rod_x, "RIGHT (Z2)", True)]:
            # Lead screw shaft
            shaft_rect = QtCore.QRectF(rx - 4, top_y, 8, rod_h - 22)
            p.setPen(QtGui.QPen(QtGui.QColor("#475569"), 1.0))
            p.setBrush(QtGui.QColor("#1E293B"))
            p.drawRoundedRect(shaft_rect, 2, 2)

            # Thread stripes
            p.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1.0))
            ty = top_y + 4
            while ty < bot_y - 26:
                p.drawLine(QtCore.QPointF(rx - 3.5, ty), QtCore.QPointF(rx + 3.5, ty + 3))
                ty += 6

            # Bottom stepper motor block
            m_rect = QtCore.QRectF(rx - 14, bot_y - 22, 28, 22)
            m_col = QtGui.QColor("#0F172A")
            border_col = C_CYAN if not is_right else (
                C_GREEN if (self.diff_z is not None and abs(self.diff_z) <= ACCEPTABLE_TOLERANCE_MM)
                else (C_AMBER if self.diff_z is not None else QtGui.QColor("#64748B"))
            )
            p.setPen(QtGui.QPen(border_col, 1.5))
            p.setBrush(m_col)
            p.drawRoundedRect(m_rect, 4, 4)

            # Motor label below
            f.setPointSizeF(7.2)
            p.setFont(f)
            p.setPen(border_col)
            p.drawText(QtCore.QRectF(rx - 36, bot_y + 3, 72, 14), Qt.AlignmentFlag.AlignCenter, label)

        # Horizontal X-Gantry at top-middle with Moving Toolhead
        gantry_y = top_y + 24
        p.setPen(QtGui.QPen(QtGui.QColor("#334155"), 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QtCore.QPointF(left_rod_x, gantry_y), QtCore.QPointF(right_rod_x, gantry_y))

        # Toolhead carriage position
        th_x = r.left() + r.width() * self.toolhead_x_norm
        th_y = gantry_y + self._nozzle_z_anim * 16.0
        th_rect = QtCore.QRectF(th_x - 11, th_y - 9, 22, 18)
        p.setPen(QtGui.QPen(C_CYAN, 1.5))
        p.setBrush(QtGui.QColor("#0F172A"))
        p.drawRoundedRect(th_rect, 4, 4)

        # Nozzle tip
        nozzle_poly = QtGui.QPolygonF([
            QtCore.QPointF(th_x - 4, th_rect.bottom()),
            QtCore.QPointF(th_x + 4, th_rect.bottom()),
            QtCore.QPointF(th_x, th_rect.bottom() + 7),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C_AMBER if self.probe_state in ("probing_left", "probing_right") else C_CYAN)
        p.drawPolygon(nozzle_poly)

        # Bed surface line (tilts based on diff_z)
        bed_base_y = top_y + rod_h * 0.56
        # Reference horizontal dashed line
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 45), 1.2, Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(left_rod_x - 12, bed_base_y), QtCore.QPointF(right_rod_x + 12, bed_base_y))

        # Calculate visual right bed Y offset (exaggerate tilt for clarity, clamp at +-22px)
        tilt_px = 0.0
        if self.diff_z is not None:
            # Positive diff_z means right side is HIGHER (smaller screen Y)
            tilt_px = max(-22.0, min(22.0, -self.diff_z * 65.0))

        left_bed_pt = QtCore.QPointF(left_rod_x - 8, bed_base_y)
        right_bed_pt = QtCore.QPointF(right_rod_x + 8, bed_base_y + tilt_px)

        if self.diff_z is None:
            bed_col = C_CYAN
        elif abs(self.diff_z) <= ACCEPTABLE_TOLERANCE_MM:
            bed_col = C_GREEN
        elif abs(self.diff_z) <= 0.12:
            bed_col = C_AMBER
        else:
            bed_col = C_RED

        p.setPen(QtGui.QPen(bed_col, 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(left_bed_pt, right_bed_pt)

        # Draw Left & Right Z value badges on bed
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)

        l_txt = f"Ref: {self.left_z:.3f}" if self.left_z is not None else "Ref: --"
        p.setPen(C_CYAN)
        p.drawText(QtCore.QRectF(left_rod_x - 32, bed_base_y + 6, 72, 16), Qt.AlignmentFlag.AlignCenter, l_txt)

        r_txt = f"Z: {self.right_z:.3f}" if self.right_z is not None else "Z: --"
        p.setPen(bed_col)
        p.drawText(QtCore.QRectF(right_rod_x - 36, bed_base_y + tilt_px + 6, 72, 16), Qt.AlignmentFlag.AlignCenter, r_txt)

        # Draw up/down adjustment arrow near Right rod if out of tolerance
        if self.diff_z is not None and abs(self.diff_z) > ACCEPTABLE_TOLERANCE_MM:
            arrow_y = bed_base_y + tilt_px - 16
            is_low = self.diff_z < 0  # Need to raise bed (up arrow)
            p.setPen(QtGui.QPen(C_AMBER if is_low else C_RED, 2.2))
            if is_low:
                # Up arrow: Raise Bed
                p.drawLine(QtCore.QPointF(right_rod_x, arrow_y + 10), QtCore.QPointF(right_rod_x, arrow_y - 4))
                p.drawLine(QtCore.QPointF(right_rod_x - 5, arrow_y + 1), QtCore.QPointF(right_rod_x, arrow_y - 4))
                p.drawLine(QtCore.QPointF(right_rod_x + 5, arrow_y + 1), QtCore.QPointF(right_rod_x, arrow_y - 4))
            else:
                # Down arrow: Lower Bed
                p.drawLine(QtCore.QPointF(right_rod_x, arrow_y - 4), QtCore.QPointF(right_rod_x, arrow_y + 10))
                p.drawLine(QtCore.QPointF(right_rod_x - 5, arrow_y + 5), QtCore.QPointF(right_rod_x, arrow_y + 10))
                p.drawLine(QtCore.QPointF(right_rod_x + 5, arrow_y + 5), QtCore.QPointF(right_rod_x, arrow_y + 10))

        # Bottom status pill inside gantry view
        pill_rect = QtCore.QRectF(r.left() + 10, bot_y + 16, r.width() - 20, 16)
        f.setPointSizeF(7.8)
        p.setFont(f)
        if self.probe_state == "probing_left":
            p.setPen(C_CYAN)
            p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, "● Probing Left Reference...")
        elif self.probe_state == "probing_right":
            p.setPen(C_AMBER)
            p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, "● Probing Right Point...")
        elif self.diff_z is not None:
            p.setPen(bed_col)
            p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, f"ΔZ (Right - Left) = {self.diff_z:+.3f} mm")
        else:
            p.setPen(C_SLATE)
            p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, "Tap 'Check' to probe Left & Right")

    def _draw_motor_dial_section(self, p: QtGui.QPainter, r: QtCore.QRectF):
        # Section Header
        f = p.font()
        f.setPointSizeF(8.0)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C_SLATE)
        p.drawText(QtCore.QRectF(r.left(), r.top(), r.width(), 16), Qt.AlignmentFlag.AlignCenter, "RIGHT MOTOR TURN GUIDE")

        cx = r.center().x()
        cy = r.top() + r.height() * 0.47
        radius = min(r.width(), r.height()) * 0.29

        # Determine state & colors
        is_aligned = self.diff_z is not None and abs(self.diff_z) <= ACCEPTABLE_TOLERANCE_MM
        needs_cw = self.diff_z is not None and self.diff_z < -ACCEPTABLE_TOLERANCE_MM  # Right too low -> CW raises bed
        needs_ccw = self.diff_z is not None and self.diff_z > ACCEPTABLE_TOLERANCE_MM  # Right too high -> CCW lowers bed

        if is_aligned:
            ring_col = C_GREEN
        elif needs_cw:
            ring_col = C_AMBER
        elif needs_ccw:
            ring_col = C_RED
        else:
            ring_col = QtGui.QColor("#475569")

        # Outer pulsing glow ring when action is needed or aligned
        pulse_r = radius + 6.0 + math.sin(self._pulse_phase) * 2.5
        glow_col = QtGui.QColor(ring_col)
        glow_col.setAlpha(45)
        p.setPen(QtGui.QPen(glow_col, 4.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QtCore.QPointF(cx, cy), pulse_r, pulse_r)

        # Draw Rotating Motor Coupler / Knurled Wheel
        p.save()
        p.translate(cx, cy)
        p.rotate(self._anim_angle)

        # Coupler body
        grad = QtGui.QRadialGradient(0, 0, radius)
        grad.setColorAt(0.0, QtGui.QColor("#334155"))
        grad.setColorAt(0.75, QtGui.QColor("#1E293B"))
        grad.setColorAt(1.0, QtGui.QColor("#0F172A"))
        p.setPen(QtGui.QPen(ring_col, 2.0))
        p.setBrush(grad)
        p.drawEllipse(QtCore.QPointF(0, 0), radius, radius)

        # Knurled gear teeth around motor coupler
        p.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        num_teeth = 12
        for i in range(num_teeth):
            ang = math.radians(i * (360.0 / num_teeth))
            x1 = math.cos(ang) * (radius * 0.78)
            y1 = math.sin(ang) * (radius * 0.78)
            x2 = math.cos(ang) * (radius * 0.96)
            y2 = math.sin(ang) * (radius * 0.96)
            p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

        # High-contrast indicator notch on the coupler
        p.setPen(QtGui.QPen(ring_col, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QtCore.QPointF(0, -radius * 0.25), QtCore.QPointF(0, -radius * 0.85))

        # Center motor D-shaft bore
        p.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 1.2))
        p.setBrush(QtGui.QColor("#090D16"))
        p.drawEllipse(QtCore.QPointF(0, 0), radius * 0.24, radius * 0.24)
        p.restore()

        # Draw CW or CCW Curved Directional Arrow Arc outside the wheel
        if needs_cw or needs_ccw:
            arc_r = radius + 11.0
            arc_rect = QtCore.QRectF(cx - arc_r, cy - arc_r, arc_r * 2.0, arc_r * 2.0)
            p.setPen(QtGui.QPen(ring_col, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            if needs_cw:
                # Top arc sweeping clockwise (from 135 deg to 45 deg in Qt 1/16th deg units)
                p.drawArc(arc_rect, 135 * 16, -90 * 16)
                # Arrowhead at 45 deg (top-right pointing clockwise/down-right)
                ah_x = cx + math.cos(math.radians(-45)) * arc_r
                ah_y = cy + math.sin(math.radians(-45)) * arc_r
                p.drawLine(QtCore.QPointF(ah_x, ah_y), QtCore.QPointF(ah_x - 8, ah_y - 2))
                p.drawLine(QtCore.QPointF(ah_x, ah_y), QtCore.QPointF(ah_x - 1, ah_y - 9))
            else:
                # Top arc sweeping counter-clockwise (from 45 deg to 135 deg)
                p.drawArc(arc_rect, 45 * 16, 90 * 16)
                # Arrowhead at 135 deg (top-left pointing CCW/down-left)
                ah_x = cx + math.cos(math.radians(-135)) * arc_r
                ah_y = cy + math.sin(math.radians(-135)) * arc_r
                p.drawLine(QtCore.QPointF(ah_x, ah_y), QtCore.QPointF(ah_x + 8, ah_y - 2))
                p.drawLine(QtCore.QPointF(ah_x, ah_y), QtCore.QPointF(ah_x + 1, ah_y - 9))

        # Bottom text summary under motor dial
        f.setPointSizeF(8.2)
        f.setBold(True)
        p.setFont(f)
        txt_rect = QtCore.QRectF(r.left(), r.bottom() - 36, r.width(), 34)

        if is_aligned:
            p.setPen(C_GREEN)
            p.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, "✓ LEVEL & TRIMMED\nNo Turn Needed")
        elif needs_cw:
            deg = round((abs(self.diff_z) / self.lead_mm) * 360.0)
            deg_str = f"~{max(1, deg)}°"
            p.setPen(C_AMBER)
            p.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, f"↻ TURN CW ({deg_str})\nRaises Right Bed")
        elif needs_ccw:
            deg = round((abs(self.diff_z) / self.lead_mm) * 360.0)
            deg_str = f"~{max(1, deg)}°"
            p.setPen(C_RED)
            p.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, f"↺ TURN CCW ({deg_str})\nLowers Right Bed")
        else:
            p.setPen(C_SLATE)
            p.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, "CW = Raises Bed\nCCW = Lowers Bed")


_BTN_CHECK = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
    border: 1px solid #38BDF8;
    border-radius: 7px;
    color: #070A10;
    font-size: 13px;
    font-weight: 900;
    min-height: 34px;
    padding: 2px 14px;
}
QPushButton:hover {
    background: #38BDF8;
}
QPushButton:disabled {
    background: rgba(30, 41, 59, 0.6);
    color: #64748B;
    border-color: rgba(255, 255, 255, 0.1);
}
"""

_BTN_PROBE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
    border: 1px solid #34D399;
    border-radius: 7px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 34px;
    padding: 2px 14px;
}
QPushButton:hover {
    background: #10B981;
}
QPushButton:disabled {
    background: rgba(30, 41, 59, 0.6);
    color: #64748B;
    border-color: rgba(255, 255, 255, 0.1);
}
"""

_BTN_GHOST = """
QPushButton {
    background: rgba(30, 41, 59, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 7px;
    color: #F8FAFC;
    font-size: 12px;
    font-weight: 700;
    min-height: 30px;
    padding: 2px 12px;
}
QPushButton:hover {
    background: rgba(51, 65, 85, 0.85);
}
QPushButton:disabled {
    color: #475569;
}
"""

_LBL_HDR = "color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;"


class DualZTrimScreen(QtWidgets.QFrame):
    """Manual Dual Z Motor Alignment / Trim Screen."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._busy = False

        # Coordinates & Lead Screw Config
        self._left_pos: Tuple[float, float] = (30.0, 120.0)
        self._right_pos: Tuple[float, float] = (205.0, 120.0)
        self._park_pos: Tuple[float, float] = (117.5, 120.0)
        self._lead_mm: float = 8.0
        self._hop_z: float = 10.0
        self._speed: float = 120.0

        # Probed Z values
        self._left_z: Optional[float] = None
        self._right_z: Optional[float] = None

        self.setObjectName("DualZTrimScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DualZTrimCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet("""
            QFrame#DualZTrimCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141C2E, stop:1 #0B0F19);
                border: 1px solid rgba(0, 229, 255, 120);
                border-radius: 14px;
            }
            QLabel { border: none; background: transparent; }
        """)
        root.addWidget(self.card)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setContentsMargins(_s(12, scale), _s(8, scale), _s(12, scale), _s(8, scale))
        card_layout.setSpacing(_s(6, scale))

        # --- Header ---
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(_s(8, scale))

        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.icon_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)
        title_lbl = QtWidgets.QLabel("MANUAL DUAL Z MOTOR TRIM")
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        sub_lbl = QtWidgets.QLabel("Probe Left side as reference, then probe Right side & turn right motor (CW raises bed, CCW lowers bed)")
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 600;")
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        header.addLayout(title_col, 1)

        self.tol_badge = QtWidgets.QLabel(f"≤ {ACCEPTABLE_TOLERANCE_MM:.3f} mm LEVEL")
        self.tol_badge.setStyleSheet("""
            color: #34D399;
            font-size: 10px;
            font-weight: 800;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid #10B981;
            border-radius: 4px;
            padding: 2px 8px;
        """)
        header.addWidget(self.tol_badge)

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
        header.addWidget(self.close_x)

        card_layout.addLayout(header)

        # --- Body: Left (Animated Canvas) | Right (Telemetry & Controls) ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # Left Column: Dual Z Gantry + Motor Turn Animation Canvas
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(_s(4, scale))

        self.canvas = DualZTrimCanvas()
        left_col.addWidget(self.canvas, 1)

        legend_row = QtWidgets.QHBoxLayout()
        legend_row.setSpacing(12)
        for col_str, txt in [
            ("#34D399", f"Green = Aligned (≤ {ACCEPTABLE_TOLERANCE_MM:.3f} mm)"),
            ("#FBBF24", "CW Turn = Raises Right Bed"),
            ("#EF4444", "CCW Turn = Lowers Right Bed"),
        ]:
            leg_lbl = QtWidgets.QLabel(f"● {txt}")
            leg_lbl.setStyleSheet(f"color: {col_str}; font-size: 10px; font-weight: 700;")
            legend_row.addWidget(leg_lbl)
        legend_row.addStretch(1)
        left_col.addLayout(legend_row)

        body.addLayout(left_col, 3)

        # Right Column: Reference / Right Z Readouts, Guidance & Buttons
        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(6, scale))

        # 1. Left & Right Probe Readout Card
        readout_box = QtWidgets.QFrame()
        readout_box.setObjectName("ReadoutBox")
        readout_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        readout_box.setStyleSheet("""
            QFrame#ReadoutBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        rb_lay = QtWidgets.QVBoxLayout(readout_box)
        rb_lay.setContentsMargins(10, 6, 10, 6)
        rb_lay.setSpacing(3)

        self.left_ref_lbl = QtWidgets.QLabel("LEFT (REFERENCE):  -- mm")
        self.left_ref_lbl.setStyleSheet("color: #00E5FF; font-size: 12px; font-weight: 900; font-family: 'Consolas', monospace;")
        rb_lay.addWidget(self.left_ref_lbl)

        self.right_val_lbl = QtWidgets.QLabel("RIGHT (MEASURED):  -- mm")
        self.right_val_lbl.setStyleSheet("color: #F8FAFC; font-size: 12px; font-weight: 900; font-family: 'Consolas', monospace;")
        rb_lay.addWidget(self.right_val_lbl)

        self.coords_lbl = QtWidgets.QLabel("Left X: 30.0   Right X: 205.0   Y: 120.0")
        self.coords_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 700;")
        rb_lay.addWidget(self.coords_lbl)

        side.addWidget(readout_box)

        # 2. Difference & Motor Adjustment Guidance Card
        guidance_box = QtWidgets.QFrame()
        guidance_box.setObjectName("GuidanceBox")
        guidance_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        guidance_box.setStyleSheet("""
            QFrame#GuidanceBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
            }
        """)
        gb_lay = QtWidgets.QVBoxLayout(guidance_box)
        gb_lay.setContentsMargins(10, 7, 10, 7)
        gb_lay.setSpacing(3)

        lbl_dev_hdr = QtWidgets.QLabel("DIFFERENCE & RIGHT MOTOR ADJUSTMENT")
        lbl_dev_hdr.setStyleSheet(_LBL_HDR)
        gb_lay.addWidget(lbl_dev_hdr)

        self.diff_lbl = QtWidgets.QLabel("Not Checked Yet")
        self.diff_lbl.setStyleSheet("color: #94A3B8; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
        gb_lay.addWidget(self.diff_lbl)

        self.guidance_note = QtWidgets.QLabel(
            "1. Tap 'Check' to probe Left reference then Right side.\n"
            "2. Turn Right Z motor as shown (CW raises bed).\n"
            "3. Tap 'Probe' to re-test Right point until level."
        )
        self.guidance_note.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        self.guidance_note.setWordWrap(True)
        gb_lay.addWidget(self.guidance_note)

        side.addWidget(guidance_box, 1)

        # 3. Primary Action Buttons: Check (Start) & Probe (Retest Right)
        self.btn_check = QtWidgets.QPushButton("⚡  Check (Probe Left && Right)")
        self.btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check.setStyleSheet(_BTN_CHECK)
        self.btn_check.clicked.connect(self._on_check_both)
        side.addWidget(self.btn_check)

        self.btn_probe = QtWidgets.QPushButton("🔍  Probe (Re-test Right Point)")
        self.btn_probe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_probe.setStyleSheet(_BTN_PROBE)
        self.btn_probe.clicked.connect(self._on_probe_right_only)
        side.addWidget(self.btn_probe)

        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side)
        side_widget.setMinimumWidth(245)
        side_widget.setMaximumWidth(305)
        body.addWidget(side_widget, 2)

        card_layout.addLayout(body, 1)

        # --- Bottom Status Bar ---
        bot = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Ready. Tap 'Check' to measure Left reference and Right side.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bot.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bot.addWidget(self.close_btn)

        card_layout.addLayout(bot)

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(40, self._load_config)

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _load_config(self):
        mr = self._get_moonraker()
        cfg = mr.config if mr else {}

        bx, by = 235.0, 225.0
        x_min, y_min = 0.0, 0.0
        if "stepper_x" in cfg:
            bx = float(cfg["stepper_x"].get("position_max", 235.0))
            x_min = float(cfg["stepper_x"].get("position_min", 0.0))
        if "stepper_y" in cfg:
            by = float(cfg["stepper_y"].get("position_max", 225.0))
            y_min = float(cfg["stepper_y"].get("position_min", 0.0))

        if "stepper_z" in cfg:
            try:
                self._lead_mm = float(cfg["stepper_z"].get("rotation_distance", 8.0))
            except Exception:
                self._lead_mm = 8.0

        # Determine safe Left & Right probe points along mid-Y
        mid_y = round(( max(0.0, y_min) + by ) / 2.0, 1)
        left_x = round(max(x_min + 25.0, 30.0), 1)
        right_x = round(min(bx - 25.0, bx - 30.0), 1)

        # If bed_mesh is configured, stay safely inside mesh_min / mesh_max X bounds
        if "bed_mesh" in cfg:
            bm = cfg["bed_mesh"]
            m_min = bm.get("mesh_min")
            m_max = bm.get("mesh_max")
            try:
                if isinstance(m_min, str):
                    m_min = [float(v.strip()) for v in m_min.split(",")]
                if isinstance(m_max, str):
                    m_max = [float(v.strip()) for v in m_max.split(",")]
                if isinstance(m_min, (list, tuple)) and len(m_min) >= 2:
                    left_x = round(max(left_x, float(m_min[0]) + 15.0), 1)
                if isinstance(m_max, (list, tuple)) and len(m_max) >= 2:
                    right_x = round(min(right_x, float(m_max[0]) - 15.0), 1)
            except Exception:
                pass

        self._left_pos = (left_x, mid_y)
        self._right_pos = (right_x, mid_y)
        self._park_pos = (round((left_x + right_x) / 2.0, 1), mid_y)

        self.coords_lbl.setText(
            f"Left X: {left_x:.1f}   Right X: {right_x:.1f}   Y: {mid_y:.1f}   (Lead: {self._lead_mm:.0f}mm)"
        )
        self.canvas.set_readings(self._left_z, self._right_z, self._lead_mm)

    def _update_ui_from_readings(self):
        self.canvas.set_readings(self._left_z, self._right_z, self._lead_mm)

        if self._left_z is not None:
            self.left_ref_lbl.setText(f"LEFT (REFERENCE):  {self._left_z:.3f} mm")
        else:
            self.left_ref_lbl.setText("LEFT (REFERENCE):  -- mm")

        if self._right_z is not None:
            self.right_val_lbl.setText(f"RIGHT (MEASURED):  {self._right_z:.3f} mm")
        else:
            self.right_val_lbl.setText("RIGHT (MEASURED):  -- mm")

        if self._left_z is None or self._right_z is None:
            return

        diff = round(self._right_z - self._left_z, 4)
        abs_diff = abs(diff)
        deg = round((abs_diff / max(0.5, self._lead_mm)) * 360.0)
        mins = round((abs_diff / max(0.5, self._lead_mm)) * 60.0)

        if abs_diff <= ACCEPTABLE_TOLERANCE_MM:
            self.diff_lbl.setText(f"✓ LEVEL (ΔZ = {diff:+.3f} mm)")
            self.diff_lbl.setStyleSheet("color: #34D399; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
            self.guidance_note.setText(
                f"✓ EXCELLENT! Right side matches Left reference within {abs_diff:.3f} mm "
                f"(≤ {ACCEPTABLE_TOLERANCE_MM:.3f} mm tolerance). No motor adjustment needed!"
            )
        elif diff < 0:
            # Right side triggered lower -> Right side of bed is TOO LOW -> Turn CW to RAISE bed
            self.diff_lbl.setText(f"▲ RIGHT LOW ({diff:+.3f} mm)")
            self.diff_lbl.setStyleSheet("color: #FBBF24; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
            turn_hint = f"~{max(1, deg)}° ({max(1, mins)} min)" if deg >= 3 else "a tiny nudge (~2°)"
            self.guidance_note.setText(
                f"Right side is {abs_diff:.3f} mm LOWER than Left reference.\n"
                f"👉 Turn RIGHT motor a little CW ({turn_hint}) to RAISE the bed, then tap 'Probe' to test again."
            )
        else:
            # Right side triggered higher -> Right side of bed is TOO HIGH -> Turn CCW to LOWER bed
            self.diff_lbl.setText(f"▼ RIGHT HIGH ({diff:+.3f} mm)")
            self.diff_lbl.setStyleSheet("color: #EF4444; font-size: 15px; font-weight: 900; font-family: 'Consolas', monospace;")
            turn_hint = f"~{max(1, deg)}° ({max(1, mins)} min)" if deg >= 3 else "a tiny nudge (~2°)"
            self.guidance_note.setText(
                f"Right side is {abs_diff:.3f} mm HIGHER than Left reference.\n"
                f"👉 Turn RIGHT motor a little CCW ({turn_hint}) to LOWER the bed, then tap 'Probe' to test again."
            )

    def _has_load_cell(self, mr) -> bool:
        if not mr:
            return False
        if hasattr(mr, "has_load_cell") and mr.has_load_cell():
            return True
        if hasattr(mr, "objects"):
            return any("load_cell" in str(o).lower() for o in mr.objects)
        return False

    def _fetch_recent_probe_readings(self, host: str, start_t: float) -> list:
        readings = []
        try:
            url = f"http://{host}/server/gcode_store?count=40"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("result", {}).get("gcode_store", []):
                        if float(item.get("time", 0.0)) < start_t - 1.0:
                            continue
                        msg = item.get("message", "")
                        m = re.search(r"(?:contact at|Result is|probe at [^i]+ is)\s+z=\s*([\d\.-]+)", msg, re.IGNORECASE)
                        if m:
                            readings.append(float(m.group(1)))
        except Exception:
            pass

        # Fallback: query probe / load_cell_probe last_z_result if single reading wasn't caught
        if not readings:
            try:
                url = f"http://{host}/printer/objects/query?probe&load_cell_probe"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        st = data.get("result", {}).get("status", {})
                        for k in ("load_cell_probe", "probe"):
                            if k in st and st[k].get("last_z_result") is not None:
                                readings.append(float(st[k]["last_z_result"]))
                                break
            except Exception:
                pass
        return readings

    def _on_check_both(self):
        """Probes Left side (Reference) first, then probes Right side, and shows difference & motor guidance."""
        if self._busy:
            return

        self._busy = True
        self.btn_check.setEnabled(False)
        self.btn_probe.setEnabled(False)
        self.btn_check.setText("⏳  Checking Left && Right...")
        self.canvas.set_probe_state("probing_left")

        lx, ly = self._left_pos
        rx, ry = self._right_pos
        px, py = self._park_pos

        self.status_lbl.setText(f"Probing Left Reference (X{lx:.0f} Y{ly:.0f}), then Right point (X{rx:.0f} Y{ry:.0f})...")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            # Simulation mode when offline
            QtCore.QTimer.singleShot(600, lambda: self.canvas.set_probe_state("probing_right"))
            QtCore.QTimer.singleShot(1200, self._finish_simulated_check)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()
        speed_f = int(self._speed * 60)
        hop = int(self._hop_z)
        tare_step = "G4 P250\nLOAD_CELL_TARE\nG4 P100\n" if self._has_load_cell(mr) else ""
        home_prefix = "G28\n" if "xyz" not in (mr.homed_axes or "").lower() else ""

        cmd = (
            f"{home_prefix}"
            f"G90\n"
            f"G1 Z{hop} F1200\n"
            f"G1 X{lx:.2f} Y{ly:.2f} F{speed_f}\n"
            f"{tare_step}"
            f"PROBE\n"
            f"G91\n"
            f"G1 Z{hop} F1200\n"
            f"G90\n"
            f"G1 X{rx:.2f} Y{ry:.2f} F{speed_f}\n"
            f"{tare_step}"
            f"PROBE\n"
            f"G91\n"
            f"G1 Z15 F1200\n"
            f"G90\n"
            f"G1 X{px:.2f} Y{py:.2f} F{speed_f}"
        )

        # Mid-way UI animation transition from Left to Right
        QtCore.QTimer.singleShot(3500, lambda: self.canvas.set_probe_state("probing_right") if self._busy else None)

        def _after(ok):
            def _bg():
                readings = self._fetch_recent_probe_readings(host, start_t)

                def _apply():
                    self._busy = False
                    self.btn_check.setEnabled(True)
                    self.btn_probe.setEnabled(True)
                    self.btn_check.setText("⚡  Check (Probe Left && Right)")
                    self.canvas.set_probe_state("done")

                    if len(readings) >= 2:
                        self._left_z = readings[-2]
                        self._right_z = readings[-1]
                        self._update_ui_from_readings()
                        diff = self._right_z - self._left_z
                        self.status_lbl.setText(
                            f"Check complete: Left Ref = {self._left_z:.3f} mm, Right = {self._right_z:.3f} mm (ΔZ = {diff:+.3f} mm)."
                        )
                    elif len(readings) == 1:
                        self._right_z = readings[0]
                        if self._left_z is None:
                            self._left_z = readings[0]
                        self._update_ui_from_readings()
                        self.status_lbl.setText("Probe finished (partial reading captured).")
                    else:
                        self.status_lbl.setText("Probe routine finished, but could not parse Z height from Klipper.")

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode(cmd, on_done=_after, timeout=65.0)

    def _on_probe_right_only(self):
        """Re-probes the Right point to test again after the user turns the right motor."""
        if self._busy:
            return

        # If Left reference hasn't been measured yet, run the full Check (Left then Right)
        if self._left_z is None:
            self._on_check_both()
            return

        self._busy = True
        self.btn_check.setEnabled(False)
        self.btn_probe.setEnabled(False)
        self.btn_probe.setText("⏳  Probing Right Point...")
        self.canvas.set_probe_state("probing_right")

        rx, ry = self._right_pos
        px, py = self._park_pos
        self.status_lbl.setText(f"Re-probing Right point (X{rx:.0f} Y{ry:.0f}) against locked Left Ref ({self._left_z:.3f} mm)...")

        mr = self._get_moonraker()
        if not (mr and mr.connected):
            QtCore.QTimer.singleShot(800, self._finish_simulated_probe_right)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        start_t = time.time()
        speed_f = int(self._speed * 60)
        hop = int(self._hop_z)
        tare_step = "G4 P250\nLOAD_CELL_TARE\nG4 P100\n" if self._has_load_cell(mr) else ""

        cmd = (
            f"G90\n"
            f"G1 Z{hop} F1200\n"
            f"G1 X{rx:.2f} Y{ry:.2f} F{speed_f}\n"
            f"{tare_step}"
            f"PROBE\n"
            f"G91\n"
            f"G1 Z15 F1200\n"
            f"G90\n"
            f"G1 X{px:.2f} Y{py:.2f} F{speed_f}"
        )

        def _after(ok):
            def _bg():
                readings = self._fetch_recent_probe_readings(host, start_t)

                def _apply():
                    self._busy = False
                    self.btn_check.setEnabled(True)
                    self.btn_probe.setEnabled(True)
                    self.btn_probe.setText("🔍  Probe (Re-test Right Point)")
                    self.canvas.set_probe_state("done")

                    if readings:
                        self._right_z = readings[-1]
                        self._update_ui_from_readings()
                        diff = self._right_z - self._left_z
                        self.status_lbl.setText(
                            f"Right re-probed: {self._right_z:.3f} mm vs Left Ref {self._left_z:.3f} mm (ΔZ = {diff:+.3f} mm)."
                        )
                    else:
                        self.status_lbl.setText("Right probe completed.")

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_apply)

            threading.Thread(target=_bg, daemon=True).start()

        mr.send_gcode(cmd, on_done=_after, timeout=45.0)

    def _finish_simulated_check(self):
        self._busy = False
        self.btn_check.setEnabled(True)
        self.btn_probe.setEnabled(True)
        self.btn_check.setText("⚡  Check (Probe Left && Right)")
        self.canvas.set_probe_state("done")
        self._left_z = 1.250
        self._right_z = 1.070  # -0.180 mm (Right side lower -> Turn CW to raise bed)
        self._update_ui_from_readings()
        self.status_lbl.setText("Simulation: Left Ref = 1.250 mm, Right = 1.070 mm (ΔZ = -0.180 mm). Turn right motor CW.")

    def _finish_simulated_probe_right(self):
        self._busy = False
        self.btn_check.setEnabled(True)
        self.btn_probe.setEnabled(True)
        self.btn_probe.setText("🔍  Probe (Re-test Right Point)")
        self.canvas.set_probe_state("done")
        if self._right_z is not None and self._left_z is not None:
            # Move closer to level each simulated probe
            err = self._right_z - self._left_z
            if abs(err) > 0.05:
                self._right_z = round(self._left_z + err * 0.15, 3)
            else:
                self._right_z = round(self._left_z + 0.010, 3)
        self._update_ui_from_readings()
        diff = (self._right_z or 0.0) - (self._left_z or 0.0)
        self.status_lbl.setText(f"Simulation re-probe: Right = {self._right_z:.3f} mm (ΔZ = {diff:+.3f} mm).")

    def accept(self):
        self.closed.emit()

    def reject(self):
        self.closed.emit()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, _s(8, s), m, _s(8, s))
        self.icon_lbl.setPixmap(icons.pixmap("gantry", _s(28, s)))
        self.icon_lbl.setFixedSize(_s(30, s), _s(30, s))

