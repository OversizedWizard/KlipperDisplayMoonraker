"""Touch-friendly modal overlay for in-flight fine tuning with 4 columns (Z-offset, Speed, Flow, Fan).

Each column features a clean Step selector and just ONE Up (▲) and ONE Down (▼) button
with prominent live readouts and tap-to-reset capabilities.
"""

from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class FineTuneOverlay(QtWidgets.QFrame):
    """Modal overlay with Step selector and 1 Up / 1 Down button per column (Z-offset, Speed, Flow, Fan)."""
    closed = Signal()

    # Step presets: index 0 = Fine, 1 = Normal, 2 = Coarse, 3 = Large
    Z_STEPS = [0.005, 0.01, 0.025, 0.05]
    PCT_STEPS = [1, 5, 10, 25]

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("FineTuneOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#FineTuneOverlay { background: rgba(5, 10, 20, 0.88); }")

        if parent:
            self.setGeometry(parent.rect())

        self._moonraker = getattr(self.window(), "moonraker", None)

        # Local tracking state
        self._z_offset = 0.0
        self._base_z_offset = 0.0
        self._babystep_count = 0
        self._speed_pct = 100
        self._flow_pct = 100
        self._fan_pct = 0

        # Active step index (default 1 -> 0.01 mm for Z, 5% for Speed/Flow/Fan)
        self._step_idx = 1
        self._z_step = self.Z_STEPS[self._step_idx]
        self._spd_step = self.PCT_STEPS[self._step_idx]
        self._flow_step = self.PCT_STEPS[self._step_idx]
        self._fan_step = self.PCT_STEPS[self._step_idx]

        # Read initial values from Moonraker if available
        if self._moonraker:
            self._base_z_offset = float(getattr(self._moonraker, "base_z_offset", 0.0))
            self._babystep_count = int(getattr(self._moonraker, "babystep_count", 0))
            if hasattr(self._moonraker, "last_print_stats") and self._moonraker.last_print_stats:
                st = self._moonraker.last_print_stats
                self._z_offset = float(st.get("z_offset", 0.0))
                self._base_z_offset = float(st.get("base_z_offset", self._base_z_offset))
                self._babystep_count = int(st.get("babystep_count", self._babystep_count))
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
        sub_lbl = QtWidgets.QLabel("Select Step Size below • Tap Center Readout to Reset")
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

        # --- Unified Step Selector Bar ---
        step_bar = QtWidgets.QFrame()
        step_bar.setObjectName("StepSelectorBar")
        step_bar.setStyleSheet(f"""
            QFrame#StepSelectorBar {{
                background: rgba(15, 23, 42, 0.9);
                border: 1px solid rgba(0, 229, 255, 0.28);
                border-radius: {_s(8, scale)}px;
            }}
        """)
        sb_lay = QtWidgets.QHBoxLayout(step_bar)
        sb_lay.setContentsMargins(_s(10, scale), _s(5, scale), _s(10, scale), _s(5, scale))
        sb_lay.setSpacing(_s(8, scale))

        sb_lbl = QtWidgets.QLabel("STEP:")
        sb_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.6px; border: none;")
        sb_lay.addWidget(sb_lbl)

        self._step_btns = []
        step_labels = [
            ("0.005 mm  /  1%", 0),
            ("0.01 mm  /  5%", 1),
            ("0.025 mm  /  10%", 2),
            ("0.05 mm  /  25%", 3),
        ]
        for txt, idx in step_labels:
            b = QtWidgets.QPushButton(txt)
            b.setCheckable(True)
            b.setChecked(idx == self._step_idx)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(28, scale))
            b.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(30, 41, 59, 0.85);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: {_s(6, scale)}px;
                    font-size: {_s(11, scale)}px;
                    font-weight: 800;
                    padding: 0 {_s(10, scale)}px;
                }}
                QPushButton:hover {{
                    border-color: #00E5FF;
                    color: #FFFFFF;
                }}
                QPushButton:checked {{
                    background: rgba(0, 229, 255, 0.22);
                    color: #00E5FF;
                    border: 1.5px solid #00E5FF;
                }}
            """)
            b.clicked.connect(lambda _c=False, i=idx: self._select_step_preset(i))
            sb_lay.addWidget(b, 1)
            self._step_btns.append(b)

        card_layout.addWidget(step_bar)

        # --- 4 Columns Row (Each has ONLY 1 Up button, 1 Value Readout, 1 Down button) ---
        cols_row = QtWidgets.QHBoxLayout()
        cols_row.setSpacing(_s(10, scale))

        # Column 1: Z-OFFSET BABYSTEP
        self.col_z = self._build_single_column(
            scale=scale,
            title="Z-OFFSET",
            accent_color="#00E5FF",
            step_text=f"Step: {self._z_step:g} mm",
            initial_val=f"{self._z_offset:+.3f} mm",
            on_up=lambda: self._on_z_adjust(+self._z_step),
            on_down=lambda: self._on_z_adjust(-self._z_step),
            on_reset=self._on_z_reset,
        )
        self.z_val_lbl = self.col_z["val_lbl"]
        cols_row.addWidget(self.col_z["frame"], 1)

        # Column 2: PRINT SPEED
        self.col_spd = self._build_single_column(
            scale=scale,
            title="SPEED",
            accent_color="#38BDF8",
            step_text=f"Step: {self._spd_step}%",
            initial_val=f"{self._speed_pct}%",
            on_up=lambda: self._on_speed_adjust(+self._spd_step),
            on_down=lambda: self._on_speed_adjust(-self._spd_step),
            on_reset=lambda: self._on_speed_adjust(0, reset=True),
        )
        self.spd_val_lbl = self.col_spd["val_lbl"]
        cols_row.addWidget(self.col_spd["frame"], 1)

        # Column 3: EXTRUSION FLOW
        self.col_flow = self._build_single_column(
            scale=scale,
            title="FLOW",
            accent_color="#34D399",
            step_text=f"Step: {self._flow_step}%",
            initial_val=f"{self._flow_pct}%",
            on_up=lambda: self._on_flow_adjust(+self._flow_step),
            on_down=lambda: self._on_flow_adjust(-self._flow_step),
            on_reset=lambda: self._on_flow_adjust(0, reset=True),
        )
        self.flow_val_lbl = self.col_flow["val_lbl"]
        cols_row.addWidget(self.col_flow["frame"], 1)

        # Column 4: COOLING FAN
        self.col_fan = self._build_single_column(
            scale=scale,
            title="FAN",
            accent_color="#C084FC",
            step_text=f"Step: {self._fan_step}%",
            initial_val=f"{self._fan_pct}%",
            on_up=lambda: self._on_fan_adjust(+self._fan_step),
            on_down=lambda: self._on_fan_adjust(-self._fan_step),
            on_reset=self._on_fan_toggle,
        )
        self.fan_val_lbl = self.col_fan["val_lbl"]
        cols_row.addWidget(self.col_fan["frame"], 1)

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
        self.card.setFixedWidth(_s(660, scale))

    def _build_single_column(
        self,
        scale: float,
        title: str,
        accent_color: str,
        step_text: str,
        initial_val: str,
        on_up,
        on_down,
        on_reset,
    ) -> dict:
        """Build a clean column with Title, Step badge, ONE Up button, Value readout, and ONE Down button."""
        frame = QtWidgets.QFrame()
        frame.setObjectName("TuneColFrame")
        frame.setStyleSheet(f"""
            QFrame#TuneColFrame {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: {_s(10, scale)}px;
            }}
        """)
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(_s(8, scale), _s(8, scale), _s(8, scale), _s(8, scale))
        lay.setSpacing(_s(6, scale))

        # Title
        t_lbl = QtWidgets.QLabel(title)
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_lbl.setStyleSheet(f"color: {accent_color}; font-size: {_s(12, scale)}px; font-weight: 900; letter-spacing: 0.5px; border: none; background: transparent;")
        lay.addWidget(t_lbl)

        # Active step sub-badge
        step_lbl = QtWidgets.QLabel(step_text)
        step_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 700; border: none; background: transparent;")
        lay.addWidget(step_lbl)

        # Single Up Button (▲)
        up_btn = QtWidgets.QPushButton("▲")
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        up_btn.setFixedHeight(_s(46, scale))
        up_btn.setStyleSheet(self._arrow_btn_style(scale, is_up=True, accent=accent_color))
        up_btn.clicked.connect(on_up)
        lay.addWidget(up_btn)

        # Center Value Readout (tap to reset)
        val_lbl = QtWidgets.QLabel(initial_val)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        val_lbl.setFixedHeight(_s(40, scale))
        val_lbl.setStyleSheet(f"""
            background: rgba(0, 0, 0, 0.40);
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

        # Single Down Button (▼)
        down_btn = QtWidgets.QPushButton("▼")
        down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        down_btn.setFixedHeight(_s(46, scale))
        down_btn.setStyleSheet(self._arrow_btn_style(scale, is_up=False, accent=accent_color))
        down_btn.clicked.connect(on_down)
        lay.addWidget(down_btn)

        return {
            "frame": frame,
            "val_lbl": val_lbl,
            "step_lbl": step_lbl,
            "up_btn": up_btn,
            "down_btn": down_btn,
        }

    def _select_step_preset(self, idx: int):
        self._step_idx = idx
        for i, b in enumerate(self._step_btns):
            b.setChecked(i == idx)
        self._z_step = self.Z_STEPS[idx]
        self._spd_step = self.PCT_STEPS[idx]
        self._flow_step = self.PCT_STEPS[idx]
        self._fan_step = self.PCT_STEPS[idx]

        self.col_z["step_lbl"].setText(f"Step: {self._z_step:g} mm")
        self.col_spd["step_lbl"].setText(f"Step: {self._spd_step}%")
        self.col_flow["step_lbl"].setText(f"Step: {self._flow_step}%")
        self.col_fan["step_lbl"].setText(f"Step: {self._fan_step}%")

    def _arrow_btn_style(self, scale: float, is_up: bool, accent: str = "#00E5FF") -> str:
        border_col = "rgba(0, 229, 255, 0.40)" if is_up else "rgba(255, 255, 255, 0.18)"
        text_col = accent if is_up else "#CBD5E1"
        bg_col = "rgba(0, 229, 255, 0.12)" if is_up else "rgba(255, 255, 255, 0.06)"
        hover_bg = "rgba(0, 229, 255, 0.25)" if is_up else "rgba(255, 255, 255, 0.16)"

        return f"""
            QPushButton {{
                background: {bg_col};
                color: {text_col};
                border: 1px solid {border_col};
                border-radius: {_s(7, scale)}px;
                font-size: {_s(16, scale)}px;
                font-weight: 900;
            }}
            QPushButton:hover {{
                background: {hover_bg};
                border-color: {accent};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background: {accent};
                color: #0F172A;
            }}
        """

    def _on_z_adjust(self, delta: float):
        self._z_offset = round(self._z_offset + delta, 4)
        if abs(self._z_offset) < 1e-4:
            self._z_offset = 0.0
            self._babystep_count = 0
        else:
            self._babystep_count += (1 if delta > 0 else -1)

        self.z_val_lbl.setText(f"{self._z_offset:+.3f} mm")

        if self._moonraker:
            self._moonraker.adjust_z_offset(delta)
            if hasattr(self._moonraker, "last_print_stats") and self._moonraker.last_print_stats:
                self._moonraker.last_print_stats["z_offset"] = self._z_offset
                self._moonraker.last_print_stats["babystep_count"] = self._babystep_count
                cur_z = float(self._moonraker.last_print_stats.get("z_pos", 0.0))
                self._moonraker.last_print_stats["z_pos"] = round(cur_z + delta, 4)

        # Immediately reflect new Z position on HomePage & PrintingPage
        win = self.window()
        pages = getattr(win, "pages", {}) if win else {}
        hp = pages.get("home")
        if hp and hasattr(hp, "_coords") and hasattr(hp, "axis_cards"):
            hp._coords["Z"] = round(float(hp._coords.get("Z", 0.0)) + delta, 4)
            is_h = ("z" in getattr(hp, "_homed", "")) if (self._moonraker and self._moonraker.connected) else True
            hp.axis_cards["Z"].set_position(hp._coords["Z"], is_h)

        pp = pages.get("printing")
        if pp and hasattr(pp, "update_z_babystep"):
            pp.update_z_babystep(
                self._z_offset,
                base_z=self._base_z_offset,
                step_count=self._babystep_count,
            )

    def _on_z_reset(self):
        diff = -self._z_offset
        if abs(diff) > 0.0001:
            self._babystep_count = 0
            self._on_z_adjust(diff)

    def _on_speed_adjust(self, val: int, reset: bool = False):
        if reset:
            self._speed_pct = 100
        else:
            self._speed_pct = max(10, min(500, self._speed_pct + val))
        self.spd_val_lbl.setText(f"{self._speed_pct}%")
        if self._moonraker:
            self._moonraker.set_speed_factor(self._speed_pct)

    def _on_flow_adjust(self, val: int, reset: bool = False):
        if reset:
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


