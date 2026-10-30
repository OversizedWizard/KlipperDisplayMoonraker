"""Printer Tests & Diagnostics Screen.

Provides interactive hardware checks in Settings:
- Live Endstop Status monitor (X, Y, Z) with real-time polling
- Load Cell Probe touch detection: automatically zeroes (tares) on open and shows
  Z Endstop / Probe as CLOSED when the nozzle is touched, just like during probing
- Stepper Motor Buzz checks (STEPPER_BUZZ for X, Y, Z, Z1, Extruder)
- Quick hardware tests (Motors Off M84, Home All G28, Part Cooling Fan test)
"""

import time
from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class PrinterTestsScreen(QtWidgets.QFrame):
    """Full-screen in-window hardware diagnostics and motor/endstop test view."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._busy_poll = False
        self._tare_timestamp = time.time()
        self._has_load_cell = True
        self._touch_threshold_g = 25.0  # Sensitive nozzle touch threshold (probing feel)

        self.setObjectName("PrinterTestsScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self.card)

        root = QtWidgets.QVBoxLayout(self.card)
        m = _s(12, scale)
        root.setContentsMargins(m, _s(10, scale), m, _s(10, scale))
        root.setSpacing(_s(8, scale))

        # --- Top Header ---
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(10, scale))

        ico = QtWidgets.QLabel()
        ico.setPixmap(icons.pixmap("endstop", _s(32, scale)))
        ico.setFixedSize(_s(36, scale), _s(36, scale))
        hdr.addWidget(ico)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)
        t_lbl = QtWidgets.QLabel("Printer Hardware Tests & Diagnostics")
        t_lbl.setObjectName("DialogTitle")
        title_col.addWidget(t_lbl)

        sub_lbl = QtWidgets.QLabel("Live Endstop & Nozzle Touch Monitor • Stepper Motor Checks")
        sub_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col, 1)

        self.live_badge = QtWidgets.QLabel("● LIVE MONITOR")
        self.live_badge.setStyleSheet(f"""
            color: #34D399;
            background: rgba(16, 185, 129, 0.16);
            border: 1px solid #10B981;
            border-radius: {_s(6, scale)}px;
            font-size: {_s(10, scale)}px;
            font-weight: 800;
            padding: {_s(3, scale)}px {_s(8, scale)}px;
        """)
        hdr.addWidget(self.live_badge)

        close_x = QtWidgets.QPushButton("\u2715")
        close_x.setObjectName("DialogCloseX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(self._on_close)
        hdr.addWidget(close_x)

        root.addLayout(hdr)

        # --- Main Two-Column Body ---
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(_s(10, scale))

        # =====================================================================
        # LEFT COLUMN: Endstop Status & Load Cell Nozzle Touch
        # =====================================================================
        left_frame = QtWidgets.QFrame()
        left_frame.setObjectName("DialogStepsBox")
        left_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left_lay = QtWidgets.QVBoxLayout(left_frame)
        left_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        left_lay.setSpacing(_s(6, scale))

        es_hdr = QtWidgets.QHBoxLayout()
        es_title = QtWidgets.QLabel("ENDSTOP & PROBE STATUS")
        es_title.setStyleSheet(f"color: #00E5FF; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        es_hdr.addWidget(es_title)
        es_hdr.addStretch(1)
        left_lay.addLayout(es_hdr)

        self.endstop_rows = {}
        endstop_defs = [
            ("stepper_x", "X-Axis Endstop", "Physical limit switch (stepper_x)"),
            ("stepper_y", "Y-Axis Endstop", "Physical limit switch (stepper_y)"),
            ("stepper_z", "Z Endstop (Load Cell Probe)", "Touch nozzle to trigger CLOSED"),
        ]

        for key, label, hint in endstop_defs:
            row_card = QtWidgets.QFrame()
            row_card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(15, 23, 42, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: {_s(8, scale)}px;
                }}
            """)
            r_lay = QtWidgets.QHBoxLayout(row_card)
            r_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
            r_lay.setSpacing(_s(8, scale))

            txt_col = QtWidgets.QVBoxLayout()
            txt_col.setSpacing(1)
            name_lbl = QtWidgets.QLabel(label)
            name_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(12, scale)}px; font-weight: 800; border: none; background: transparent;")
            sub_hint = QtWidgets.QLabel(hint)
            sub_hint.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600; border: none; background: transparent;")
            txt_col.addWidget(name_lbl)
            txt_col.addWidget(sub_hint)
            r_lay.addLayout(txt_col, 1)

            pill = QtWidgets.QLabel("OPEN")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setMinimumWidth(_s(86, scale))
            pill.setFixedHeight(_s(28, scale))
            self._style_endstop_pill(pill, is_closed=False)
            r_lay.addWidget(pill)

            left_lay.addWidget(row_card)
            self.endstop_rows[key] = {
                "card": row_card,
                "name": name_lbl,
                "sub": sub_hint,
                "pill": pill,
            }

        # Live Load Cell Force Meter bar
        self.lc_info_lbl = QtWidgets.QLabel("Load Cell Force: 0.0 g  •  Touch nozzle to test trigger")
        self.lc_info_lbl.setStyleSheet(f"color: #38BDF8; font-size: {_s(10, scale)}px; font-weight: 700;")
        left_lay.addWidget(self.lc_info_lbl)

        left_lay.addStretch(1)

        # Endstop action buttons
        es_btn_row = QtWidgets.QHBoxLayout()
        es_btn_row.setSpacing(_s(6, scale))

        self.btn_query_es = QtWidgets.QPushButton("⟳ Refresh Endstops")
        self.btn_query_es.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_query_es.setFixedHeight(_s(34, scale))
        self.btn_query_es.setStyleSheet(self._action_btn_style("#00E5FF", "#0F172A", filled=False))
        self.btn_query_es.clicked.connect(self._manual_refresh_endstops)
        es_btn_row.addWidget(self.btn_query_es, 1)

        self.btn_tare = QtWidgets.QPushButton("⚖️ Tare Nozzle")
        self.btn_tare.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tare.setFixedHeight(_s(34, scale))
        self.btn_tare.setStyleSheet(self._action_btn_style("#34D399", "#0F172A", filled=False))
        self.btn_tare.clicked.connect(self._on_tare_nozzle)
        es_btn_row.addWidget(self.btn_tare, 1)

        left_lay.addLayout(es_btn_row)
        body.addWidget(left_frame, 11)

        # =====================================================================
        # RIGHT COLUMN: Stepper Motor Buzz & Hardware Checks
        # =====================================================================
        right_frame = QtWidgets.QFrame()
        right_frame.setObjectName("DialogStepsBox")
        right_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        right_lay = QtWidgets.QVBoxLayout(right_frame)
        right_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        right_lay.setSpacing(_s(6, scale))

        mt_title = QtWidgets.QLabel("MOTOR BUZZ & HARDWARE CHECKS")
        mt_title.setStyleSheet(f"color: #00E5FF; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        right_lay.addWidget(mt_title)

        mt_sub = QtWidgets.QLabel("STEPPER_BUZZ oscillates each motor ±1mm to verify wiring:")
        mt_sub.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        right_lay.addWidget(mt_sub)

        motor_grid = QtWidgets.QGridLayout()
        motor_grid.setHorizontalSpacing(_s(6, scale))
        motor_grid.setVerticalSpacing(_s(6, scale))

        motor_buttons = [
            ("⇄  Buzz X Motor", "stepper_x", 0, 0),
            ("⇅  Buzz Y Motor", "stepper_y", 0, 1),
            ("⇵  Buzz Z Motor", "stepper_z", 1, 0),
            ("⇵  Buzz Z1 Motor", "stepper_z1", 1, 1),
            ("⚙  Buzz Extruder", "extruder", 2, 0),
        ]
        self.motor_btns = {}
        for text, stepper_id, r, c in motor_buttons:
            btn = QtWidgets.QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_s(36, scale))
            btn.setStyleSheet(self._motor_btn_style())
            btn.clicked.connect(lambda _checked=False, s_id=stepper_id, lbl=text: self._on_buzz_motor(s_id, lbl))
            motor_grid.addWidget(btn, r, c)
            self.motor_btns[stepper_id] = btn

        # Disable Motors (M84) button in slot (2, 1)
        self.btn_m84 = QtWidgets.QPushButton("🛑  Motors Off (M84)")
        self.btn_m84.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_m84.setFixedHeight(_s(36, scale))
        self.btn_m84.setStyleSheet(self._action_btn_style("#F59E0B", "#0F172A", filled=False))
        self.btn_m84.clicked.connect(self._on_motors_off)
        motor_grid.addWidget(self.btn_m84, 2, 1)

        right_lay.addLayout(motor_grid)

        # Aux Fan & Homing Quick Row
        aux_lbl = QtWidgets.QLabel("COOLING FAN & HOMING TEST")
        aux_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 800; margin-top: {_s(2, scale)}px;")
        right_lay.addWidget(aux_lbl)

        aux_row = QtWidgets.QHBoxLayout()
        aux_row.setSpacing(_s(6, scale))

        btn_fan_on = QtWidgets.QPushButton("💨 Fan 100%")
        btn_fan_on.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fan_on.setFixedHeight(_s(32, scale))
        btn_fan_on.setStyleSheet(self._motor_btn_style())
        btn_fan_on.clicked.connect(lambda: self._on_fan_test(255))
        aux_row.addWidget(btn_fan_on, 1)

        btn_fan_off = QtWidgets.QPushButton("💨 Fan Off")
        btn_fan_off.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fan_off.setFixedHeight(_s(32, scale))
        btn_fan_off.setStyleSheet(self._motor_btn_style())
        btn_fan_off.clicked.connect(lambda: self._on_fan_test(0))
        aux_row.addWidget(btn_fan_off, 1)

        btn_home_all = QtWidgets.QPushButton("🏠 Home All")
        btn_home_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_home_all.setFixedHeight(_s(32, scale))
        btn_home_all.setStyleSheet(self._action_btn_style("#38BDF8", "#0F172A", filled=False))
        btn_home_all.clicked.connect(self._on_home_all)
        aux_row.addWidget(btn_home_all, 1)

        right_lay.addLayout(aux_row)
        right_lay.addStretch(1)

        # Live test output status banner
        self.status_banner = QtWidgets.QLabel("Ready • Touch nozzle or tap any button to run check")
        self.status_banner.setStyleSheet(f"""
            color: #E2E8F0;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: {_s(6, scale)}px;
            font-size: {_s(10, scale)}px;
            font-weight: 700;
            padding: {_s(5, scale)}px {_s(8, scale)}px;
        """)
        right_lay.addWidget(self.status_banner)

        body.addWidget(right_frame, 12)
        root.addLayout(body, 1)

        # --- Bottom Navigation Row ---
        bot = QtWidgets.QHBoxLayout()
        bot.addStretch(1)
        back_btn = QtWidgets.QPushButton("\u2039  Back to Settings")
        back_btn.setObjectName("DialogStartBtn")
        back_btn.setStyleSheet(f"font-size: {_s(12, scale)}px; font-weight: 800; padding: {_s(6, scale)}px {_s(18, scale)}px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._on_close)
        bot.addWidget(back_btn)
        root.addLayout(bot)

        # Polling timer for live endstop & load cell nozzle touch status
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(350)
        self._poll_timer.timeout.connect(self._poll_status)

        QtCore.QTimer.singleShot(100, self._init_screen)

    def _style_endstop_pill(self, pill: QtWidgets.QLabel, is_closed: bool):
        s = self.scale
        if is_closed:
            pill.setText("● CLOSED")
            pill.setStyleSheet(f"""
                color: #FFFFFF;
                background: #EF4444;
                border: 1.5px solid #F87171;
                border-radius: {_s(6, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 900;
                padding: 0 {_s(8, s)}px;
            """)
        else:
            pill.setText("○ OPEN")
            pill.setStyleSheet(f"""
                color: #34D399;
                background: rgba(16, 185, 129, 0.18);
                border: 1.5px solid #10B981;
                border-radius: {_s(6, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 900;
                padding: 0 {_s(8, s)}px;
            """)

    def _motor_btn_style(self) -> str:
        s = self.scale
        return f"""
            QPushButton {{
                background: #1E293B;
                color: #F8FAFC;
                border: 1px solid rgba(0, 229, 255, 0.35);
                border-radius: {_s(7, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 800;
                padding: 0 {_s(8, s)}px;
            }}
            QPushButton:hover {{
                background: rgba(0, 229, 255, 0.18);
                border-color: #00E5FF;
            }}
            QPushButton:pressed {{
                background: #00E5FF;
                color: #0F172A;
            }}
        """

    def _action_btn_style(self, accent: str, dark_fg: str, filled: bool = False) -> str:
        s = self.scale
        if filled:
            return f"""
                QPushButton {{
                    background: {accent};
                    color: {dark_fg};
                    border: 1px solid {accent};
                    border-radius: {_s(7, s)}px;
                    font-size: {_s(11, s)}px;
                    font-weight: 900;
                }}
            """
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.06);
                color: {accent};
                border: 1px solid {accent};
                border-radius: {_s(7, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.14);
            }}
        """

    def _get_moonraker(self):
        main_win = self.window()
        return getattr(main_win, "moonraker", None)

    def _init_screen(self):
        mr = self._get_moonraker()
        if mr:
            # Check if stepper_z1 exists in config
            cfg = getattr(mr, "config_settings", {}) or {}
            if cfg and "stepper_z1" not in cfg and "stepper_z1" in self.motor_btns:
                self.motor_btns["stepper_z1"].setEnabled(False)
                self.motor_btns["stepper_z1"].setText("⇵  Z1 (N/A)")

            # Automatically tare load cell on open so nozzle touch starts from 0.0g
            if mr.has_load_cell():
                self._tare_timestamp = time.time()
                mr.tare_load_cell()

        self._poll_timer.start()
        self._poll_status()

    def _poll_status(self):
        if self._busy_poll:
            return
        mr = self._get_moonraker()
        if not mr:
            return
        self._busy_poll = True

        def _on_res(data: dict):
            self._busy_poll = False
            self._update_ui_from_status(data)

        mr.query_diagnostics_status(on_done=_on_res, query_hw_endstops=True)

    def _update_ui_from_status(self, data: dict):
        endstops = data.get("endstops", {})
        has_lc = bool(data.get("has_load_cell", False))
        self._has_load_cell = has_lc

        fg = float(data.get("force_g", 0.0))
        min_fg = float(data.get("min_force_g", fg))
        max_fg = float(data.get("max_force_g", fg))
        trig_f = float(data.get("trigger_force", 60.0))

        # Update X and Y endstops
        for key in ("stepper_x", "stepper_y"):
            row = self.endstop_rows.get(key)
            if not row:
                continue
            raw_val = str(endstops.get(key, "open")).lower()
            is_closed = raw_val not in ("open", "0", "false", "")
            self._style_endstop_pill(row["pill"], is_closed=is_closed)

        # Update Z Endstop / Load Cell Probe
        z_row = self.endstop_rows.get("stepper_z")
        if z_row:
            raw_z = str(endstops.get("stepper_z", endstops.get("z", "open"))).lower()
            hw_z_closed = raw_z not in ("open", "0", "false", "")

            if has_lc:
                z_row["name"].setText("Z Endstop (Load Cell Probe)")
                # Wait 1.1s after tare so pre-tare min/max window clears
                since_tare = time.time() - self._tare_timestamp
                if since_tare > 1.1:
                    peak_force = max(abs(fg), abs(max_fg), abs(min_fg))
                else:
                    peak_force = abs(fg)

                # Trigger CLOSED when nozzle is touched (just like probing)
                threshold = min(trig_f, self._touch_threshold_g) if trig_f > 0 else self._touch_threshold_g
                is_touched = (peak_force >= threshold) or bool(data.get("probe_closed", False)) or hw_z_closed

                self._style_endstop_pill(z_row["pill"], is_closed=is_touched)
                if is_touched:
                    z_row["sub"].setText(f"NOZZLE TOUCHED! ({peak_force:.1f} g)")
                    z_row["sub"].setStyleSheet(f"color: #F87171; font-size: {_s(10, self.scale)}px; font-weight: 800; border: none; background: transparent;")
                    self.lc_info_lbl.setText(f"● PROBE CLOSED • Force: {fg:+.1f} g (Peak: {peak_force:.1f} g)")
                    self.lc_info_lbl.setStyleSheet(f"color: #EF4444; font-size: {_s(10, self.scale)}px; font-weight: 900;")
                else:
                    z_row["sub"].setText(f"Force: {fg:+.1f} g • Touch nozzle")
                    z_row["sub"].setStyleSheet(f"color: #94A3B8; font-size: {_s(10, self.scale)}px; font-weight: 600; border: none; background: transparent;")
                    self.lc_info_lbl.setText(f"○ Probe Open • Force: {fg:+.1f} g (Touch ≥ {threshold:.0f} g)")
                    self.lc_info_lbl.setStyleSheet(f"color: #38BDF8; font-size: {_s(10, self.scale)}px; font-weight: 700;")
            else:
                z_row["name"].setText("Z-Axis Endstop")
                z_row["sub"].setText("Physical / inductive Z endstop (stepper_z)")
                self._style_endstop_pill(z_row["pill"], is_closed=hw_z_closed)
                self.lc_info_lbl.setText("Standard Z Endstop active")

    def _manual_refresh_endstops(self):
        self.status_banner.setText("Querying all endstops & load cell probe...")
        self._busy_poll = False
        self._poll_status()
        QtCore.QTimer.singleShot(400, lambda: self.status_banner.setText("✓ Endstop states refreshed"))

    def _on_tare_nozzle(self):
        mr = self._get_moonraker()
        if not mr:
            return
        self._tare_timestamp = time.time()
        self.status_banner.setText("⚖️ Taring Load Cell Probe to 0.0 g...")
        def _done(ok: bool):
            self.status_banner.setText("✓ Load Cell zeroed (0.0 g) — touch nozzle to test CLOSED state")
        mr.tare_load_cell(on_done=_done)

    def _on_buzz_motor(self, stepper_id: str, label: str):
        mr = self._get_moonraker()
        if not mr:
            return
        clean_lbl = label.split("  ")[-1]
        self.status_banner.setText(f"⚡ Running STEPPER_BUZZ on {stepper_id} ({clean_lbl})...")
        def _done(ok: bool):
            if ok:
                self.status_banner.setText(f"✓ {clean_lbl} ({stepper_id}) buzz check complete")
            else:
                self.status_banner.setText(f"⚠ {stepper_id} buzz command failed (check [force_move] in printer.cfg)")
        mr.stepper_buzz(stepper_id, on_done=_done)

    def _on_motors_off(self):
        mr = self._get_moonraker()
        if not mr:
            return
        self.status_banner.setText("🛑 Disabling all stepper motors (M84)...")
        mr.motors_off(on_done=lambda ok: self.status_banner.setText("✓ All stepper motors disabled (M84)"))

    def _on_fan_test(self, speed_255: int):
        mr = self._get_moonraker()
        if not mr:
            return
        pct = round(speed_255 / 255 * 100)
        self.status_banner.setText(f"💨 Setting Part Cooling Fan to {pct}% (M106 S{speed_255})...")
        mr.send_gcode(f"M106 S{speed_255}", on_done=lambda ok: self.status_banner.setText(f"✓ Part Cooling Fan set to {pct}%"))

    def _on_home_all(self):
        mr = self._get_moonraker()
        if not mr:
            return
        self.status_banner.setText("🏠 Homing all axes (G28)...")
        mr.home(on_done=lambda ok: self.status_banner.setText("✓ Homing (G28) complete" if ok else "⚠ Homing failed or interrupted"))

    def _on_close(self):
        self._poll_timer.stop()
        self.closed.emit()

    def hideEvent(self, event):
        self._poll_timer.stop()
        super().hideEvent(event)

    def apply_scale(self, s: float):
        self.scale = s
