"""Bed Mesh screen.

In-window touch screen to run BED_MESH_CALIBRATE with a live probing animation,
view the resulting mesh as a colour heat-map grid, name / save profiles and
load previously saved profiles from Klipper.
"""

import json
import math
import threading
import urllib.request

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def _parse_pair(val, default):
    """Parse '10, 10' / [10, 10] / '5' into a 2-tuple of floats."""
    try:
        if isinstance(val, (list, tuple)):
            parts = [float(v) for v in val]
        else:
            parts = [float(p) for p in str(val).replace(" ", "").split(",") if p]
        if len(parts) == 1:
            parts = parts * 2
        return float(parts[0]), float(parts[1])
    except Exception:
        return default


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        int(_lerp(c1.red(), c2.red(), t)),
        int(_lerp(c1.green(), c2.green(), t)),
        int(_lerp(c1.blue(), c2.blue(), t)),
    )


C_LOW = QtGui.QColor("#3B82F6")    # deepest point
C_MID = QtGui.QColor("#10B981")    # flat / zero
C_HIGH1 = QtGui.QColor("#FBBF24")  # slightly high
C_HIGH2 = QtGui.QColor("#EF4444")  # highest point
C_CYAN = QtGui.QColor("#00E5FF")


def mesh_color(z: float, span: float) -> QtGui.QColor:
    """Map a Z deviation to the theme heat-map colour."""
    if span <= 1e-6:
        return QtGui.QColor(C_MID)
    t = max(-1.0, min(1.0, z / span))
    if t < 0:
        return _mix(C_MID, C_LOW, -t)
    if t < 0.5:
        return _mix(C_MID, C_HIGH1, t * 2)
    return _mix(C_HIGH1, C_HIGH2, (t - 0.5) * 2)


