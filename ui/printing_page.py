"""Active 3D printing screen.

Displays live print progress, large gcode thumbnail, elapsed / remaining time,
temperatures, Fine Tune button (baby stepping, temps, speed/flow/fan),
and completion actions (Return to Home, Save Z-offset).
"""

from datetime import datetime, timedelta
from typing import Optional

from .qt import QtWidgets, QtCore, QtGui, Qt, Signal
from . import icons
from .thumbnail_helper import load_thumbnail_async, get_default_thumbnail
from .fine_tune_dialog import FineTuneOverlay


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def format_hms(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "--:--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class CancelConfirmOverlay(QtWidgets.QFrame):
    """Touch confirmation before aborting a live print."""
    confirmed = Signal()
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.setObjectName("CancelOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#CancelOverlay { background: rgba(5, 10, 20, 0.85); }")
        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QtWidgets.QFrame(self)
        card.setObjectName("CancelCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            QFrame#CancelCard {{
                background: #0F172A;
                border: 2px solid #EF4444;
                border-radius: {_s(14, scale)}px;
            }}
        """)
        c_lay = QtWidgets.QVBoxLayout(card)
        c_lay.setContentsMargins(_s(24, scale), _s(18, scale), _s(24, scale), _s(18, scale))
        c_lay.setSpacing(_s(12, scale))
        c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        t = QtWidgets.QLabel("CANCEL ACTIVE PRINT?")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(f"color: #EF4444; font-size: {_s(16, scale)}px; font-weight: 900; letter-spacing: 0.5px;")
        c_lay.addWidget(t)

        msg = QtWidgets.QLabel("Are you sure you want to cancel and stop this print job?")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color: #CBD5E1; font-size: {_s(12, scale)}px;")
        c_lay.addWidget(msg)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(_s(12, scale))

        btn_no = QtWidgets.QPushButton("Keep Printing")
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setFixedHeight(_s(42, scale))
        btn_no.setStyleSheet(f"""
            QPushButton {{
                background: #334155;
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: {_s(8, scale)}px;
                font-size: {_s(12, scale)}px;
                font-weight: 800;
                padding: 0 {_s(14, scale)}px;
            }}
            QPushButton:hover {{ background: #475569; }}
            QPushButton:pressed {{ background: #1E293B; }}
        """)
        btn_no.clicked.connect(self.close)

        btn_yes = QtWidgets.QPushButton("Yes, Cancel Print")
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes.setFixedHeight(_s(42, scale))
        btn_yes.setStyleSheet(f"""
            QPushButton {{
                background: #EF4444;
                color: #FFFFFF;
                border: 1px solid #DC2626;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(12, scale)}px;
                font-weight: 900;
                padding: 0 {_s(14, scale)}px;
            }}
            QPushButton:hover {{ background: #DC2626; }}
            QPushButton:pressed {{ background: #B91C1C; }}
        """)
        btn_yes.clicked.connect(self._on_confirm)

        btn_row.addWidget(btn_no, 1)
        btn_row.addWidget(btn_yes, 1)
        c_lay.addLayout(btn_row)

        card.setFixedWidth(_s(420, scale))
        outer.addWidget(card)

    def _on_confirm(self):
        self.confirmed.emit()
        self.close()

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()


class PrintingPage(QtWidgets.QWidget):
    """Full-featured screen displaying live print status, metrics, tuning, and completion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PrintingPage")
        self._scale = 1.0

        self._current_filename = ""
        self._print_state = "standby"
        self._total_duration = 0.0
        self._print_duration = 0.0
        self._progress = 0.0
        self._estimated_total = 0.0

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 12)
        main_layout.setSpacing(14)

        # =========================================================================
        # Left Panel: Large Thumbnail & File Info
        # =========================================================================
        self.left_card = QtWidgets.QFrame()
        self.left_card.setObjectName("ModelCard")
        self.left_card.setStyleSheet("""
            QFrame#ModelCard {
                background: #111827;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        left_layout = QtWidgets.QVBoxLayout(self.left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Big Thumbnail image
        self.thumb_lbl = QtWidgets.QLabel()
        self.thumb_lbl.setFixedSize(200, 200)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet("""
            background: #1E293B;
            border: 1.5px solid rgba(0, 229, 255, 0.25);
            border-radius: 10px;
        """)
        self.thumb_lbl.setPixmap(get_default_thumbnail(130))
        left_layout.addWidget(self.thumb_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        # File name
        self.filename_lbl = QtWidgets.QLabel("No Active Print")
        self.filename_lbl.setWordWrap(True)
        self.filename_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_lbl.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 800;")
        left_layout.addWidget(self.filename_lbl)

        # Layer & Height tag
        self.layer_lbl = QtWidgets.QLabel("Layer: -- / --")
        self.layer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layer_lbl.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 800;")
        left_layout.addWidget(self.layer_lbl)

        left_layout.addStretch(1)
        main_layout.addWidget(self.left_card, 0)
        self.left_card.setFixedWidth(240)

        # =========================================================================
        # Right Panel: Progress, Times, Temps & Actions
        # =========================================================================
        self.right_card = QtWidgets.QFrame()
        self.right_card.setObjectName("MetricsCard")
        self.right_card.setStyleSheet("""
            QFrame#MetricsCard {
                background: #111827;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        right_layout = QtWidgets.QVBoxLayout(self.right_card)
        right_layout.setContentsMargins(14, 12, 14, 12)
        right_layout.setSpacing(10)

        # Top Status Badge Row
        status_row = QtWidgets.QHBoxLayout()
        self.status_pill = QtWidgets.QLabel("STANDBY")
        self.status_pill.setStyleSheet("""
            color: #38BDF8; background: rgba(56, 189, 248, 0.15);
            border: 1px solid rgba(56, 189, 248, 0.4);
            border-radius: 6px; font-size: 11px; font-weight: 800; padding: 2px 8px;
        """)
        status_row.addWidget(self.status_pill)
        status_row.addStretch(1)

        self.babystep_lbl = QtWidgets.QLabel("Z-Offset: +0.000 mm")
        self.babystep_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700; font-family: monospace;")
        status_row.addWidget(self.babystep_lbl)
        right_layout.addLayout(status_row)

        # Large Progress Row: Percentage & Progress Bar
        prog_row = QtWidgets.QHBoxLayout()
        self.pct_lbl = QtWidgets.QLabel("0%")
        self.pct_lbl.setStyleSheet("color: #00E5FF; font-size: 26px; font-weight: 900; letter-spacing: -0.5px;")
        prog_row.addWidget(self.pct_lbl)
        prog_row.addSpacing(10)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setObjectName("PrintProgressBar")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(18)
        prog_row.addWidget(self.progress_bar, 1)
        right_layout.addLayout(prog_row)

        # Time Metrics (3 Columns: Elapsed, Remaining, ETA)
        time_grid = QtWidgets.QGridLayout()
        time_grid.setHorizontalSpacing(10)

        # Elapsed
        el_card = QtWidgets.QFrame()
        el_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 4px;")
        el_lay = QtWidgets.QVBoxLayout(el_card)
        el_lay.setContentsMargins(6, 4, 6, 4)
        el_lay.setSpacing(1)
        el_t = QtWidgets.QLabel("ELAPSED")
        el_t.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800;")
        self.el_val = QtWidgets.QLabel("00:00:00")
        self.el_val.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 900; font-family: monospace;")
        el_lay.addWidget(el_t)
        el_lay.addWidget(self.el_val)
        time_grid.addWidget(el_card, 0, 0)

        # Remaining
        rem_card = QtWidgets.QFrame()
        rem_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 4px;")
        rem_lay = QtWidgets.QVBoxLayout(rem_card)
        rem_lay.setContentsMargins(6, 4, 6, 4)
        rem_lay.setSpacing(1)
        rem_t = QtWidgets.QLabel("REMAINING")
        rem_t.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800;")
        self.rem_val = QtWidgets.QLabel("--:--:--")
        self.rem_val.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 900; font-family: monospace;")
        rem_lay.addWidget(rem_t)
        rem_lay.addWidget(self.rem_val)
        time_grid.addWidget(rem_card, 0, 1)

        # ETA
        eta_card = QtWidgets.QFrame()
        eta_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 4px;")
        eta_lay = QtWidgets.QVBoxLayout(eta_card)
        eta_lay.setContentsMargins(6, 4, 6, 4)
        eta_lay.setSpacing(1)
        eta_t = QtWidgets.QLabel("EST. FINISH (ETA)")
        eta_t.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800;")
        self.eta_val = QtWidgets.QLabel("--:--")
        self.eta_val.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 900; font-family: monospace;")
        eta_lay.addWidget(eta_t)
        eta_lay.addWidget(self.eta_val)
        time_grid.addWidget(eta_card, 0, 2)

        right_layout.addLayout(time_grid)

        # Live Temperatures & Fan Info Strip
        info_strip = QtWidgets.QHBoxLayout()
        info_strip.setSpacing(12)

        self.noz_lbl = QtWidgets.QLabel("Nozzle: 0.0°C / 0°C")
        self.noz_lbl.setStyleSheet("color: #FF9A3C; font-size: 11px; font-weight: 700;")
        info_strip.addWidget(self.noz_lbl)

        self.bed_lbl = QtWidgets.QLabel("Bed: 0.0°C / 0°C")
        self.bed_lbl.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 700;")
        info_strip.addWidget(self.bed_lbl)

        info_strip.addStretch(1)

        self.rates_lbl = QtWidgets.QLabel("Spd: 100%  •  Flow: 100%")
        self.rates_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        info_strip.addWidget(self.rates_lbl)
        right_layout.addLayout(info_strip)

        right_layout.addStretch(1)

        # =========================================================================
        # Dynamic Action Buttons Area: Active Print vs Complete
        # =========================================================================
        self.actions_stack = QtWidgets.QStackedWidget()

        # Page 0: Active Printing Actions (Pause, Fine Tune, Cancel)
        self.active_actions = QtWidgets.QWidget()
        act_lay = QtWidgets.QHBoxLayout(self.active_actions)
        act_lay.setContentsMargins(0, 0, 0, 0)
        act_lay.setSpacing(10)

        # Pause / Resume Button
        self.btn_pause = QtWidgets.QPushButton(" ⏸  PAUSE ")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setFixedHeight(42)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background: rgba(251, 191, 36, 0.15);
                color: #FBBF24;
                border: 1px solid rgba(251, 191, 36, 0.4);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(251, 191, 36, 0.3); }
        """)
        self.btn_pause.clicked.connect(self._on_pause_toggle)
        act_lay.addWidget(self.btn_pause, 1)

        # Fine Tune Button (Z babystepping, temps, speed/flow/fan)
        self.btn_tune = QtWidgets.QPushButton(" ⚙  FINE TUNE ")
        self.btn_tune.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tune.setFixedHeight(42)
        self.btn_tune.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #3B82F6);
                color: #0F172A;
                border: 1px solid #00E5FF;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 900;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { background: #38BDF8; }
        """)
        self.btn_tune.clicked.connect(self._open_fine_tune)
        act_lay.addWidget(self.btn_tune, 1)

        # Cancel Print Button
        self.btn_cancel = QtWidgets.QPushButton(" ✕  CANCEL ")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.18);
                color: #FCA5A5;
                border: 1px solid rgba(239, 68, 68, 0.45);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.35); color: #FFFFFF; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        act_lay.addWidget(self.btn_cancel, 1)

        self.actions_stack.addWidget(self.active_actions)

        # Page 1: Print Complete Actions (Return to Home, Save Z-offset)
        self.complete_actions = QtWidgets.QWidget()
        comp_lay = QtWidgets.QVBoxLayout(self.complete_actions)
        comp_lay.setContentsMargins(0, 0, 0, 0)
        comp_lay.setSpacing(8)

        # Congratulations header
        self.comp_banner = QtWidgets.QLabel("🎉  Print Finished Successfully!")
        self.comp_banner.setStyleSheet("color: #34D399; font-size: 14px; font-weight: 900;")
        comp_lay.addWidget(self.comp_banner)

        comp_btn_row = QtWidgets.QHBoxLayout()
        comp_btn_row.setSpacing(10)

        # Save Z-Offset button
        self.btn_save_z = QtWidgets.QPushButton(" 💾  SAVE Z-OFFSET TO CONFIG ")
        self.btn_save_z.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_z.setFixedHeight(42)
        self.btn_save_z.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.18);
                color: #34D399;
                border: 1px solid #10B981;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 900;
            }
            QPushButton:hover { background: rgba(16, 185, 129, 0.35); }
        """)
        self.btn_save_z.clicked.connect(self._on_save_z_offset)
        comp_btn_row.addWidget(self.btn_save_z, 1)

        # Return to Home button
        self.btn_home = QtWidgets.QPushButton(" 🏠  RETURN TO HOME ")
        self.btn_home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home.setFixedHeight(42)
        self.btn_home.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #3B82F6);
                color: #0F172A;
                border: 1px solid #00E5FF;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 900;
            }
            QPushButton:hover { background: #38BDF8; }
        """)
        self.btn_home.clicked.connect(self._on_return_home)
        comp_btn_row.addWidget(self.btn_home, 1)

        comp_lay.addLayout(comp_btn_row)
        self.actions_stack.addWidget(self.complete_actions)

        right_layout.addWidget(self.actions_stack)
        main_layout.addWidget(self.right_card, 1)

    def prepare_print(self, file_info: dict):
        """Immediately preview the selected gcode file and show starting state."""
        fn = file_info.get("filename") or file_info.get("full_path") or ""
        self._current_filename = fn
        self.filename_lbl.setText(fn)

        self._print_state = "starting"
        self.status_pill.setText("● STARTING")
        self.status_pill.setStyleSheet("""
            color: #F59E0B; background: rgba(245, 158, 11, 0.2);
            border: 1px solid rgba(245, 158, 11, 0.5); border-radius: 6px; font-weight: 800; font-size: 11px; padding: 2px 8px;
        """)

        self.progress_bar.setValue(0)
        self.pct_lbl.setText("0%")
        self.el_val.setText("00:00:00")

        est = file_info.get("estimated_time") or 0.0
        self._estimated_total = float(est)
        self.rem_val.setText(format_hms(est))
        self.eta_val.setText("--:--")
        self.layer_lbl.setText("Starting print...")

        self.actions_stack.setCurrentIndex(0)
        self.btn_pause.setText(" ⏸  PAUSE ")

        # Load large thumbnail immediately
        mr = getattr(self, "moonraker", None) or getattr(self.window(), "moonraker", None)
        host = (mr.active_host or mr.hosts[0]) if (mr and mr.hosts) else "127.0.0.1:7125"

        thumbs = file_info.get("thumbnails", [])
        rel_p = thumbs[0].get("relative_path") if thumbs else None
        dir_p = file_info.get("dir_path", "gcodes")

        load_thumbnail_async(
            host=host,
            dir_path=dir_p,
            thumb_rel_path=rel_p,
            filename=fn,
            target_size=_s(190, self._scale),
            on_loaded=self._set_thumb
        )

    def update_print_stats(self, st: dict):
        """Called whenever Moonraker emits print_stats_updated."""
        state = st.get("state", "standby")
        fn = st.get("filename", "")

        # If user just initiated a print and Klipper is preparing, keep the preview active
        if self._print_state == "starting" and state == "standby" and not fn:
            return

        self._print_state = state
        self._progress = float(st.get("progress", 0.0))
        self._print_duration = float(st.get("print_duration", 0.0))
        self._total_duration = float(st.get("total_duration", 0.0))

        if fn and fn != self._current_filename:
            self._current_filename = fn
            self.filename_lbl.setText(fn)
            self._fetch_print_metadata(fn)

        # Update Progress Bar & Percentage
        pct = int(self._progress * 100)
        self.pct_lbl.setText(f"{pct}%")
        self.progress_bar.setValue(int(self._progress * 1000))

        # Times
        self.el_val.setText(format_hms(self._print_duration))
        if self._progress > 0.01 and self._print_duration > 10:
            total_est = self._print_duration / self._progress
            rem = max(0.0, total_est - self._print_duration)
            self.rem_val.setText(format_hms(rem))
            eta_time = datetime.now() + timedelta(seconds=rem)
            self.eta_val.setText(eta_time.strftime("%H:%M"))
        elif self._estimated_total > 0:
            rem = max(0.0, self._estimated_total - self._print_duration)
            self.rem_val.setText(format_hms(rem))
            eta_time = datetime.now() + timedelta(seconds=rem)
            self.eta_val.setText(eta_time.strftime("%H:%M"))
        else:
            self.rem_val.setText("--:--:--")
            self.eta_val.setText("--:--")

        # Layers
        cur_l = st.get("current_layer")
        tot_l = st.get("total_layer")
        z_pos = st.get("z_pos", 0.0)
        if cur_l is not None and tot_l is not None:
            self.layer_lbl.setText(f"Layer: {cur_l} / {tot_l}  (Z: {z_pos:.2f} mm)")
        else:
            self.layer_lbl.setText(f"Z Height: {z_pos:.2f} mm")

        # Temps
        n_cur = st.get("nozzle_cur", 0.0)
        n_tgt = st.get("nozzle_tgt", 0.0)
        b_cur = st.get("bed_cur", 0.0)
        b_tgt = st.get("bed_tgt", 0.0)
        self.noz_lbl.setText(f"Nozzle: {n_cur:.1f}°C / {n_tgt:.0f}°C")
        self.bed_lbl.setText(f"Bed: {b_cur:.1f}°C / {b_tgt:.0f}°C")

        # Speeds & Babystep
        spd = round(float(st.get("speed_factor", 1.0)) * 100)
        flow = round(float(st.get("extrude_factor", 1.0)) * 100)
        fan = round(float(st.get("fan_speed", 0.0)) * 100)
        self.rates_lbl.setText(f"Spd: {spd}% • Flow: {flow}% • Fan: {fan}%")

        z_off = float(st.get("z_offset", 0.0))
        self.babystep_lbl.setText(f"Z-Offset: {z_off:+.3f} mm")

        # State badge & action button switching
        if state == "printing":
            self.status_pill.setText("● PRINTING")
            self.status_pill.setStyleSheet("""
                color: #34D399; background: rgba(16, 185, 129, 0.18);
                border: 1px solid #10B981; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 2px 8px;
            """)
            self.btn_pause.setText(" ⏸  PAUSE ")
            self.actions_stack.setCurrentIndex(0)
        elif state == "paused":
            self.status_pill.setText("⏸ PAUSED")
            self.status_pill.setStyleSheet("""
                color: #FBBF24; background: rgba(251, 191, 36, 0.18);
                border: 1px solid #F59E0B; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 2px 8px;
            """)
            self.btn_pause.setText(" ▶  RESUME ")
            self.actions_stack.setCurrentIndex(0)
        elif state == "complete":
            self.status_pill.setText("🎉 COMPLETE")
            self.status_pill.setStyleSheet("""
                color: #00E5FF; background: rgba(0, 229, 255, 0.18);
                border: 1px solid #00E5FF; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 2px 8px;
            """)
            self.actions_stack.setCurrentIndex(1)
        else:
            self.status_pill.setText(state.upper())
            self.status_pill.setStyleSheet("""
                color: #94A3B8; background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 6px; font-weight: 700; font-size: 11px; padding: 2px 8px;
            """)
            self.actions_stack.setCurrentIndex(0)

    def _fetch_print_metadata(self, filename: str):
        mr = getattr(self.window(), "moonraker", None)
        if not mr:
            return
        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        # Immediately kick off async thumbnail load
        load_thumbnail_async(
            host=host,
            dir_path="gcodes",
            thumb_rel_path=None,
            filename=filename,
            target_size=_s(190, self._scale),
            on_loaded=self._set_thumb
        )

        def _on_meta(m: dict):
            est = m.get("estimated_time")
            if est:
                self._estimated_total = float(est)
            thumbs = m.get("thumbnails", [])
            if thumbs:
                best = max(thumbs, key=lambda t: t.get("width", 0) * t.get("height", 0))
                rel_p = best.get("relative_path")
                if rel_p:
                    load_thumbnail_async(
                        host=host,
                        dir_path="gcodes",
                        thumb_rel_path=rel_p,
                        filename=filename,
                        target_size=_s(190, self._scale),
                        on_loaded=self._set_thumb
                    )

        mr.get_file_metadata(filename, on_done=_on_meta)

    def _set_thumb(self, pm: QtGui.QPixmap):
        if not pm.isNull():
            sz = _s(190, self._scale)
            scaled = pm.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumb_lbl.setPixmap(scaled)

    def _on_pause_toggle(self):
        mr = getattr(self.window(), "moonraker", None)
        if not mr:
            return
        if self._print_state == "printing":
            mr.pause_print()
        elif self._print_state == "paused":
            mr.resume_print()

    def _open_fine_tune(self):
        main_win = self.window()
        overlay = FineTuneOverlay(parent=main_win, scale=self._scale)
        overlay.show()
        overlay.raise_()

    def _on_cancel_clicked(self):
        main_win = self.window()
        overlay = CancelConfirmOverlay(scale=self._scale, parent=main_win)
        overlay.confirmed.connect(self._do_cancel)
        overlay.show()
        overlay.raise_()

    def _do_cancel(self):
        mr = getattr(self.window(), "moonraker", None)
        if mr:
            mr.cancel_print()

    def _on_save_z_offset(self):
        mr = getattr(self.window(), "moonraker", None)
        if mr:
            self.btn_save_z.setText(" SAVING TO CONFIG... ")
            self.btn_save_z.setEnabled(False)
            def _done(ok):
                self.btn_save_z.setText(" ✅ Z-OFFSET SAVED! ")
            mr.save_z_offset(on_done=_done)

    def _on_return_home(self):
        main_win = self.window()
        if hasattr(main_win, "show_page"):
            main_win.show_page("home")

    def apply_scale(self, s: float):
        self._scale = s
        self.left_card.setFixedWidth(_s(240, s))
        sz = _s(190, s)
        self.thumb_lbl.setFixedSize(sz, sz)

