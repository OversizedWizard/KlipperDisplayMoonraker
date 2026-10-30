"""Touch-friendly modal overlay for in-flight fine tuning with 4 columns (Z-offset, Speed, Flow, Fan).

Each column features dedicated Up / Down arrow buttons, prominent live readouts, and quick-reset capabilities.
Renders directly within the MainWindow as a dimmed modal overlay on 800x480 screens.
"""

from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class FineTuneOverlay(QtWidgets.QFrame):
    """Modal overlay with 4 vertical columns and up/down arrows for Z-offset, speed, flow, and fan."""
    closed = Signal()

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("FineTuneOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#FineTuneOverlay { background: rgba(5, 10, 20, 0.85); }")

        if parent:
            self.setGeometry(parent.rect())

        self._moonraker = getattr(self.window(), "moonraker", None)

        # Local tracking state
        self._z_offset = 0.0
        self._speed_pct = 100
        self._flow_pct = 100
        self._fan_pct = 0

        # Read initial values from Moonraker if available
        if self._moonraker and hasattr(self._moonraker, "last_print_stats") and self._moonraker.last_print_stats:
            st = self._moonraker.last_print_stats
            self._z_offset = float(st.get("z_offset", 0.0))
            self._speed_pct = round(float(st.get("speed_factor", 1.0)) * 100)
            self._flow_pct = round(float(st.get("extrude_factor", 1.0)) * 100)
            self._fan_pct = round(float(st.get("fan_speed", 0.0)) * 100)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Main Card Container
        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("FineTuneCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet(f"""
            QFrame#FineTuneCard {{
                background: #0F172A;
                border: 2px solid #00E5FF;
                border-radius: {_s(14, scale)}px;
            }}
        """)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setContentsMargins(_s(16, scale), _s(12, scale), _s(16, scale), _s(12, scale))
        card_layout.setSpacing(_s(10, scale))

        # --- Top Header Bar ---
        hdr = QtWidgets.QHBoxLayout()
        hdr_icon = QtWidgets.QLabel()
        hdr_icon.setPixmap(icons.pixmap("tune", _s(22, scale)))
        hdr.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(1)
        t_lbl = QtWidgets.QLabel("FINE TUNE PRINT")
        t_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(14, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        sub_lbl = QtWidgets.QLabel("4-Channel Tuning: Z-Babystep, Print Speed, Flow & Fan")
        sub_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        title_box.addWidget(t_lbl)
        title_box.addWidget(sub_lbl)
        hdr.addLayout(title_box)
        hdr.addStretch(1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(_s(30, scale), _s(30, scale))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: {_s(15, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background: rgba(239, 68, 68, 0.4); color: #FFFFFF; border-color: #EF4444; }}
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        card_layout.addLayout(hdr)

        # --- 4 Columns Row ---
        cols_row = QtWidgets.QHBoxLayout()
        cols_row.setSpacing(_s(10, scale))

        # =========================================================================
        # Column 1: Z-OFFSET BABYSTEP
        # =========================================================================
        col1 = self._build_column(
            scale=scale,
            title="Z-OFFSET",
            accent_color="#00E5FF",
            up_labels=[("▲ +0.05", lambda: self._on_z_adjust(+0.05)), ("▲ +0.01", lambda: self._on_z_adjust(+0.01))],
            down_labels=[("▼ -0.01", lambda: self._on_z_adjust(-0.01)), ("▼ -0.05", lambda: self._on_z_adjust(-0.05))],
            initial_val=f"{self._z_offset:+.3f} mm",
            on_reset=lambda: self._on_z_reset()
        )
        self.z_val_lbl = col1["val_lbl"]
        cols_row.addWidget(col1["frame"], 1)

        # =========================================================================
        # Column 2: PRINT SPEED
        # =========================================================================
        col2 = self._build_column(
            scale=scale,
            title="SPEED",
            accent_color="#38BDF8",
            up_labels=[("▲ +10%", lambda: self._on_speed_adjust(+10)), ("▲ +5%", lambda: self._on_speed_adjust(+5))],
            down_labels=[("▼ -5%", lambda: self._on_speed_adjust(-5)), ("▼ -10%", lambda: self._on_speed_adjust(-10))],
            initial_val=f"{self._speed_pct}%",
            on_reset=lambda: self._on_speed_adjust(100)
        )
        self.spd_val_lbl = col2["val_lbl"]
        cols_row.addWidget(col2["frame"], 1)

        # =========================================================================
        # Column 3: EXTRUSION FLOW
        # =========================================================================
        col3 = self._build_column(
            scale=scale,
            title="FLOW",
            accent_color="#34D399",
            up_labels=[("▲ +5%", lambda: self._on_flow_adjust(+5)), ("▲ +1%", lambda: self._on_flow_adjust(+1))],
            down_labels=[("▼ -1%", lambda: self._on_flow_adjust(-1)), ("▼ -5%", lambda: self._on_flow_adjust(-5))],
            initial_val=f"{self._flow_pct}%",
            on_reset=lambda: self._on_flow_adjust(100)
        )
        self.flow_val_lbl = col3["val_lbl"]
        cols_row.addWidget(col3["frame"], 1)

        # =========================================================================
        # Column 4: COOLING FAN
        # =========================================================================
        col4 = self._build_column(
            scale=scale,
            title="FAN",
            accent_color="#C084FC",
            up_labels=[("▲ +25%", lambda: self._on_fan_adjust(+25)), ("▲ +10%", lambda: self._on_fan_adjust(+10))],
            down_labels=[("▼ -10%", lambda: self._on_fan_adjust(-10)), ("▼ -25%", lambda: self._on_fan_adjust(-25))],
            initial_val=f"{self._fan_pct}%",
            on_reset=lambda: self._on_fan_toggle()
        )
        self.fan_val_lbl = col4["val_lbl"]
        cols_row.addWidget(col4["frame"], 1)

        card_layout.addLayout(cols_row)

        # --- Done / Close Button ---
        done_btn = QtWidgets.QPushButton("DONE / RETURN TO PRINT")
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFixedHeight(_s(36, scale))
        done_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #3B82F6);
                color: #0F172A;
                border: 1px solid #00E5FF;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(12, scale)}px;
                font-weight: 900;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: #38BDF8;
            }}
            QPushButton:pressed {{
                background: #0284C7;
                color: #FFFFFF;
            }}
        """)
        done_btn.clicked.connect(self.close)
        card_layout.addWidget(done_btn)

        outer.addWidget(self.card)
        self.card.setFixedWidth(_s(650, scale))

    def _build_column(self, scale: float, title: str, accent_color: str, up_labels: list, down_labels: list, initial_val: str, on_reset) -> dict:
        """Helper to build a standardized column with up arrows, value display, and down arrows."""
        frame = QtWidgets.QFrame()
        frame.setStyleSheet(f"""
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: {_s(10, scale)}px;
        """)
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(_s(8, scale), _s(8, scale), _s(8, scale), _s(8, scale))
        lay.setSpacing(_s(5, scale))

        # Title
        t_lbl = QtWidgets.QLabel(title)
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_lbl.setStyleSheet(f"color: {accent_color}; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.5px;")
        lay.addWidget(t_lbl)

        # Up Buttons
        for text, fn in up_labels:
            btn = QtWidgets.QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_s(32, scale))
            btn.setStyleSheet(self._arrow_btn_style(scale, is_up=True))
            btn.clicked.connect(fn)
            lay.addWidget(btn)

        # Center Value Readout (clickable to reset)
        val_lbl = QtWidgets.QLabel(initial_val)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        val_lbl.setFixedHeight(_s(36, scale))
        val_lbl.setStyleSheet(f"""
            background: rgba(0, 0, 0, 0.35);
            color: #FFFFFF;
            border: 1.5px solid {accent_color};
            border-radius: {_s(6, scale)}px;
            font-size: {_s(13, scale)}px;
            font-weight: 900;
            font-family: monospace;
        """)
        val_lbl.mousePressEvent = lambda e: on_reset()
        val_lbl.setToolTip("Tap to reset")
        lay.addWidget(val_lbl)

        # Down Buttons
        for text, fn in down_labels:
            btn = QtWidgets.QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_s(32, scale))
            btn.setStyleSheet(self._arrow_btn_style(scale, is_up=False))
            btn.clicked.connect(fn)
            lay.addWidget(btn)

        return {"frame": frame, "val_lbl": val_lbl}

    def _arrow_btn_style(self, scale: float, is_up: bool) -> str:
        border_col = "rgba(0, 229, 255, 0.35)" if is_up else "rgba(255, 255, 255, 0.15)"
        text_col = "#00E5FF" if is_up else "#CBD5E1"
        bg_col = "rgba(0, 229, 255, 0.10)" if is_up else "rgba(255, 255, 255, 0.06)"
        hover_bg = "rgba(0, 229, 255, 0.25)" if is_up else "rgba(255, 255, 255, 0.16)"

        return f"""
            QPushButton {{
                background: {bg_col};
                color: {text_col};
                border: 1px solid {border_col};
                border-radius: {_s(6, scale)}px;
                font-size: {_s(11, scale)}px;
                font-weight: 800;
                padding: 0 {_s(4, scale)}px;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                border-color: #00E5FF;
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background: #00E5FF;
                color: #0F172A;
            }}
        """

    def _on_z_adjust(self, delta: float):
        self._z_offset += delta
        self.z_val_lbl.setText(f"{self._z_offset:+.3f} mm")
        if self._moonraker:
            self._moonraker.adjust_z_offset(delta)

    def _on_z_reset(self):
        # Reset Z-offset babystep back to 0
        diff = -self._z_offset
        if abs(diff) > 0.0001:
            self._on_z_adjust(diff)

    def _on_speed_adjust(self, val: int):
        if val == 100:
            self._speed_pct = 100
        else:
            self._speed_pct = max(10, min(500, self._speed_pct + val))
        self.spd_val_lbl.setText(f"{self._speed_pct}%")
        if self._moonraker:
            self._moonraker.set_speed_factor(self._speed_pct)

    def _on_flow_adjust(self, val: int):
        if val == 100:
            self._flow_pct = 100
        else:
            self._flow_pct = max(10, min(300, self._flow_pct + val))
        self.flow_val_lbl.setText(f"{self._flow_pct}%")
        if self._moonraker:
            self._moonraker.set_flow_factor(self._flow_pct)

    def _on_fan_adjust(self, val: int):
        self._fan_pct = max(0, min(100, self._fan_pct + val))
        self.fan_val_lbl.setText(f"{self._fan_pct}%")
        if self._moonraker:
            self._moonraker.set_fan_speed(self._fan_pct)

    def _on_fan_toggle(self):
        self._fan_pct = 0 if self._fan_pct > 0 else 100
        self.fan_val_lbl.setText(f"{self._fan_pct}%")
        if self._moonraker:
            self._moonraker.set_fan_speed(self._fan_pct)

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()
