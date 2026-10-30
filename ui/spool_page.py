"""Spool Page: Filament management, AMS/MMU detection, spool selection, type, color, and automatic preset temperatures."""

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
    },
    "spool_2": {
        "id": 2,
        "name": "Spool 2",
        "type": "PETG",
        "color": "#10B981",
        "nozzle_temp": 240,
        "bed_temp": 75,
    },
    "spool_3": {
        "id": 3,
        "name": "Spool 3",
        "type": "ABS",
        "color": "#EF4444",
        "nozzle_temp": 250,
        "bed_temp": 100,
    },
    "spool_4": {
        "id": 4,
        "name": "Spool 4",
        "type": "TPU",
        "color": "#F59E0B",
        "nozzle_temp": 220,
        "bed_temp": 50,
    },
}


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
        color = spool_data.get("color", "#3B82F6")
        f_type = spool_data.get("type", "PLA")
        name = spool_data.get("name", f"Spool {self.slot_id}")

        self.setText(f"  ● {name} ({f_type})")
        
        # Style based on active state
        b_color = "#00E5FF" if is_active else "rgba(255, 255, 255, 0.12)"
        bg = "rgba(0, 229, 255, 0.15)" if is_active else "rgba(30, 41, 59, 0.7)"
        text_col = "#00E5FF" if is_active else "#E2E8F0"
        fw = "800" if is_active else "600"
        
        radius = _s(10, scale)
        pad_v = _s(7, scale)
        pad_h = _s(12, scale)
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
    """Spool Screen Interface supporting standalone Spool 1 or multi-spool AMS/MMU."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "spool"
        self._scale = 1.0
        self._active_slot = 1
        self._has_ams = False
        self._ams_count = 4
        self._spools = dict(DEFAULT_SPOOLS)
        self._load_saved_spools()

        self.setObjectName("SpoolPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Touch-friendly Scroll Area
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("CalScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("CalContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.vbox = QtWidgets.QVBoxLayout(self.container)

        self.headers = []

        # --- Section 1: AMS / Multi-Spool Selector Bar ---
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
        self.sel_layout.setContentsMargins(10, 8, 10, 8)
        self.sel_layout.setSpacing(8)

        self.slot_buttons = []
        for i in range(1, 5):
            btn = SpoolSelectorButton(i, on_select=self._on_slot_selected, parent=self)
            self.sel_layout.addWidget(btn)
            self.slot_buttons.append(btn)

        self.vbox.addWidget(self.selector_box)
        self.vbox.addSpacing(6)

        # --- Section 2: Active Spool Detail & Configuration ---
        self.config_header = QtWidgets.QLabel("ACTIVE SPOOL CONFIGURATION")
        self.config_header.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(self.config_header)
        self.headers.append(self.config_header)

        # Grid container for Spool Visual Preview + Filament Config Form
        self.detail_frame = QtWidgets.QFrame()
        self.detail_frame.setObjectName("CalibrateCard")
        self.detail_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.grid = QtWidgets.QGridLayout(self.detail_frame)
        self.grid.setContentsMargins(14, 12, 14, 12)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(10)

        # Left Column: Spool Preview Card
        self.preview_card = QtWidgets.QFrame()
        self.preview_card.setStyleSheet("background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px;")
        prev_lay = QtWidgets.QVBoxLayout(self.preview_card)
        prev_lay.setContentsMargins(12, 10, 12, 10)
        prev_lay.setSpacing(6)

        self.spool_icon_lbl = QtWidgets.QLabel()
        self.spool_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spool_icon_lbl.setPixmap(icons.pixmap("spool", 64))
        prev_lay.addWidget(self.spool_icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.spool_title_lbl = QtWidgets.QLabel("Spool 1")
        self.spool_title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; text-align: center;")
        self.spool_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev_lay.addWidget(self.spool_title_lbl)

        # Color Swatch pill
        self.color_swatch = QtWidgets.QLabel("● Blue")
        self.color_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_swatch.setStyleSheet("background: #3B82F6; color: #FFFFFF; font-size: 12px; font-weight: 800; border-radius: 8px; padding: 4px 10px;")
        prev_lay.addWidget(self.color_swatch)

        # Type & Temps Summary badge
        self.summary_badge = QtWidgets.QLabel("PLA  •  210°C / 60°C")
        self.summary_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_badge.setStyleSheet("color: #00E5FF; font-size: 12px; font-weight: 700; background: rgba(0, 229, 255, 0.1); border: 1px solid rgba(0, 229, 255, 0.3); border-radius: 6px; padding: 4px;")
        prev_lay.addWidget(self.summary_badge)
        prev_lay.addStretch(1)

        self.grid.addWidget(self.preview_card, 0, 0, 4, 1)

        # Right Column: Controls
        # Row 0: Filament Type Preset Selector
        type_lbl = QtWidgets.QLabel("Filament Type:")
        type_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 700;")
        self.grid.addWidget(type_lbl, 0, 1)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.type_combo.addItems(list(FILAMENT_PRESETS.keys()))
        self.type_combo.setStyleSheet("""
            QComboBox {
                background: #1E293B;
                border: 1px solid #475569;
                border-radius: 8px;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 13px;
                padding: 6px 12px;
                min-height: 24px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #0F172A;
                border: 1px solid #00E5FF;
                color: #FFFFFF;
                selection-background-color: #00E5FF;
                selection-color: #000000;
            }
        """)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.grid.addWidget(self.type_combo, 0, 2)

        # Row 1: Color Palette Grid
        col_lbl = QtWidgets.QLabel("Filament Color:")
        col_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 700;")
        self.grid.addWidget(col_lbl, 1, 1)

        color_container = QtWidgets.QWidget()
        self.color_grid = QtWidgets.QGridLayout(color_container)
        self.color_grid.setContentsMargins(0, 0, 0, 0)
        self.color_grid.setSpacing(4)
        self.color_btns = []

        for idx, (hex_code, col_name) in enumerate(PALETTE_COLORS):
            c_btn = QtWidgets.QPushButton()
            c_btn.setFixedSize(24, 24)
            c_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            c_btn.setToolTip(col_name)
            c_btn.setProperty("hex", hex_code)
            c_btn.setProperty("name", col_name)
            c_btn.setStyleSheet(f"background-color: {hex_code}; border: 1.5px solid rgba(255,255,255,0.3); border-radius: 12px;")
            c_btn.clicked.connect(lambda _checked=False, h=hex_code, n=col_name: self._on_color_picked(h, n))
            self.color_grid.addWidget(c_btn, idx // 8, idx % 8)
            self.color_btns.append(c_btn)

        self.grid.addWidget(color_container, 1, 2)

        # Row 2: Standard Extruder Nozzle Temperature (with auto-fill & step adjustment)
        nozzle_lbl = QtWidgets.QLabel("Nozzle Temp (°C):")
        nozzle_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 700;")
        self.grid.addWidget(nozzle_lbl, 2, 1)

        noz_box = QtWidgets.QHBoxLayout()
        noz_box.setSpacing(6)

        self.noz_down_btn = QtWidgets.QPushButton("-5")
        self.noz_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.noz_down_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px; padding: 4px 10px;")
        self.noz_down_btn.clicked.connect(lambda: self._adj_temp("nozzle", -5))
        noz_box.addWidget(self.noz_down_btn)

        self.noz_val_lbl = QtWidgets.QLabel("210 °C")
        self.noz_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.noz_val_lbl.setStyleSheet("color: #FF5A5F; font-size: 14px; font-weight: 800; min-width: 60px;")
        noz_box.addWidget(self.noz_val_lbl)

        self.noz_up_btn = QtWidgets.QPushButton("+5")
        self.noz_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.noz_up_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px; padding: 4px 10px;")
        self.noz_up_btn.clicked.connect(lambda: self._adj_temp("nozzle", +5))
        noz_box.addWidget(self.noz_up_btn)

        noz_box.addStretch(1)
        self.grid.addLayout(noz_box, 2, 2)

        # Row 3: Standard Heated Bed Temperature (with auto-fill & step adjustment)
        bed_lbl = QtWidgets.QLabel("Bed Temp (°C):")
        bed_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 700;")
        self.grid.addWidget(bed_lbl, 3, 1)

        bed_box = QtWidgets.QHBoxLayout()
        bed_box.setSpacing(6)

        self.bed_down_btn = QtWidgets.QPushButton("-5")
        self.bed_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bed_down_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px; padding: 4px 10px;")
        self.bed_down_btn.clicked.connect(lambda: self._adj_temp("bed", -5))
        bed_box.addWidget(self.bed_down_btn)

        self.bed_val_lbl = QtWidgets.QLabel("60 °C")
        self.bed_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bed_val_lbl.setStyleSheet("color: #00E5FF; font-size: 14px; font-weight: 800; min-width: 60px;")
        bed_box.addWidget(self.bed_val_lbl)

        self.bed_up_btn = QtWidgets.QPushButton("+5")
        self.bed_up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bed_up_btn.setStyleSheet("background: #334155; color: #FFFFFF; font-weight: 800; border-radius: 6px; padding: 4px 10px;")
        self.bed_up_btn.clicked.connect(lambda: self._adj_temp("bed", +5))
        bed_box.addWidget(self.bed_up_btn)

        bed_box.addStretch(1)
        self.grid.addLayout(bed_box, 3, 2)

        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 0)
        self.grid.setColumnStretch(2, 1)

        self.vbox.addWidget(self.detail_frame)
        self.vbox.addSpacing(8)

        # --- Section 3: Quick Action Load & Unload Buttons ---
        self.actions_header = QtWidgets.QLabel("FILAMENT OPERATIONS")
        self.actions_header.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(self.actions_header)
        self.headers.append(self.actions_header)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)

        # 1. Load Filament (LOAD_FILAMENT)
        self.load_btn = QtWidgets.QPushButton("📥  Load Filament")
        self.load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);
                border: 1px solid #34D399;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 10px;
                padding: 12px 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34D399, stop:1 #10B981);
            }
        """)
        self.load_btn.clicked.connect(self._on_load_filament)
        btn_row.addWidget(self.load_btn, 1)

        # 2. Unload Filament (UNLOAD_FILAMENT)
        self.unload_btn = QtWidgets.QPushButton("📤  Unload Filament")
        self.unload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unload_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #475569, stop:1 #334155);
                border: 1px solid #64748B;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 10px;
                padding: 12px 18px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #64748B, stop:1 #475569);
            }
        """)
        self.unload_btn.clicked.connect(self._on_unload_filament)
        btn_row.addWidget(self.unload_btn, 1)

        self.vbox.addLayout(btn_row)

        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 700; margin-top: 4px;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vbox.addWidget(self.status_lbl)

        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        # Initialize UI with Spool 1
        self._refresh_spool_display()

    def update_config(self, config: dict, objects: list = None):
        """Detect AMS/MMU multi-material hardware (MMU, ERCF, TradRack, Box, AMS) or default to standalone Spool 1."""
        cfg = config or {}
        objs = objects or []
        
        cfg_keys = [str(k).lower().strip() for k in cfg.keys()]
        obj_names = [str(o).lower().strip() for o in objs]

        # Multi-material / AMS signature sections and object names
        # Check explicit section keys (not arbitrary parameter substrings like 'params')
        has_ams = False

        # 1. Check for MMU / ERCF / Happy Hare / TradRack sections
        ams_section_prefixes = [
            "mmu", "ercf", "tradrack", "happy_hare", "ams", "bambu_ams",
            "anycubic_ace", "filament_box", "filament_switch_sensor"
        ]
        
        for k in cfg_keys:
            # Check if any config section starts with or equals an AMS/MMU system
            words = k.replace("_", " ").split()
            if any(p in words or k.startswith(p) for p in ["mmu", "ercf", "tradrack", "happy_hare", "bambu_ams", "anycubic_ace"]):
                has_ams = True
                break
            # Multiple extruders (e.g. extruder1, extruder2)
            if k.startswith("extruder") and k != "extruder":
                has_ams = True
                break

        # 2. Check registered Klipper objects
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
            self.ams_header.setText("AMS / MMU DETECTED — SELECT ACTIVE SPOOL")
            self.ams_header.setVisible(True)
            self.selector_box.setVisible(True)
            for btn in self.slot_buttons:
                btn.setVisible(True)
        else:
            self.ams_header.setText("FILAMENT SPOOL")
            # In single spool setup without AMS, hide the multi-spool selector row and default to Spool 1
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

        # Update slot buttons
        for btn in self.slot_buttons:
            s_data = self._spools.get(f"spool_{btn.slot_id}", DEFAULT_SPOOLS["spool_1"])
            btn.update_data(s_data, is_active=(btn.slot_id == self._active_slot), scale=self._scale)

        # Update detail fields
        name = data.get("name", f"Spool {self._active_slot}")
        f_type = data.get("type", "PLA")
        color = data.get("color", "#3B82F6")
        noz_temp = int(data.get("nozzle_temp", 210))
        bed_temp = int(data.get("bed_temp", 60))

        self.spool_title_lbl.setText(name)
        
        # Find color name
        col_name = "Custom"
        for hex_code, c_name in PALETTE_COLORS:
            if hex_code.lower() == color.lower():
                col_name = c_name
                break
        
        self.color_swatch.setText(f"● {col_name}")
        self.color_swatch.setStyleSheet(f"background: {color}; color: {'#000000' if color in ('#FFFFFF', '#FDE047', '#EAB308') else '#FFFFFF'}; font-size: 12px; font-weight: 800; border-radius: 8px; padding: 4px 10px;")
        
        self.summary_badge.setText(f"{f_type}  •  {noz_temp}°C / {bed_temp}°C")
        self.noz_val_lbl.setText(f"{noz_temp} °C")
        self.bed_val_lbl.setText(f"{bed_temp} °C")

        # Update combo box without triggering signal loop
        self.type_combo.blockSignals(True)
        idx = self.type_combo.findText(f_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.type_combo.blockSignals(False)

    def _on_type_changed(self, f_type: str):
        """Auto-fill standard nozzle and bed temperatures for the selected filament type."""
        preset = FILAMENT_PRESETS.get(f_type, {"nozzle": 210, "bed": 60})
        spool_key = f"spool_{self._active_slot}"
        
        self._spools[spool_key]["type"] = f_type
        self._spools[spool_key]["nozzle_temp"] = preset["nozzle"]
        self._spools[spool_key]["bed_temp"] = preset["bed"]
        
        self._save_spools()
        self._refresh_spool_display()
        self.status_lbl.setText(f"Auto-filled {f_type} standard temps: {preset['nozzle']}°C Nozzle / {preset['bed']}°C Bed")

    def _on_color_picked(self, hex_code: str, col_name: str):
        spool_key = f"spool_{self._active_slot}"
        self._spools[spool_key]["color"] = hex_code
        self._save_spools()
        self._refresh_spool_display()
        self.status_lbl.setText(f"Spool {self._active_slot} color set to {col_name}")

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

    def _on_load_filament(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        main_win = self.window()
        view = FilamentActionDialog(mode="load", spool_data=data, scale=self._scale, parent=self)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=f"Load Filament — Spool {self._active_slot}", return_page="spool")
        else:
            view.show()

    def _on_unload_filament(self):
        spool_key = f"spool_{self._active_slot}"
        data = self._spools.get(spool_key, DEFAULT_SPOOLS["spool_1"])
        main_win = self.window()
        view = FilamentActionDialog(mode="unload", spool_data=data, scale=self._scale, parent=self)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=f"Unload Filament — Spool {self._active_slot}", return_page="spool")
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
        m = _s(14, s)
        self.vbox.setContentsMargins(m, m, m, m)
        self.vbox.setSpacing(_s(8, s))

        for h in self.headers:
            h.setStyleSheet(f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8; margin-top: {_s(6, s)}px; margin-bottom: {_s(2, s)}px;")

        for btn in self.slot_buttons:
            s_data = self._spools.get(f"spool_{btn.slot_id}", DEFAULT_SPOOLS["spool_1"])
            btn.update_data(s_data, is_active=(btn.slot_id == self._active_slot), scale=s)

        self.spool_icon_lbl.setPixmap(icons.pixmap("spool", _s(56, s)))
        self.load_btn.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669); border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; font-size: {_s(12, s)}px; border-radius: {_s(10, s)}px; padding: {_s(10, s)}px {_s(16, s)}px;")
        self.unload_btn.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #475569, stop:1 #334155); border: 1px solid #64748B; color: #FFFFFF; font-weight: 800; font-size: {_s(12, s)}px; border-radius: {_s(10, s)}px; padding: {_s(10, s)}px {_s(16, s)}px;")

