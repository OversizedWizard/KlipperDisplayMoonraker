"""Extruder & Filament Animation Canvas for Load/Unload sequence.

Visualizes:
1. Toolhead heating up (glow & temperature rise).
2. Filament inserting/gripping or pulling/retracting with rotating drive gear teeth.
3. Filament sensor status indicator (waiting for insertion vs detected).
4. Nozzle extruding molten plastic bead or retracting tip.
"""

import math
from .qt import QtWidgets, QtCore, QtGui, Qt

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class ExtruderAnimationCanvas(QtWidgets.QWidget):
    """Real-time animated extruder toolhead, drive gears, filament path, and molten nozzle."""

    def __init__(self, mode: str = "load", filament_color: str = "#3B82F6", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMinimumSize(280, 200)

        self._mode = mode  # "load" or "unload"
        self._filament_color = filament_color
        self._gear_angle = 0.0
        self._flow_offset = 0.0
        self._stage = "heating"  # "heating", "waiting_sensor", "gripping", "extruding", "pulling", "done", "cancelled"
        self._nozzle_temp = 25.0
        self._target_temp = 210.0
        self._sensor_triggered = False

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(25)  # 40 FPS
        self._timer.timeout.connect(self._step)
        self._timer.start()

    def set_mode(self, mode: str, filament_color: str = None):
        self._mode = mode
        if filament_color:
            self._filament_color = filament_color
        self.update()

    def set_stage(self, stage: str):
        self._stage = stage
        self.update()

    def set_temp(self, current: float, target: float):
        self._nozzle_temp = current
        self._target_temp = target
        self.update()

    def set_sensor_triggered(self, triggered: bool):
        self._sensor_triggered = triggered
        self.update()

    def _step(self):
        # Rotate drive gear when moving filament
        if self._stage in ("gripping", "extruding"):
            self._gear_angle = (self._gear_angle + 4.0) % 360.0
            self._flow_offset = (self._flow_offset + 2.5) % 24.0
        elif self._stage == "pulling":
            self._gear_angle = (self._gear_angle - 4.0) % 360.0
            self._flow_offset = (self._flow_offset - 2.5) % 24.0
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 - 10.0

        # Background subtle tech frame
        painter.setPen(Qt.PenStyle.NoPen)
        grad_bg = QtGui.QRadialGradient(cx, cy + 20, max(w, h) * 0.6)
        grad_bg.setColorAt(0.0, QtGui.QColor(22, 33, 54, 180))
        grad_bg.setColorAt(1.0, QtGui.QColor(10, 15, 26, 230))
        painter.setBrush(grad_bg)
        painter.drawRoundedRect(QtCore.QRectF(10, 10, w - 20, h - 20), 16, 16)

        # 1. Filament Path Guide (Vertical Tube)
        painter.setPen(QtGui.QPen(QtGui.QColor(71, 85, 105, 120), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tube_w = 18.0
        painter.drawRoundedRect(QtCore.QRectF(cx - tube_w / 2, 20, tube_w, cy + 50), 4, 4)

        # 2. Filament Strand
        f_color = QtGui.QColor(self._filament_color)
        f_color_glow = QtGui.QColor(self._filament_color)
        f_color_glow.setAlpha(100)

        # Draw glowing filament line
        f_pen = QtGui.QPen(f_color, 7.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(f_pen)

        if self._mode == "load":
            if self._stage == "waiting_sensor":
                # Partial filament near top sensor
                painter.drawLine(QtCore.QPointF(cx, 25), QtCore.QPointF(cx, cy - 40))
            elif self._stage in ("gripping", "extruding", "done"):
                # Full strand reaching nozzle
                painter.drawLine(QtCore.QPointF(cx, 25), QtCore.QPointF(cx, cy + 70))
            else:
                # Hovering strand
                painter.drawLine(QtCore.QPointF(cx, 25), QtCore.QPointF(cx, cy))
        else: # Unload
            if self._stage in ("pulling", "done"):
                # Retracted up
                painter.drawLine(QtCore.QPointF(cx, 25), QtCore.QPointF(cx, cy - 25))
            else:
                painter.drawLine(QtCore.QPointF(cx, 25), QtCore.QPointF(cx, cy + 60))

        # 3. Dual Drive Gears (Left & Right of Filament)
        gear_r = 22.0
        left_gx = cx - 22.0
        right_gx = cx + 22.0
        gy = cy - 10.0

        self._draw_gear(painter, left_gx, gy, gear_r, self._gear_angle, is_active=(self._stage in ("gripping", "extruding", "pulling")))
        self._draw_gear(painter, right_gx, gy, gear_r, -self._gear_angle, is_active=(self._stage in ("gripping", "extruding", "pulling")))

        # 4. Filament Runout Sensor Module (Near top of filament tube)
        sensor_y = 45.0
        sensor_box = QtCore.QRectF(cx - 36, sensor_y, 72, 22)
        painter.setPen(QtGui.QPen(QtGui.QColor(51, 65, 85), 1.5))
        painter.setBrush(QtGui.QColor(15, 23, 42, 220))
        painter.drawRoundedRect(sensor_box, 6, 6)

        # Sensor LED status
        s_led_col = QtGui.QColor("#10B981") if self._sensor_triggered else QtGui.QColor("#F59E0B")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(s_led_col)
        painter.drawEllipse(QtCore.QPointF(cx - 22, sensor_y + 11), 4, 4)

        painter.setPen(QtGui.QColor("#E2E8F0"))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        lbl_text = "SENSOR: OK" if self._sensor_triggered else "SENSOR: WAIT"
        painter.drawText(QtCore.QRectF(cx - 14, sensor_y, 48, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, lbl_text)

        # 5. Hotend Heatblock & Nozzle
        block_w = 44.0
        block_h = 28.0
        block_x = cx - block_w / 2.0
        block_y = cy + 42.0

        # Heating glow intensity based on temperature
        heat_ratio = min(1.0, max(0.0, (self._nozzle_temp - 30.0) / max(1.0, self._target_temp - 30.0)))
        block_col = QtGui.QColor(
            int(30 + 190 * heat_ratio),
            int(41 + 40 * (1.0 - heat_ratio)),
            int(59 * (1.0 - heat_ratio)),
            240
        )
        glow_col = QtGui.QColor(239, 68, 68, int(160 * heat_ratio))

        # Block glow
        if heat_ratio > 0.4:
            painter.setPen(QtGui.QPen(glow_col, 8.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QtCore.QRectF(block_x - 3, block_y - 3, block_w + 6, block_h + 6), 6, 6)

        # Block body
        painter.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184), 1.5))
        painter.setBrush(block_col)
        painter.drawRoundedRect(QtCore.QRectF(block_x, block_y, block_w, block_h), 5, 5)

        # Heater cartridge line
        painter.setPen(QtGui.QPen(QtGui.QColor(245, 158, 11), 2.5))
        painter.drawLine(QtCore.QPointF(block_x + 6, block_y + block_h / 2), QtCore.QPointF(block_x + block_w - 6, block_y + block_h / 2))

        # Brass Nozzle Tip (Cone)
        nozzle_top_y = block_y + block_h
        nozzle_tip_y = nozzle_top_y + 16.0
        nozzle_cone = QtGui.QPolygonF([
            QtCore.QPointF(cx - 10, nozzle_top_y),
            QtCore.QPointF(cx + 10, nozzle_top_y),
            QtCore.QPointF(cx + 2.5, nozzle_tip_y),
            QtCore.QPointF(cx - 2.5, nozzle_tip_y),
        ])
        painter.setPen(QtGui.QPen(QtGui.QColor(234, 179, 8), 1.5))
        painter.setBrush(QtGui.QColor(202, 138, 4))
        painter.drawPolygon(nozzle_cone)

        # 6. Extruded Molten Filament Bead / Droplet
        if self._stage in ("extruding", "done") and self._mode == "load":
            bead_w = 5.0
            painter.setPen(QtGui.QPen(f_color, bead_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QtCore.QPointF(cx, nozzle_tip_y), QtCore.QPointF(cx, nozzle_tip_y + 18))
            # Droplet at bottom
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(f_color)
            painter.drawEllipse(QtCore.QPointF(cx, nozzle_tip_y + 20), 4.5, 4.5)

        # 7. Directional Arrows Overlay
        if self._stage in ("gripping", "extruding"):
            self._draw_arrow(painter, cx + 38, cy + 10, direction="down")
        elif self._stage == "pulling":
            self._draw_arrow(painter, cx + 38, cy + 10, direction="up")

        painter.end()

    def _draw_gear(self, painter: QtGui.QPainter, gx: float, gy: float, r: float, angle_deg: float, is_active: bool):
        painter.save()
        painter.translate(gx, gy)
        painter.rotate(angle_deg)

        # Gear outer body
        g_col = QtGui.QColor(56, 189, 248) if is_active else QtGui.QColor(100, 116, 139)
        painter.setPen(QtGui.QPen(g_col, 2.0))
        painter.setBrush(QtGui.QColor(30, 41, 59, 220))
        painter.drawEllipse(QtCore.QPointF(0, 0), r, r)

        # Gear teeth (8 teeth)
        teeth = 8
        for i in range(teeth):
            rad = math.radians(i * (360.0 / teeth))
            tx1 = math.cos(rad) * (r - 2)
            ty1 = math.sin(rad) * (r - 2)
            tx2 = math.cos(rad) * (r + 4)
            ty2 = math.sin(rad) * (r + 4)
            painter.setPen(QtGui.QPen(g_col, 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QtCore.QPointF(tx1, ty1), QtCore.QPointF(tx2, ty2))

        # Center shaft
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(15, 23, 42))
        painter.drawEllipse(QtCore.QPointF(0, 0), 6, 6)

        painter.restore()

    def _draw_arrow(self, painter: QtGui.QPainter, x: float, y: float, direction: str = "down"):
        painter.save()
        painter.translate(x, y)
        col = QtGui.QColor("#10B981") if direction == "down" else QtGui.QColor("#F59E0B")
        painter.setPen(QtGui.QPen(col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        dy = 14 if direction == "down" else -14
        painter.drawLine(QtCore.QPointF(0, -dy/2), QtCore.QPointF(0, dy/2))
        
        # Arrowhead
        arrow_poly = QtGui.QPolygonF([
            QtCore.QPointF(-6, dy/2 - (4 if direction == "down" else -4)),
            QtCore.QPointF(0, dy/2 + (2 if direction == "down" else -2)),
            QtCore.QPointF(6, dy/2 - (4 if direction == "down" else -4)),
        ])
        painter.setBrush(col)
        painter.drawPolygon(arrow_poly)
        painter.restore()