class BedMeshCanvas(QtWidgets.QWidget):
    """Draws either the probing animation or the finished mesh heat-map."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 200)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self._mode = "empty"              # "empty" | "probing" | "result"
        self._count = (5, 5)              # grid currently drawn (X, Y)
        self._cfg_count = (5, 5)          # probe_count from [bed_mesh] config
        self._round = False               # round (delta) bed: skip points outside radius
        self._cfg_loaded = False
        self._mesh_min = (10.0, 10.0)
        self._mesh_max = (225.0, 215.0)
        self._matrix = []                 # rows (Y) of columns (X)
        self._probed = set()
        self._order = []
        self._head = [0.0, 0.0]           # normalised 0..1 toolhead position
        self._target_head = [0.0, 0.0]    # target normalized position from live telemetry
        self._cur_z = 10.0
        self._live_vel = 0.0
        self._live = False                # True when following real toolhead
        self._sim_idx = 0
        self._sim_t = 0.0
        self._phase = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(25)       # 40 FPS
        self._timer.timeout.connect(self._step)

    # ----- configuration -----
    def set_geometry(self, count, mesh_min, mesh_max, round_bed=False, from_config=True):
        self._cfg_count = (max(2, int(count[0])), max(2, int(count[1])))
        self._mesh_min = mesh_min
        self._mesh_max = mesh_max
        self._round = bool(round_bed)
        self._cfg_loaded = self._cfg_loaded or from_config
        if self._mode != "result":
            self._count = self._cfg_count
            self._build_order()
        self.update()

    def _in_bed(self, x, y):
        """False for grid points outside the probe radius on a round bed."""
        if not self._round:
            return True
        nx, ny = self._count
        cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
        return ((x - cx) / max(cx, 1e-6)) ** 2 + ((y - cy) / max(cy, 1e-6)) ** 2 <= 1.0001

    def _build_order(self):
        nx, ny = self._count
        self._order = []
        for y in range(ny):
            xs = range(nx) if y % 2 == 0 else range(nx - 1, -1, -1)
            for x in xs:
                if self._in_bed(x, y):
                    self._order.append((x, y))

    def total_points(self):
        return len(self._order) if self._order else self._count[0] * self._count[1]

    def grid_label(self):
        nx, ny = self._cfg_count
        n = sum(1 for y in range(ny) for x in range(nx) if not self._round or
                ((x - (nx - 1) / 2) / max((nx - 1) / 2, 1e-6)) ** 2 + ((y - (ny - 1) / 2) / max((ny - 1) / 2, 1e-6)) ** 2 <= 1.0001)
        return f"{nx} \u00D7 {ny} GRID  \u2022  {n} POINTS" + ("  \u2022  ROUND" if self._round else "")

    # ----- modes -----
    def start_probing(self, live: bool):
        self._mode = "probing"
        self._live = live
        self._probed = set()
        self._sim_idx = 0
        self._sim_t = 0.0
        self._head = [0.0, 0.0]
        self._target_head = [0.0, 0.0]
        self._cur_z = 10.0
        self._live_vel = 0.0
        self._count = self._cfg_count
        self._build_order()
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()

    def show_matrix(self, matrix):
        self._timer.stop()
        rows = [list(r) for r in (matrix or []) if r]
        if rows:
            self._matrix = rows
            self._count = (len(rows[0]), len(rows))
            self._build_order()
            self._mode = "result"
        else:
            self._matrix = []
            self._mode = "empty"
            self._count = self._cfg_count
            self._build_order()
        self.update()

    def set_toolhead(self, x: float, y: float, z: float = 10.0, vel: float = 0.0):
        """Feed live toolhead coordinates (mm) during probing."""
        if self._mode != "probing":
            return
        x0, y0 = self._mesh_min
        x1, y1 = self._mesh_max
        nx = (x - x0) / max(1e-6, x1 - x0)
        ny = (y - y0) / max(1e-6, y1 - y0)
        self._target_head = [max(-0.1, min(1.1, nx)), max(-0.1, min(1.1, ny))]
        self._cur_z = z
        self._live_vel = vel

        # Check if the physical nozzle has reached any grid spot
        cx, cy = self._count
        for (gx, gy) in self._order:
            if (gx, gy) in self._probed:
                continue
            # Distance in normalized grid coordinates (0 = exact center of grid point)
            grid_dx = self._target_head[0] * (cx - 1) - gx
            grid_dy = self._target_head[1] * (cy - 1) - gy
            dist_grid = math.hypot(grid_dx, grid_dy)

            # Only when the physical nozzle has reached the spot (<= 0.16 pitch):
            if dist_grid < 0.16:
                # Wait for the nozzle to actually probe at this position:
                # 1. Z drops down below horizontal move clearance (z <= 3.5mm; travel clearance is 5.0mm)
                # 2. Or the toolhead dwells at low velocity on the spot (vel < 3.0 mm/s)
                if z <= 3.5 or vel < 3.0:
                    if self._in_bed(gx, gy):
                        self._probed.add((gx, gy))
                break

    def stats(self):
        flat = [v for r in self._matrix for v in r]
        if not flat:
            return None
        return min(flat), max(flat)

    # ----- animation -----
    def _step(self):
        self._phase = (self._phase + 0.06) % (math.pi * 2)
        if self._live:
            # Smoothly glide toolhead crosshair towards latest physical position
            if hasattr(self, '_target_head') and self._target_head:
                self._head[0] += (self._target_head[0] - self._head[0]) * 0.4
                self._head[1] += (self._target_head[1] - self._head[1]) * 0.4
        elif self._order:
            cx, cy = self._count
            self._sim_t += 0.045
            cur = self._order[self._sim_idx % len(self._order)]
            nxt = self._order[(self._sim_idx + 1) % len(self._order)]
            if self._sim_t < 0.55:
                # dwell on point: probe tap
                px, py = cur
                self._head = [px / (cx - 1), py / (cy - 1)]
                if self._sim_t > 0.3:
                    self._probed.add(cur)
            else:
                t = min(1.0, (self._sim_t - 0.55) / 0.45)
                t = t * t * (3 - 2 * t)
                self._head = [
                    _lerp(cur[0], nxt[0], t) / (cx - 1),
                    _lerp(cur[1], nxt[1], t) / (cy - 1),
                ]
                if self._sim_t >= 1.0:
                    self._sim_t = 0.0
                    self._sim_idx += 1
                    if self._sim_idx % len(self._order) == 0:
                        self._probed = set()
        self.update()

    # ----- painting -----
    def _bed_rect(self):
        m = 18
        w = self.width() - m * 2
        h = self.height() - m * 2 - 22
        bx0, by0 = self._mesh_min
        bx1, by1 = self._mesh_max
        aspect = max(0.3, min(3.0, (bx1 - bx0) / max(1.0, by1 - by0)))
        if w / max(1, h) > aspect:
            rw, rh = h * aspect, h
        else:
            rw, rh = w, w / aspect
        return QtCore.QRectF((self.width() - rw) / 2, m, rw, rh)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = self._bed_rect()

        # Bed plate
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QtGui.QColor(30, 41, 59, 230))
        grad.setColorAt(1, QtGui.QColor(15, 23, 42, 230))
        p.setBrush(QtGui.QBrush(grad))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 110), 1.5))
        p.drawRoundedRect(r.adjusted(-10, -10, 10, 10), 10, 10)

        if self._mode == "result":
            self._paint_result(p, r)
        elif self._mode == "probing":
            self._paint_probing(p, r)
        else:
            self._paint_empty(p, r)
        p.end()

    def _cell_rects(self, r):
        cx, cy = self._count
        cw, ch = r.width() / cx, r.height() / cy
        for y in range(cy):
            for x in range(cx):
                # Row 0 = front of bed (min Y) drawn at the bottom
                yield x, y, QtCore.QRectF(r.left() + x * cw, r.bottom() - (y + 1) * ch, cw, ch)

    def _paint_empty(self, p, r):
        p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 60), 1, Qt.PenStyle.DashLine))
        for _x, _y, cr in self._cell_rects(r):
            if self._in_bed(_x, _y):
                p.drawRect(cr)
        self._paint_grid_label(p)
        p.setPen(QtGui.QColor("#94A3B8"))
        f = p.font()
        f.setPointSizeF(max(8.0, r.height() / 18))
        f.setBold(True)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "No mesh loaded\nRun calibration or load a profile")

    def _paint_grid_label(self, p):
        f = p.font()
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QtGui.QColor("#7DD3FC"))
        p.drawText(QtCore.QRectF(0, self.height() - 22, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                   self.grid_label())

    def _paint_probing(self, p, r):
        cx, cy = self._count
        # grid lines
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 40), 1))
        for i in range(cx):
            x = r.left() + r.width() * i / (cx - 1)
            p.drawLine(QtCore.QPointF(x, r.top()), QtCore.QPointF(x, r.bottom()))
        for j in range(cy):
            y = r.bottom() - r.height() * j / (cy - 1)
            p.drawLine(QtCore.QPointF(r.left(), y), QtCore.QPointF(r.right(), y))

        # serpentine path
        path = QtGui.QPainterPath()
        for i, (gx, gy) in enumerate(self._order):
            pt = QtCore.QPointF(r.left() + r.width() * gx / (cx - 1), r.bottom() - r.height() * gy / (cy - 1))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 55), 1.2, Qt.PenStyle.DotLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # probe points
        rad = max(2.0, min(8.0, min(r.width() / cx, r.height() / cy) * 0.14))
        for gx in range(cx):
            for gy in range(cy):
                if not self._in_bed(gx, gy):
                    continue
                pt = QtCore.QPointF(r.left() + r.width() * gx / (cx - 1), r.bottom() - r.height() * gy / (cy - 1))
                if (gx, gy) in self._probed:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QtGui.QColor(52, 211, 153, 70))
                    p.drawEllipse(pt, rad * 2.0, rad * 2.0)
                    p.setBrush(QtGui.QColor("#34D399"))
                    p.drawEllipse(pt, rad, rad)
                else:
                    p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 150), 1.2))
                    p.setBrush(QtGui.QColor(15, 23, 42))
                    p.drawEllipse(pt, rad * 0.8, rad * 0.8)

        # toolhead crosshair + pulsing ring
        hx = r.left() + r.width() * self._head[0]
        hy = r.bottom() - r.height() * self._head[1]
        head = QtCore.QPointF(hx, hy)
        pulse = (math.sin(self._phase * 3) + 1) / 2
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, int(90 + 120 * pulse)), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(head, rad * (2.2 + pulse * 1.4), rad * (2.2 + pulse * 1.4))
        p.setPen(QtGui.QPen(C_CYAN, 1.5))
        p.drawLine(QtCore.QPointF(hx - rad * 4, hy), QtCore.QPointF(hx + rad * 4, hy))
        p.drawLine(QtCore.QPointF(hx, hy - rad * 4), QtCore.QPointF(hx, hy + rad * 4))
        p.setBrush(C_CYAN)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(head, rad * 0.7, rad * 0.7)

        # progress text
        total = self.total_points()
        done = min(len(self._probed), total)
        p.setPen(QtGui.QColor("#E2E8F0"))
        f = p.font()
        f.setPointSizeF(9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QtCore.QRectF(0, self.height() - 22, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                   f"PROBING  {done}/{total} points  \u2022  {cx} \u00D7 {cy}")

    def _paint_result(self, p, r):
        st = self.stats()
        lo, hi = st if st else (0.0, 0.0)
        span = max(abs(lo), abs(hi), 0.01)
        f = p.font()
        for x, y, cr in self._cell_rects(r):
            try:
                z = float(self._matrix[y][x])
            except Exception:
                continue
            if not self._in_bed(x, y):
                continue
            col = mesh_color(z, span)
            fill = QtGui.QColor(col)
            fill.setAlpha(200)
            p.setPen(QtGui.QPen(QtGui.QColor(11, 15, 25), 2))
            p.setBrush(fill)
            p.drawRoundedRect(cr.adjusted(2, 2, -2, -2), 5, 5)
            # value text
            f.setPointSizeF(max(6.5, min(cr.width() / 6.0, cr.height() / 3.2)))
            f.setBold(True)
            p.setFont(f)
            if cr.width() >= 34 and cr.height() >= 16:
                p.setPen(QtGui.QColor("#0B0F19") if col.lightness() > 120 else QtGui.QColor("#FFFFFF"))
                p.drawText(cr, Qt.AlignmentFlag.AlignCenter, f"{z:+.3f}" if cr.width() >= 46 else f"{z:+.2f}")

        # highlight extremes
        for target, colr in ((lo, C_LOW), (hi, C_HIGH2)):
            for x, y, cr in self._cell_rects(r):
                try:
                    if abs(float(self._matrix[y][x]) - target) < 1e-9:
                        p.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(cr.adjusted(2, 2, -2, -2), 5, 5)
                        break
                except Exception:
                    pass

        # legend bar
        lg = QtCore.QRectF(r.left(), self.height() - 16, r.width(), 8)
        g = QtGui.QLinearGradient(lg.topLeft(), lg.topRight())
        g.setColorAt(0.0, C_LOW)
        g.setColorAt(0.5, C_MID)
        g.setColorAt(0.75, C_HIGH1)
        g.setColorAt(1.0, C_HIGH2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(g))
        p.drawRoundedRect(lg, 4, 4)
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.setPen(QtGui.QColor("#94A3B8"))
        p.drawText(QtCore.QRectF(lg.left(), lg.top() - 14, 80, 12), Qt.AlignmentFlag.AlignLeft, f"{-span:+.3f}")
        p.drawText(QtCore.QRectF(lg.center().x() - 40, lg.top() - 14, 80, 12), Qt.AlignmentFlag.AlignCenter, "0.000")
        p.drawText(QtCore.QRectF(lg.right() - 80, lg.top() - 14, 80, 12), Qt.AlignmentFlag.AlignRight, f"{span:+.3f}")
        p.drawText(QtCore.QRectF(r.left(), r.top() - 16, r.width(), 12), Qt.AlignmentFlag.AlignCenter, "REAR")


_BTN_PRIMARY = """
QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
  border: 1px solid rgba(255,255,255,0.3); border-radius: 7px; color: #FFFFFF;
  font-size: 12px; font-weight: 800; min-height: 30px; padding: 2px 10px; }
