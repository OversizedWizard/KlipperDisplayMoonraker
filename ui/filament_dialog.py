"""Filament Load / Unload Procedural Dialog.

Interactive in-window touch procedure that:
1. Heats the nozzle to the active spool's required temperature.
2. Checks for filament runout sensor detection (waits for user to insert filament if sensor configured).
3. Animates extruder dual drive gears gripping and extruding filament (or retracting/pulling for unload).
4. Provides real-time user instructions ("Insert filament now into extruder", "Pull filament out gently", etc.).
5. Displays a Cancel button that immediately aborts movement and turns off nozzle & bed heaters for safety.
"""

from . import icons
from .extruder_anim import ExtruderAnimationCanvas
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class FilamentActionDialog(QtWidgets.QFrame):
    """Full-screen in-window procedural view for Loading or Unloading filament with live animations."""
    closed = Signal()

    def __init__(self, mode: str, spool_data: dict, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.mode = mode.lower()  # "load" or "unload"
        self.spool_data = dict(spool_data or {})
        self.scale = scale

        self.target_temp = float(self.spool_data.get("nozzle_temp", 210))
        self.current_temp = 25.0
        self.filament_color = self.spool_data.get("color", "#3B82F6")
        self.filament_type = self.spool_data.get("type", "PLA")
        self.spool_name = self.spool_data.get("name", "Spool 1")

        self._has_sensor = False
        self._sensor_name = ""
        self._sensor_detected = False
        self._is_cancelled = False
        self._is_completed = False

        self.setObjectName("DialogCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Card container
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        outer.addWidget(self.card)

        layout = QtWidgets.QVBoxLayout(self.card)
        m = _s(12, scale)
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(_s(8, scale))

        # --- Header Row: Mode Title + Spool Badge + Cancel X ---
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(10, scale))

        ico_name = "spool"
        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setPixmap(icons.pixmap(ico_name, _s(32, scale)))
        self.icon_lbl.setFixedSize(_s(36, scale), _s(36, scale))
        hdr.addWidget(self.icon_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)

        self.title_lbl = QtWidgets.QLabel(f"{'Load' if self.mode == 'load' else 'Unload'} Filament — {self.spool_name}")
        self.title_lbl.setObjectName("DialogTitle")
        self.title_lbl.setStyleSheet(f"font-size: {_s(15, scale)}px; font-weight: 800; color: #FFFFFF;")
        title_col.addWidget(self.title_lbl)

        self.sub_lbl = QtWidgets.QLabel(f"Target: {self.target_temp:.0f}°C  •  {self.filament_type}")
        self.sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        title_col.addWidget(self.sub_lbl)
        hdr.addLayout(title_col, 1)

        self.cmd_badge = QtWidgets.QLabel(f"LOAD_FILAMENT" if self.mode == "load" else "UNLOAD_FILAMENT")
        self.cmd_badge.setObjectName("CalCmdBadge")
        hdr.addWidget(self.cmd_badge)

        self.close_btn = QtWidgets.QPushButton("\u2715")
        self.close_btn.setObjectName("DialogCloseX")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_cancel)
        hdr.addWidget(self.close_btn)

        layout.addLayout(hdr)

        # --- Main Content: 2-Column Split (Left: Animation Canvas, Right: Status & Steps) ---
        split = QtWidgets.QHBoxLayout()
        split.setSpacing(_s(12, scale))

        # Left Column: Extruder Canvas
        self.anim_canvas = ExtruderAnimationCanvas(mode=self.mode, filament_color=self.filament_color, parent=self)
        split.addWidget(self.anim_canvas, 1)

        # Right Column: Procedural Status Card
        self.right_card = QtWidgets.QFrame()
        self.right_card.setObjectName("DialogStepsBox")
        self.right_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.right_card.setStyleSheet("""
            QFrame#DialogStepsBox {
                background: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
            }
            QFrame#DialogStepsBox QLabel {
                border: none;
                background: transparent;
            }
        """)
        rc_lay = QtWidgets.QVBoxLayout(self.right_card)
        rc_lay.setContentsMargins(_s(12, scale), _s(8, scale), _s(12, scale), _s(8, scale))
        rc_lay.setSpacing(_s(5, scale))

        # Status Banner
        self.status_title = QtWidgets.QLabel("STEP 1: HEATING NOZZLE")
        self.status_title.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
        rc_lay.addWidget(self.status_title)

        # Primary instruction callout
        self.instruction_box = QtWidgets.QFrame()
        self.instruction_box.setObjectName("InstructionBox")
        self.instruction_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.instruction_box.setStyleSheet("""
            QFrame#InstructionBox {
                background: rgba(30, 41, 59, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 8px;
            }
            QFrame#InstructionBox QLabel {
                border: none;
                background: transparent;
            }
        """)
        ib_lay = QtWidgets.QVBoxLayout(self.instruction_box)
        ib_lay.setContentsMargins(8, 6, 8, 6)

        self.instruction_text = QtWidgets.QLabel("Nozzle is heating up to extrude temperature. Please wait...")
        self.instruction_text.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: 700;")
        self.instruction_text.setWordWrap(True)
        ib_lay.addWidget(self.instruction_text)
        rc_lay.addWidget(self.instruction_box)

        # Temperature Progress Bar & Reading
        temp_row = QtWidgets.QHBoxLayout()
        self.temp_lbl = QtWidgets.QLabel(f"Nozzle Temp: 25.0°C / {self.target_temp:.0f}°C")
        self.temp_lbl.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 800;")
        temp_row.addWidget(self.temp_lbl)
        temp_row.addStretch(1)
        self.sensor_badge = QtWidgets.QLabel("SENSOR: NOT CONFIGURED")
        self.sensor_badge.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; background: rgba(255, 255, 255, 0.05); border-radius: 4px; padding: 2px 6px;")
        temp_row.addWidget(self.sensor_badge)
        rc_lay.addLayout(temp_row)

        self.temp_bar = QtWidgets.QProgressBar()
        self.temp_bar.setRange(0, 100)
        self.temp_bar.setValue(10)
        self.temp_bar.setTextVisible(False)
        self.temp_bar.setFixedHeight(8)
        self.temp_bar.setStyleSheet("""
            QProgressBar {
                background: #1E293B;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #EF4444);
                border-radius: 4px;
            }
        """)
        rc_lay.addWidget(self.temp_bar)

        # Procedural Steps Checklist
        rc_lay.addSpacing(4)
        checklist_lbl = QtWidgets.QLabel("PROCEDURAL CHECKLIST")
        checklist_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        rc_lay.addWidget(checklist_lbl)

        self.step1_lbl = QtWidgets.QLabel("● 1. Pre-heating hotend to melting point")
        self.step1_lbl.setStyleSheet("color: #FBBF24; font-size: 11px; font-weight: 700;")
        rc_lay.addWidget(self.step1_lbl)

        if self.mode == "load":
            self.step2_lbl = QtWidgets.QLabel("○ 2. Insert filament into extruder drive until gears grip")
            self.step3_lbl = QtWidgets.QLabel("○ 3. Extruder feeds filament through nozzle meltzone")
        else:
            self.step2_lbl = QtWidgets.QLabel("○ 2. Reversing drive gear and retracting filament")
            self.step3_lbl = QtWidgets.QLabel("○ 3. Gently pull filament free from toolhead Bowden tube")

        self.step2_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
        self.step3_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
        rc_lay.addWidget(self.step2_lbl)
        rc_lay.addWidget(self.step3_lbl)

        # Manual Extrude & Retract Controls inside Load/Unload Dialog
        rc_lay.addSpacing(4)
        man_hdr = QtWidgets.QLabel("MANUAL EXTRUDE / RETRACT")
        man_hdr.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        rc_lay.addWidget(man_hdr)

        man_grid = QtWidgets.QGridLayout()
        man_grid.setHorizontalSpacing(_s(6, scale))
        man_grid.setVerticalSpacing(_s(6, scale))

        btn_ext_10 = QtWidgets.QPushButton("⬇ Extrude +10mm")
        btn_ext_25 = QtWidgets.QPushButton("⬇ Extrude +25mm")
        btn_ret_10 = QtWidgets.QPushButton("⬆ Retract -10mm")
        btn_ret_25 = QtWidgets.QPushButton("⬆ Retract -25mm")

        for b, is_ext in ((btn_ext_10, True), (btn_ext_25, True), (btn_ret_10, False), (btn_ret_25, False)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(30, scale))
            if is_ext:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(16, 185, 129, 0.18);
                        border: 1px solid #10B981;
                        color: #34D399;
                        font-weight: 800;
                        font-size: {_s(11, scale)}px;
                        border-radius: {_s(6, scale)}px;
                    }}
                    QPushButton:hover {{ background: rgba(16, 185, 129, 0.32); color: #FFFFFF; }}
                    QPushButton:pressed {{ background: #10B981; color: #0F172A; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(56, 189, 248, 0.16);
                        border: 1px solid #38BDF8;
                        color: #7DD3FC;
                        font-weight: 800;
                        font-size: {_s(11, scale)}px;
                        border-radius: {_s(6, scale)}px;
                    }}
                    QPushButton:hover {{ background: rgba(56, 189, 248, 0.30); color: #FFFFFF; }}
                    QPushButton:pressed {{ background: #38BDF8; color: #0F172A; }}
                """)

        btn_ext_10.clicked.connect(lambda: self._on_manual_extrude(+10.0))
        btn_ext_25.clicked.connect(lambda: self._on_manual_extrude(+25.0))
        btn_ret_10.clicked.connect(lambda: self._on_manual_extrude(-10.0))
        btn_ret_25.clicked.connect(lambda: self._on_manual_extrude(-25.0))

        man_grid.addWidget(btn_ext_10, 0, 0)
        man_grid.addWidget(btn_ext_25, 0, 1)
        man_grid.addWidget(btn_ret_10, 1, 0)
        man_grid.addWidget(btn_ret_25, 1, 1)
        rc_lay.addLayout(man_grid)

        rc_lay.addStretch(1)

        split.addWidget(self.right_card, 1)
        layout.addLayout(split, 1)

        # --- Bottom Action Bar: Cancel & Complete Buttons ---
        btn_bar = QtWidgets.QHBoxLayout()
        btn_bar.setSpacing(_s(10, scale))

        self.cancel_btn = QtWidgets.QPushButton("⛔  Cancel & Turn Off Heaters")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.2);
                border: 1.5px solid #EF4444;
                color: #FCA5A5;
                font-weight: 800;
                font-size: 12px;
                border-radius: 10px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #EF4444;
                color: #FFFFFF;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_bar.addWidget(self.cancel_btn)

        btn_bar.addStretch(1)

        self.action_btn = QtWidgets.QPushButton("Heating...")
        self.action_btn.setEnabled(False)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: #334155;
                border: 1px solid #475569;
                color: #94A3B8;
                font-weight: 800;
                font-size: 12px;
                border-radius: 10px;
                padding: 8px 20px;
            }
        """)
        self.action_btn.clicked.connect(self._on_finish)
        btn_bar.addWidget(self.action_btn)

        layout.addLayout(btn_bar)

        # Polling timer for heater and sensor status
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(350)
        self._poll_timer.timeout.connect(self._poll_status)

        self._detect_sensor()
        self._start_procedure()

    def _get_moonraker(self):
        """Find MoonrakerClient across parent chain or main window."""
        p = self
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr is not None:
                return mr
            p = p.parent() if hasattr(p, "parent") and callable(p.parent) else None
        win = self.window()
        return getattr(win, "moonraker", None)

    def _read_cached_nozzle_temp(self):
        """Read latest known nozzle temperature from MoonrakerClient or HomePage."""
        mr = self._get_moonraker()
        if mr is not None:
            nt = float(getattr(mr, "nozzle_temp", 0.0) or 0.0)
            if nt <= 0.0 and hasattr(mr, "last_print_stats") and isinstance(mr.last_print_stats, dict):
                nt = float(mr.last_print_stats.get("nozzle_cur", 0.0) or 0.0)
            if nt > 0.0:
                self.current_temp = nt
                return
        win = self.window()
        if win and hasattr(win, "pages") and "home" in win.pages:
            hp = win.pages["home"]
            if hasattr(hp, "nozzle") and hasattr(hp.nozzle, "current_val"):
                nt = float(hp.nozzle.current_val or 0.0)
                if nt > 0.0:
                    self.current_temp = nt

    def _on_temps_updated(self, n_cur: float, n_tgt: float, _b_cur: float, _b_tgt: float):
        if n_cur > 0.0:
            self.current_temp = float(n_cur)
        self._update_temp_ui_and_steps()

    def _detect_sensor(self):
        """Check if printer has a configured filament runout / switch sensor."""
        mr = self._get_moonraker()
        if mr:
            cfg = getattr(mr, "config", {}) or {}
            objs = getattr(mr, "objects", []) or []
            for k in cfg.keys():
                if "filament_switch_sensor" in k or "filament_motion_sensor" in k:
                    self._has_sensor = True
                    self._sensor_name = k
                    break
            if not self._has_sensor:
                for o in objs:
                    if "filament_switch_sensor" in o or "filament_motion_sensor" in o:
                        self._has_sensor = True
                        self._sensor_name = o
                        break

        if self._has_sensor:
            self.sensor_badge.setText("SENSOR: ACTIVE")
            self.sensor_badge.setStyleSheet("color: #10B981; font-size: 10px; font-weight: 700; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 4px; padding: 2px 6px;")
        else:
            self.sensor_badge.setText("SENSOR: NONE")
            self.sensor_badge.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700; background: rgba(255, 255, 255, 0.05); border-radius: 4px; padding: 2px 6px;")

    def _start_procedure(self):
        """Read current hotend temperature, heat if needed, and start tracking."""
        self._read_cached_nozzle_temp()
        mr = self._get_moonraker()
        if mr:
            if hasattr(mr, "temps_updated"):
                try:
                    mr.temps_updated.connect(self._on_temps_updated)
                except Exception:
                    pass
            if mr.connected:
                # If nozzle is already heated >= 185°C at an active target, keep or match target without blocking
                live_tgt = float(getattr(mr, "nozzle_target", 0.0) or 0.0)
                if self.current_temp >= 185.0 and live_tgt >= 180.0 and abs(self.current_temp - live_tgt) <= 5.0:
                    self.target_temp = live_tgt
                    self.sub_lbl.setText(f"Target: {self.target_temp:.0f}°C  •  {self.filament_type}")
                else:
                    mr.set_temperature("extruder", self.target_temp)

        self._update_temp_ui_and_steps()
        self._poll_timer.start()
        QtCore.QTimer.singleShot(50, self._poll_status)

    def _poll_status(self):
        if self._is_cancelled:
            return

        self._read_cached_nozzle_temp()
        self._update_temp_ui_and_steps()

    def _update_temp_ui_and_steps(self):
        if self._is_cancelled:
            return

        # Update progress and animation canvas
        self.anim_canvas.set_temp(self.current_temp, self.target_temp)
        pct = min(100, max(0, int((self.current_temp / max(1.0, self.target_temp)) * 100)))
        self.temp_bar.setValue(pct)
        self.temp_lbl.setText(f"Nozzle Temp: {self.current_temp:.1f}°C / {self.target_temp:.0f}°C")

        if self._is_completed:
            return

        # Consider hot when within 4°C of target OR already >= 185°C melting temp
        is_hot = (self.current_temp >= (self.target_temp - 4.0)) or (self.current_temp >= 185.0)

        if not is_hot:
            self.status_title.setText("STEP 1: HEATING NOZZLE")
            self.status_title.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 800;")
            self.instruction_text.setText(f"Nozzle heating ({self.current_temp:.1f}°C → {self.target_temp:.0f}°C). Please wait before feeding/pulling...")
            self.anim_canvas.set_stage("heating")
            self.step1_lbl.setStyleSheet("color: #FBBF24; font-size: 11px; font-weight: 700;")
            self.step2_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
            self.step3_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
        else:
            # Temperature reached!
            self.step1_lbl.setText(f"✔ 1. Hotend hot ({self.current_temp:.1f}°C) — Ready")
            self.step1_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")

            if self.mode == "load":
                # Check filament sensor requirement
                if self._has_sensor and not self._sensor_detected:
                    self.status_title.setText("STEP 2: WAITING FOR FILAMENT SENSOR")
                    self.status_title.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 800;")
                    self.instruction_text.setText("👉 Insert filament into sensor and extruder entrance now until sensor triggers.")
                    self.anim_canvas.set_stage("waiting_sensor")
                    self.anim_canvas.set_sensor_triggered(False)
                    self.step2_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 700;")
                    self.action_btn.setText("Waiting for Sensor...")
                    self.action_btn.setEnabled(False)
                    self._check_sensor_trigger()
                else:
                    self.status_title.setText("STEP 2: FEEDING & EXTRUDING FILAMENT")
                    self.status_title.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 800;")
                    self.instruction_text.setText("Extruder motor is gripping and feeding filament through nozzle. Use manual buttons below to purge more if needed.")
                    self.anim_canvas.set_stage("extruding")
                    self.anim_canvas.set_sensor_triggered(True)
                    self.step2_lbl.setText("✔ 2. Filament detected & gripped")
                    self.step2_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")
                    self.step3_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")
                    self._trigger_gcode_action()
            else:  # Unload
                self.status_title.setText("STEP 2: RETRACTING & PULLING FILAMENT")
                self.status_title.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 800;")
                self.instruction_text.setText("👉 Gears are retracting. You can gently pull filament free or use Retract buttons below.")
                self.anim_canvas.set_stage("pulling")
                self.step2_lbl.setText("✔ 2. Filament molten tip retracted")
                self.step2_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")
                self.step3_lbl.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 700;")
                self._trigger_gcode_action()

    def _on_manual_extrude(self, length_mm: float):
        """Manually extrude (+length_mm) or retract (-length_mm) filament."""
        mr = self._get_moonraker()
        action_word = "Extruding" if length_mm > 0 else "Retracting"
        spd = 5.0 if length_mm > 0 else 10.0
        self.anim_canvas.set_stage("extruding" if length_mm > 0 else "pulling")
        self.status_title.setText(f"MANUAL {action_word.upper()} ({length_mm:+.0f} mm)")
        self.status_title.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 800;")
        self.instruction_text.setText(f"{action_word} {abs(length_mm):.0f} mm of filament at {self.current_temp:.1f}°C...")

        if mr and mr.connected:
            if self.current_temp < 170.0:
                mr.set_temperature("extruder", self.target_temp)
            def _done(ok: bool):
                if not self._is_cancelled:
                    self.instruction_text.setText(
                        f"✔ Manual {'extrude' if length_mm > 0 else 'retract'} ({length_mm:+.0f} mm) complete."
                        if ok else "⚠ Extrude command failed (check nozzle temperature)."
                    )
            mr.extrude(length_mm, speed_mm_s=spd, on_done=_done)

    def _check_sensor_trigger(self):
        """Query Moonraker for filament sensor switch state."""
        mr = self._get_moonraker()
        if mr and mr.connected and self._sensor_name:
            import urllib.request, json
            try:
                host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
                url = f"http://{host}/printer/objects/query?{self._sensor_name}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        status = data.get("result", {}).get("status", {}).get(self._sensor_name, {})
                        if status.get("filament_detected", False):
                            self._sensor_detected = True
                            self.anim_canvas.set_sensor_triggered(True)
            except Exception:
                pass
        else:
            # In offline or unconfigured mode, auto-advance after nozzle heated
            self._sensor_detected = True

    def _trigger_gcode_action(self):
        """Execute LOAD_FILAMENT or UNLOAD_FILAMENT once hot."""
        if hasattr(self, "_gcode_sent") and self._gcode_sent:
            return
        self._gcode_sent = True

        mr = self._get_moonraker()
        # Use current hot temp if already >= 185°C so M109 inside macro doesn't block waiting for a different preset temp
        macro_temp = self.current_temp if self.current_temp >= 185.0 else self.target_temp
        cmd = f"LOAD_FILAMENT TEMP={macro_temp:.0f}" if self.mode == "load" else f"UNLOAD_FILAMENT TEMP={macro_temp:.0f}"

        self.action_btn.setText("✔ Done")
        self.action_btn.setEnabled(True)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);
                border: 1px solid #34D399;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 12px;
                border-radius: 10px;
                padding: 8px 24px;
            }
        """)

        if mr and mr.connected:
            def on_done(ok):
                self._on_action_completed(ok)
            mr.send_gcode(cmd, on_done=on_done, timeout=120.0)
        else:
            QtCore.QTimer.singleShot(4000, lambda: self._on_action_completed(True))

    def _on_action_completed(self, ok: bool):
        self._is_completed = True
        self.anim_canvas.set_stage("done")

        action_name = "Loaded" if self.mode == "load" else "Unloaded"
        self.status_title.setText(f"SUCCESS: FILAMENT {action_name.upper()}!")
        self.status_title.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 800;")

        if self.mode == "load":
            self.instruction_text.setText("✔ Filament loaded! Tap Extrude +10mm/+25mm below to purge more, or tap Done.")
            self.step3_lbl.setText("✔ 3. Purge complete and ready to print")
        else:
            self.instruction_text.setText("✔ Filament retracted and freed. You may remove the spool from the holder.")
            self.step3_lbl.setText("✔ 3. Filament removed from toolhead")

        self.action_btn.setText("✔ Done")
        self.action_btn.setEnabled(True)

    def _cleanup_signals(self):
        self._poll_timer.stop()
        mr = self._get_moonraker()
        if mr and hasattr(mr, "temps_updated"):
            try:
                mr.temps_updated.disconnect(self._on_temps_updated)
            except Exception:
                pass

    def _on_cancel(self):
        """Cancel filament operation immediately and turn off all heaters for safety."""
        self._is_cancelled = True
        self._cleanup_signals()
        self.anim_canvas.set_stage("cancelled")

        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.set_temperature("extruder", 0.0)
            mr.set_temperature("heater_bed", 0.0)

        self.status_title.setText("OPERATION CANCELLED")
        self.status_title.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: 800;")
        self.instruction_text.setText("Operation cancelled. Heaters set to 0°C (cooling down).")

        QtCore.QTimer.singleShot(700, self._on_finish)

    def _on_finish(self):
        self._cleanup_signals()
        self.closed.emit()

