"""Spool Page: Clean filament spool showcase, tap-to-edit settings modal, load/unload, and manual extrude."""

import json
import os
from . import icons
from .filament_dialog import FilamentActionDialog
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


CONFIG_STORE_PATH = os.path.expanduser("~/.klipper_display_spools.json")

# Standard filament presets with recommended nozzle and bed temperatures
FILAMENT_PRESETS = {
    "PLA": {"nozzle": 210, "bed": 60, "density": 1.24},
    "PLA+": {"nozzle": 215, "bed": 60, "density": 1.24},
    "PETG": {"nozzle": 240, "bed": 75, "density": 1.27},
    "ABS": {"nozzle": 250, "bed": 100, "density": 1.04},
    "ASA": {"nozzle": 255, "bed": 105, "density": 1.07},
    "TPU": {"nozzle": 220, "bed": 50, "density": 1.21},
    "Nylon": {"nozzle": 260, "bed": 90, "density": 1.14},
    "PC": {"nozzle": 270, "bed": 110, "density": 1.20},
    "PVA": {"nozzle": 215, "bed": 60, "density": 1.19},
    "HIPS": {"nozzle": 240, "bed": 100, "density": 1.07},
}

PALETTE_COLORS = [
    ("#EF4444", "Red"),
    ("#F97316", "Orange"),
    ("#F59E0B", "Amber"),
    ("#EAB308", "Yellow"),
    ("#10B981", "Green"),
    ("#06B6D4", "Cyan"),
    ("#3B82F6", "Blue"),
    ("#8B5CF6", "Purple"),
    ("#EC4899", "Pink"),
    ("#FFFFFF", "White"),
    ("#94A3B8", "Silver/Grey"),
    ("#1E293B", "Black"),
    ("#78350F", "Brown"),
    ("#14B8A6", "Teal"),
    ("#6366F1", "Indigo"),
    ("#84CC16", "Lime"),
]

DEFAULT_SPOOLS = {
    "spool_1": {
        "id": 1,
        "name": "Spool 1",
        "type": "PLA",
        "color": "#3B82F6",
        "nozzle_temp": 210,
        "bed_temp": 60,
        "weight_g": 850,
        "capacity_g": 1000,
    },
    "spool_2": {
        "id": 2,
        "name": "Spool 2",
        "type": "PETG",
        "color": "#10B981",
        "nozzle_temp": 240,
        "bed_temp": 75,
        "weight_g": 1000,
        "capacity_g": 1000,
    },
    "spool_3": {
        "id": 3,
        "name": "Spool 3",
        "type": "ABS",
        "color": "#EF4444",
        "nozzle_temp": 250,
        "bed_temp": 100,
        "weight_g": 650,
        "capacity_g": 1000,
    },
    "spool_4": {
        "id": 4,
        "name": "Spool 4",
        "type": "TPU",
        "color": "#F59E0B",
        "nozzle_temp": 220,
        "bed_temp": 50,
        "weight_g": 500,
        "capacity_g": 1000,
    },
}


