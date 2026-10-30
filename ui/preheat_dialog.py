"""Preheat modal dialog for setting nozzle or bed target temperature and cooldown."""

from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons

PRESETS = {
    "nozzle": [
        ("PLA", 205),
        ("PETG", 240),
        ("ABS", 250),
        ("TPU", 220),
        ("Nylon", 260),
    ],
    "bed": [
        ("PLA", 60),
        ("PETG", 75),
        ("ABS", 100),
        ("TPU", 50),
        ("Nylon", 90),
    ],
}


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class PreheatDialog(QtWidgets.QFrame):
    """Touch-friendly in-window view to set heater temperature or cooldown."""
    temp_selected = Signal(float)
    closed = Signal()

    def __init__(self, kind: str, current_temp: float, target_temp: float, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.kind = kind.lower()
        self.current_temp = float(current_temp)
        # Default starting target: if active target > 0, use it; otherwise preset default
        if target_temp > 0:
            self.target_temp = float(target_temp)
        else:
            self.target_temp = 205.0 if self.kind == "nozzle" else 60.0
        self.scale = scale

        self.setObjectName("PreheatView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        accent_border = "rgba(255, 122, 0, 120)" if self.kind == "nozzle" else "rgba(0, 229, 255, 120)"
        self.card.setStyleSheet(f"QFrame#DialogCard {{ border-color: {accent_border}; }}")
        outer.addWidget(self.card)

        layout = QtWidgets.QVBoxLayout(self.card)
        m = _s(14, scale)
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(_s(10, scale))

        # 1. Header Row: Icon + Title + Current / Active info + Close X
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(12, scale))

        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setPixmap(icons.pixmap(self.kind, _s(40, scale)))
        icon_lbl.setFixedSize(_s(44, scale), _s(44, scale))
        hdr.addWidget(icon_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(2)
        title_text = "Nozzle Temperature" if self.kind == "nozzle" else "Bed Temperature"
        t_lbl = QtWidgets.QLabel(title_text)
        t_lbl.setObjectName("DialogTitle")
        title_col.addWidget(t_lbl)

        cur_str = (
            f"Current: {self.current_temp:.1f}°C  •  Active Target: {target_temp:.0f}°C"
            if target_temp > 0
            else f"Current: {self.current_temp:.1f}°C  •  Heater Idle / Off"
        )
        self.sub_lbl = QtWidgets.QLabel(cur_str)
        self.sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        title_col.addWidget(self.sub_lbl)
        hdr.addLayout(title_col, 1)

        close_x = QtWidgets.QPushButton("✕")
        close_x.setObjectName("DialogCloseX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(self.reject)
        hdr.addWidget(close_x, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(hdr)

        # 2. Main Adjuster Row: [-10] [-1] [  TARGET °C  ] [+1] [+10]
        adj_box = QtWidgets.QFrame()
        adj_box.setObjectName("DialogStepsBox")
        adj_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        adj_lay = QtWidgets.QHBoxLayout(adj_box)
        adj_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        adj_lay.setSpacing(_s(8, scale))

        for delta in (-10, -1):
            b = QtWidgets.QPushButton(f"{delta:+d}")
            b.setObjectName("StepBtn")
            b.setFixedSize(_s(48, scale), _s(44, scale))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, d=delta: self._adjust_target(d))
            adj_lay.addWidget(b)

        # Center Target Display
        self.target_display = QtWidgets.QLabel(f"{int(self.target_temp)} °C")
        accent = "#FF7A00" if self.kind == "nozzle" else "#00E5FF"
        self.target_display.setStyleSheet(
            f"color: #FFFFFF; font-size: 28px; font-weight: 800; font-family: 'Consolas', monospace;"
            f"background: rgba(0,0,0,50); border: 1px solid {accent}; border-radius: 8px; padding: 4px 16px;"
        )
        self.target_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        adj_lay.addWidget(self.target_display, 1)

        for delta in (+1, +10):
            b = QtWidgets.QPushButton(f"+{delta}")
            b.setObjectName("StepBtn")
            b.setFixedSize(_s(48, scale), _s(44, scale))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, d=delta: self._adjust_target(d))
            adj_lay.addWidget(b)

        layout.addWidget(adj_box)

        # 3. Preset Material Buttons Row
        preset_hdr = QtWidgets.QLabel("MATERIAL PRESETS")
        preset_hdr.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        layout.addWidget(preset_hdr)

        preset_row = QtWidgets.QHBoxLayout()
        preset_row.setSpacing(_s(8, scale))
        self.preset_buttons = []
        for mat_name, mat_temp in PRESETS.get(self.kind, []):
            p_btn = QtWidgets.QPushButton(f"{mat_name}\n{mat_temp}°C")
            p_btn.setObjectName("PreheatPresetBtn")
            p_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            p_btn.setFixedHeight(_s(44, scale))
            p_btn.clicked.connect(lambda _c=False, t=mat_temp: self._set_target(t))
            preset_row.addWidget(p_btn, 1)
            self.preset_buttons.append((mat_temp, p_btn))

        layout.addLayout(preset_row)

        # 4. Bottom Action Row: [ ❄ Cooldown (Off) ]  [ Cancel ] [ 🔥 Set Target ]
        btn_bar = QtWidgets.QHBoxLayout()
        btn_bar.setSpacing(_s(10, scale))

        self.cooldown_btn = QtWidgets.QPushButton("❄  Cooldown (Off)")
        self.cooldown_btn.setObjectName("PreheatCooldownBtn")
        self.cooldown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cooldown_btn.setFixedHeight(_s(40, scale))
        self.cooldown_btn.clicked.connect(self._on_cooldown)
        btn_bar.addWidget(self.cooldown_btn, 2)

        btn_bar.addStretch(1)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName("DialogCancelBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFixedHeight(_s(40, scale))
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn, 1)

        self.apply_btn = QtWidgets.QPushButton(f"🔥  Set to {int(self.target_temp)}°C")
        self.apply_btn.setObjectName("PreheatApplyBtn")
        self.apply_btn.setProperty("kind", self.kind)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setFixedHeight(_s(40, scale))
        self.apply_btn.clicked.connect(self._on_apply)
        btn_bar.addWidget(self.apply_btn, 2)

        layout.addLayout(btn_bar)
        layout.addStretch(1)

        self._highlight_matching_preset()

    def _adjust_target(self, delta: int):
        max_limit = 300 if self.kind == "nozzle" else 130
        self.target_temp = float(max(0, min(max_limit, round(self.target_temp + delta))))
        self._update_display()

    def _set_target(self, temp: float):
        self.target_temp = float(temp)
        self._update_display()

    def _highlight_matching_preset(self):
        for temp, btn in self.preset_buttons:
            is_match = (abs(self.target_temp - temp) < 0.5)
            btn.setProperty("active", "true" if is_match else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _update_display(self):
        self.target_display.setText(f"{int(self.target_temp)} °C")
        if self.target_temp == 0:
            self.apply_btn.setText("❄  Turn Off (0°C)")
        else:
            self.apply_btn.setText(f"🔥  Set to {int(self.target_temp)}°C")
        self._highlight_matching_preset()

    def _on_cooldown(self):
        self.target_temp = 0.0
        self.temp_selected.emit(0.0)
        self.closed.emit()

    def _on_apply(self):
        self.temp_selected.emit(self.target_temp)
        self.closed.emit()

    def accept(self):
        self.temp_selected.emit(self.target_temp)
        self.closed.emit()

    def reject(self):
        self.closed.emit()

    def close(self):
        self.closed.emit()
        super().close()

    def apply_scale(self, s: float):
        m = _s(14, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.card.layout().setSpacing(_s(10, s))

