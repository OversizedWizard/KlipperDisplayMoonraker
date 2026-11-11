"""Home page: live temperature cards (compact -20%), X/Y/Z axis coordinate cards, XY and Z move controls,
single column step distance selection (0.1 - 100mm) placed between XY and Z, and emergency/turn off motors control.
"""

from . import icons
from .qt import QtWidgets, QtCore, Qt, Signal
from .preheat_dialog import PreheatDialog

STEP_VALUES = [0.1, 1.0, 5.0, 10.0, 50.0, 100.0]


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class TempCard(QtWidgets.QFrame):
    clicked = Signal()

    def __init__(self, kind: str, title: str, current: float, target: float, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.current_val = float(current)
        self.target_val = float(target)
        self.setObjectName("TempCard")
        self.setProperty("kind", kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Tap to set {title} temperature / preheat / cooldown")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.icon = QtWidgets.QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title = QtWidgets.QLabel(title.upper())
        self.title.setObjectName("TempTitle")

        self.state = QtWidgets.QLabel()
        self.state.setObjectName("TempState")

        self.value = QtWidgets.QLabel()
        self.value.setObjectName("TempValue")

        self.target = QtWidgets.QLabel()
        self.target.setObjectName("TempTarget")

        self.bar = QtWidgets.QProgressBar()
        self.bar.setObjectName("TempBar")
        self.bar.setProperty("kind", kind)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)

        self._grid = QtWidgets.QGridLayout(self)
        self._grid.addWidget(self.icon, 0, 0, 2, 1)
        self._grid.addWidget(self.title, 0, 1, Qt.AlignmentFlag.AlignBottom)
        self._grid.addWidget(self.state, 0, 2,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._grid.addWidget(self.value, 1, 1, Qt.AlignmentFlag.AlignTop)
        self._grid.addWidget(self.target, 1, 2,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._grid.addWidget(self.bar, 2, 0, 1, 3)
        self._grid.setColumnStretch(1, 1)

        self.set_temps(current, target)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self._pressed = False
        for child in (self.icon, self.title, self.state, self.value, self.target, self.bar):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if getattr(self, "_pressed", False) and self.rect().contains(event.pos()):
                self._pressed = False
                self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def event(self, e):
        if e.type() == QtCore.QEvent.Type.TouchEnd:
            self.clicked.emit()
            return True
        return super().event(e)

    @staticmethod
    def _lerp_hex(c1: tuple, c2: tuple, t: float) -> str:
        t = max(0.0, min(1.0, t))
        r = round(c1[0] + (c2[0] - c1[0]) * t)
        g = round(c1[1] + (c2[1] - c1[1]) * t)
        b = round(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02X}{g:02X}{b:02X}"

    def _update_bar_thermal_color(self, current: float, target: float):
        """Color bar blue when cold, orange when warm, and red when hot / at target temp."""
        if self.kind == "bed":
            # Bed: <= 28°C cold (blue), ~42°C warm to touch (orange), >= 55°C hot to touch (red)
            abs_t = (current - 26.0) / (55.0 - 26.0)
            if target > 30.0:
                tgt_t = (current - 25.0) / max(target - 25.0, 15.0)
                t = max(abs_t, tgt_t)
            else:
                t = abs_t
        else:
            # Nozzle: <= 32°C cold (blue), ~95°C warm (orange), >= 165°C or at target (red)
            abs_t = (current - 30.0) / (165.0 - 30.0)
            if target > 45.0:
                tgt_t = (current - 28.0) / max(target - 28.0, 25.0)
                t = max(abs_t, tgt_t)
            else:
                t = abs_t

        t = max(0.0, min(1.0, t))

        # Cold Blue -> Warm Orange -> Hot Red
        cold_start, cold_end = (0, 210, 255), (37, 99, 235)     # #00D2FF -> #2563EB (Blue)
        warm_start, warm_end = (245, 158, 11), (255, 102, 0)    # #F59E0B -> #FF6600 (Orange)
        hot_start, hot_end = (255, 77, 0), (239, 30, 30)        # #FF4D00 -> #EF1E1E (Red)

        if t <= 0.5:
            u = t / 0.5
            c0 = self._lerp_hex(cold_start, warm_start, u)
            c1 = self._lerp_hex(cold_end, warm_end, u)
        else:
            u = (t - 0.5) / 0.5
            c0 = self._lerp_hex(warm_start, hot_start, u)
            c1 = self._lerp_hex(warm_end, hot_end, u)

        self.bar.setStyleSheet(f"""
            QProgressBar#TempBar {{
                background: rgba(255, 255, 255, 18);
                border: none;
                border-radius: 4px;
            }}
            QProgressBar#TempBar::chunk {{
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c0}, stop:1 {c1});
            }}
        """)

    def set_temps(self, current: float, target: float):
        self.current_val = float(current)
        self.target_val = float(target)
        self.value.setText(f"{current:.1f}\u00B0C")
        self.target.setText(f"Target {target:.0f}\u00B0C" if target > 0 else "Target off")

        if target <= 0:
            hot_thresh = 38.0 if self.kind == "bed" else 45.0
            state, text = ("cooling", "COOLING") if current >= hot_thresh else ("off", "IDLE")
        elif abs(current - target) <= 1.5:
            state, text = "ready", "READY"
        elif current < target:
            state, text = "heating", "HEATING"
        else:
            state, text = "cooling", "COOLING"
        self.state.setText(text)
        self.state.setProperty("state", state)
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)

        max_scale = 260.0 if self.kind == "nozzle" else 100.0
        if target > 0:
            ratio = min(max(current / target, 0.18), 1.0)
        else:
            # Keep a clearly visible cold blue bar (minimum 22%) when idle/cold, scaling up with heat
            ratio = min(max(current / max_scale, 0.22), 1.0)
        self.bar.setValue(int(ratio * 1000))
        self._update_bar_thermal_color(current, target)

    def apply_scale(self, s: float):
        # Sized +20% again
        m = _s(13, s)
        self._grid.setContentsMargins(m, _s(9, s), m, _s(9, s))
        self._grid.setHorizontalSpacing(_s(12, s))
        self._grid.setVerticalSpacing(_s(4, s))
        self.icon.setPixmap(icons.pixmap(self.kind, _s(52, s)))
        self.icon.setFixedSize(_s(54, s), _s(60, s))
        self.bar.setFixedHeight(_s(7, s))
        self.setFixedHeight(_s(98, s))


class AxisCoordCard(QtWidgets.QFrame):
    """Displays current coordinate for a specific axis (X, Y, or Z)."""

    def __init__(self, axis: str, parent=None):
        super().__init__(parent)
        self.axis = axis.upper()
        self.setObjectName("AxisCard")
        self.setProperty("axis", self.axis)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(1)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)
        self.title_lbl = QtWidgets.QLabel(self.axis)
        self.title_lbl.setObjectName("AxisTitle")
        top_row.addWidget(self.title_lbl)
        top_row.addStretch(1)

        self.homed_badge = QtWidgets.QLabel("UNHOMED")
        self.homed_badge.setObjectName("AxisHomedBadge")
        self.homed_badge.setProperty("homed", "false")
        top_row.addWidget(self.homed_badge)
        self._layout.addLayout(top_row)

        self.coord_lbl = QtWidgets.QLabel("0.00 mm")
        self.coord_lbl.setObjectName("AxisCoord")
        self._layout.addWidget(self.coord_lbl)

    def set_position(self, pos: float, is_homed: bool):
        if self.axis == "Z" and abs(pos * 100 - round(pos * 100)) > 1e-4:
            self.coord_lbl.setText(f"{pos:.3f} mm")
        else:
            self.coord_lbl.setText(f"{pos:.2f} mm")
        h_str = "true" if is_homed else "false"
        if self.homed_badge.property("homed") != h_str:
            self.homed_badge.setProperty("homed", h_str)
            self.homed_badge.setText("HOMED" if is_homed else "UNHOMED")
            self.homed_badge.style().unpolish(self.homed_badge)
            self.homed_badge.style().polish(self.homed_badge)

    def apply_scale(self, s: float):
        m = _s(6, s)
        self._layout.setContentsMargins(m, _s(5, s), m, _s(5, s))




class LevellingModeOverlay(QtWidgets.QFrame):
    """Touch modal to select Bed Levelling mode: Normal (Saved Mesh), KAMP (Adaptive), or Off."""
    mode_selected = Signal(str)
    closed = Signal()

    def __init__(self, current_mode: str = "off", scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.current_mode = (current_mode or "off").lower()
        self.setObjectName("LevellingModeOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#LevellingModeOverlay { background: rgba(5, 10, 20, 0.88); }")
        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QtWidgets.QFrame(self)
        card.setObjectName("LevellingModeCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            QFrame#LevellingModeCard {{
                background: #0F172A;
                border: 2px solid #00E5FF;
                border-radius: {_s(14, scale)}px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(_s(18, scale), _s(14, scale), _s(18, scale), _s(14, scale))
        lay.setSpacing(_s(10, scale))

        hdr = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("CHOOSE BED LEVELLING MODE")
        title.setStyleSheet(f"color: #00E5FF; font-size: {_s(16, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        hdr.addWidget(title)
        hdr.addStretch(1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(_s(34, scale), _s(34, scale))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: {_s(17, scale)}px;
                font-size: {_s(14, scale)}px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background: rgba(239, 68, 68, 0.4); color: #FFFFFF; }}
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        sub = QtWidgets.QLabel("Updates PRINT_START & KAMP_Settings.cfg in printer.cfg and restarts Klipper")
        sub.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 600;")
        lay.addWidget(sub)

        modes = [
            (
                "normal",
                "⊞  Normal (Saved Bed Mesh)",
                "Loads your saved default mesh profile (BED_MESH_PROFILE LOAD=default)",
                "#10B981",
                "rgba(16, 185, 129, 0.16)",
            ),
            (
                "kamp",
                "⚡  KAMP (Adaptive Mesh)",
                "Probes only the model print area before each print (BED_MESH_CALIBRATE)",
                "#00E5FF",
                "rgba(0, 229, 255, 0.16)",
            ),
            (
                "off",
                "✕  Levelling Off",
                "Disables bed mesh in PRINT_START (runs with no mesh compensation)",
                "#EF4444",
                "rgba(239, 68, 68, 0.16)",
            ),
        ]

        for m_key, m_title, m_desc, accent, bg_active in modes:
            is_cur = (self.current_mode == m_key)
            btn = QtWidgets.QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_s(68, scale))
            border_w = "2px" if is_cur else "1px"
            border_col = accent if is_cur else "rgba(255, 255, 255, 0.14)"
            bg_col = bg_active if is_cur else "rgba(30, 41, 59, 0.75)"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_col};
                    border: {border_w} solid {border_col};
                    border-radius: {_s(10, scale)}px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    border: 2px solid {accent};
                    background: {bg_active};
                }}
            """)
            b_lay = QtWidgets.QVBoxLayout(btn)
            b_lay.setContentsMargins(_s(14, scale), _s(8, scale), _s(14, scale), _s(8, scale))
            b_lay.setSpacing(2)

            top_r = QtWidgets.QHBoxLayout()
            tl = QtWidgets.QLabel(m_title)
            tl.setStyleSheet(f"color: {accent if is_cur else '#F8FAFC'}; font-size: {_s(14, scale)}px; font-weight: 900;")
            tl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            top_r.addWidget(tl)
            top_r.addStretch(1)
            if is_cur:
                badge = QtWidgets.QLabel("● ACTIVE")
                badge.setStyleSheet(f"color: {accent}; font-size: {_s(11, scale)}px; font-weight: 900;")
                badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                top_r.addWidget(badge)
            b_lay.addLayout(top_r)

            dl = QtWidgets.QLabel(m_desc)
            dl.setStyleSheet(f"color: #CBD5E1; font-size: {_s(11, scale)}px; font-weight: 600;")
            dl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            b_lay.addWidget(dl)

            btn.clicked.connect(lambda _c=False, k=m_key: self._pick(k))
            lay.addWidget(btn)

        card.setFixedWidth(_s(540, scale))
        outer.addWidget(card)

    def _pick(self, mode: str):
        self.mode_selected.emit(mode)
        self.close()

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()


class HomePage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "home"
        self._scale = 1.0
        self.selected_step = 10.0
        self._coords = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self._homed = ""
        self._homing_busy = False
        self._mesh_configured = True
        self._mesh_active = False
        self._homing_timer = QtCore.QTimer(self)
        self._homing_timer.setSingleShot(True)
        self._homing_timer.timeout.connect(lambda: self._set_homing_lock(False))

        # Outer layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("CalScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("CalContainer")
        self.vbox = QtWidgets.QVBoxLayout(self.container)

        # 1. Top Section: Temperature Cards (Nozzle, Bed) - reduced 20%
        self._temps = QtWidgets.QHBoxLayout()
        self.nozzle = TempCard("nozzle", "Nozzle", 0.0, 0.0)
        self.bed = TempCard("bed", "Bed", 0.0, 0.0)
        self.nozzle.clicked.connect(lambda: self._open_preheat("nozzle"))
        self.bed.clicked.connect(lambda: self._open_preheat("bed"))
        self._temps.addWidget(self.nozzle, 1)
        self._temps.addWidget(self.bed, 1)
        self.vbox.addLayout(self._temps)

        # 2. Middle Section: Axis Cards + [XY Move Pad] + [Step Single Column] + [Z Move Pad]
        self.mid_layout = QtWidgets.QHBoxLayout()

        # Left Column: X, Y, Z Coordinate Cards (30% narrower)
        self.axis_col = QtWidgets.QVBoxLayout()
        self.axis_col.setSpacing(4)
        self.axis_cards = {}
        for ax in ("X", "Y", "Z"):
            card = AxisCoordCard(ax)
            self.axis_cards[ax] = card
            self.axis_col.addWidget(card)
        self.mid_layout.addLayout(self.axis_col, 3)

        # Center Column: XY Move Pad with Home in centre (Icon only, no text)
        self.xy_card = QtWidgets.QFrame()
        self.xy_card.setObjectName("JogCard")
        xy_vbox = QtWidgets.QVBoxLayout(self.xy_card)
        xy_vbox.setContentsMargins(6, 6, 6, 6)
        xy_vbox.setSpacing(4)

        self.xy_title = QtWidgets.QLabel("XY GANTRY")
        self.xy_title.setObjectName("AxisTitle")
        self.xy_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.xy_title.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        xy_vbox.addWidget(self.xy_title, 0, Qt.AlignmentFlag.AlignTop)

        self.xy_grid = QtWidgets.QGridLayout()
        self.xy_grid.setContentsMargins(0, 0, 0, 0)
        self.xy_grid.setSpacing(6)

        self.btn_y_plus = QtWidgets.QPushButton("\u25B2")
        self.btn_y_plus.setObjectName("JogBtn")
        self.btn_y_plus.setToolTip("Y+ (Forward)")
        self.btn_y_plus.clicked.connect(lambda: self._on_jog("Y", 1.0))
        self.xy_grid.addWidget(self.btn_y_plus, 0, 1)

        self.btn_x_minus = QtWidgets.QPushButton("\u25C0")
        self.btn_x_minus.setObjectName("JogBtn")
        self.btn_x_minus.setToolTip("X- (Left)")
        self.btn_x_minus.clicked.connect(lambda: self._on_jog("X", -1.0))
        self.xy_grid.addWidget(self.btn_x_minus, 1, 0)

        # Home button: Icon only (no text)
        self.btn_home_xy = QtWidgets.QPushButton()
        self.btn_home_xy.setObjectName("JogHomeBtn")
        self.btn_home_xy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home_xy.setToolTip("Home XY Axes (G28 X Y)")
        self.btn_home_xy.clicked.connect(self._on_home_xy)
        self.xy_grid.addWidget(self.btn_home_xy, 1, 1)

        self.btn_x_plus = QtWidgets.QPushButton("\u25B6")
        self.btn_x_plus.setObjectName("JogBtn")
        self.btn_x_plus.setToolTip("X+ (Right)")
        self.btn_x_plus.clicked.connect(lambda: self._on_jog("X", 1.0))
        self.xy_grid.addWidget(self.btn_x_plus, 1, 2)

        self.btn_y_minus = QtWidgets.QPushButton("\u25BC")
        self.btn_y_minus.setObjectName("JogBtn")
        self.btn_y_minus.setToolTip("Y- (Backward)")
        self.btn_y_minus.clicked.connect(lambda: self._on_jog("Y", -1.0))
        self.xy_grid.addWidget(self.btn_y_minus, 2, 1)

        xy_center_h = QtWidgets.QHBoxLayout()
        xy_center_h.addStretch(1)
        xy_center_h.addLayout(self.xy_grid)
        xy_center_h.addStretch(1)

        xy_vbox.addStretch(1)
        xy_vbox.addLayout(xy_center_h)
        xy_vbox.addStretch(1)

        self.mid_layout.addWidget(self.xy_card, 6)

        # Middle Column: Step Selection in a SINGLE COLUMN between XY and Z
        self.step_card = QtWidgets.QFrame()
        self.step_card.setObjectName("JogCard")
        step_vbox = QtWidgets.QVBoxLayout(self.step_card)
        step_vbox.setContentsMargins(12, 6, 12, 8)
        step_vbox.setSpacing(4)

        self.step_title = QtWidgets.QLabel("STEP")
        self.step_title.setObjectName("AxisTitle")
        self.step_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_title.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        step_vbox.addWidget(self.step_title, 0, Qt.AlignmentFlag.AlignTop)

        self.step_btn_group = QtWidgets.QButtonGroup(self)
        self.step_btn_group.setExclusive(True)
        self.step_buttons = []

        step_col_layout = QtWidgets.QVBoxLayout()
        step_col_layout.setContentsMargins(0, 0, 0, 0)
        step_col_layout.setSpacing(6)
        for val in STEP_VALUES:
            txt = f"{val:g}"
            btn = QtWidgets.QPushButton(txt)
            btn.setObjectName("StepBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if val == self.selected_step:
                btn.setChecked(True)
            btn.clicked.connect(lambda _c=False, v=val: self._on_step_selected(v))
            self.step_btn_group.addButton(btn)
            step_col_layout.addWidget(btn)
            self.step_buttons.append(btn)

        step_vbox.addStretch(1)
        step_vbox.addLayout(step_col_layout)
        step_vbox.addStretch(1)
        self.mid_layout.addWidget(self.step_card, 2)

        # Right Column: Z Move Pad with Home in centre (Icon only, no text)
        self.z_card = QtWidgets.QFrame()
        self.z_card.setObjectName("JogCard")
        z_vbox = QtWidgets.QVBoxLayout(self.z_card)
        z_vbox.setContentsMargins(6, 6, 6, 6)
        z_vbox.setSpacing(4)

        self.z_title = QtWidgets.QLabel("Z AXIS")
        self.z_title.setObjectName("AxisTitle")
        self.z_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.z_title.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        z_vbox.addWidget(self.z_title, 0, Qt.AlignmentFlag.AlignTop)

        self.z_grid = QtWidgets.QGridLayout()
        self.z_grid.setContentsMargins(0, 0, 0, 0)
        self.z_grid.setSpacing(6)

        self.btn_z_plus = QtWidgets.QPushButton("\u25B2")
        self.btn_z_plus.setObjectName("JogBtn")
        self.btn_z_plus.setToolTip("Z+ (Up)")
        self.btn_z_plus.clicked.connect(lambda: self._on_jog("Z", 1.0))
        self.z_grid.addWidget(self.btn_z_plus, 0, 0)

        # Home Z button: Icon only (no text)
        self.btn_home_z = QtWidgets.QPushButton()
        self.btn_home_z.setObjectName("JogHomeBtn")
        self.btn_home_z.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home_z.setToolTip("Home Z Axis (G28 Z)")
        self.btn_home_z.clicked.connect(self._on_home_z)
        self.z_grid.addWidget(self.btn_home_z, 1, 0)

        self.btn_z_minus = QtWidgets.QPushButton("\u25BC")
        self.btn_z_minus.setObjectName("JogBtn")
        self.btn_z_minus.setToolTip("Z- (Down)")
        self.btn_z_minus.clicked.connect(lambda: self._on_jog("Z", -1.0))
        self.z_grid.addWidget(self.btn_z_minus, 2, 0)

        z_center_h = QtWidgets.QHBoxLayout()
        z_center_h.addStretch(1)
        z_center_h.addLayout(self.z_grid)
        z_center_h.addStretch(1)

        z_vbox.addStretch(1)
        z_vbox.addLayout(z_center_h)
        z_vbox.addStretch(1)

        self.mid_layout.addWidget(self.z_card, 2)

        self.vbox.addLayout(self.mid_layout)

        # 3. Bottom Action Bar: Turn Off Motors Button + Home All Button
        self.bottom_bar = QtWidgets.QHBoxLayout()
        self.bottom_bar.setContentsMargins(0, 0, 0, 0)
        self.bottom_bar.setSpacing(6)

        self.btn_home_all = QtWidgets.QPushButton("  Home All (G28)")
        self.btn_home_all.setObjectName("HomeAllBtn")
        self.btn_home_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home_all.clicked.connect(self._on_home_all)
        self.bottom_bar.addWidget(self.btn_home_all, 1)

        self.btn_bed_mesh = QtWidgets.QPushButton("⊞  Bed Levelling Off")
        self.btn_bed_mesh.setObjectName("BedMeshBtn")
        self.btn_bed_mesh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bed_mesh.clicked.connect(self._on_toggle_bed_mesh)
        self.bottom_bar.addWidget(self.btn_bed_mesh, 1)

        self.btn_motors_off = QtWidgets.QPushButton("\u26A1  Turn Off Motors (M84)")
        self.btn_motors_off.setObjectName("MotorsOffBtn")
        self.btn_motors_off.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_motors_off.clicked.connect(self._on_motors_off)
        self.bottom_bar.addWidget(self.btn_motors_off, 1)

        self.vbox.addLayout(self.bottom_bar)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    def _on_step_selected(self, val: float):
        self.selected_step = val

    def _set_homing_lock(self, locked: bool):
        self._homing_busy = locked
        if locked:
            self._homing_timer.start(35000)
        else:
            self._homing_timer.stop()
        self.btn_home_all.setEnabled(not locked)
        self.btn_home_xy.setEnabled(not locked)
        self.btn_home_z.setEnabled(not locked)
        self.btn_y_plus.setEnabled(not locked)
        self.btn_y_minus.setEnabled(not locked)
        self.btn_x_plus.setEnabled(not locked)
        self.btn_x_minus.setEnabled(not locked)
        self.btn_z_plus.setEnabled(not locked)
        self.btn_z_minus.setEnabled(not locked)

    def _on_jog(self, axis: str, direction: float):
        if self._homing_busy:
            return
        dist = self.selected_step * direction
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        self._coords[axis] += dist
        is_h = (axis.lower() in self._homed) if (mr and mr.connected) else True
        self.axis_cards[axis].set_position(self._coords[axis], is_h)
        if mr and mr.connected:
            mr.jog(axis, dist)

    def _on_home_all(self):
        if self._homing_busy:
            return
        self._set_homing_lock(True)
        self.btn_home_all.setText("Homing All Axes...")
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)

        def _finish(ok):
            self._set_homing_lock(False)
            self.btn_home_all.setText("  Home All (G28)")

        if mr and mr.connected:
            mr.home("", on_done=_finish)
        else:
            self._coords["X"] = 0.0
            self._coords["Y"] = 0.0
            self._coords["Z"] = 0.0
            for ax in ("X", "Y", "Z"):
                self.axis_cards[ax].set_position(0.0, True)
            QtCore.QTimer.singleShot(900, lambda: _finish(True))

    def _on_home_xy(self):
        if self._homing_busy:
            return
        self._set_homing_lock(True)
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if mr and mr.connected:
            mr.home("X Y", on_done=lambda ok: self._set_homing_lock(False))
        else:
            self._coords["X"] = 0.0
            self._coords["Y"] = 0.0
            self.axis_cards["X"].set_position(0.0, True)
            self.axis_cards["Y"].set_position(0.0, True)
            QtCore.QTimer.singleShot(600, lambda: self._set_homing_lock(False))

    def _on_home_z(self):
        if self._homing_busy:
            return
        self._set_homing_lock(True)
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if mr and mr.connected:
            mr.home("Z", on_done=lambda ok: self._set_homing_lock(False))
        else:
            self._coords["Z"] = 0.0
            self.axis_cards["Z"].set_position(0.0, True)
            QtCore.QTimer.singleShot(600, lambda: self._set_homing_lock(False))

    def _on_motors_off(self):
        self.btn_motors_off.setText("Motors Disabled (M84 Sent)")
        self._set_homing_lock(False)
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if mr and mr.connected:
            mr.motors_off()
        QtCore.QTimer.singleShot(1400, lambda: self.btn_motors_off.setText("\u26A1  Turn Off Motors (M84)"))

    def showEvent(self, event):
        super().showEvent(event)
        import time as _time
        last = getattr(self, "_mesh_checked_at", 0.0)
        if (_time.monotonic() - last) > 15.0 or not hasattr(self, "_mesh_mode"):
            self._check_mesh_config()

    def _check_mesh_config(self):
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if mr:
            import time as _time
            self._mesh_checked_at = _time.monotonic()
            mr.check_start_gcode_mesh(on_done=self._on_mesh_checked)
        else:
            QtCore.QTimer.singleShot(1000, self._check_mesh_config)

    def _on_mesh_checked(self, mode, is_configured: bool):
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if not is_configured and mode == "off":
            if not mr or not mr.connected or mr.klippy_state != "ready":
                QtCore.QTimer.singleShot(1500, self._check_mesh_config)
                return

        if isinstance(mode, bool):
            mode = "normal" if mode else "off"
        self._mesh_mode = str(mode or "off").lower()
        self._mesh_active = (self._mesh_mode != "off")
        self._mesh_configured = is_configured
        self._update_mesh_button_ui()

    def update_config(self, config: dict, objects: list):
        """Called when Moonraker loads Klipper configuration. Checks if bed_mesh is enabled or commented out."""
        self._mesh_configured = ("bed_mesh" in config) or ("bed_mesh" in objects)
        self._check_mesh_config()

    def _on_toggle_bed_mesh(self):
        """Open the 3-mode Bed Levelling selector (Normal / KAMP / Off)."""
        main_win = self.window()
        s = getattr(self, "_scale", 1.0)
        cur_mode = getattr(self, "_mesh_mode", "off")
        overlay = LevellingModeOverlay(current_mode=cur_mode, scale=s, parent=main_win)
        overlay.mode_selected.connect(self._apply_bed_mesh_mode)
        overlay.show()
        overlay.raise_()

    def _apply_bed_mesh_mode(self, mode: str):
        """Write chosen bed levelling mode ('normal', 'kamp', 'off') to printer.cfg and restart Klipper."""
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if not mr:
            return

        s = getattr(self, "_scale", 1.0)
        self.btn_bed_mesh.setText("⊞  Saving & Restarting...")
        self.btn_bed_mesh.setStyleSheet(f"""
            QPushButton#BedMeshBtn {{
                background: rgba(245, 158, 11, 0.25);
                color: #F59E0B;
                border: 1.5px solid #F59E0B;
                border-radius: {_s(8, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 800;
                padding: 0 {_s(6, s)}px;
            }}
        """)

        def _done(new_mode: str):
            self._mesh_mode = str(new_mode or mode).lower()
            self._mesh_active = (self._mesh_mode != "off")
            self._update_mesh_button_ui()
            QtCore.QTimer.singleShot(3500, self._check_mesh_config)

        mr.set_start_gcode_mesh_mode(mode, on_done=_done)

    def _update_mesh_button_ui(self):
        s = getattr(self, "_scale", 1.0)
        mode = getattr(self, "_mesh_mode", "normal" if getattr(self, "_mesh_active", False) else "off")
        if not self._mesh_configured:
            self.btn_bed_mesh.setText("⊞  Bed Levelling (N/A)")
            self.btn_bed_mesh.setStyleSheet(f"""
                QPushButton#BedMeshBtn {{
                    background: rgba(239, 68, 68, 0.10);
                    color: #EF4444;
                    border: 1px dashed rgba(239, 68, 68, 0.5);
                    border-radius: {_s(8, s)}px;
                    font-size: {_s(11, s)}px;
                    font-weight: 700;
                    padding: 0 {_s(6, s)}px;
                }}
            """)
        elif mode == "kamp":
            self.btn_bed_mesh.setText("⚡  Levelling: KAMP")
            self.btn_bed_mesh.setStyleSheet(f"""
                QPushButton#BedMeshBtn {{
                    background: rgba(0, 229, 255, 0.20);
                    color: #00E5FF;
                    border: 1.5px solid #00E5FF;
                    border-radius: {_s(8, s)}px;
                    font-size: {_s(12, s)}px;
                    font-weight: 800;
                    padding: 0 {_s(6, s)}px;
                }}
                QPushButton#BedMeshBtn:hover {{
                    background: rgba(0, 229, 255, 0.35);
                    border-color: #38BDF8;
                    color: #FFFFFF;
                }}
            """)
        elif mode == "normal":
            self.btn_bed_mesh.setText("⊞  Levelling: Normal")
            self.btn_bed_mesh.setStyleSheet(f"""
                QPushButton#BedMeshBtn {{
                    background: rgba(16, 185, 129, 0.20);
                    color: #34D399;
                    border: 1.5px solid #10B981;
                    border-radius: {_s(8, s)}px;
                    font-size: {_s(12, s)}px;
                    font-weight: 800;
                    padding: 0 {_s(6, s)}px;
                }}
                QPushButton#BedMeshBtn:hover {{
                    background: rgba(16, 185, 129, 0.35);
                    border-color: #34D399;
                    color: #FFFFFF;
                }}
            """)
        else:
            self.btn_bed_mesh.setText("⊞  Levelling: Off")
            self.btn_bed_mesh.setStyleSheet(f"""
                QPushButton#BedMeshBtn {{
                    background: rgba(239, 68, 68, 0.16);
                    color: #F87171;
                    border: 1.5px solid #EF4444;
                    border-radius: {_s(8, s)}px;
                    font-size: {_s(12, s)}px;
                    font-weight: 800;
                    padding: 0 {_s(6, s)}px;
                }}
                QPushButton#BedMeshBtn:hover {{
                    background: rgba(239, 68, 68, 0.28);
                    border-color: #F87171;
                    color: #FFFFFF;
                }}
            """)

    def update_temps(self, nozzle_cur: float, nozzle_tgt: float, bed_cur: float, bed_tgt: float):
        self.nozzle.set_temps(nozzle_cur, nozzle_tgt)
        self.bed.set_temps(bed_cur, bed_tgt)

    def _open_preheat(self, kind: str):
        card = self.nozzle if kind == "nozzle" else self.bed
        win = self.window()
        view = PreheatDialog(
            kind=kind,
            current_temp=card.current_val,
            target_temp=card.target_val,
            scale=self._scale,
            parent=self
        )

        def _on_target_applied(target: float):
            heater = "extruder" if kind == "nozzle" else "heater_bed"
            mr = getattr(win, "moonraker", None)
            if mr and mr.connected:
                mr.set_temperature(heater, target)
            card.set_temps(card.current_val, target)

        view.temp_selected.connect(_on_target_applied)
        if hasattr(win, "open_sub_screen"):
            title = "Nozzle Temperature" if kind == "nozzle" else "Bed Temperature"
            win.open_sub_screen(view, title=title, return_page="home")
        else:
            view.show()

    def update_coords(self, x: float, y: float, z: float, homed_axes: str):
        self._coords["X"] = x
        self._coords["Y"] = y
        self._coords["Z"] = z
        self._homed = homed_axes.lower()

        self.axis_cards["X"].set_position(x, "x" in self._homed)
        self.axis_cards["Y"].set_position(y, "y" in self._homed)
        self.axis_cards["Z"].set_position(z, "z" in self._homed)

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(8, s)
        self.vbox.setContentsMargins(m, m, m, m)
        self.vbox.setSpacing(_s(6, s))
        self._temps.setSpacing(_s(6, s))
        self.mid_layout.setSpacing(_s(6, s))

        self.nozzle.apply_scale(s)
        self.bed.apply_scale(s)

        for card in self.axis_cards.values():
            card.apply_scale(s)

        # Scale jog buttons to neatly center in cards
        btn_w = _s(74, s)
        btn_h = _s(58, s)
        for b in (self.btn_y_plus, self.btn_x_minus, self.btn_home_xy,
                  self.btn_x_plus, self.btn_y_minus,
                  self.btn_z_plus, self.btn_home_z, self.btn_z_minus):
            b.setFixedSize(btn_w, btn_h)

        # Home icon
        home_ico = icons.icon("home", _s(28, s))
        self.btn_home_xy.setIcon(home_ico)
        self.btn_home_xy.setIconSize(QtCore.QSize(_s(28, s), _s(28, s)))
        self.btn_home_z.setIcon(home_ico)
        self.btn_home_z.setIconSize(QtCore.QSize(_s(28, s), _s(28, s)))

        # Step buttons in single column with neat padding
        step_btn_h = _s(32, s)
        for sb in self.step_buttons:
            sb.setFixedHeight(step_btn_h)
            sb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        action_btn_h = _s(32, s)
        self.btn_home_all.setFixedHeight(action_btn_h)
        self.btn_home_all.setIcon(icons.icon("home", _s(18, s)))
        self.btn_home_all.setIconSize(QtCore.QSize(_s(18, s), _s(18, s)))
        self.btn_motors_off.setFixedHeight(action_btn_h)
        if hasattr(self, "btn_bed_mesh"):
            self.btn_bed_mesh.setFixedHeight(action_btn_h)
            self._update_mesh_button_ui()
