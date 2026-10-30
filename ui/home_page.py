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

    def set_temps(self, current: float, target: float):
        self.current_val = float(current)
        self.target_val = float(target)
        self.value.setText(f"{current:.1f}\u00B0C")
        self.target.setText(f"Target {target:.0f}\u00B0C" if target > 0 else "Target off")

        if target <= 0:
            state, text = ("cooling", "COOLING") if current >= 45.0 else ("off", "IDLE")
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

        max_scale = 260.0 if self.kind == "nozzle" else 110.0
        ratio = min(current / target, 1.0) if target > 0 else min(max(current, 0.0) / max_scale, 1.0)
        self.bar.setValue(int(ratio * 1000))

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


class HomePage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "home"
        self._scale = 1.0
        self.selected_step = 10.0
        self._coords = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self._homed = ""
        self._homing_busy = False
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
        if mr and mr.connected:
            mr.jog(axis, dist)
        else:
            self._coords[axis] += dist
            self.axis_cards[axis].set_position(self._coords[axis], True)

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
