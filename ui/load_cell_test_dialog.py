"""Load Cell Weight Test Dialog.

Provides an interactive touch modal to test and read the weight attached to the
load cell probe using LOAD_CELL_READ, alongside live streaming sensor force.
"""

import json
import re
import threading
import urllib.request
from typing import Optional

from . import icons
from .qt import QtWidgets, QtCore, Qt, Signal


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class LoadCellWeightTestDialog(QtWidgets.QFrame):
    """Full-screen in-window view to test and read weight attached to the load cell probe."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._live_grams = 0.0
        self._last_reading = "---.- g"
        self._counts_per_gram = 0.0
        self._tare_counts = 0
        self._sample_rate = 0
        self._is_calibrated = False
        self._closed = False

        self.setObjectName("LoadCellTestDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        # Outer layout
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Dialog Card container
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.card.setStyleSheet("""
            QFrame#DialogCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #141C2E, stop:1 #0B0F19);
                border: 1px solid rgba(0, 229, 255, 120);
                border-radius: 14px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setSpacing(_s(8, scale))

        # --- Header ---
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(_s(8, scale))

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.icon_label)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)

        self.title_lbl = QtWidgets.QLabel("LOAD CELL WEIGHT TEST")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        title_col.addWidget(self.title_lbl)
        header_layout.addLayout(title_col, 1)

        self.close_x = QtWidgets.QPushButton("\u2715")
        self.close_x.setObjectName("DialogCloseX")
        self.close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_x.setStyleSheet("""
            QPushButton#DialogCloseX {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 13px;
                color: #94A3B8;
                font-size: 13px;
                font-weight: 700;
                min-width: 26px;
                min-height: 26px;
                max-width: 26px;
                max-height: 26px;
            }
            QPushButton#DialogCloseX:hover {
                background: rgba(239, 68, 68, 0.3);
                border-color: #EF4444;
                color: #FFFFFF;
            }
        """)
        self.close_x.clicked.connect(self.reject)
        header_layout.addWidget(self.close_x)

        card_layout.addLayout(header_layout)

        # --- Section 1: Live Probe Force Card ---
        live_card = QtWidgets.QFrame()
        live_card.setObjectName("LiveForceBox")
        live_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        live_card.setStyleSheet("""
            QFrame#LiveForceBox {
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 8px;
            }
        """)
        lc_vbox = QtWidgets.QVBoxLayout(live_card)
        lc_vbox.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        lc_vbox.setSpacing(2)

        live_hdr_row = QtWidgets.QHBoxLayout()
        live_title = QtWidgets.QLabel("LIVE PROBE FORCE:")
        live_title.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        live_hdr_row.addWidget(live_title)

        live_hdr_row.addStretch(1)
        lc_vbox.addLayout(live_hdr_row)

        live_val_row = QtWidgets.QHBoxLayout()
        self.live_grams_lbl = QtWidgets.QLabel("+0.0 g")
        self.live_grams_lbl.setStyleSheet("""
            color: #34D399;
            font-size: 26px;
            font-weight: 900;
            font-family: 'Consolas', monospace;
        """)
        live_val_row.addWidget(self.live_grams_lbl)

        live_val_row.addSpacing(8)

        live_sub_col = QtWidgets.QVBoxLayout()
        live_sub_col.setSpacing(1)
        self.live_status_txt = QtWidgets.QLabel("Real-time load cell probe force")
        self.live_status_txt.setStyleSheet("color: #94A3B8; font-size: 10px;")
        live_sub_col.addWidget(self.live_status_txt)

        self.live_stream_badge = QtWidgets.QLabel("\u25CF LIVE STREAMING")
        self.live_stream_badge.setStyleSheet("color: #10B981; font-size: 9px; font-weight: 800; font-family: 'Consolas', monospace;")
        live_sub_col.addWidget(self.live_stream_badge)
        live_val_row.addLayout(live_sub_col)

        live_val_row.addStretch(1)

        self.tare_btn = QtWidgets.QPushButton("\u2316  Tare Zero")
        self.tare_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tare_btn.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.6);
                border-radius: 6px;
                color: #7DD3FC;
                font-size: 11px;
                font-weight: 800;
                padding: 4px 10px;
                min-height: 26px;
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.3);
                border-color: #38BDF8;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background: #0284C7;
                color: #FFFFFF;
            }
        """)
        self.tare_btn.clicked.connect(self._on_tare)
        live_val_row.addWidget(self.tare_btn)

        lc_vbox.addLayout(live_val_row)
        card_layout.addWidget(live_card)

        # --- Section 2: Attached Weight Snapshot Card ---
        snap_card = QtWidgets.QFrame()
        snap_card.setObjectName("SnapshotBox")
        snap_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        snap_card.setStyleSheet("""
            QFrame#SnapshotBox {
                background: rgba(0, 229, 255, 0.08);
                border: 1px solid rgba(0, 229, 255, 0.5);
                border-left: 4px solid #00E5FF;
                border-radius: 8px;
            }
        """)
        sn_vbox = QtWidgets.QVBoxLayout(snap_card)
        sn_vbox.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        sn_vbox.setSpacing(3)

        sn_hdr = QtWidgets.QLabel("ATTACHED WEIGHT READING")
        sn_hdr.setStyleSheet("color: #00E5FF; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        sn_vbox.addWidget(sn_hdr)

        sn_val_row = QtWidgets.QHBoxLayout()
        self.snapshot_val_lbl = QtWidgets.QLabel("---.- g")
        self.snapshot_val_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-size: 28px;
            font-weight: 900;
            font-family: 'Consolas', monospace;
        """)
        sn_val_row.addWidget(self.snapshot_val_lbl)

        sn_val_row.addSpacing(10)

        sn_info_col = QtWidgets.QVBoxLayout()
        sn_info_col.setSpacing(1)
        self.snapshot_note_lbl = QtWidgets.QLabel("Tap button below to capture weight attached to probe")
        self.snapshot_note_lbl.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        sn_info_col.addWidget(self.snapshot_note_lbl)

        self.snapshot_sub_lbl = QtWidgets.QLabel("Performs a precision static read cycle on the load cell sensor.")
        self.snapshot_sub_lbl.setStyleSheet("color: #94A3B8; font-size: 10px;")
        sn_info_col.addWidget(self.snapshot_sub_lbl)
        sn_val_row.addLayout(sn_info_col)

        sn_val_row.addStretch(1)
        sn_vbox.addLayout(sn_val_row)

        # Primary Action Button: Read Attached Weight
        self.read_btn = QtWidgets.QPushButton("\u2696  Read Attached Weight")
        self.read_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.read_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284C7, stop:1 #00E5FF);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 7px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 800;
                min-height: 32px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0369A1, stop:1 #38BDF8);
                border-color: #FFFFFF;
            }
            QPushButton:pressed {
                background: #0284C7;
            }
            QPushButton:disabled {
                background: rgba(30, 41, 59, 0.6);
                border-color: rgba(255, 255, 255, 0.1);
                color: #64748B;
            }
        """)
        self.read_btn.clicked.connect(self._on_read_weight)
        sn_vbox.addWidget(self.read_btn)

        card_layout.addWidget(snap_card)

        # --- Section 3: Diagnostic Telemetry & Status Bar ---
        self.meta_lbl = QtWidgets.QLabel("Reading load cell telemetry...")
        self.meta_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-family: 'Consolas', monospace;")
        card_layout.addWidget(self.meta_lbl)

        # Bottom Bar: Status note + Close button
        bot_row = QtWidgets.QHBoxLayout()
        self.status_lbl = QtWidgets.QLabel("Ready to test weight.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        bot_row.addWidget(self.status_lbl, 1)

        self.close_btn = QtWidgets.QPushButton("Close")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(30, 41, 59, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 6px;
                color: #CBD5E1;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 16px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: rgba(51, 65, 85, 0.9);
                border-color: rgba(255, 255, 255, 0.35);
                color: #FFFFFF;
            }
        """)
        self.close_btn.clicked.connect(self.accept)
        bot_row.addWidget(self.close_btn)

        card_layout.addLayout(bot_row)
        outer_layout.addWidget(self.card)

        # Timer to poll real-time status and sensor force while open
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(250)
        self._poll_timer.timeout.connect(self._poll_sensor_force)
        self._poll_timer.start()

        self.apply_scale(scale)
        self._poll_sensor_force()

        # Connect to Moonraker real-time stream when ready
        QtCore.QTimer.singleShot(60, self._connect_stream)

    def _get_moonraker(self):
        """Traverse parent hierarchy or window to find live MoonrakerClient."""
        p = self.parent()
        while p:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        win = self.window()
        mr = getattr(win, "moonraker", None)
        if mr:
            return mr
        return None

    def _connect_stream(self):
        mr = self._get_moonraker()
        if mr and hasattr(mr, "load_cell_updated"):
            try:
                mr.load_cell_updated.connect(self.update_live_grams)
            except Exception:
                pass

    def _poll_sensor_force(self):
        """Polls force_g from Moonraker or local client."""
        mr = self._get_moonraker()
        if mr and mr.connected:
            host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _bg():
            if self._closed:
                return
            fg = None
            tare_val = None
            cpg_val = None
            rate_val = None
            is_cal = False
            try:
                url = f"http://{host}/printer/objects/query?load_cell_probe&load_cell&probe"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        status = data.get("result", {}).get("status", {})
                        lc = status.get("load_cell_probe") or status.get("load_cell") or status.get("probe") or {}
                        is_cal = bool(lc.get("is_calibrated", False))
                        if lc.get("force_g") is not None:
                            fg = float(lc["force_g"])
                        tc_raw = lc.get("tare_counts")
                        if tc_raw is None:
                            tc_raw = lc.get("reference_tare_counts")
                        if tc_raw is not None:
                            tare_val = int(tc_raw)
                        if lc.get("counts_per_gram") is not None:
                            cpg_val = float(lc["counts_per_gram"])
                        if lc.get("sample_rate") is not None:
                            rate_val = int(lc["sample_rate"])
            except Exception:
                pass

            def _apply():
                if self._closed:
                    return
                self._is_calibrated = is_cal
                if fg is not None:
                    self.update_live_grams(fg)
                elif not is_cal:
                    self.live_grams_lbl.setText("Uncalibrated")
                    self.live_grams_lbl.setStyleSheet("color: #F59E0B; font-size: 22px; font-weight: 900; font-family: 'Consolas', monospace;")
                if tare_val is not None:
                    self._tare_counts = tare_val
                if cpg_val is not None:
                    self._counts_per_gram = cpg_val
                if rate_val is not None:
                    self._sample_rate = rate_val
                tare_s = f"{self._tare_counts:,} counts" if self._tare_counts else "uncalibrated"
                cpg_s = f"{self._counts_per_gram:.1f} counts/g" if self._counts_per_gram > 0 else "uncalibrated"
                rate_s = f"{self._sample_rate} Hz" if self._sample_rate > 0 else "-- Hz"
                try:
                    self.meta_lbl.setText(f"Tare: {tare_s}  \u2022  {cpg_s}  \u2022  Sample Rate: {rate_s}")
                except RuntimeError:
                    pass

            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_apply)
            else:
                QtCore.QTimer.singleShot(0, _apply)

        threading.Thread(target=_bg, daemon=True).start()

    def update_live_grams(self, grams: float):
        if self._closed:
            return
        self._live_grams = grams
        sign = "+" if grams > 0 else ""
        try:
            self.live_grams_lbl.setText(f"{sign}{grams:.1f} g")
            if abs(grams) > 20.0:
                self.live_grams_lbl.setStyleSheet("color: #FBBF24; font-size: 26px; font-weight: 900; font-family: 'Consolas', monospace;")
            else:
                self.live_grams_lbl.setStyleSheet("color: #34D399; font-size: 26px; font-weight: 900; font-family: 'Consolas', monospace;")
        except RuntimeError:
            pass

    def _on_read_weight(self):
        self.read_btn.setEnabled(False)
        self.read_btn.setText("Reading attached weight...")
        self.status_lbl.setText("Reading attached weight...")
        mr = self._get_moonraker()

        if mr and mr.connected:
            mr.send_gcode("LOAD_CELL_READ", on_done=self._on_read_done)
        else:
            # Standalone simulation fallback
            QtCore.QTimer.singleShot(600, lambda: self._on_read_done(True, sim_val=100.0))

    def _on_read_done(self, ok: bool, sim_val: Optional[float] = None):
        self.read_btn.setEnabled(True)
        self.read_btn.setText("\u2696  Read Attached Weight")
        if not ok:
            self.status_lbl.setText("LOAD_CELL_READ command failed.")
            return

        if sim_val is not None:
            self.snapshot_val_lbl.setText(f"{sim_val:.1f} g")
            self.snapshot_note_lbl.setText(f"Attached Weight: {sim_val:.1f} g (Simulated)")
            self.status_lbl.setText("\u2713 Weight measurement captured successfully.")
            return

        # Fetch latest output from Moonraker gcode_store
        mr = self._get_moonraker()
        host = (mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")) if mr else "127.0.0.1:7125"

        def _bg():
            read_str = None
            pct_str = None
            try:
                url = f"http://{host}/server/gcode_store?count=8"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in reversed(data.get("result", {}).get("gcode_store", [])):
                            msg = item.get("message", "")
                            m = re.search(r"//\s*(-?[\d\.]+|---.-)\s*g(?:\s*\((-?[\d\.]+%?)\))?", msg)
                            if m:
                                read_str = (m.group(1) + " g") if m.group(1) != "---.-" else "Uncalibrated"
                                pct_str = m.group(2)
                                break
            except Exception:
                pass

            # Also query force_g
            force_val = None
            try:
                url_q = f"http://{host}/printer/objects/query?load_cell_probe"
                req_q = urllib.request.Request(url_q, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req_q, timeout=1.2) as resp:
                    if resp.status == 200:
                        data_q = json.loads(resp.read().decode("utf-8"))
                        lcp = data_q.get("result", {}).get("status", {}).get("load_cell_probe", {})
                        if lcp.get("force_g") is not None:
                            force_val = float(lcp["force_g"])
            except Exception:
                pass

            def _update():
                if self._closed:
                    return
                try:
                    if read_str:
                        disp = read_str
                        if pct_str:
                            disp += f" ({pct_str})" if read_str != "Uncalibrated" else f": {pct_str}"
                        self.snapshot_val_lbl.setText(disp)
                        self.snapshot_note_lbl.setText(f"Probe reading captured: {disp}")
                    elif force_val is not None:
                        self.snapshot_val_lbl.setText(f"{force_val:.1f} g")
                        self.snapshot_note_lbl.setText(f"Probe force: {force_val:.1f} g")
                    self.status_lbl.setText("\u2713 Attached weight reading captured.")
                except RuntimeError:
                    pass

            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_update)
            else:
                QtCore.QTimer.singleShot(0, _update)

        threading.Thread(target=_bg, daemon=True).start()

    def _on_tare(self):
        self.tare_btn.setEnabled(False)
        self.tare_btn.setText("Taring zero...")
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.tare_load_cell(on_done=self._after_tare)
        else:
            QtCore.QTimer.singleShot(400, lambda: self._after_tare(True))

    def _after_tare(self, ok: bool):
        self.tare_btn.setEnabled(True)
        self.tare_btn.setText("\u2316  Tare Zero")
        self.status_lbl.setText("\u2713 Sensor zero point reset." if ok else "Tare command failed.")
        self._poll_sensor_force()
        mr = self._get_moonraker()
        if mr and hasattr(mr, "poll_now"):
            mr.poll_now()

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def accept(self):
        self._cleanup()
        self.closed.emit()

    def reject(self):
        self._cleanup()
        self.closed.emit()

    def close(self):
        self._cleanup()
        self.closed.emit()
        super().close()

    def _cleanup(self):
        self._closed = True
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        mr = self._get_moonraker()
        if mr and hasattr(mr, "load_cell_updated"):
            try:
                mr.load_cell_updated.disconnect(self.update_live_grams)
            except Exception:
                pass

    def apply_scale(self, s: float):
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("probe", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