class TempTuneOverlay(QtWidgets.QFrame):
    """Touch overlay to fine tune a heater target (nozzle or bed) with big +/- buttons."""
    closed = Signal()

    def __init__(self, heater: str, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = scale
        self.heater = heater  # "extruder" or "heater_bed"
        self._is_nozzle = heater == "extruder"
        self._accent = "#FF9A3C" if self._is_nozzle else "#00E5FF"
        self._max_t = 300 if self._is_nozzle else 120
        self._steps = [1, 5, 10]
        self._step = 5
        self.setObjectName("TempTuneOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#TempTuneOverlay { background: rgba(5, 10, 20, 0.88); }")
        if parent:
            self.setGeometry(parent.rect())

        self._mr = getattr(self.window(), "moonraker", None)
        self._cur = 0.0
        self._tgt = 0.0
        if self._mr:
            self._cur = float(getattr(self._mr, "nozzle_temp" if self._is_nozzle else "bed_temp", 0.0) or 0.0)
            self._tgt = float(getattr(self._mr, "nozzle_target" if self._is_nozzle else "bed_target", 0.0) or 0.0)
            if hasattr(self._mr, "temps_updated"):
                self._mr.temps_updated.connect(self._on_temps)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QtWidgets.QFrame(self)
        card.setObjectName("TempTuneCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"QFrame#TempTuneCard {{ background: #0F172A; border: 2px solid {self._accent};"
                           f" border-radius: {_s(14, scale)}px; }} QLabel {{ background: transparent; border: none; }}")
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(_s(18, scale), _s(12, scale), _s(18, scale), _s(12, scale))
        lay.setSpacing(_s(10, scale))

        hdr = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("NOZZLE TEMPERATURE" if self._is_nozzle else "BED TEMPERATURE")
        title.setStyleSheet(f"color: {self._accent}; font-size: {_s(16, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        hdr.addWidget(title)
        hdr.addStretch(1)
        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(_s(36, scale), _s(36, scale))
        close_btn.setStyleSheet(f"QPushButton {{ background: rgba(255,255,255,0.08); color: #CBD5E1;"
                                f" border: 1px solid rgba(255,255,255,0.15); border-radius: {_s(18, scale)}px;"
                                f" font-size: {_s(15, scale)}px; font-weight: 800; }}")
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self.cur_lbl = QtWidgets.QLabel("")
        self.cur_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cur_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(14, scale)}px; font-weight: 700;")
        lay.addWidget(self.cur_lbl)

        # - [target] + row
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(_s(14, scale))

        def _big_btn(txt, delta):
            b = QtWidgets.QPushButton(txt)
            b.setFixedSize(_s(96, scale), _s(76, scale))
            b.setStyleSheet(f"QPushButton {{ background: rgba(255,255,255,0.07); color: {self._accent};"
                            f" border: 1.5px solid {self._accent}; border-radius: {_s(12, scale)}px;"
                            f" font-size: {_s(38, scale)}px; font-weight: 900; }}"
                            f"QPushButton:pressed {{ background: rgba(255,255,255,0.22); }}")
            b.clicked.connect(lambda _c=False: self._adjust(delta))
            return b

        row.addWidget(_big_btn("−", -1))
        self.tgt_lbl = QtWidgets.QLabel("0°C")
        self.tgt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tgt_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(48, scale)}px; font-weight: 900; font-family: monospace;")
        row.addWidget(self.tgt_lbl, 1)
        row.addWidget(_big_btn("+", +1))
        lay.addLayout(row)

        # Step selector
        step_row = QtWidgets.QHBoxLayout()
        step_row.setSpacing(_s(8, scale))
        sl = QtWidgets.QLabel("STEP:")
        sl.setStyleSheet(f"color: {self._accent}; font-size: {_s(13, scale)}px; font-weight: 900;")
        step_row.addWidget(sl)
        self._step_btns = []
        for st in self._steps:
            b = QtWidgets.QPushButton(f"{st}°")
            b.setCheckable(True)
            b.setChecked(st == self._step)
            b.setFixedHeight(_s(40, scale))
            b.setStyleSheet(f"QPushButton {{ background: rgba(30,41,59,0.85); color: #94A3B8;"
                            f" border: 1px solid rgba(255,255,255,0.14); border-radius: {_s(8, scale)}px;"
                            f" font-size: {_s(14, scale)}px; font-weight: 800; }}"
                            f"QPushButton:checked {{ background: rgba(255,255,255,0.15); color: {self._accent};"
                            f" border: 1.5px solid {self._accent}; }}")
            b.clicked.connect(lambda _c=False, v=st: self._set_step(v))
            step_row.addWidget(b, 1)
            self._step_btns.append(b)
        lay.addLayout(step_row)

        # Preset / off row
        presets = ([("PLA", 210), ("PETG", 240), ("ABS", 260)] if self._is_nozzle
                   else [("PLA", 60), ("PETG", 80), ("ABS", 100)])
        pr = QtWidgets.QHBoxLayout()
        pr.setSpacing(_s(8, scale))
        for name, t in presets:
            b = QtWidgets.QPushButton(f"{name} {t}°")
            b.setFixedHeight(_s(40, scale))
            b.setStyleSheet(f"QPushButton {{ background: rgba(255,255,255,0.06); color: #E2E8F0;"
                            f" border: 1px solid rgba(255,255,255,0.15); border-radius: {_s(8, scale)}px;"
                            f" font-size: {_s(13, scale)}px; font-weight: 800; }}"
                            f"QPushButton:pressed {{ background: rgba(255,255,255,0.2); }}")
            b.clicked.connect(lambda _c=False, v=t: self._apply(v))
            pr.addWidget(b, 1)
        off = QtWidgets.QPushButton("OFF")
        off.setFixedHeight(_s(40, scale))
        off.setStyleSheet(f"QPushButton {{ background: rgba(239,68,68,0.18); color: #F87171;"
                          f" border: 1px solid #EF4444; border-radius: {_s(8, scale)}px;"
                          f" font-size: {_s(13, scale)}px; font-weight: 900; }}")
        off.clicked.connect(lambda: self._apply(0))
        pr.addWidget(off, 1)
        lay.addLayout(pr)

        done = QtWidgets.QPushButton("DONE")
        done.setFixedHeight(_s(44, scale))
        done.setStyleSheet(f"QPushButton {{ background: {self._accent}; color: #0F172A; border: none;"
                           f" border-radius: {_s(10, scale)}px; font-size: {_s(15, scale)}px; font-weight: 900; }}")
        done.clicked.connect(self.close)
        lay.addWidget(done)

        outer.addWidget(card)
        card.setFixedWidth(_s(520, scale))
        self._refresh()

    def _refresh(self):
        self.cur_lbl.setText(f"Current: {self._cur:.1f}°C")
        self.tgt_lbl.setText(f"{self._tgt:.0f}°C" if self._tgt > 0 else "OFF")

    def _on_temps(self, n_cur, n_tgt, b_cur, b_tgt):
        if self._is_nozzle:
            self._cur = n_cur
            self._tgt = n_tgt
        else:
            self._cur = b_cur
            self._tgt = b_tgt
        self._refresh()

    def _set_step(self, v: int):
        self._step = v
        for b, st in zip(self._step_btns, self._steps):
            b.setChecked(st == v)

    def _adjust(self, direction: int):
        base = self._tgt if self._tgt > 0 else (self._cur if direction > 0 and self._cur > 40 else 0.0)
        self._apply(max(0, min(self._max_t, round(base + direction * self._step))))

    def _apply(self, target: float):
        self._tgt = float(target)
        self._refresh()
        if self._mr:
            self._mr.set_temperature(self.heater, float(target))

    def close(self):
        if self._mr and hasattr(self._mr, "temps_updated"):
            try:
                self._mr.temps_updated.disconnect(self._on_temps)
            except Exception:
                pass
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()
