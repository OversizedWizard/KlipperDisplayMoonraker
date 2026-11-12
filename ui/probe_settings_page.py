"""Probe Speeds & Heights Screen.

Touch-friendly configuration screen to adjust probe descent speed, lift speed,
and retract clearance between probes without manually editing printer.cfg.
Values are saved locally for probing tests and can optionally be saved permanently
into printer.cfg.
"""

import json
import os
import re
import threading
import urllib.request

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal

DISPLAY_SETTINGS_PATH = os.path.expanduser("~/.klipper_display_settings.json")


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def load_probe_display_settings() -> dict:
    try:
        if os.path.exists(DISPLAY_SETTINGS_PATH):
            with open(DISPLAY_SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("probe_settings", {})
    except Exception:
        pass
    return {}


def save_probe_display_settings(p_cfg: dict):
    try:
        cur = {}
        if os.path.exists(DISPLAY_SETTINGS_PATH):
            with open(DISPLAY_SETTINGS_PATH, "r", encoding="utf-8") as f:
                cur = json.load(f)
        cur["probe_settings"] = p_cfg
        with open(DISPLAY_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=2)
    except Exception:
        pass


_BTN_PRIMARY = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #00E5FF);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 8px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 40px;
    padding: 4px 16px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #38BDF8);
    border-color: #FFFFFF;
}
QPushButton:pressed { background: #0284C7; }
QPushButton:disabled {
    background: rgba(30, 41, 59, 0.6);
    border-color: rgba(255, 255, 255, 0.1);
    color: #64748B;
}
"""

_BTN_SUCCESS = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10B981);
    border: 1px solid rgba(52, 211, 153, 0.5);
    border-radius: 8px;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 800;
    min-height: 40px;
    padding: 4px 16px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #34D399);
}
QPushButton:pressed { background: #059669; }
QPushButton:disabled { background: rgba(30, 41, 59, 0.6); color: #64748B; }
"""

_BTN_GHOST = """
QPushButton {
    background: rgba(30, 41, 59, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 7px;
    color: #CBD5E1;
    font-size: 12px;
    font-weight: 700;
    min-height: 38px;
    padding: 4px 12px;
}
QPushButton:hover {
    background: rgba(51, 65, 85, 0.95);
    border-color: rgba(255, 255, 255, 0.35);
    color: #FFFFFF;
}
QPushButton:pressed { background: #0284C7; color: #FFFFFF; }
QPushButton:disabled { color: #475569; }
"""

_LBL_HDR = "color: #94A3B8; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;"


class ProbeSettingsScreen(QtWidgets.QFrame):
    """Full-screen in-window view to inspect and adjust probe speeds and heights."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._probe_section = "load_cell_probe"
        self._cfg_probe_speed = 8.0
        self._cfg_lift_speed = 10.0
        self._cfg_retract_dist = 3.0

        saved = load_probe_display_settings()
        self._probe_speed = float(saved.get("probe_speed", self._cfg_probe_speed))
        self._lift_speed = float(saved.get("lift_speed", self._cfg_lift_speed))
        self._retract_dist = float(saved.get("sample_retract_dist", self._cfg_retract_dist))

        self._busy = False

        self.setObjectName("ProbeSettingsScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet("""
            QFrame#DialogCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141C2E, stop:1 #0B0F19);
                border: 1px solid rgba(0, 229, 255, 120);
                border-radius: 14px;
            }
            QLabel { border: none; background: transparent; }
        """)
        outer.addWidget(self.card)

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

        self.title_lbl = QtWidgets.QLabel("PROBE SPEEDS & HEIGHTS")
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;")
        title_col.addWidget(self.title_lbl)

        header_layout.addLayout(title_col, 1)

        self.section_badge = QtWidgets.QLabel("[LOAD_CELL_PROBE]")
        self.section_badge.setStyleSheet("""
            color: #00E5FF; font-size: 10px; font-weight: 800;
            font-family: 'Consolas', monospace;
            background: rgba(0, 229, 255, 0.15); border: 1px solid rgba(0, 229, 255, 0.4);
            border-radius: 4px; padding: 2px 8px;
        """)
        header_layout.addWidget(self.section_badge)

        self.close_x = QtWidgets.QPushButton("✕")
        self.close_x.setObjectName("DialogCloseX")
        self.close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_x.setFixedSize(28, 28)
        self.close_x.setStyleSheet("""
            QPushButton#DialogCloseX {
                background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px; color: #94A3B8; font-size: 13px; font-weight: 700;
            }
            QPushButton#DialogCloseX:hover {
                background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF;
            }
        """)
        self.close_x.clicked.connect(self.accept)
        header_layout.addWidget(self.close_x)

        card_layout.addLayout(header_layout)

        # --- Body: 3 Big Control Cards ---
        body = QtWidgets.QVBoxLayout()
        body.setSpacing(_s(8, scale))

        self.val_labels = {}
        self.preset_btn_groups = {}

        # Row 1: Probe Speed Card
        body.addWidget(self._create_param_card(
            key="probe_speed",
            title="PROBE DESCENT SPEED",
            desc="Speed nozzle/probe descends toward bed surface to detect touch.",
            unit="mm/s",
            color="#00E5FF",
            current_val=self._probe_speed,
            step=0.5,
            mn=1.0,
            mx=25.0,
            presets=[2.0, 3.0, 4.0, 6.0, 8.0]
        ))

        # Row 2: Lift Speed Card
        body.addWidget(self._create_param_card(
            key="lift_speed",
            title="LIFT SPEED (RETRACT)",
            desc="Speed nozzle raises away after probe contact.",
            unit="mm/s",
            color="#FBBF24",
            current_val=self._lift_speed,
            step=1.0,
            mn=2.0,
            mx=40.0,
            presets=[5.0, 8.0, 10.0, 15.0]
        ))

        # Row 3: Retract Height Card
        body.addWidget(self._create_param_card(
            key="sample_retract_dist",
            title="RETRACT HEIGHT (CLEARANCE)",
            desc="Height toolhead lifts between consecutive probe samples.",
            unit="mm",
            color="#34D399",
            current_val=self._retract_dist,
            step=0.5,
            mn=0.5,
            mx=15.0,
            presets=[1.0, 1.5, 2.0, 3.0, 4.0]
        ))

        card_layout.addLayout(body, 1)

        # --- Bottom Action Controls ---
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(_s(8, scale))

        self.reset_btn = QtWidgets.QPushButton("↺  Reset to Config Defaults")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(_BTN_GHOST)
        self.reset_btn.clicked.connect(self._on_reset)
        action_row.addWidget(self.reset_btn)

        action_row.addStretch(1)

        self.apply_btn = QtWidgets.QPushButton("✓  Apply Tweaks (No Restart)")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet(_BTN_SUCCESS)
        self.apply_btn.setToolTip("Applies tweaks to live probe tests and accuracy runs immediately without restarting Klipper.")
        self.apply_btn.clicked.connect(self._on_apply)
        action_row.addWidget(self.apply_btn)

        self.save_btn = QtWidgets.QPushButton("💾  Save to printer.cfg & Restart")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(_BTN_PRIMARY)
        self.save_btn.setToolTip("Permanently updates probe speeds/height in printer.cfg and restarts Klipper firmware.")
        self.save_btn.clicked.connect(self._on_save_config)
        action_row.addWidget(self.save_btn)

        card_layout.addLayout(action_row)

        # Status Bar
        self.status_lbl = QtWidgets.QLabel("Select speeds & retract clearance. Tweak without touching config files.")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        card_layout.addWidget(self.status_lbl)

        self.apply_scale(scale)
        QtCore.QTimer.singleShot(50, self._load_klipper_config)

    def _create_param_card(self, key: str, title: str, desc: str, unit: str, color: str,
                           current_val: float, step: float, mn: float, mx: float, presets: list) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            QFrame {{
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
        """)
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        top_row = QtWidgets.QHBoxLayout()
        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)

        hdr = QtWidgets.QLabel(title)
        hdr.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        title_col.addWidget(hdr)

        desc_lbl = QtWidgets.QLabel(desc)
        desc_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 600;")
        title_col.addWidget(desc_lbl)
        top_row.addLayout(title_col, 1)

        # Stepper buttons + Value readout
        btn_minus = QtWidgets.QPushButton("–")
        btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minus.setFixedSize(38, 34)
        btn_minus.setStyleSheet(_BTN_GHOST)
        btn_minus.clicked.connect(lambda: self._adjust_param(key, -step, mn, mx, unit))
        top_row.addWidget(btn_minus)

        val_lbl = QtWidgets.QLabel(f"{current_val:.1f} {unit}")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setFixedWidth(90)
        val_lbl.setStyleSheet(f"color: #FFFFFF; font-size: 18px; font-weight: 900; font-family: 'Consolas', monospace;")
        top_row.addWidget(val_lbl)
        self.val_labels[key] = val_lbl

        btn_plus = QtWidgets.QPushButton("+")
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_plus.setFixedSize(38, 34)
        btn_plus.setStyleSheet(_BTN_GHOST)
        btn_plus.clicked.connect(lambda: self._adjust_param(key, step, mn, mx, unit))
        top_row.addWidget(btn_plus)

        lay.addLayout(top_row)

        # Preset Pills Row
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.setSpacing(6)
        preset_lbl = QtWidgets.QLabel("Presets:")
        preset_lbl.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 700;")
        preset_row.addWidget(preset_lbl)

        p_btns = []
        for p in presets:
            btn = QtWidgets.QPushButton(f"{p:.1f} {unit}")
            btn.setCheckable(True)
            btn.setChecked(abs(current_val - p) < 1e-4)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(30, 41, 59, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    color: #94A3B8;
                    font-size: 11px;
                    font-weight: 800;
                    min-height: 28px;
                    padding: 2px 10px;
                }
                QPushButton:hover { border-color: #00E5FF; color: #FFFFFF; }
                QPushButton:checked {
                    background: rgba(0, 229, 255, 0.2);
                    border: 1.5px solid #00E5FF;
                    color: #00E5FF;
                }
            """)
            btn.clicked.connect(lambda _=False, k=key, v=p, u=unit, lo=mn, hi=mx: self._set_param(k, v, lo, hi, u))
            preset_row.addWidget(btn)
            p_btns.append((p, btn))

        self.preset_btn_groups[key] = p_btns
        preset_row.addStretch(1)
        lay.addLayout(preset_row)

        return card

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        return getattr(self.window(), "moonraker", None)

    def _load_klipper_config(self):
        mr = self._get_moonraker()
        cfg = getattr(mr, "config", {}) if mr else {}
        for sec in ("load_cell_probe", "probe", "bltouch", "smart_effector", "beacon"):
            if sec in cfg:
                self._probe_section = sec
                self.section_badge.setText(f"[{sec.upper()}]")
                p = cfg[sec]
                if "speed" in p:
                    self._cfg_probe_speed = float(p["speed"])
                if "lift_speed" in p:
                    self._cfg_lift_speed = float(p["lift_speed"])
                if "sample_retract_dist" in p:
                    self._cfg_retract_dist = float(p["sample_retract_dist"])
                break

    def _adjust_param(self, key: str, delta: float, lo: float, hi: float, unit: str):
        cur = getattr(self, f"_{key}", 0.0)
        new_val = round(max(lo, min(hi, cur + delta)), 1)
        self._set_param(key, new_val, lo, hi, unit)

    def _set_param(self, key: str, val: float, lo: float, hi: float, unit: str):
        val = round(max(lo, min(hi, val)), 1)
        setattr(self, f"_{key}", val)
        if key in self.val_labels:
            self.val_labels[key].setText(f"{val:.1f} {unit}")
        if key in self.preset_btn_groups:
            for p, btn in self.preset_btn_groups[key]:
                btn.setChecked(abs(val - p) < 1e-4)

    def _on_reset(self):
        self._set_param("probe_speed", self._cfg_probe_speed, 1.0, 25.0, "mm/s")
        self._set_param("lift_speed", self._cfg_lift_speed, 2.0, 40.0, "mm/s")
        self._set_param("sample_retract_dist", self._cfg_retract_dist, 0.5, 15.0, "mm")
        self._on_apply(show_toast=False)
        self.status_lbl.setText("Reset to printer.cfg defaults.")

    def _on_apply(self, show_toast: bool = True):
        cfg = {
            "probe_speed": self._probe_speed,
            "lift_speed": self._lift_speed,
            "sample_retract_dist": self._retract_dist,
        }
        save_probe_display_settings(cfg)
        if show_toast:
            self.status_lbl.setText(
                f"✓ Active for all probing: Speed = {self._probe_speed:.1f} mm/s, "
                f"Retract = {self._retract_dist:.1f} mm, Lift = {self._lift_speed:.1f} mm/s"
            )

    def _on_save_config(self):
        if self._busy:
            return
        mr = self._get_moonraker()
        if not (mr and mr.connected):
            self.status_lbl.setText("Printer offline — cannot save to config.")
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        self._busy = True
        self.save_btn.setEnabled(False)
        self.save_btn.setText("Saving to printer.cfg...")

        def _bg():
            err_msg = None
            try:
                url_get = f"http://{host}/server/files/config/printer.cfg"
                req_get = urllib.request.Request(url_get, headers={"Accept": "text/plain"})
                with urllib.request.urlopen(req_get, timeout=5.0) as resp:
                    txt = resp.read().decode("utf-8")

                sec_name = self._probe_section or "load_cell_probe"
                sec_re = re.compile(rf"(\[{sec_name}\][\s\S]*?)(?=\n\[|$)", re.IGNORECASE)
                m = sec_re.search(txt)
                if not m:
                    raise RuntimeError(f"[{sec_name}] section not found in printer.cfg")

                block = m.group(1)
                def _rep_or_add(b, k, v):
                    k_re = re.compile(rf"^([ \t]*${k}[ \t]*:)[ \t]*[^\r\n#]*", re.IGNORECASE | re.MULTILINE)
                    if k_re.search(b):
                        return k_re.sub(rf"\g<1> {v}", b)
                    return b.rstrip() + f"\n{k}: {v}\n"

                block = _rep_or_add(block, "speed", f"{self._probe_speed:.1f}")
                block = _rep_or_add(block, "lift_speed", f"{self._lift_speed:.1f}")
                block = _rep_or_add(block, "sample_retract_dist", f"{self._retract_dist:.1f}")
                new_txt = sec_re.sub(block, txt, count=1)

                boundary = "----ProbeSpeedBoundary12345"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="printer.cfg"\r\n'
                    f"Content-Type: text/plain\r\n\r\n"
                    f"{new_txt}\r\n"
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="root"\r\n\r\n'
                    f"config\r\n"
                    f"--{boundary}--\r\n"
                ).encode("utf-8")

                url_post = f"http://{host}/server/files/upload"
                req_post = urllib.request.Request(
                    url_post,
                    data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    method="POST"
                )
                with urllib.request.urlopen(req_post, timeout=10.0) as resp:
                    pass
            except Exception as e:
                err_msg = str(e)

            def _done():
                self._busy = False
                self.save_btn.setEnabled(True)
                self.save_btn.setText("💾  Save to printer.cfg & Restart")
                if err_msg:
                    self.status_lbl.setText(f"Save failed: {err_msg}")
                else:
                    self._on_apply(show_toast=False)
                    self.status_lbl.setText("✓ Saved to printer.cfg! Restarting Klipper firmware...")
                    if mr:
                        mr.send_gcode("FIRMWARE_RESTART")

            if hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_done)
            else:
                QtCore.QTimer.singleShot(0, _done)

        threading.Thread(target=_bg, daemon=True).start()

    def accept(self):
        self.closed.emit()

    def reject(self):
        self.closed.emit()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(12, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.icon_label.setPixmap(icons.pixmap("tune", _s(28, s)))
        self.icon_label.setFixedSize(_s(30, s), _s(30, s))
