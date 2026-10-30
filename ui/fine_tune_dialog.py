"""Touch-friendly modal overlay for in-flight fine tuning (Z-offset babystep, temps, speed, flow, fan).

Renders directly within the MainWindow as a dimmed modal overlay with zero window-manager dependencies.
"""

from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class FineTuneOverlay(QtWidgets.QFrame):
    """Modal overlay allowing quick on-the-fly tuning during 3D printing."""
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
        self._nozzle_tgt = 205.0
        self._bed_tgt = 60.0
        self._speed_pct = 100
        self._flow_pct = 100
        self._fan_pct = 0

        # Read initial from moonraker last_print_stats if available
        if self._moonraker and hasattr(self._moonraker, "last_print_stats") and self._moonraker.last_print_stats:
            st = self._moonraker.last_print_stats
            self._z_offset = float(st.get("z_offset", 0.0))
            self._nozzle_tgt = float(st.get("nozzle_tgt", 205.0))
            self._bed_tgt = float(st.get("bed_tgt", 60.0))
            self._speed_pct = round(float(st.get("speed_factor", 1.0)) * 100)
            self._flow_pct = round(float(st.get("extrude_factor", 1.0)) * 100)
            self._fan_pct = round(float(st.get("fan_speed", 0.0)) * 100)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Card container
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
        card_layout.setContentsMargins(_s(20, scale), _s(16, scale), _s(20, scale), _s(16, scale))
        card_layout.setSpacing(_s(12, scale))

        # Header
        hdr = QtWidgets.QHBoxLayout()
        hdr_icon = QtWidgets.QLabel()
        hdr_icon.setPixmap(icons.pixmap("tune", _s(26, scale)))
        hdr.addWidget(hdr_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(1)
        t_lbl = QtWidgets.QLabel("FINE TUNE PRINT")
        t_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(15, scale)}px; font-weight: 900; letter-spacing: 0.8px;")
        sub_lbl = QtWidgets.QLabel("Live Z-Babystep, Temperatures & Speed Overrides")
        sub_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        title_box.addWidget(t_lbl)
        title_box.addWidget(sub_lbl)
        hdr.addLayout(title_box)
        hdr.addStretch(1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(_s(32, scale), _s(32, scale))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 255, 255, 12);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: {_s(16, scale)}px;
                font-size: {_s(14, scale)}px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background: rgba(239, 68, 68, 0.4); color: #FFFFFF; border-color: #EF4444; }}
        """)
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        card_layout.addLayout(hdr)

        # Tab / sections container (Grid layout for compact 800x480 fit)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(_s(12, scale))
        grid.setVerticalSpacing(_s(10, scale))

        # --- Section 1: Z-Offset Babystepping ---
        z_box = QtWidgets.QFrame()
        z_box.setStyleSheet(f"background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: {_s(10, scale)}px; padding: {_s(4, scale)}px;")
        z_lay = QtWidgets.QVBoxLayout(z_box)
        z_lay.setContentsMargins(_s(8, scale), _s(6, scale), _s(8, scale), _s(6, scale))
        z_lay.setSpacing(_s(6, scale))

        z_title_row = QtWidgets.QHBoxLayout()
        z_title = QtWidgets.QLabel("Z-OFFSET BABYSTEP")
        z_title.setStyleSheet(f"color: #F8FAFC; font-size: {_s(11, scale)}px; font-weight: 800;")
        self.z_val_lbl = QtWidgets.QLabel(f"{self._z_offset:+.3f} mm")
        self.z_val_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(12, scale)}px; font-weight: 900; font-family: monospace;")
        z_title_row.addWidget(z_title)
        z_title_row.addStretch(1)
        z_title_row.addWidget(self.z_val_lbl)
        z_lay.addLayout(z_title_row)

        z_btn_row = QtWidgets.QHBoxLayout()
        z_btn_row.setSpacing(_s(6, scale))
        for delta, label in [(-0.05, "▼ -0.05"), (-0.01, "▼ -0.01"), (+0.01, "▲ +0.01"), (+0.05, "▲ +0.05")]:
            btn = QtWidgets.QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_s(34, scale))
            btn.setStyleSheet(self._btn_style(scale, is_accent=(delta > 0)))
            btn.clicked.connect(lambda ch, d=delta: self._on_z_adjust(d))
            z_btn_row.addWidget(btn)
        z_lay.addLayout(z_btn_row)
        grid.addWidget(z_box, 0, 0, 1, 2)

        # --- Section 2: Nozzle & Bed Temperature Adjust ---
        # Nozzle
        noz_box = QtWidgets.QFrame()
        noz_box.setStyleSheet(f"background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: {_s(10, scale)}px;")
        noz_lay = QtWidgets.QVBoxLayout(noz_box)
        noz_lay.setContentsMargins(_s(8, scale), _s(6, scale), _s(8, scale), _s(6, scale))
        noz_lay.setSpacing(_s(6, scale))
        noz_row1 = QtWidgets.QHBoxLayout()
        noz_title = QtWidgets.QLabel("HOTEND TARGET")
        noz_title.setStyleSheet(f"color: #F8FAFC; font-size: {_s(11, scale)}px; font-weight: 800;")
        self.noz_val_lbl = QtWidgets.QLabel(f"{self._nozzle_tgt:.0f}°C")
        self.noz_val_lbl.setStyleSheet(f"color: #FF9A3C; font-size: {_s(12, scale)}px; font-weight: 900; font-family: monospace;")
        noz_row1.addWidget(noz_title)
        noz_row1.addStretch(1)
        noz_row1.addWidget(self.noz_val_lbl)
        noz_lay.addLayout(noz_row1)

        noz_btns = QtWidgets.QHBoxLayout()
        noz_btns.setSpacing(_s(4, scale))
        for diff, lbl in [(-5, "-5°"), (-1, "-1°"), (+1, "+1°"), (+5, "+5°")]:
            b = QtWidgets.QPushButton(lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(30, scale))
            b.setStyleSheet(self._btn_style(scale, is_accent=(diff > 0)))
            b.clicked.connect(lambda ch, d=diff: self._on_temp_adjust("extruder", d))
            noz_btns.addWidget(b)
        noz_lay.addLayout(noz_btns)
        grid.addWidget(noz_box, 1, 0)

        # Bed
        bed_box = QtWidgets.QFrame()
        bed_box.setStyleSheet(f"background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: {_s(10, scale)}px;")
        bed_lay = QtWidgets.QVBoxLayout(bed_box)
        bed_lay.setContentsMargins(_s(8, scale), _s(6, scale), _s(8, scale), _s(6, scale))
        bed_lay.setSpacing(_s(6, scale))
        bed_row1 = QtWidgets.QHBoxLayout()
        bed_title = QtWidgets.QLabel("BED TARGET")
        bed_title.setStyleSheet(f"color: #F8FAFC; font-size: {_s(11, scale)}px; font-weight: 800;")
        self.bed_val_lbl = QtWidgets.QLabel(f"{self._bed_tgt:.0f}°C")
        self.bed_val_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(12, scale)}px; font-weight: 900; font-family: monospace;")
        bed_row1.addWidget(bed_title)
        bed_row1.addStretch(1)
        bed_row1.addWidget(self.bed_val_lbl)
        bed_lay.addLayout(bed_row1)

        bed_btns = QtWidgets.QHBoxLayout()
        bed_btns.setSpacing(_s(4, scale))
        for diff, lbl in [(-5, "-5°"), (-1, "-1°"), (+1, "+1°"), (+5, "+5°")]:
            b = QtWidgets.QPushButton(lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(30, scale))
            b.setStyleSheet(self._btn_style(scale, is_accent=(diff > 0)))
            b.clicked.connect(lambda ch, d=diff: self._on_temp_adjust("heater_bed", d))
            bed_btns.addWidget(b)
        bed_lay.addLayout(bed_btns)
        grid.addWidget(bed_box, 1, 1)

        # --- Section 3: Speed, Flow & Fan ---
        sf_box = QtWidgets.QFrame()
        sf_box.setStyleSheet(f"background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: {_s(10, scale)}px;")
        sf_lay = QtWidgets.QVBoxLayout(sf_box)
        sf_lay.setContentsMargins(_s(8, scale), _s(6, scale), _s(8, scale), _s(6, scale))
        sf_lay.setSpacing(_s(6, scale))

        # Speed Row
        spd_row = QtWidgets.QHBoxLayout()
        spd_lbl = QtWidgets.QLabel("PRINT SPEED (FEEDRATE):")
        spd_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 700;")
        self.spd_val_lbl = QtWidgets.QLabel(f"{self._speed_pct}%")
        self.spd_val_lbl.setStyleSheet(f"color: #38BDF8; font-size: {_s(11, scale)}px; font-weight: 900;")
        spd_row.addWidget(spd_lbl)
        spd_row.addWidget(self.spd_val_lbl)
        spd_row.addStretch(1)
        for diff, lbl in [(-10, "-10%"), (-5, "-5%"), (100, "100%"), (+5, "+5%"), (+10, "+10%")]:
            b = QtWidgets.QPushButton(lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(28, scale))
            b.setStyleSheet(self._btn_style(scale, is_accent=(diff == 100)))
            b.clicked.connect(lambda ch, d=diff: self._on_speed_adjust(d))
            spd_row.addWidget(b)
        sf_lay.addLayout(spd_row)

        # Flow Row
        flow_row = QtWidgets.QHBoxLayout()
        flow_lbl = QtWidgets.QLabel("EXTRUSION FLOW:")
        flow_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 700;")
        self.flow_val_lbl = QtWidgets.QLabel(f"{self._flow_pct}%")
        self.flow_val_lbl.setStyleSheet(f"color: #34D399; font-size: {_s(11, scale)}px; font-weight: 900;")
        flow_row.addWidget(flow_lbl)
        flow_row.addWidget(self.flow_val_lbl)
        flow_row.addStretch(1)
        for diff, lbl in [(-5, "-5%"), (-1, "-1%"), (100, "100%"), (+1, "+1%"), (+5, "+5%")]:
            b = QtWidgets.QPushButton(lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(28, scale))
            b.setStyleSheet(self._btn_style(scale, is_accent=(diff == 100)))
            b.clicked.connect(lambda ch, d=diff: self._on_flow_adjust(d))
            flow_row.addWidget(b)
        sf_lay.addLayout(flow_row)

        # Fan Row
        fan_row = QtWidgets.QHBoxLayout()
        fan_lbl = QtWidgets.QLabel("PART COOLING FAN:")
        fan_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 700;")
        self.fan_val_lbl = QtWidgets.QLabel(f"{self._fan_pct}%")
        self.fan_val_lbl.setStyleSheet(f"color: #C084FC; font-size: {_s(11, scale)}px; font-weight: 900;")
        fan_row.addWidget(fan_lbl)
        fan_row.addWidget(self.fan_val_lbl)
        fan_row.addStretch(1)
        for pct, lbl in [(0, "OFF"), (25, "25%"), (50, "50%"), (75, "75%"), (100, "100%")]:
            b = QtWidgets.QPushButton(lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(28, scale))
            b.setStyleSheet(self._btn_style(scale, is_accent=(pct == self._fan_pct)))
            b.clicked.connect(lambda ch, p=pct: self._on_fan_set(p))
            fan_row.addWidget(b)
        sf_lay.addLayout(fan_row)

        grid.addWidget(sf_box, 2, 0, 1, 2)

        card_layout.addLayout(grid)

        # Done button
        done_btn = QtWidgets.QPushButton("DONE / CLOSE")
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFixedHeight(_s(38, scale))
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
        self.card.setFixedWidth(_s(540, scale))

    def _btn_style(self, scale: float, is_accent: bool = False) -> str:
        if is_accent:
            return f"""
                QPushButton {{
                    background: rgba(0, 229, 255, 0.18);
                    color: #00E5FF;
                    border: 1px solid rgba(0, 229, 255, 0.5);
                    border-radius: {_s(6, scale)}px;
                    font-size: {_s(11, scale)}px;
                    font-weight: 800;
                    padding: 0 {_s(8, scale)}px;
                }}
                QPushButton:hover {{
                    background: rgba(0, 229, 255, 0.35);
                    border-color: #00E5FF;
                }}
                QPushButton:pressed {{
                    background: #00E5FF;
                    color: #0F172A;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background: rgba(255, 255, 255, 0.08);
                    color: #F1F5F9;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: {_s(6, scale)}px;
                    font-size: {_s(11, scale)}px;
                    font-weight: 700;
                    padding: 0 {_s(8, scale)}px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.16);
                    border-color: rgba(255, 255, 255, 0.35);
                }}
                QPushButton:pressed {{
                    background: rgba(255, 255, 255, 0.3);
                }}
            """

    def _on_z_adjust(self, delta: float):
        self._z_offset += delta
        self.z_val_lbl.setText(f"{self._z_offset:+.3f} mm")
        if self._moonraker:
            self._moonraker.adjust_z_offset(delta)

    def _on_temp_adjust(self, heater: str, diff: float):
        if heater == "extruder":
            self._nozzle_tgt = max(0.0, min(320.0, self._nozzle_tgt + diff))
            self.noz_val_lbl.setText(f"{self._nozzle_tgt:.0f}°C")
            if self._moonraker:
                self._moonraker.set_temperature("extruder", self._nozzle_tgt)
        else:
            self._bed_tgt = max(0.0, min(140.0, self._bed_tgt + diff))
            self.bed_val_lbl.setText(f"{self._bed_tgt:.0f}°C")
            if self._moonraker:
                self._moonraker.set_temperature("heater_bed", self._bed_tgt)

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

    def _on_fan_set(self, pct: int):
        self._fan_pct = pct
        self.fan_val_lbl.setText(f"{pct}%")
        if self._moonraker:
            self._moonraker.set_fan_speed(pct)

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()