QPushButton:pressed { background: #0284C7; }
QPushButton:disabled { background: rgba(30,41,59,0.6); border-color: rgba(255,255,255,0.1); color: #64748B; }
"""
_BTN_SAVE = """
QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);
  border: 1px solid #34D399; border-radius: 7px; color: #FFFFFF;
  font-size: 12px; font-weight: 800; min-height: 30px; padding: 2px 10px; }
QPushButton:pressed { background: #047857; }
QPushButton:disabled { background: rgba(30,41,59,0.6); border-color: rgba(255,255,255,0.1); color: #64748B; }
"""
_BTN_GHOST = """
QPushButton { background: rgba(30,41,59,0.8); border: 1px solid rgba(255,255,255,0.18);
  border-radius: 6px; color: #CBD5E1; font-size: 11px; font-weight: 700; min-height: 26px; padding: 2px 10px; }
QPushButton:pressed { background: rgba(51,65,85,0.9); color: #FFFFFF; }
QPushButton:disabled { color: #475569; }
"""
_BTN_DANGER = """
QPushButton { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.5);
  border-radius: 6px; color: #FCA5A5; font-size: 11px; font-weight: 800; min-height: 26px; padding: 2px 8px; }
QPushButton:pressed { background: rgba(239,68,68,0.35); color: #FFFFFF; }
"""
_LBL_HDR = "color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;"


class BedMeshScreen(QtWidgets.QFrame):
    """Full in-window Bed Mesh screen: calibrate, view, name, save and load profiles."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._profiles = {}
        self._active_profile = ""
        self._busy = False
        self._confirm_action = None   # ("save"|"delete", name)
        self._sim_matrix = None

        self.setObjectName("BedMeshScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet("""
            QFrame#DialogCard { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141C2E, stop:1 #0B0F19);
                border: 1px solid rgba(0, 229, 255, 120); border-radius: 14px; }
            QLabel { border: none; background: transparent; }
        """)
        outer.addWidget(self.card)
        lay = QtWidgets.QVBoxLayout(self.card)
        lay.setSpacing(_s(8, scale))

        # --- Header ---
        hdr = QtWidgets.QHBoxLayout()
        self.icon_label = QtWidgets.QLabel()
        hdr.addWidget(self.icon_label)
        self.title_lbl = QtWidgets.QLabel("BED MESH")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        hdr.addWidget(self.title_lbl, 1)
        self.active_badge = QtWidgets.QLabel("NO MESH ACTIVE")
        self.active_badge.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: 800; background: rgba(148,163,184,0.12);"
            "border: 1px solid rgba(148,163,184,0.35); border-radius: 4px; padding: 2px 8px;")
        hdr.addWidget(self.active_badge)
        self.close_x = QtWidgets.QPushButton("\u2715")
        self.close_x.setFixedSize(26, 26)
        self.close_x.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);"
            "border-radius: 13px; color: #94A3B8; font-size: 13px; font-weight: 700; }"
            "QPushButton:pressed { background: rgba(239,68,68,0.3); color: #FFFFFF; }")
        self.close_x.clicked.connect(self.reject)
        hdr.addWidget(self.close_x)
        lay.addLayout(hdr)

        # --- Body ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))
        self.canvas = BedMeshCanvas()
        body.addWidget(self.canvas, 3)

        side = QtWidgets.QVBoxLayout()
        side.setSpacing(_s(6, scale))

        lbl = QtWidgets.QLabel("MESH NAME")
        lbl.setStyleSheet(_LBL_HDR)
        side.addWidget(lbl)
        self.name_edit = QtWidgets.QLineEdit("default")
        self.name_edit.setMaxLength(24)
        self.name_edit.setStyleSheet(
            "QLineEdit { background: rgba(15,23,42,0.9); border: 1px solid rgba(0,229,255,0.45);"
            "border-radius: 6px; color: #FFFFFF; font-size: 13px; font-weight: 700; padding: 4px 8px; min-height: 24px; }"
            "QLineEdit:focus { border-color: #00E5FF; }")
        side.addWidget(self.name_edit)

        # Stats box
        stats = QtWidgets.QFrame()
        stats.setObjectName("MeshStats")
        stats.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        stats.setStyleSheet("QFrame#MeshStats { background: rgba(0,229,255,0.07); border: 1px solid rgba(0,229,255,0.35);"
                            "border-left: 4px solid #00E5FF; border-radius: 8px; }")
        sg = QtWidgets.QGridLayout(stats)
        sg.setContentsMargins(8, 4, 8, 4)
        sg.setVerticalSpacing(1)
        self.stat_vals = {}
        for i, (key, colr) in enumerate((("MIN", "#60A5FA"), ("MAX", "#F87171"), ("RANGE", "#34D399"))):
            k = QtWidgets.QLabel(key)
            k.setStyleSheet(_LBL_HDR)
            v = QtWidgets.QLabel("--")
            v.setStyleSheet(f"color: {colr}; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
            sg.addWidget(k, 0, i)
            sg.addWidget(v, 1, i)
            self.stat_vals[key] = v
        side.addWidget(stats)
        self.grid_lbl = QtWidgets.QLabel("Reading [bed_mesh] config...")
        self.grid_lbl.setStyleSheet("color: #7DD3FC; font-size: 10px; font-weight: 800; font-family: 'Consolas', monospace;")
        side.addWidget(self.grid_lbl)

        lbl2 = QtWidgets.QLabel("SAVED PROFILES")
        lbl2.setStyleSheet(_LBL_HDR)
        side.addWidget(lbl2)
        self.prof_scroll = QtWidgets.QScrollArea()
        self.prof_scroll.setWidgetResizable(True)
        self.prof_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.prof_scroll.setStyleSheet("QScrollArea { background: transparent; } QWidget#ProfList { background: transparent; }")
        self.prof_box = QtWidgets.QWidget()
        self.prof_box.setObjectName("ProfList")
        self.prof_layout = QtWidgets.QVBoxLayout(self.prof_box)
        self.prof_layout.setContentsMargins(0, 0, 0, 0)
        self.prof_layout.setSpacing(4)
        self.prof_layout.addStretch(1)
        self.prof_scroll.setWidget(self.prof_box)
        side.addWidget(self.prof_scroll, 1)

        self.cal_btn = QtWidgets.QPushButton("\u25B6  Calibrate Mesh")
        self.cal_btn.setStyleSheet(_BTN_PRIMARY)
        self.cal_btn.clicked.connect(self._on_calibrate)
        side.addWidget(self.cal_btn)

        row = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("\U0001F4BE  Save")
        self.save_btn.setStyleSheet(_BTN_SAVE)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        row.addWidget(self.save_btn, 1)
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setStyleSheet(_BTN_GHOST)
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)
        side.addLayout(row)

        side_w = QtWidgets.QWidget()
        side_w.setLayout(side)
        side_w.setMinimumWidth(190)
        side_w.setMaximumWidth(300)
        body.addWidget(side_w, 2)
        lay.addLayout(body, 1)

        # --- Bottom status ---
        bot = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Loading bed mesh data...")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bot.addWidget(self.status_lbl, 1)
        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setStyleSheet(_BTN_GHOST)
        self.close_btn.clicked.connect(self.accept)
        bot.addWidget(self.close_btn)
        lay.addLayout(bot)

        self._pos_timer = QtCore.QTimer(self)
        self._pos_timer.setInterval(80)
        self._pos_timer.timeout.connect(self._poll_toolhead)

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(50, self.refresh)

    # ------------------------------------------------------------------ helpers
    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = p.parent()
        return getattr(self.window(), "moonraker", None)

    def _host(self, mr):
        return mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

    def _ui(self, mr, fn):
        if mr is not None and hasattr(mr, "_dispatch_signal"):
            mr._dispatch_signal.emit(fn)
        else:
            QtCore.QTimer.singleShot(0, fn)

    def _set_status(self, text, color="#94A3B8"):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")

    def _profile_name(self):
        name = "".join(c for c in self.name_edit.text().strip() if c.isalnum() or c in "_-")
        return name or "default"

    def _set_busy(self, busy):
        self._busy = busy
        for b in (self.cal_btn, self.clear_btn, self.name_edit):
            b.setEnabled(not busy)
        self.save_btn.setEnabled(not busy and bool(self.canvas.stats()))
        for i in range(self.prof_layout.count()):
            w = self.prof_layout.itemAt(i).widget()
            if w:
                w.setEnabled(not busy)

    # ------------------------------------------------------------------ data
    def refresh(self, after=None):
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self.canvas.set_geometry((5, 5), (10.0, 10.0), (225.0, 215.0), from_config=False)
            self.grid_lbl.setText(self.canvas.grid_label() + " (offline default)")
            self._apply_mesh_data({}, None)
            self._set_status("Printer offline \u2013 simulation mode.", "#FBBF24")
            return
        host = self._host(mr)

        def _bg():
            bm, cfg = {}, {}
            try:
                url = f"http://{host}/printer/objects/query?bed_mesh&configfile=settings"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=3.0) as resp:
                    st = json.loads(resp.read().decode("utf-8")).get("result", {}).get("status", {})
                    bm = st.get("bed_mesh", {}) or {}
                    cfg = (st.get("configfile", {}) or {}).get("settings", {}).get("bed_mesh", {}) or {}
            except Exception:
                pass
            self._ui(mr, lambda: (self._apply_mesh_data(bm, cfg), after() if after else None))

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_config(self, cfg):
        """Apply [bed_mesh] geometry (probe_count / mesh_min / mesh_max or round-bed radius)."""
        if not cfg:
            return
        if cfg.get("mesh_radius"):
            rad = float(cfg.get("mesh_radius"))
            ox, oy = _parse_pair(cfg.get("mesh_origin", (0, 0)), (0.0, 0.0))
            n = int(float(cfg.get("round_probe_count", 5)))
            self.canvas.set_geometry((n, n), (ox - rad, oy - rad), (ox + rad, oy + rad), round_bed=True)
        else:
            self.canvas.set_geometry(
                _parse_pair(cfg.get("probe_count", (3, 3)), (3, 3)),
                _parse_pair(cfg.get("mesh_min", (10, 10)), (10.0, 10.0)),
                _parse_pair(cfg.get("mesh_max", (225, 215)), (225.0, 215.0)),
            )
        self.grid_lbl.setText(self.canvas.grid_label())

    def _apply_mesh_data(self, bm, cfg):
        self._apply_config(cfg)
        self._profiles = dict(bm.get("profiles", {}) or {})
        if self._sim_matrix is not None and not (self._get_moonraker() and self._get_moonraker().connected):
            self._profiles.setdefault("default", {"points": self._sim_matrix})
        self._active_profile = bm.get("profile_name", "") or ""
        matrix = bm.get("probed_matrix") or []
        has_mesh = bool(matrix and matrix[0])
        if has_mesh:
            self.canvas.show_matrix(matrix)
        elif self.canvas._mode != "probing":
            self.canvas.show_matrix([])
        self._update_badge(has_mesh)
        self._update_stats()
        self._rebuild_profiles()
        self._set_busy(False)
        if has_mesh:
            self._set_status(f"Mesh '{self._active_profile or 'unsaved'}' active.", "#34D399")
        elif self._profiles:
            self._set_status("No mesh active. Tap a saved profile to load it.")
        else:
            self._set_status("No saved meshes. Tap Calibrate Mesh to probe the bed.")

    def _update_badge(self, has_mesh):
        if has_mesh:
            name = self._active_profile or "UNSAVED"
            self.active_badge.setText(f"\u25CF ACTIVE: {name.upper()}")
            self.active_badge.setStyleSheet(
                "color: #34D399; font-size: 10px; font-weight: 800; background: rgba(16,185,129,0.15);"
                "border: 1px solid rgba(52,211,153,0.5); border-radius: 4px; padding: 2px 8px;")
        else:
            self.active_badge.setText("NO MESH ACTIVE")
            self.active_badge.setStyleSheet(
                "color: #94A3B8; font-size: 10px; font-weight: 800; background: rgba(148,163,184,0.12);"
                "border: 1px solid rgba(148,163,184,0.35); border-radius: 4px; padding: 2px 8px;")

    def _update_stats(self):
        st = self.canvas.stats()
        if st:
            lo, hi = st
            self.stat_vals["MIN"].setText(f"{lo:+.3f}")
            self.stat_vals["MAX"].setText(f"{hi:+.3f}")
            rng = hi - lo
            self.stat_vals["RANGE"].setText(f"{rng:.3f}")
            colr = "#34D399" if rng < 0.2 else ("#FBBF24" if rng < 0.5 else "#EF4444")
            self.stat_vals["RANGE"].setStyleSheet(
                f"color: {colr}; font-size: 14px; font-weight: 900; font-family: 'Consolas', monospace;")
        else:
            for v in self.stat_vals.values():
                v.setText("--")

    def _rebuild_profiles(self):
        while self.prof_layout.count() > 1:
            it = self.prof_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not self._profiles:
            empty = QtWidgets.QLabel("No saved profiles")
            empty.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic; padding: 4px;")
            self.prof_layout.insertWidget(0, empty)
            return
        for i, name in enumerate(sorted(self._profiles)):
            roww = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(roww)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            active = (name == self._active_profile)
            btn = QtWidgets.QPushButton(("\u25CF  " if active else "\u25B8  ") + name)
            btn.setStyleSheet(_BTN_GHOST + (
                "QPushButton { border-color: #34D399; color: #34D399; text-align: left; }" if active
                else "QPushButton { text-align: left; }"))
            btn.clicked.connect(lambda _=False, n=name: self._on_load(n))
            rl.addWidget(btn, 1)
            dl = QtWidgets.QPushButton("\u2715")
            dl.setFixedWidth(30)
            dl.setStyleSheet(_BTN_DANGER)
            dl.clicked.connect(lambda _=False, n=name: self._on_delete(n))
            rl.addWidget(dl)
            self.prof_layout.insertWidget(i, roww)

    # ------------------------------------------------------------------ actions
    def _armed(self, action, name, prompt):
        """Two-tap confirmation for actions that run SAVE_CONFIG (restarts Klipper)."""
        if self._confirm_action == (action, name):
            self._confirm_action = None
            return True
        self._confirm_action = (action, name)
        self._set_status(prompt, "#FBBF24")
        QtCore.QTimer.singleShot(4000, lambda: self._disarm(action, name))
        return False

    def _disarm(self, action, name):
        if self._confirm_action == (action, name):
            self._confirm_action = None
            if not self._busy:
                self._set_status("Ready.")

    def _on_load(self, name):
        if self._busy:
            return
        self.name_edit.setText(name)
        pts = (self._profiles.get(name) or {}).get("points")
        if pts:
            self.canvas.show_matrix(pts)   # instant preview
            self._update_stats()
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._active_profile = name
            self._update_badge(bool(pts))
            self._rebuild_profiles()
            self.save_btn.setEnabled(bool(pts))
            self._set_status(f"Loaded '{name}' (simulated).", "#34D399")
            return
        self._set_busy(True)
        self._set_status(f"Loading mesh '{name}'...", "#7DD3FC")

        def _done(ok):
            if ok:
                self.refresh()
            else:
                self._set_busy(False)
                self._set_status(f"Failed to load '{name}'.", "#EF4444")

        mr.send_gcode(f"BED_MESH_PROFILE LOAD={name}", on_done=_done, timeout=15.0)

    def _on_delete(self, name):
        if self._busy or not self._armed("delete", name,
                                         f"Tap \u2715 again to delete '{name}' (runs SAVE_CONFIG, Klipper restarts)."):
            return
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self._profiles.pop(name, None)
            if name == "default":
                self._sim_matrix = None
            self._rebuild_profiles()
            self._set_status(f"Deleted '{name}' (simulated).")
            return
        self._set_busy(True)
        self._set_status(f"Deleting '{name}' and saving config...", "#7DD3FC")
        mr.send_gcode(f"BED_MESH_PROFILE REMOVE={name}\nSAVE_CONFIG",
                      on_done=lambda ok: self._after_restart(ok, f"Deleted '{name}'."), timeout=30.0)

    def _on_clear(self):
        if self._busy:
            return
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("BED_MESH_CLEAR", on_done=lambda ok: self.refresh(), timeout=10.0)
        else:
            self.canvas.show_matrix([])
            self._active_profile = ""
            self._update_badge(False)
            self._update_stats()
            self._rebuild_profiles()
            self.save_btn.setEnabled(False)
        self._set_status("Active mesh cleared (saved profiles kept).")

    def _on_calibrate(self):
        if self._busy:
            return
        name = self._profile_name()
        self.name_edit.setText(name)
        mr = self._get_moonraker()
        live = bool(mr and mr.connected)
        self._set_busy(True)
        self.canvas.start_probing(live=live)
        self._update_badge(False)
        self.active_badge.setText("\u25CF PROBING")
        self.active_badge.setStyleSheet(
            "color: #00E5FF; font-size: 10px; font-weight: 800; background: rgba(0,229,255,0.15);"
            "border: 1px solid rgba(0,229,255,0.5); border-radius: 4px; padding: 2px 8px;")

        if not live:
            nx, ny = self.canvas._count
            self._set_status(f"Simulating mesh probe '{name}'...", "#7DD3FC")
            QtCore.QTimer.singleShot(int(self.canvas.total_points() * 560), lambda: self._sim_finish(name))
            return

        host = self._host(mr)

        def _check_home():
            homed = ""
            cfg = {}
            try:
                url = f"http://{host}/printer/objects/query?configfile=settings"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=2.0) as resp:
                    cfg = json.loads(resp.read().decode("utf-8"))["result"]["status"]["configfile"]["settings"].get("bed_mesh", {})
            except Exception:
                pass
            try:
                url = f"http://{host}/printer/objects/query?toolhead=homed_axes"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=2.0) as resp:
                    homed = json.loads(resp.read().decode("utf-8"))["result"]["status"]["toolhead"]["homed_axes"]
            except Exception:
                pass
            def _go():
                if cfg:
                    self._apply_config(cfg)
                    self.canvas.start_probing(live=True)
                self._run_mesh(mr, name, all(a in str(homed).lower() for a in "xyz"))
            self._ui(mr, _go)

        self._set_status("Checking homing state...", "#7DD3FC")
        threading.Thread(target=_check_home, daemon=True).start()

    def _run_mesh(self, mr, name, homed):
        cmd = f"BED_MESH_CALIBRATE PROFILE={name}"
        tare = mr.tare_gcode() if hasattr(mr, "tare_gcode") else ""
        if tare:
            cmd = tare + cmd  # load cell only: settle + tare before the mesh starts
        if not homed:
            cmd = "G28\n" + cmd
            self._set_status("Homing (G28) then probing bed mesh...", "#7DD3FC")
        else:
            self._set_status(f"Probing bed mesh '{name}'...", "#7DD3FC")
        self._pos_timer.start()
        mr.send_gcode(cmd, on_done=lambda ok: self._on_mesh_done(ok, name), timeout=600.0)

    def _poll_toolhead(self):
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            return
        if getattr(self, "_poll_active", False):
            return
        self._poll_active = True
        host = self._host(mr)

        def _bg():
            try:
                url = f"http://{host}/printer/objects/query?motion_report&toolhead=position"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=0.6) as resp:
                    data = json.loads(resp.read().decode("utf-8")).get("result", {}).get("status", {})
                    mr_st = data.get("motion_report", {})
                    live_pos = mr_st.get("live_position")
                    live_vel = float(mr_st.get("live_velocity", 0.0))
                    th_pos = data.get("toolhead", {}).get("position")
                    pos = live_pos if (live_pos and len(live_pos) >= 3) else th_pos
                    if pos and len(pos) >= 2:
                        x, y = float(pos[0]), float(pos[1])
                        z = float(pos[2]) if len(pos) > 2 else 10.0
                        self._ui(mr, lambda: self.canvas.set_toolhead(x, y, z, live_vel))
            except Exception:
                pass
            finally:
                self._poll_active = False

        threading.Thread(target=_bg, daemon=True).start()

    def _on_mesh_done(self, ok, name):
        self._pos_timer.stop()
        self.canvas.stop()
        if not ok:
            self.canvas.show_matrix([])
            self._set_busy(False)
            self._update_badge(False)
            self._set_status("Bed mesh calibration failed or timed out.", "#EF4444")
            return
        self.refresh(after=lambda: self._set_status(
            f"\u2713 Mesh '{name}' complete. Tap Save to store it permanently.", "#34D399"))

    def _sim_finish(self, name):
        self.canvas.stop()
        nx, ny = self.canvas._cfg_count
        cxm, cym = (nx - 1) / 2, (ny - 1) / 2
        m = []
        for y in range(ny):
            m.append([round(0.06 * ((x - cxm) ** 2 + (y - cym) ** 2) / max(1, cxm * cym)
                            + 0.04 * math.sin(x * 1.3 + y) - 0.05, 3) for x in range(nx)])
        self._sim_matrix = m
        self._profiles[name] = {"points": m}
        self._active_profile = name
        self.canvas.show_matrix(m)
        self._update_stats()
        self._update_badge(True)
        self._rebuild_profiles()
        self._set_busy(False)
        self._set_status(f"\u2713 Mesh '{name}' complete (simulated). Tap Save to store.", "#34D399")

    def _on_save(self):
        if self._busy:
            return
        name = self._profile_name()
        self.name_edit.setText(name)
        if not self._armed("save", name, f"Tap Save again to store '{name}' (runs SAVE_CONFIG, Klipper restarts)."):
            return
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            st = self.canvas._matrix
            self._profiles[name] = {"points": st}
            self._active_profile = name
            self._update_badge(True)
            self._rebuild_profiles()
            self._set_status(f"\u2713 Saved '{name}' (simulated).", "#34D399")
            return
        self._set_busy(True)
        self._set_status(f"Saving '{name}' to printer.cfg...", "#7DD3FC")
        mr.send_gcode(f"BED_MESH_PROFILE SAVE={name}\nSAVE_CONFIG",
                      on_done=lambda ok: self._after_restart(ok, f"\u2713 Mesh '{name}' saved.", name), timeout=30.0)

    def _after_restart(self, ok, msg, reload_name=None):
        """SAVE_CONFIG restarts Klipper; wait for it to come back, then reload."""
        if not ok:
            # SAVE_CONFIG often drops the request as Klipper restarts - still treat as pending
            self._set_status("Klipper restarting...", "#FBBF24")
        else:
            self._set_status("Klipper restarting to apply config...", "#FBBF24")
        mr = self._get_moonraker()
        host = self._host(mr) if mr else None
        self._restart_tries = 0

        def _poll():
            self._restart_tries += 1
            ready = False
            try:
                url = f"http://{host}/printer/info"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=1.5) as resp:
                    ready = json.loads(resp.read().decode("utf-8"))["result"].get("state") == "ready"
            except Exception:
                pass
            if ready:
                def _fin():
                    if reload_name:
                        mr.send_gcode(f"BED_MESH_PROFILE LOAD={reload_name}",
                                      on_done=lambda _ok: self.refresh(after=lambda: self._set_status(msg, "#34D399")))
                    else:
                        self.refresh(after=lambda: self._set_status(msg, "#34D399"))
                self._ui(mr, _fin)
            elif self._restart_tries < 30:
                threading.Timer(1.0, _poll).start()
            else:
                self._ui(mr, lambda: (self._set_busy(False),
                                      self._set_status("Klipper did not come back ready. Check printer.", "#EF4444")))

        threading.Timer(2.0, _poll).start()

    # ------------------------------------------------------------------ lifecycle
    def _cleanup(self):
        self._pos_timer.stop()
        self.canvas.stop()

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
        self.icon_label.setPixmap(icons.pixmap("mesh", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