class SpoolGraphicWidget(QtWidgets.QWidget):
    """Custom vector filament spool illustration tinted with the active filament colour."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor("#3B82F6")
        self._type_text = "PLA"
        self.setMinimumSize(130, 130)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_spool(self, hex_color: str, f_type: str):
        self._color = QtGui.QColor(hex_color or "#3B82F6")
        self._type_text = f_type or "PLA"
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        cx, cy = w * 0.5, h * 0.5
        r_outer = min(w, h) * 0.44
        r_fila = r_outer * 0.83
        r_hub = r_outer * 0.42
        r_hole = r_outer * 0.22

        # Outer ambient glow in filament color
        glow = QtGui.QRadialGradient(QtCore.QPointF(cx, cy), r_outer * 1.12)
        c_glow = QtGui.QColor(self._color)
        c_glow.setAlpha(70)
        glow.setColorAt(0.6, c_glow)
        glow.setColorAt(1.0, QtGui.QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(glow))
        p.drawEllipse(QtCore.QPointF(cx, cy), r_outer * 1.12, r_outer * 1.12)

        # Dark polycarbonate spool flange
        flange_grad = QtGui.QLinearGradient(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer)
        flange_grad.setColorAt(0.0, QtGui.QColor("#334155"))
        flange_grad.setColorAt(1.0, QtGui.QColor("#0F172A"))
        p.setBrush(QtGui.QBrush(flange_grad))
        p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 140), 2.0))
        p.drawEllipse(QtCore.QPointF(cx, cy), r_outer, r_outer)

        # Wound filament body with 3D radial shading & concentric strand rings
        f_grad = QtGui.QRadialGradient(QtCore.QPointF(cx - r_fila * 0.25, cy - r_fila * 0.25), r_fila * 1.2)
        f_grad.setColorAt(0.0, self._color.lighter(135))
        f_grad.setColorAt(0.55, self._color)
        f_grad.setColorAt(1.0, self._color.darker(155))
        p.setBrush(QtGui.QBrush(f_grad))
        p.setPen(QtGui.QPen(self._color.lighter(150), 1.5))
        p.drawEllipse(QtCore.QPointF(cx, cy), r_fila, r_fila)

        # Concentric filament wind lines
        ring_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 42), 1.0)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for frac in (0.52, 0.62, 0.72):
            rr = r_outer * frac
            p.drawEllipse(QtCore.QPointF(cx, cy), rr, rr)

        # Filament loose strand leading out from bottom-right of spool
        strand_path = QtGui.QPainterPath()
        strand_path.moveTo(cx + r_fila * 0.68, cy + r_fila * 0.68)
        strand_path.cubicTo(
            cx + r_outer * 0.98, cy + r_outer * 0.45,
            cx + r_outer * 1.05, cy + r_outer * 0.85,
            cx + r_outer * 0.88, cy + r_outer * 1.02,
        )
        p.setPen(QtGui.QPen(self._color.lighter(120), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(strand_path)

        # Flange cutout spokes (subtle translucent overlays)
        import math
        p.setPen(QtGui.QPen(QtGui.QColor(15, 23, 42, 130), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for k in range(6):
            ang = k * math.pi / 3.0 + 0.3
            x1 = cx + math.cos(ang) * (r_hub + 2)
            y1 = cy + math.sin(ang) * (r_hub + 2)
            x2 = cx + math.cos(ang) * (r_outer - 3)
            y2 = cy + math.sin(ang) * (r_outer - 3)
            p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

        # Inner hub ring
        p.setBrush(QtGui.QColor("#1E293B"))
        p.setPen(QtGui.QPen(QtGui.QColor(148, 163, 184, 150), 1.8))
        p.drawEllipse(QtCore.QPointF(cx, cy), r_hub, r_hub)

        # Center bore hole
        p.setBrush(QtGui.QColor("#0B0F19"))
        p.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 130), 1.5))
        p.drawEllipse(QtCore.QPointF(cx, cy), r_hole, r_hole)

        # Material label inside center bore
        f = p.font()
        f.setPointSizeF(max(7.5, r_hole * 0.52))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QtGui.QColor("#FFFFFF"))
        p.drawText(
            QtCore.QRectF(cx - r_hub, cy - r_hole, r_hub * 2.0, r_hole * 2.0),
            Qt.AlignmentFlag.AlignCenter,
            self._type_text,
        )
        p.end()


class ClickableSpoolCard(QtWidgets.QFrame):
    """Interactive Spool Showcase Card — emits clicked() when touched anywhere."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SpoolSelectorButton(QtWidgets.QPushButton):
    """Spool slot selection pill showing slot number, color swatch, filament type, and active indicator."""

    def __init__(self, slot_id: int, on_select, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.on_select = on_select
        self.is_active = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.clicked.connect(lambda: self.on_select(self.slot_id))

    def update_data(self, spool_data: dict, is_active: bool, scale: float = 1.0):
        self.is_active = is_active
        self.setChecked(is_active)
        f_type = spool_data.get("type", "PLA")
        name = spool_data.get("name", f"Spool {self.slot_id}")

        self.setText(f"  \u25CF {name} ({f_type})")

        b_color = "#00E5FF" if is_active else "rgba(255, 255, 255, 0.12)"
        bg = "rgba(0, 229, 255, 0.15)" if is_active else "rgba(30, 41, 59, 0.7)"
        text_col = "#00E5FF" if is_active else "#E2E8F0"
        fw = "800" if is_active else "600"

        radius = _s(10, scale)
        pad_v = _s(6, scale)
        pad_h = _s(10, scale)
        font_sz = _s(12, scale)

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1.5px solid {b_color};
                border-radius: {radius}px;
                color: {text_col};
                font-weight: {fw};
                font-size: {font_sz}px;
                padding: {pad_v}px {pad_h}px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: #38BDF8;
                background: rgba(56, 189, 248, 0.22);
            }}
        """)


class SpoolPage(QtWidgets.QWidget):
    """Neat, non-scrolling Spool Screen with visual spool card and tap-to-open Settings modal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "spool"
        self._scale = 1.0
        self._active_slot = 1
        self._has_ams = False
        self._ams_count = 4
        self._extrude_dist = 10.0
        self._live_nozzle_cur = 0.0
        self._live_nozzle_tgt = 0.0
        self._live_bed_cur = 0.0
        self._live_bed_tgt = 0.0
        self._spools = dict(DEFAULT_SPOOLS)
        self._load_saved_spools()

        self.setObjectName("SpoolPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(8)
        self.vbox = main_layout
        self.headers = []

        # --- Top AMS / Multi-Spool Bar (only visible when AMS/MMU hardware detected) ---
        self.ams_header = QtWidgets.QLabel("AMS / MMU SPOOL SELECTION")
        self.ams_header.setObjectName("SettingsSecHeader")
        self.ams_header.setVisible(False)
        self.vbox.addWidget(self.ams_header)
        self.headers.append(self.ams_header)

        self.selector_box = QtWidgets.QFrame()
        self.selector_box.setObjectName("CalibrateCard")
        self.selector_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.selector_box.setVisible(False)
        self.sel_layout = QtWidgets.QHBoxLayout(self.selector_box)
        self.sel_layout.setContentsMargins(8, 6, 8, 6)
        self.sel_layout.setSpacing(8)

        self.slot_buttons = []
        for i in range(1, 5):
            btn = SpoolSelectorButton(i, on_select=self._on_slot_selected, parent=self)
            self.sel_layout.addWidget(btn)
            self.slot_buttons.append(btn)

        self.vbox.addWidget(self.selector_box)

        # --- Section Header Row: Active Spool + Live Nozzle Badge ---
        top_hdr = QtWidgets.QHBoxLayout()
        self.config_header = QtWidgets.QLabel("ACTIVE FILAMENT SPOOL")
        self.config_header.setObjectName("SettingsSecHeader")
        top_hdr.addWidget(self.config_header)
        self.headers.append(self.config_header)
        top_hdr.addStretch(1)

        self.live_temp_badge = QtWidgets.QLabel("\u25CF Nozzle: --.-\u00B0C")
        self.live_temp_badge.setStyleSheet(
            "color: #38BDF8; background: rgba(56, 189, 248, 0.14); border: 1px solid rgba(56, 189, 248, 0.45); "
            "border-radius: 6px; font-size: 11px; font-weight: 800; padding: 3px 10px;"
        )
        top_hdr.addWidget(self.live_temp_badge)
        self.vbox.addLayout(top_hdr)

        # --- Main 2-Column Split: Left = Touchable Active Spool Card, Right = Filament Actions & Extrude ---
        body_row = QtWidgets.QHBoxLayout()
        body_row.setSpacing(12)

        # LEFT: Touchable Active Spool Card
        self.spool_card = ClickableSpoolCard(self)
        self.spool_card.setObjectName("SpoolShowcaseCard")
        self.spool_card.clicked.connect(self._open_settings_modal)
        self.spool_card.setStyleSheet("""
            QFrame#SpoolShowcaseCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #162032, stop:1 #0F172A);
                border: 1.5px solid rgba(0, 229, 255, 0.45);
                border-radius: 14px;
            }
            QFrame#SpoolShowcaseCard:hover {
                border: 1.5px solid #00E5FF;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E293B, stop:1 #111C2D);
            }
            QFrame#SpoolShowcaseCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        sc_lay = QtWidgets.QVBoxLayout(self.spool_card)
        sc_lay.setContentsMargins(16, 12, 16, 12)
        sc_lay.setSpacing(8)

        # Top row inside Spool Card: Spool Graphic + Info Column
        sc_top = QtWidgets.QHBoxLayout()
        sc_top.setSpacing(14)

        self.spool_graphic = SpoolGraphicWidget(self.spool_card)
        sc_top.addWidget(self.spool_graphic, 0, Qt.AlignmentFlag.AlignVCenter)

        info_col = QtWidgets.QVBoxLayout()
        info_col.setSpacing(6)
        info_col.addStretch(1)

        self.spool_title_lbl = QtWidgets.QLabel("Spool 1")
        self.spool_title_lbl.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: 900;")
        info_col.addWidget(self.spool_title_lbl)

        # Material + Color pills row
        pills_row = QtWidgets.QHBoxLayout()
        pills_row.setSpacing(6)
        self.type_pill = QtWidgets.QLabel("PLA")
        self.type_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_pill.setStyleSheet(
            "background: rgba(0, 229, 255, 0.16); color: #00E5FF; border: 1px solid rgba(0, 229, 255, 0.45); "
            "font-size: 13px; font-weight: 900; border-radius: 7px; padding: 3px 10px;"
        )
        pills_row.addWidget(self.type_pill)

        self.color_swatch = QtWidgets.QLabel("\u25CF Blue")
        self.color_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_swatch.setStyleSheet(
            "background: #3B82F6; color: #FFFFFF; font-size: 12px; font-weight: 800; "
            "border-radius: 7px; padding: 3px 10px;"
        )
        pills_row.addWidget(self.color_swatch)
        pills_row.addStretch(1)
        info_col.addLayout(pills_row)

        # Temperature summary boxes
        temps_grid = QtWidgets.QHBoxLayout()
        temps_grid.setSpacing(8)

        self.noz_stat_box = QtWidgets.QFrame()
        self.noz_stat_box.setStyleSheet(
            "QFrame { background: rgba(255, 90, 95, 0.10); border: 1px solid rgba(255, 90, 95, 0.35); border-radius: 8px; } QLabel { border: none; background: transparent; }"
        )
        nb_l = QtWidgets.QVBoxLayout(self.noz_stat_box)
        nb_l.setContentsMargins(8, 4, 8, 4)
        nb_l.setSpacing(1)
        nb_k = QtWidgets.QLabel("NOZZLE PRESET")
        nb_k.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 800;")
        self.card_noz_lbl = QtWidgets.QLabel("210 \u00B0C")
        self.card_noz_lbl.setStyleSheet("color: #FF5A5F; font-size: 15px; font-weight: 900;")
        nb_l.addWidget(nb_k)
        nb_l.addWidget(self.card_noz_lbl)
        temps_grid.addWidget(self.noz_stat_box, 1)

        self.bed_stat_box = QtWidgets.QFrame()
        self.bed_stat_box.setStyleSheet(
            "QFrame { background: rgba(0, 229, 255, 0.10); border: 1px solid rgba(0, 229, 255, 0.35); border-radius: 8px; } QLabel { border: none; background: transparent; }"
        )
        bb_l = QtWidgets.QVBoxLayout(self.bed_stat_box)
        bb_l.setContentsMargins(8, 4, 8, 4)
        bb_l.setSpacing(1)
        bb_k = QtWidgets.QLabel("BED PRESET")
        bb_k.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 800;")
        self.card_bed_lbl = QtWidgets.QLabel("60 \u00B0C")
        self.card_bed_lbl.setStyleSheet("color: #00E5FF; font-size: 15px; font-weight: 900;")
        bb_l.addWidget(bb_k)
        bb_l.addWidget(self.card_bed_lbl)
        temps_grid.addWidget(self.bed_stat_box, 1)

        info_col.addLayout(temps_grid)

        # Remaining spool weight & length box
        self.weight_box = QtWidgets.QFrame()
        self.weight_box.setStyleSheet(
            "QFrame { background: rgba(15, 23, 42, 0.72); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; } QLabel { border: none; background: transparent; }"
        )
        wb_lay = QtWidgets.QVBoxLayout(self.weight_box)
        wb_lay.setContentsMargins(8, 4, 8, 5)
        wb_lay.setSpacing(3)
        wb_top = QtWidgets.QHBoxLayout()
        wb_k = QtWidgets.QLabel("REMAINING SPOOL")
        wb_k.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 800;")
        self.card_weight_lbl = QtWidgets.QLabel("850g / 1000g (~285m)")
        self.card_weight_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 900;")
        wb_top.addWidget(wb_k)
        wb_top.addStretch(1)
        wb_top.addWidget(self.card_weight_lbl)
        wb_lay.addLayout(wb_top)

        self.weight_pbar = QtWidgets.QProgressBar()
        self.weight_pbar.setRange(0, 100)
        self.weight_pbar.setValue(85)
        self.weight_pbar.setTextVisible(False)
        self.weight_pbar.setFixedHeight(6)
        self.weight_pbar.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); border: none; border-radius: 3px; } "
            "QProgressBar::chunk { background: #34D399; border-radius: 3px; }"
        )
        wb_lay.addWidget(self.weight_pbar)
        info_col.addWidget(self.weight_box)

        info_col.addStretch(1)
        sc_top.addLayout(info_col, 1)
        sc_lay.addLayout(sc_top, 1)

        # Bottom callout bar inside Spool Card ("Tap Card to Configure Spool Settings")
        self.tap_hint_bar = QtWidgets.QFrame()
        self.tap_hint_bar.setStyleSheet(
            "QFrame { background: rgba(0, 229, 255, 0.10); border: 1px dashed rgba(0, 229, 255, 0.45); border-radius: 8px; } QLabel { border: none; background: transparent; }"
        )
        th_lay = QtWidgets.QHBoxLayout(self.tap_hint_bar)
        th_lay.setContentsMargins(10, 6, 10, 6)
        self.tap_hint_lbl = QtWidgets.QLabel("\u2699  Tap Spool Card to Change Material, Colour & Temperatures")
        self.tap_hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tap_hint_lbl.setStyleSheet("color: #7DD3FC; font-size: 11px; font-weight: 800;")
        th_lay.addWidget(self.tap_hint_lbl)
        sc_lay.addWidget(self.tap_hint_bar)

        body_row.addWidget(self.spool_card, 11)

        # RIGHT: Filament Operations + Manual Extrude / Retract Card
        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(10)

        # Card 1: Load / Unload / Preheat
        ops_card = QtWidgets.QFrame()
        ops_card.setObjectName("CalibrateCard")
        ops_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ops_card.setStyleSheet("""
            QFrame#CalibrateCard {
                background: rgba(21, 29, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
            }
            QFrame#CalibrateCard QLabel { background: transparent; border: none; }
        """)
        ops_lay = QtWidgets.QVBoxLayout(ops_card)
        ops_lay.setContentsMargins(12, 10, 12, 10)
        ops_lay.setSpacing(8)

        ops_title = QtWidgets.QLabel("FILAMENT ACTIONS")
        ops_title.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;")
        ops_lay.addWidget(ops_title)

        lu_row = QtWidgets.QHBoxLayout()
        lu_row.setSpacing(8)

        self.load_btn = QtWidgets.QPushButton("\U0001F4E5  Load")
        self.load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_btn.setMinimumHeight(42)
        self.load_btn.clicked.connect(self._on_load_filament)
        lu_row.addWidget(self.load_btn, 1)

        self.unload_btn = QtWidgets.QPushButton("\U0001F4E4  Unload")
        self.unload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unload_btn.setMinimumHeight(42)
        self.unload_btn.clicked.connect(self._on_unload_filament)
        lu_row.addWidget(self.unload_btn, 1)

        ops_lay.addLayout(lu_row)

        self.preheat_btn = QtWidgets.QPushButton("\U0001F525  Preheat Nozzle to Spool Temp")
        self.preheat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preheat_btn.setMinimumHeight(36)
        self.preheat_btn.clicked.connect(self._on_heat_spool_nozzle)
        ops_lay.addWidget(self.preheat_btn)

        right_col.addWidget(ops_card)

        # Card 2: Manual Extrude & Retract
        ext_card = QtWidgets.QFrame()
        ext_card.setObjectName("CalibrateCard")
        ext_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ext_card.setStyleSheet("""
            QFrame#CalibrateCard {
                background: rgba(21, 29, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
            }
            QFrame#CalibrateCard QLabel { background: transparent; border: none; }
        """)
        ext_lay = QtWidgets.QVBoxLayout(ext_card)
        ext_lay.setContentsMargins(12, 10, 12, 10)
        ext_lay.setSpacing(8)

        ext_hdr = QtWidgets.QHBoxLayout()
        ext_title = QtWidgets.QLabel("MANUAL EXTRUDE / RETRACT")
        ext_title.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.8px;")
        ext_hdr.addWidget(ext_title)
        ext_hdr.addStretch(1)
        ext_lay.addLayout(ext_hdr)

        dist_row = QtWidgets.QHBoxLayout()
        dist_row.setSpacing(6)
        self.dist_btns = {}
        for d in (5, 10, 25, 50):
            b = QtWidgets.QPushButton(f"{d}mm")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _c=False, val=float(d): self._set_extrude_dist(val))
            dist_row.addWidget(b, 1)
            self.dist_btns[float(d)] = b
        ext_lay.addLayout(dist_row)

        er_row = QtWidgets.QHBoxLayout()
        er_row.setSpacing(8)

        self.btn_extrude = QtWidgets.QPushButton("\u2B07  Extrude +10mm")
        self.btn_extrude.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_extrude.setMinimumHeight(38)
        self.btn_extrude.clicked.connect(lambda: self._on_manual_extrude(+self._extrude_dist))
        er_row.addWidget(self.btn_extrude, 1)

        self.btn_retract = QtWidgets.QPushButton("\u2B06  Retract -10mm")
        self.btn_retract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retract.setMinimumHeight(38)
        self.btn_retract.clicked.connect(lambda: self._on_manual_extrude(-self._extrude_dist))
        er_row.addWidget(self.btn_retract, 1)

        ext_lay.addLayout(er_row)
        right_col.addWidget(ext_card)

        body_row.addLayout(right_col, 10)
        self.vbox.addLayout(body_row, 1)

        # Bottom Status Line
        self.status_lbl = QtWidgets.QLabel("Touch the Spool card to configure filament type, colour, and preset temperatures.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vbox.addWidget(self.status_lbl)

        # --- Build In-Window Spool Settings Modal Overlay (hidden by default) ---
        self._build_settings_modal()

        # Initialize UI with Spool 1
        self._set_extrude_dist(10.0)
        self._refresh_spool_display()

    def _build_settings_modal(self):
        """Create the touch modal overlay that appears when the Spool Card is tapped."""
        self.settings_overlay = QtWidgets.QFrame(self)
        self.settings_overlay.setObjectName("SpoolSettingsOverlay")
        self.settings_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.settings_overlay.setStyleSheet("QFrame#SpoolSettingsOverlay { background: rgba(6, 10, 19, 0.86); }")
        self.settings_overlay.hide()

        ov_lay = QtWidgets.QVBoxLayout(self.settings_overlay)
        ov_lay.setContentsMargins(28, 16, 28, 16)
        ov_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.modal_card = QtWidgets.QFrame(self.settings_overlay)
        self.modal_card.setObjectName("SpoolSettingsCard")
        self.modal_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.modal_card.setMinimumWidth(560)
        self.modal_card.setMaximumWidth(740)
        self.modal_card.setStyleSheet("""
            QFrame#SpoolSettingsCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #162032, stop:1 #0B0F19);
                border: 1.5px solid #00E5FF;
                border-radius: 16px;
            }
            QFrame#SpoolSettingsCard QLabel {
                background: transparent;
                border: none;
            }
        """)
        mc_lay = QtWidgets.QVBoxLayout(self.modal_card)
        mc_lay.setContentsMargins(18, 14, 18, 14)
        mc_lay.setSpacing(10)

        # Modal Header
        m_hdr = QtWidgets.QHBoxLayout()
        self.modal_title = QtWidgets.QLabel("\u2699  SPOOL 1 SETTINGS")
        self.modal_title.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: 900; letter-spacing: 0.5px;")
        m_hdr.addWidget(self.modal_title)
        m_hdr.addStretch(1)

        self.modal_summary = QtWidgets.QLabel("PLA  \u2022  210\u00B0C / 60\u00B0C")
        self.modal_summary.setStyleSheet(
            "color: #00E5FF; background: rgba(0, 229, 255, 0.14); border: 1px solid rgba(0, 229, 255, 0.4); "
            "border-radius: 6px; font-size: 12px; font-weight: 800; padding: 3px 10px;"
        )
        m_hdr.addWidget(self.modal_summary)

        close_x = QtWidgets.QPushButton("\u2715")
        close_x.setFixedSize(30, 30)
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.18); "
            "border-radius: 15px; color: #CBD5E1; font-size: 14px; font-weight: 800; }"
            "QPushButton:pressed { background: rgba(239,68,68,0.35); color: #FFFFFF; }"
        )
        close_x.clicked.connect(self._close_settings_modal)
        m_hdr.addWidget(close_x)
        mc_lay.addLayout(m_hdr)

        # 1. Filament Type Preset Pills (2 rows of 5 touch buttons)
        type_hdr = QtWidgets.QLabel("FILAMENT MATERIAL (AUTO-SETS NOZZLE & BED TEMPS)")
        type_hdr.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.6px;")
        mc_lay.addWidget(type_hdr)

        type_grid = QtWidgets.QGridLayout()
        type_grid.setSpacing(6)
        self.type_btns = {}
        for idx, f_type in enumerate(FILAMENT_PRESETS.keys()):
            tb = QtWidgets.QPushButton(f_type)
            tb.setCursor(Qt.CursorShape.PointingHandCursor)
            tb.setFixedHeight(32)
            tb.clicked.connect(lambda _c=False, t=f_type: self._on_type_changed(t))
            type_grid.addWidget(tb, idx // 5, idx % 5)
            self.type_btns[f_type] = tb
        mc_lay.addLayout(type_grid)

        # 2. Filament Color Swatches (2 rows of 8)
        col_hdr = QtWidgets.QLabel("FILAMENT COLOUR")
        col_hdr.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.6px;")
        mc_lay.addWidget(col_hdr)

        self.color_grid = QtWidgets.QGridLayout()
        self.color_grid.setSpacing(6)
        self.color_btns = []
        for idx, (hex_code, col_name) in enumerate(PALETTE_COLORS):
            c_btn = QtWidgets.QPushButton()
            c_btn.setFixedSize(30, 30)
            c_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            c_btn.setToolTip(col_name)
            c_btn.setProperty("hex", hex_code)
            c_btn.setProperty("name", col_name)
            c_btn.clicked.connect(lambda _checked=False, h=hex_code, n=col_name: self._on_color_picked(h, n))
            self.color_grid.addWidget(c_btn, idx // 8, idx % 8)
            self.color_btns.append(c_btn)
        mc_lay.addLayout(self.color_grid)

        # 3. Nozzle & Bed Preset Temperature Steppers side-by-side
        temp_row = QtWidgets.QHBoxLayout()
        temp_row.setSpacing(12)

        # Nozzle stepper box
        noz_frame = QtWidgets.QFrame()
        noz_frame.setStyleSheet(
            "QFrame { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 90, 95, 0.35); border-radius: 10px; } QLabel { border: none; background: transparent; }"
        )
        nf_lay = QtWidgets.QHBoxLayout(noz_frame)
        nf_lay.setContentsMargins(10, 6, 10, 6)
        nf_lbl = QtWidgets.QLabel("Nozzle:")
        nf_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: 800;")
        nf_lay.addWidget(nf_lbl)

        self.noz_down_btn = QtWidgets.QPushButton("-5\u00B0")
        self.noz_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.noz_down_btn.setFixedSize(44, 30)
        self.noz_down_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        self.noz_down_btn.clicked.connect(lambda: self._adj_temp("nozzle", -5))
        nf_lay.addWidget(self.noz_down_btn)

        self.noz_val_lbl = QtWidgets.QLabel("210 \u00B0C")
        self.noz_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.noz_val_lbl.setStyleSheet("color: #FF5A5F; font-size: 15px; font-weight: 900; min-width: 64px;")
        nf_lay.addWidget(self.noz_val_lbl, 1)

        self.noz_up_btn = QtWidgets.QPushButton("+5\u00B0")
        self.noz_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.noz_up_btn.setFixedSize(44, 30)
        self.noz_up_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        self.noz_up_btn.clicked.connect(lambda: self._adj_temp("nozzle", +5))
        nf_lay.addWidget(self.noz_up_btn)
        temp_row.addWidget(noz_frame, 1)

        # Bed stepper box
        bed_frame = QtWidgets.QFrame()
        bed_frame.setStyleSheet(
            "QFrame { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 229, 255, 0.35); border-radius: 10px; } QLabel { border: none; background: transparent; }"
        )
        bf_lay = QtWidgets.QHBoxLayout(bed_frame)
        bf_lay.setContentsMargins(10, 6, 10, 6)
        bf_lbl = QtWidgets.QLabel("Bed:")
        bf_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: 800;")
        bf_lay.addWidget(bf_lbl)

        self.bed_down_btn = QtWidgets.QPushButton("-5\u00B0")
        self.bed_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bed_down_btn.setFixedSize(44, 30)
        self.bed_down_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        self.bed_down_btn.clicked.connect(lambda: self._adj_temp("bed", -5))
        bf_lay.addWidget(self.bed_down_btn)

        self.bed_val_lbl = QtWidgets.QLabel("60 \u00B0C")
        self.bed_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bed_val_lbl.setStyleSheet("color: #00E5FF; font-size: 15px; font-weight: 900; min-width: 64px;")
        bf_lay.addWidget(self.bed_val_lbl, 1)

        self.bed_up_btn = QtWidgets.QPushButton("+5\u00B0")
        self.bed_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bed_up_btn.setFixedSize(44, 30)
        self.bed_up_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        self.bed_up_btn.clicked.connect(lambda: self._adj_temp("bed", +5))
        bf_lay.addWidget(self.bed_up_btn)
        temp_row.addWidget(bed_frame, 1)

        mc_lay.addLayout(temp_row)

        # 4. Spool Remaining Weight Stepper & Quick Presets
        w_frame = QtWidgets.QFrame()
        w_frame.setStyleSheet(
            "QFrame { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 10px; } QLabel { border: none; background: transparent; }"
        )
        wf_lay = QtWidgets.QHBoxLayout(w_frame)
        wf_lay.setContentsMargins(10, 5, 10, 5)
        wf_lay.setSpacing(6)
        wf_lbl = QtWidgets.QLabel("Spool Weight:")
        wf_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: 800;")
        wf_lay.addWidget(wf_lbl)

        w_dn = QtWidgets.QPushButton("-50g")
        w_dn.setCursor(Qt.CursorShape.PointingHandCursor)
        w_dn.setFixedSize(46, 28)
        w_dn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        w_dn.clicked.connect(lambda: self._adj_weight(-50))
        wf_lay.addWidget(w_dn)

        self.weight_val_lbl = QtWidgets.QLabel("850 g")
        self.weight_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_val_lbl.setStyleSheet("color: #34D399; font-size: 14px; font-weight: 900; min-width: 64px;")
        wf_lay.addWidget(self.weight_val_lbl)

        w_up = QtWidgets.QPushButton("+50g")
        w_up.setCursor(Qt.CursorShape.PointingHandCursor)
        w_up.setFixedSize(46, 28)
        w_up.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px;")
        w_up.clicked.connect(lambda: self._adj_weight(+50))
        wf_lay.addWidget(w_up)

        wf_lay.addStretch(1)
        for preset_g, lbl in ((1000, "Full 1kg"), (750, "750g"), (500, "500g"), (250, "250g")):
            pb = QtWidgets.QPushButton(lbl)
            pb.setCursor(Qt.CursorShape.PointingHandCursor)
            pb.setFixedHeight(26)
            pb.setStyleSheet(
                "QPushButton { background: #1E293B; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.16); "
                "border-radius: 6px; font-size: 11px; font-weight: 800; padding: 0 8px; }"
                "QPushButton:pressed { background: #10B981; color: #0B0F19; }"
            )
            pb.clicked.connect(lambda _c=False, g=preset_g: self._set_weight(g))
            wf_lay.addWidget(pb)

        mc_lay.addWidget(w_frame)

        # Done button row
        done_row = QtWidgets.QHBoxLayout()
        done_row.addStretch(1)
        done_btn = QtWidgets.QPushButton("\u2713  Save && Close")
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFixedHeight(36)
        done_btn.setMinimumWidth(160)
        done_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
                border: 1px solid rgba(255,255,255,0.35);
                border-radius: 9px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 900;
                padding: 0 20px;
            }
            QPushButton:pressed { background: #0284C7; }
        """)
        done_btn.clicked.connect(self._close_settings_modal)
        done_row.addWidget(done_btn)
        mc_lay.addLayout(done_row)

        ov_lay.addWidget(self.modal_card)

    def _open_settings_modal(self):
        self._refresh_spool_display()
        self.settings_overlay.setGeometry(self.rect())
        self.settings_overlay.show()
        self.settings_overlay.raise_()

    def _close_settings_modal(self):
        self.settings_overlay.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "settings_overlay") and self.settings_overlay.isVisible():
            self.settings_overlay.setGeometry(self.rect())

    def update_config(self, config: dict, objects: list = None):
        """Detect AMS/MMU multi-material hardware (MMU, ERCF, TradRack, Box, AMS) or default to standalone Spool 1."""
        cfg = config or {}
        objs = objects or []

        cfg_keys = [str(k).lower().strip() for k in cfg.keys()]
        obj_names = [str(o).lower().strip() for o in objs]

        has_ams = False
        for k in cfg_keys:
            words = k.replace("_", " ").split()
            if any(p in words or k.startswith(p) for p in ["mmu", "ercf", "tradrack", "happy_hare", "bambu_ams", "anycubic_ace"]):
                has_ams = True
                break
            if k.startswith("extruder") and k != "extruder":
                has_ams = True
                break

        if not has_ams:
            for o in obj_names:
                if any(o.startswith(p) or f" {p}" in o for p in ["mmu", "ercf", "tradrack", "happy_hare", "bambu_ams", "anycubic_ace"]):
                    has_ams = True
                    break
                if o.startswith("extruder") and o != "extruder":
                    has_ams = True
                    break

        self._has_ams = has_ams
        if has_ams:
            self.ams_header.setText("AMS / MMU DETECTED \u2014 SELECT ACTIVE SPOOL")
            self.ams_header.setVisible(True)
            self.selector_box.setVisible(True)
            for btn in self.slot_buttons:
                btn.setVisible(True)
        else:
            self._active_slot = 1
            self.selector_box.setVisible(False)
            self.ams_header.setVisible(False)

        self._refresh_spool_display()

    def _on_slot_selected(self, slot_id: int):
        self._active_slot = slot_id
        self._refresh_spool_display()

    def _refresh_spool_display(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])

        for btn in self.slot_buttons:
            s_data = self._spools.get(f"spool_{btn.slot_id}", DEFAULT_SPOOLS["spool_1"])
            btn.update_data(s_data, is_active=(btn.slot_id == self._active_slot), scale=self._scale)

        name = data.get("name", f"Spool {self._active_slot}")
        f_type = data.get("type", "PLA")
        color = data.get("color", "#3B82F6")
        noz_temp = int(data.get("nozzle_temp", 210))
        bed_temp = int(data.get("bed_temp", 60))

        self.spool_title_lbl.setText(name)
        self.type_pill.setText(f_type)
        self.spool_graphic.set_spool(color, f_type)

        col_name = "Custom"
        for hex_code, c_name in PALETTE_COLORS:
            if hex_code.lower() == color.lower():
                col_name = c_name
                break

        text_fg = "#000000" if color.upper() in ("#FFFFFF", "#FDE047", "#EAB308") else "#FFFFFF"
        self.color_swatch.setText(f"\u25CF {col_name}")
        self.color_swatch.setStyleSheet(
            f"background: {color}; color: {text_fg}; font-size: 12px; font-weight: 800; "
            f"border-radius: 7px; padding: 3px 10px;"
        )

        self.card_noz_lbl.setText(f"{noz_temp} \u00B0C")
        self.card_bed_lbl.setText(f"{bed_temp} \u00B0C")
        self.noz_val_lbl.setText(f"{noz_temp} \u00B0C")
        self.bed_val_lbl.setText(f"{bed_temp} \u00B0C")

        w_g = float(data.get("weight_g", 1000))
        cap_g = max(100.0, float(data.get("capacity_g", 1000)))
        pct_w = max(0, min(100, int(round((w_g / cap_g) * 100))))
        est_m = int(round(w_g / 2.98))
        w_col = "#34D399" if pct_w > 25 else ("#FBBF24" if pct_w > 10 else "#EF4444")
        if hasattr(self, "card_weight_lbl"):
            self.card_weight_lbl.setText(f"{int(round(w_g))}g / {int(round(cap_g))}g (~{est_m}m)")
            self.card_weight_lbl.setStyleSheet(f"color: {w_col}; font-size: 11px; font-weight: 900;")
        if hasattr(self, "weight_pbar"):
            self.weight_pbar.setValue(pct_w)
            self.weight_pbar.setStyleSheet(
                f"QProgressBar {{ background: rgba(255,255,255,0.08); border: none; border-radius: 3px; }} "
                f"QProgressBar::chunk {{ background: {w_col}; border-radius: 3px; }}"
            )
        if hasattr(self, "weight_val_lbl"):
            self.weight_val_lbl.setText(f"{int(round(w_g))} g")

        if hasattr(self, "modal_title"):
            self.modal_title.setText(f"\u2699  {name.upper()} SETTINGS")
            self.modal_summary.setText(f"{f_type}  \u2022  {col_name}  \u2022  {int(round(w_g))}g  \u2022  {noz_temp}\u00B0C / {bed_temp}\u00B0C")

        # Highlight active filament type pill inside settings modal
        if hasattr(self, "type_btns"):
            for t_key, tb in self.type_btns.items():
                if t_key == f_type:
                    tb.setStyleSheet(
                        "QPushButton { background: #00E5FF; color: #0B0F19; border: 1.5px solid #FFFFFF; "
                        "border-radius: 7px; font-size: 12px; font-weight: 900; }"
                    )
                else:
                    tb.setStyleSheet(
                        "QPushButton { background: #1E293B; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.16); "
                        "border-radius: 7px; font-size: 12px; font-weight: 700; }"
                        "QPushButton:hover { border-color: #38BDF8; color: #FFFFFF; }"
                    )

        # Highlight active color button inside settings modal
        if hasattr(self, "color_btns"):
            for c_btn in self.color_btns:
                hex_c = str(c_btn.property("hex") or "")
                is_sel = hex_c.lower() == color.lower()
                border = "3px solid #FFFFFF" if is_sel else "1.5px solid rgba(255,255,255,0.28)"
                c_btn.setStyleSheet(f"background-color: {hex_c}; border: {border}; border-radius: 15px;")

    def _on_type_changed(self, f_type: str):
        """Auto-fill standard nozzle and bed temperatures for the selected filament type."""
        preset = FILAMENT_PRESETS.get(f_type, {"nozzle": 210, "bed": 60})
        spool_key = f"spool_{self._active_slot}"

        self._spools[spool_key]["type"] = f_type
        self._spools[spool_key]["nozzle_temp"] = preset["nozzle"]
        self._spools[spool_key]["bed_temp"] = preset["bed"]

        self._save_spools()
        self._refresh_spool_display()
        self.status_lbl.setText(f"Auto-filled {f_type} standard temps: {preset['nozzle']}\u00B0C Nozzle / {preset['bed']}\u00B0C Bed")

    def _on_color_picked(self, hex_code: str, col_name: str):
        spool_key = f"spool_{self._active_slot}"
        self._spools[spool_key]["color"] = hex_code
        self._save_spools()
        self._refresh_spool_display()
        self.status_lbl.setText(f"Spool {self._active_slot} colour set to {col_name}")

    def _adj_temp(self, kind: str, delta: int):
        spool_key = f"spool_{self._active_slot}"
        if kind == "nozzle":
            cur = int(self._spools[spool_key].get("nozzle_temp", 210))
            new_val = max(0, min(350, cur + delta))
            self._spools[spool_key]["nozzle_temp"] = new_val
        else:
            cur = int(self._spools[spool_key].get("bed_temp", 60))
            new_val = max(0, min(150, cur + delta))
            self._spools[spool_key]["bed_temp"] = new_val
        self._save_spools()
        self._refresh_spool_display()

    def _adj_weight(self, delta_g: int):
        spool_key = f"spool_{self._active_slot}"
        cur_w = float(self._spools[spool_key].get("weight_g", 1000))
        cap_w = float(self._spools[spool_key].get("capacity_g", 1000))
        new_w = max(0.0, min(cap_w, cur_w + delta_g))
        self._spools[spool_key]["weight_g"] = round(new_w, 1)
        self._save_spools()
        self._refresh_spool_display()

    def _set_weight(self, grams: int):
        spool_key = f"spool_{self._active_slot}"
        self._spools[spool_key]["weight_g"] = float(grams)
        self._spools[spool_key]["capacity_g"] = 1000.0
        self._save_spools()
        self._refresh_spool_display()

    def get_active_spool_data(self) -> dict:
        spool_key = f"spool_{self._active_slot}"
        return dict(self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"]))

    def deduct_filament_mm(self, used_mm: float):
        """Deduct used filament length (mm) from active spool (~2.98g per meter of 1.75mm filament)."""
        if used_mm <= 0:
            return
        spool_key = f"spool_{self._active_slot}"
        cur_w = float(self._spools[spool_key].get("weight_g", 1000))
        used_g = (used_mm / 1000.0) * 2.98
        self._spools[spool_key]["weight_g"] = round(max(0.0, cur_w - used_g), 1)
        self._save_spools()
        self._refresh_spool_display()

    def update_temps(self, n_cur: float, n_tgt: float, b_cur: float, b_tgt: float):
        """Receive live nozzle and bed temperatures from MoonrakerClient."""
        self._live_nozzle_cur = float(n_cur)
        self._live_nozzle_tgt = float(n_tgt)
        self._live_bed_cur = float(b_cur)
        self._live_bed_tgt = float(b_tgt)

        if n_cur >= 180.0:
            tgt_str = f" / {n_tgt:.0f}\u00B0C" if n_tgt > 0 else ""
            self.live_temp_badge.setText(f"\U0001F525 Nozzle: {n_cur:.1f}\u00B0C{tgt_str} (HOT)")
            self.live_temp_badge.setStyleSheet(
                "color: #FFFFFF; background: #EF4444; border: 1px solid #F87171; "
                "border-radius: 6px; font-size: 11px; font-weight: 900; padding: 3px 10px;"
            )
        elif n_tgt > 0:
            self.live_temp_badge.setText(f"\U0001F525 Heating Nozzle: {n_cur:.1f}\u00B0C \u2192 {n_tgt:.0f}\u00B0C")
            self.live_temp_badge.setStyleSheet(
                "color: #FBBF24; background: rgba(245, 158, 11, 0.18); border: 1px solid #F59E0B; "
                "border-radius: 6px; font-size: 11px; font-weight: 800; padding: 3px 10px;"
            )
        else:
            self.live_temp_badge.setText(f"\u25CF Nozzle: {n_cur:.1f}\u00B0C (Idle)")
            self.live_temp_badge.setStyleSheet(
                "color: #38BDF8; background: rgba(56, 189, 248, 0.14); border: 1px solid rgba(56, 189, 248, 0.45); "
                "border-radius: 6px; font-size: 11px; font-weight: 800; padding: 3px 10px;"
            )

    def _set_extrude_dist(self, dist: float):
        self._extrude_dist = dist
        s = self._scale
        for d, btn in self.dist_btns.items():
            active = abs(d - dist) < 0.01
            if active:
                btn.setStyleSheet(
                    f"background: #00E5FF; color: #0F172A; border: 1px solid #00E5FF; "
                    f"border-radius: {_s(6, s)}px; font-size: {_s(11, s)}px; font-weight: 900; padding: 0 {_s(6, s)}px;"
                )
            else:
                btn.setStyleSheet(
                    f"background: #1E293B; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.16); "
                    f"border-radius: {_s(6, s)}px; font-size: {_s(11, s)}px; font-weight: 700; padding: 0 {_s(6, s)}px;"
                )
        if hasattr(self, "btn_extrude"):
            self.btn_extrude.setText(f"\u2B07  Extrude +{int(dist)}mm")
        if hasattr(self, "btn_retract"):
            self.btn_retract.setText(f"\u2B06  Retract -{int(dist)}mm")

    def _get_moonraker(self):
        mr = getattr(self, "moonraker", None)
        if mr:
            return mr
        win = self.window()
        return getattr(win, "moonraker", None)

    def _on_heat_spool_nozzle(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        noz_temp = float(data.get("nozzle_temp", 210))
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.set_temperature("extruder", noz_temp)
            self.status_lbl.setText(f"\U0001F525 Heating nozzle to {noz_temp:.0f}\u00B0C ({data.get('type', 'PLA')})...")
        else:
            self.status_lbl.setText(f"Target set: {noz_temp:.0f}\u00B0C")

    def _on_manual_extrude(self, length_mm: float):
        mr = self._get_moonraker()
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        target_noz = float(data.get("nozzle_temp", 210))
        cur_noz = self._live_nozzle_cur or (float(getattr(mr, "nozzle_temp", 0.0)) if mr else 0.0)
        action_lbl = "Extruding" if length_mm > 0 else "Retracting"
        spd = 5.0 if length_mm > 0 else 10.0

        if mr and mr.connected:
            if cur_noz < 170.0 and self._live_nozzle_tgt < 170.0:
                mr.set_temperature("extruder", target_noz)
                self.status_lbl.setText(
                    f"\U0001F525 Heating nozzle to {target_noz:.0f}\u00B0C & {action_lbl.lower()} {length_mm:+.0f}mm..."
                )
            else:
                self.status_lbl.setText(f"\u2699 {action_lbl} {abs(length_mm):.0f}mm at {cur_noz:.1f}\u00B0C...")

            def _done(ok: bool):
                if ok:
                    self.status_lbl.setText(
                        f"\u2713 Manual {'extrude' if length_mm > 0 else 'retract'} ({length_mm:+.0f}mm) complete"
                    )
                else:
                    self.status_lbl.setText("\u26A0 Extrude rejected by Klipper (wait for nozzle to heat up)")

            mr.extrude(length_mm, speed_mm_s=spd, on_done=_done)
        else:
            self.status_lbl.setText(f"Simulated {action_lbl}: {length_mm:+.0f}mm")

    def _on_load_filament(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        main_win = self.window()
        view = FilamentActionDialog(mode="load", spool_data=data, scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=f"Load Filament \u2014 Spool {self._active_slot}", return_page="spool")
        else:
            view.show()

    def _on_unload_filament(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        main_win = self.window()
        view = FilamentActionDialog(mode="unload", spool_data=data, scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=f"Unload Filament \u2014 Spool {self._active_slot}", return_page="spool")
        else:
            view.show()

    def _load_saved_spools(self):
        try:
            if os.path.exists(CONFIG_STORE_PATH):
                with open(CONFIG_STORE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._spools.update(data)
        except Exception:
            pass

    def _save_spools(self):
        try:
            with open(CONFIG_STORE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._spools, f, indent=2)
        except Exception:
            pass

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.vbox.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self.vbox.setSpacing(_s(8, s))

        for h in self.headers:
            h.setStyleSheet(
                f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8;"
            )

        for btn in self.slot_buttons:
            s_data = self._spools.get(f"spool_{btn.slot_id}", DEFAULT_SPOOLS["spool_1"])
            btn.update_data(s_data, is_active=(btn.slot_id == self._active_slot), scale=s)

        g_sz = _s(144, s)
        self.spool_graphic.setFixedSize(g_sz, g_sz)

        self.load_btn.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669); "
            f"border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; font-size: {_s(13, s)}px; "
            f"border-radius: {_s(9, s)}px; padding: {_s(8, s)}px {_s(12, s)}px;"
        )
        self.unload_btn.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #475569, stop:1 #334155); "
            f"border: 1px solid #64748B; color: #FFFFFF; font-weight: 800; font-size: {_s(13, s)}px; "
            f"border-radius: {_s(9, s)}px; padding: {_s(8, s)}px {_s(12, s)}px;"
        )
        self.preheat_btn.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F97316, stop:1 #EA580C); "
            f"border: 1px solid #FB923C; color: #FFFFFF; font-weight: 800; font-size: {_s(12, s)}px; "
            f"border-radius: {_s(9, s)}px; padding: {_s(6, s)}px {_s(12, s)}px;"
        )
        self.btn_extrude.setStyleSheet(
            f"background: rgba(16, 185, 129, 0.22); border: 1.5px solid #10B981; color: #34D399; "
            f"font-weight: 900; font-size: {_s(12, s)}px; border-radius: {_s(8, s)}px; padding: 0 {_s(10, s)}px;"
        )
        self.btn_retract.setStyleSheet(
            f"background: rgba(56, 189, 248, 0.20); border: 1.5px solid #38BDF8; color: #7DD3FC; "
            f"font-weight: 900; font-size: {_s(12, s)}px; border-radius: {_s(8, s)}px; padding: 0 {_s(10, s)}px;"
        )
        self._set_extrude_dist(self._extrude_dist)
