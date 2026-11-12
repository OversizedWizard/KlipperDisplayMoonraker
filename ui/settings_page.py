"""Settings Page: includes Bed Mesh, Z-Offset, Probe Accuracy, Moonraker host, and display settings.

Moved Bed Mesh, Z-Offset, and Probe Accuracy here as requested. Tapping them
opens the detailed procedural modal explanation.
"""

import json
import os
import threading
import time
from . import icons
from .calibrate_page import CalibrationDialog, CALIBRATION_DETAILS, is_calibration_supported
from .load_cell_test_dialog import LoadCellWeightTestDialog
from .qt import QtWidgets, QtCore, Qt, Signal
from .touch_scroll import touch_press, touch_move, touch_release

DISPLAY_SETTINGS_PATH = os.path.expanduser("~/.klipper_display_settings.json")


def load_display_settings() -> dict:
    cfg = {"sleep_timeout_min": 10}
    try:
        if os.path.exists(DISPLAY_SETTINGS_PATH):
            with open(DISPLAY_SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    cfg.update(d)
    except Exception:
        pass
    return cfg


def save_display_settings(cfg: dict):
    try:
        with open(DISPLAY_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))

SETTINGS_CAL_ITEMS = [
    CALIBRATION_DETAILS["bed_mesh"],
    CALIBRATION_DETAILS["probe_acc"],
    CALIBRATION_DETAILS["probe_settings"],
    CALIBRATION_DETAILS["load_cell_weight_test"],
]

class SettingActionCard(QtWidgets.QFrame):
    """Touch card for Bed Mesh, Z-Offset, and Probe Accuracy with procedural modal."""

    def __init__(self, item: dict, on_tap, parent=None):
        super().__init__(parent)
        self.item = item
        self.on_tap = on_tap
        self.setObjectName("CalibrateCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)

        self._layout = QtWidgets.QHBoxLayout(self)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(2)

        self.title_label = QtWidgets.QLabel(item["title"])
        self.title_label.setObjectName("CalTitle")
        self.title_label.setMinimumWidth(0)
        mid.addWidget(self.title_label)

        self.desc_label = QtWidgets.QLabel(item["desc"])
        self.desc_label.setObjectName("CalDesc")
        self.desc_label.setMinimumWidth(0)
        mid.addWidget(self.desc_label)

        cmd_badge_text = item.get("cmd") or "CALIBRATE"
        cmd_row = QtWidgets.QHBoxLayout()
        self.cmd_badge = QtWidgets.QLabel(cmd_badge_text)
        self.cmd_badge.setObjectName("CalCmdBadge")
        cmd_row.addWidget(self.cmd_badge)
        cmd_row.addStretch(1)
        mid.addLayout(cmd_row)

        self._layout.addLayout(mid, 1)

        self.arrow = QtWidgets.QLabel("\u203A")
        self.arrow.setObjectName("CalCardArrow")
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            touch_press(self, event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not touch_move(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if touch_release(self) and self.on_tap:
                self.on_tap(self.item)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def apply_scale(self, s: float):
        m = _s(12, s)
        self._layout.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self._layout.setSpacing(_s(10, s))
        self.icon_label.setPixmap(icons.pixmap(self.item["icon"], _s(38, s)))
        self.icon_label.setFixedSize(_s(42, s), _s(42, s))
        self.setFixedHeight(_s(82, s))


class SystemOptionTile(QtWidgets.QFrame):
    """Touch card for Klipper host commands like Save Config, Firmware Restart, Moonraker."""

    def __init__(self, icon_name: str, title: str, subtitle: str, badge: str, on_click=None, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.on_click = on_click
        self.setObjectName("CalibrateCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)

        self._layout = QtWidgets.QHBoxLayout(self)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(2)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("CalTitle")
        self.title_label.setMinimumWidth(0)
        mid.addWidget(self.title_label)

        self.sub_label = QtWidgets.QLabel(subtitle)
        self.sub_label.setObjectName("CalDesc")
        self.sub_label.setMinimumWidth(0)
        mid.addWidget(self.sub_label)

        cmd_row = QtWidgets.QHBoxLayout()
        self.badge_lbl = QtWidgets.QLabel(badge)
        self.badge_lbl.setObjectName("CalCmdBadge")
        cmd_row.addWidget(self.badge_lbl)
        cmd_row.addStretch(1)
        mid.addLayout(cmd_row)

        self._layout.addLayout(mid, 1)

        self.arrow = QtWidgets.QLabel("\u203A")
        self.arrow.setObjectName("CalCardArrow")
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            touch_press(self, event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not touch_move(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if touch_release(self) and self.on_click:
                self.on_click(self)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def apply_scale(self, s: float):
        m = _s(12, s)
        self._layout.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self._layout.setSpacing(_s(10, s))
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, _s(38, s)))
        self.icon_label.setFixedSize(_s(42, s), _s(42, s))
        self.setFixedHeight(_s(82, s))


class SettingsInfoView(QtWidgets.QFrame):
    """In-window full-screen view for settings system and display diagnostics."""
    closed = Signal()

    def __init__(self, icon_name: str, title: str, subtitle: str, badge: str, items: list, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("SettingsInfoView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QtWidgets.QFrame()
        card.setObjectName("DialogCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        outer.addWidget(card)

        lay = QtWidgets.QVBoxLayout(card)
        m = _s(14, scale)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(_s(10, scale))

        # Header
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(10, scale))

        ico_lbl = QtWidgets.QLabel()
        ico_lbl.setPixmap(icons.pixmap(icon_name, _s(34, scale)))
        ico_lbl.setFixedSize(_s(38, scale), _s(38, scale))
        hdr.addWidget(ico_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)
        t_lbl = QtWidgets.QLabel(title)
        t_lbl.setObjectName("DialogTitle")
        title_col.addWidget(t_lbl)

        sub_lbl = QtWidgets.QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col, 1)

        b_lbl = QtWidgets.QLabel(badge)
        b_lbl.setObjectName("CalCmdBadge")
        hdr.addWidget(b_lbl)

        close_x = QtWidgets.QPushButton("\u2715")
        close_x.setObjectName("DialogCloseX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(self.closed.emit)
        hdr.addWidget(close_x)

        lay.addLayout(hdr)

        # Content info box
        info_box = QtWidgets.QFrame()
        info_box.setObjectName("DialogStepsBox")
        info_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ib_lay = QtWidgets.QVBoxLayout(info_box)
        ib_lay.setContentsMargins(_s(12, scale), _s(10, scale), _s(12, scale), _s(10, scale))
        ib_lay.setSpacing(_s(8, scale))

        for k, v in items:
            row = QtWidgets.QHBoxLayout()
            kl = QtWidgets.QLabel(f"{k}:")
            kl.setStyleSheet("color: #00E5FF; font-size: 12px; font-weight: 800; min-width: 140px;")
            vl = QtWidgets.QLabel(v)
            vl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 600;")
            vl.setWordWrap(True)
            row.addWidget(kl)
            row.addWidget(vl, 1)
            ib_lay.addLayout(row)

        lay.addWidget(info_box, 1)

        # Bottom row
        bot = QtWidgets.QHBoxLayout()
        bot.addStretch(1)
        back_btn = QtWidgets.QPushButton("\u2039  Back to Settings")
        back_btn.setObjectName("DialogStartBtn")
        back_btn.setStyleSheet("font-size: 12px; font-weight: 800; padding: 6px 18px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.closed.emit)
        bot.addWidget(back_btn)

        lay.addLayout(bot)


class LiveSystemLoadsView(QtWidgets.QFrame):
    """Live System Loads & Firmware Telemetry view (matches Mainsail/Fluidd System Loads panel)."""
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self._busy_poll = False
        self.setObjectName("LiveSystemLoadsView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QtWidgets.QFrame()
        card.setObjectName("DialogCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(card)

        root = QtWidgets.QVBoxLayout(card)
        m = _s(12, scale)
        root.setContentsMargins(m, _s(10, scale), m, _s(10, scale))
        root.setSpacing(_s(8, scale))

        # --- Top Header ---
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(10, scale))

        ico_lbl = QtWidgets.QLabel()
        ico_lbl.setPixmap(icons.pixmap("firmware", _s(32, scale)))
        ico_lbl.setFixedSize(_s(36, scale), _s(36, scale))
        hdr.addWidget(ico_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(1)
        t_lbl = QtWidgets.QLabel("System Loads & Firmware Telemetry")
        t_lbl.setObjectName("DialogTitle")
        title_col.addWidget(t_lbl)

        self.sub_lbl = QtWidgets.QLabel("Live Host CPU, RAM, Storage & Microcontroller (MCU) Loads")
        self.sub_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        title_col.addWidget(self.sub_lbl)
        hdr.addLayout(title_col, 1)

        self.live_badge = QtWidgets.QLabel("● LIVE SYSTEM LOADS")
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
        # LEFT COLUMN: Host (Raspberry Pi / Linux) Live System Loads
        # =====================================================================
        host_box = QtWidgets.QFrame()
        host_box.setObjectName("DialogStepsBox")
        host_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h_lay = QtWidgets.QVBoxLayout(host_box)
        h_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        h_lay.setSpacing(_s(6, scale))

        self.host_hdr_lbl = QtWidgets.QLabel("HOST SYSTEM (RASPBERRY PI)")
        self.host_hdr_lbl.setStyleSheet(f"color: #00E5FF; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        h_lay.addWidget(self.host_hdr_lbl)

        self.distro_lbl = QtWidgets.QLabel("OS: Linux • Connecting...")
        self.distro_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600;")
        h_lay.addWidget(self.distro_lbl)

        self.cpu_bar, self.cpu_val_lbl = self._make_metric_row(h_lay, "CPU Load", "0.0% (Load: 0.00)", "#00E5FF")
        self.temp_bar, self.temp_val_lbl = self._make_metric_row(h_lay, "CPU Temp", "0.0°C", "#34D399")
        self.mem_bar, self.mem_val_lbl = self._make_metric_row(h_lay, "Memory", "0 / 0 MB (0%)", "#38BDF8")
        self.disk_bar, self.disk_val_lbl = self._make_metric_row(h_lay, "SD Storage", "0.0 / 0.0 GB (0%)", "#A78BFA")

        h_lay.addStretch(1)

        # Software versions box
        sw_card = QtWidgets.QFrame()
        sw_card.setStyleSheet(f"""
            QFrame {{
                background: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {_s(6, scale)}px;
            }}
        """)
        sw_lay = QtWidgets.QVBoxLayout(sw_card)
        sw_lay.setContentsMargins(_s(8, scale), _s(5, scale), _s(8, scale), _s(5, scale))
        sw_lay.setSpacing(2)

        self.sw_klipper_lbl = QtWidgets.QLabel("Klipper: --  •  Moonraker: --")
        self.sw_klipper_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(10, scale)}px; font-weight: 700; border: none; background: transparent;")
        sw_lay.addWidget(self.sw_klipper_lbl)

        self.sw_mr_stats_lbl = QtWidgets.QLabel("Moonraker Load: --  •  Uptime: --")
        self.sw_mr_stats_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px; font-weight: 600; border: none; background: transparent;")
        sw_lay.addWidget(self.sw_mr_stats_lbl)

        h_lay.addWidget(sw_card)
        body.addWidget(host_box, 11)

        # =====================================================================
        # RIGHT COLUMN: Live Microcontroller (MCU) Loads
        # =====================================================================
        mcu_box = QtWidgets.QFrame()
        mcu_box.setObjectName("DialogStepsBox")
        mcu_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.mcu_lay = QtWidgets.QVBoxLayout(mcu_box)
        self.mcu_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        self.mcu_lay.setSpacing(_s(6, scale))

        mcu_hdr = QtWidgets.QLabel("MICROCONTROLLER (MCU) LOADS")
        mcu_hdr.setStyleSheet(f"color: #00E5FF; font-size: {_s(11, scale)}px; font-weight: 900; letter-spacing: 0.6px;")
        self.mcu_lay.addWidget(mcu_hdr)

        self.mcu_cards_container = QtWidgets.QVBoxLayout()
        self.mcu_cards_container.setSpacing(_s(6, scale))
        self.mcu_lay.addLayout(self.mcu_cards_container)
        self.mcu_lay.addStretch(1)

        self.mcu_widgets = {}
        body.addWidget(mcu_box, 12)

        root.addLayout(body, 1)

        # --- Bottom Row ---
        bot = QtWidgets.QHBoxLayout()
        bot.addStretch(1)
        back_btn = QtWidgets.QPushButton("\u2039  Back to Settings")
        back_btn.setObjectName("DialogStartBtn")
        back_btn.setStyleSheet(f"font-size: {_s(12, scale)}px; font-weight: 800; padding: {_s(6, scale)}px {_s(18, scale)}px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._on_close)
        bot.addWidget(back_btn)
        root.addLayout(bot)

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_loads)
        QtCore.QTimer.singleShot(80, self._start_polling)

    def _make_metric_row(self, parent_lay, label_txt: str, init_val: str, color: str):
        s = self.scale
        wrap = QtWidgets.QVBoxLayout()
        wrap.setSpacing(2)

        top = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(label_txt)
        lbl.setStyleSheet(f"color: #E2E8F0; font-size: {_s(11, s)}px; font-weight: 800;")
        val = QtWidgets.QLabel(init_val)
        val.setStyleSheet(f"color: {color}; font-size: {_s(11, s)}px; font-weight: 800;")
        top.addWidget(lbl)
        top.addStretch(1)
        top.addWidget(val)
        wrap.addLayout(top)

        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(_s(7, s))
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(15, 23, 42, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: {_s(3, s)}px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: {_s(2, s)}px;
            }}
        """)
        wrap.addWidget(bar)
        parent_lay.addLayout(wrap)
        return bar, val

    def _create_mcu_card(self, key: str):
        s = self.scale
        card = QtWidgets.QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: rgba(15, 23, 42, 0.78);
                border: 1px solid rgba(0, 229, 255, 0.22);
                border-radius: {_s(8, s)}px;
            }}
        """)
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(_s(9, s), _s(6, s), _s(9, s), _s(6, s))
        lay.setSpacing(_s(4, s))

        top = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel(key.upper())
        title_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(11, s)}px; font-weight: 900; border: none; background: transparent;")
        chip_badge = QtWidgets.QLabel("MCU")
        chip_badge.setStyleSheet(f"""
            color: #00E5FF;
            background: rgba(0, 229, 255, 0.14);
            border: 1px solid rgba(0, 229, 255, 0.4);
            border-radius: {_s(4, s)}px;
            font-size: {_s(9, s)}px;
            font-weight: 800;
            padding: 1px {_s(6, s)}px;
        """)
        top.addWidget(title_lbl)
        top.addStretch(1)
        top.addWidget(chip_badge)
        lay.addLayout(top)

        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(_s(6, s))
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(2, 6, 23, 0.9);
                border: none;
                border-radius: {_s(3, s)}px;
            }}
            QProgressBar::chunk {{
                background: #34D399;
                border-radius: {_s(3, s)}px;
            }}
        """)
        lay.addWidget(bar)

        metrics_lbl = QtWidgets.QLabel("Load: 0.0%  •  Awake: 0.0%  •  Freq: -- MHz")
        metrics_lbl.setStyleSheet(f"color: #E2E8F0; font-size: {_s(10, s)}px; font-weight: 700; border: none; background: transparent;")
        lay.addWidget(metrics_lbl)

        ver_lbl = QtWidgets.QLabel("Version: --  •  TX/RX: --")
        ver_lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(9, s)}px; font-weight: 600; border: none; background: transparent;")
        lay.addWidget(ver_lbl)

        self.mcu_cards_container.addWidget(card)
        w_dict = {
            "card": card,
            "title": title_lbl,
            "badge": chip_badge,
            "bar": bar,
            "metrics": metrics_lbl,
            "ver": ver_lbl,
        }
        self.mcu_widgets[key] = w_dict
        return w_dict

    def _start_polling(self):
        self._poll_timer.start()
        self._poll_loads()

    def _poll_loads(self):
        if self._busy_poll:
            return
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if not mr:
            return
        self._busy_poll = True

        def _done(data: dict):
            self._busy_poll = False
            self._update_telemetry(data)

        mr.query_system_loads(on_done=_done)

    @staticmethod
    def _fmt_bytes(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b / (1024 * 1024):.1f} MB"

    @staticmethod
    def _fmt_uptime(sec: float) -> str:
        if sec <= 0:
            return "--"
        m, _ = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        if d > 0:
            return f"{d}d {h}h {m}m"
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    def _update_telemetry(self, d: dict):
        model = d.get("host_model") or "Raspberry Pi Host"
        distro = d.get("distro") or "Linux"
        kernel = d.get("kernel") or ""
        cores = int(d.get("cpu_count") or 4)
        self.host_hdr_lbl.setText(f"HOST ({model.upper()[:28]})")
        self.distro_lbl.setText(f"{distro}  •  Kernel {kernel}" if kernel else distro)

        cpu_pct = float(d.get("cpu_usage_pct") or 0.0)
        sysload = float(d.get("sysload") or 0.0)
        self.cpu_bar.setValue(min(100, max(1, round(cpu_pct))))
        self.cpu_val_lbl.setText(f"{cpu_pct:.1f}%  (SysLoad: {sysload:.2f} / {cores}c)")

        c_temp = float(d.get("cpu_temp") or 0.0)
        self.temp_bar.setValue(min(100, max(1, round(c_temp))))
        self.temp_val_lbl.setText(f"{c_temp:.1f}°C")

        mem_u = float(d.get("mem_used_mb") or 0.0)
        mem_t = float(d.get("mem_total_mb") or 0.0)
        mem_p = float(d.get("mem_pct") or 0.0)
        self.mem_bar.setValue(min(100, max(1, round(mem_p))))
        self.mem_val_lbl.setText(f"{mem_u:.0f} / {mem_t:.0f} MB ({mem_p:.1f}%)")

        d_u = float(d.get("disk_used_gb") or 0.0)
        d_t = float(d.get("disk_total_gb") or 0.0)
        d_p = float(d.get("disk_pct") or 0.0)
        self.disk_bar.setValue(min(100, max(1, round(d_p))))
        self.disk_val_lbl.setText(f"{d_u:.1f} / {d_t:.1f} GB ({d_p:.1f}%)")

        k_ver = str(d.get("klipper_version") or "v0.13.0")
        short_k = "-".join(k_ver.split("-")[:2]) if "-" in k_ver else k_ver
        m_ver = str(d.get("moonraker_version") or "v0.10.0")
        short_m = "-".join(m_ver.split("-")[:2]) if "-" in m_ver else m_ver
        self.sw_klipper_lbl.setText(f"Klipper: {short_k}   •   Moonraker: {short_m}")

        mr_cpu = float(d.get("moonraker_cpu_pct") or 0.0)
        mr_mem = float(d.get("moonraker_mem_mb") or 0.0)
        up_str = self._fmt_uptime(float(d.get("uptime_sec") or 0.0))
        ws_c = int(d.get("ws_connections") or 0)
        self.sw_mr_stats_lbl.setText(f"Moonraker: {mr_cpu:.1f}% CPU, {mr_mem:.0f} MB  •  Clients: {ws_c}  •  Up: {up_str}")

        # Update MCU cards
        mcus = d.get("mcus") or []
        for m in mcus:
            key = m.get("key", "mcu")
            w = self.mcu_widgets.get(key)
            if not w:
                w = self._create_mcu_card(key)
            w["title"].setText(m.get("title", key))
            w["badge"].setText(f"{m.get('chip', 'MCU')} • {m.get('freq_mhz', 0.0):.0f} MHz")
            load_p = float(m.get("load_pct") or 0.0)
            awake_p = float(m.get("awake_pct") or 0.0)
            w["bar"].setValue(min(100, max(2, round(max(load_p, awake_p)))))
            w["metrics"].setText(
                f"Load: {load_p:.1f}%   •   Awake: {awake_p:.1f}%   •   Clock: {m.get('freq_mhz', 0.0):.2f} MHz"
            )
            tx = self._fmt_bytes(int(m.get("bytes_write") or 0))
            rx = self._fmt_bytes(int(m.get("bytes_read") or 0))
            retx = int(m.get("bytes_retransmit") or 0)
            w["ver"].setText(
                f"FW: {m.get('version', '--')}   •   TX: {tx} / RX: {rx}   •   Retransmits: {retx}"
            )

    def _on_close(self):
        self._poll_timer.stop()
        self.closed.emit()

    def hideEvent(self, event):
        self._poll_timer.stop()
        super().hideEvent(event)


class SettingsPage(QtWidgets.QWidget):
    _wifi_status_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "settings"
        self._scale = 1.0
        self._config = {}
        self._objects = []
        self._wifi_status_ts = 0.0
        self._wifi_status_inflight = False
        self._wifi_status_ready.connect(self._apply_wifi_status)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for clean touch scrolling
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("CalScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("CalContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.vbox = QtWidgets.QVBoxLayout(self.container)

        self.headers = []

        # --- Section 1: Bed & Probe Calibration (Moved here) ---
        self.sec1 = QtWidgets.QLabel("BED & PROBE CALIBRATION")
        self.sec1.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(self.sec1)
        self.headers.append(self.sec1)

        self.grid_cal = QtWidgets.QGridLayout()
        self.grid_cal.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cal_cards = []
        self._rebuild_cal_cards()

        self.grid_cal.setColumnMinimumWidth(0, 1)
        self.grid_cal.setColumnMinimumWidth(1, 1)
        self.grid_cal.setColumnStretch(0, 1)
        self.grid_cal.setColumnStretch(1, 1)
        self.vbox.addLayout(self.grid_cal)

        # --- Section 2: Diagnostics, Firmware & Host ---
        sec2 = QtWidgets.QLabel("DIAGNOSTICS, FIRMWARE & HOST")
        sec2.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(sec2)
        self.headers.append(sec2)

        self.grid_sys = QtWidgets.QGridLayout()
        self.grid_sys.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.sys_cards = []

        self.tests_card = SystemOptionTile(
            "endstop", "Printer Tests",
            "Motor buzz, endstops & nozzle touch.",
            "MOTORS \u2022 ENDSTOPS",
            on_click=self._on_printer_tests
        )
        self.grid_sys.addWidget(self.tests_card, 0, 0)
        self.sys_cards.append(self.tests_card)

        self.fw_info_card = SystemOptionTile(
            "firmware", "Firmware & MCU Info",
            "Live Host, MCU & Klipper telemetry.",
            "v0.13.0 Klipper",
            on_click=self._on_firmware_info
        )
        self.grid_sys.addWidget(self.fw_info_card, 0, 1)
        self.sys_cards.append(self.fw_info_card)

        self.wifi_card = SystemOptionTile(
            "wifi", "Wi-Fi & Network Settings",
            "Manage Wi-Fi, scan SSIDs & network status.",
            "WLAN: CONNECTING...",
            on_click=self._on_wifi_settings
        )
        self.grid_sys.addWidget(self.wifi_card, 1, 0)
        self.sys_cards.append(self.wifi_card)

        self.disp_card = SystemOptionTile(
            "sun", "Display & Sleep Timer",
            "Screen sleep timeout & display info.",
            self._sleep_badge_text(),
            on_click=self._on_display_info
        )
        self.grid_sys.addWidget(self.disp_card, 1, 1)
        self.sys_cards.append(self.disp_card)

        self.disp_restart_card = SystemOptionTile(
            "reload", "Display Service Restart",
            "Restart Klipper Display screen app.",
            "RESTART APP",
            on_click=self._on_restart_display_service
        )
        self.grid_sys.addWidget(self.disp_restart_card, 2, 0)
        self.sys_cards.append(self.disp_restart_card)

        self.update_wifi_badge()

        self.grid_sys.setColumnMinimumWidth(0, 1)
        self.grid_sys.setColumnMinimumWidth(1, 1)
        self.grid_sys.setColumnStretch(0, 1)
        self.grid_sys.setColumnStretch(1, 1)
        self.vbox.addLayout(self.grid_sys)

        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    def update_connection(self, connected: bool, host: str, klippy_state: str):
        if connected:
            mr = getattr(self.window(), "moonraker", None)
            if mr and hasattr(mr, "firmware_info"):
                self.update_firmware_info(mr.firmware_info)

    def update_firmware_info(self, fw_info: dict):
        if not fw_info:
            return
        kver = fw_info.get("klipper_version", "v0.13.0")
        chip = fw_info.get("mcu_chip", "MCU")
        short_ver = kver.split("-")[0] if "-" in kver else kver
        self.fw_info_card.badge_lbl.setText(f"{short_ver} Klipper")
        self.fw_info_card.sub_label.setText(f"MCU: {chip} \u2022 Live System Loads")

    def update_config(self, config: dict, objects: list = None):
        """Update active Klipper config and dynamically rebuild supported setting/calibration cards."""
        self._config = config or {}
        self._objects = objects or []
        self._rebuild_cal_cards()

    def _rebuild_cal_cards(self):
        while self.grid_cal.count():
            item = self.grid_cal.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.cal_cards.clear()

        filtered_items = [
            item for item in SETTINGS_CAL_ITEMS
            if is_calibration_supported(item["id"], self._config, self._objects)
        ]

        if hasattr(self, "sec1"):
            self.sec1.setVisible(len(filtered_items) > 0)

        for i, item in enumerate(filtered_items):
            card = SettingActionCard(item, on_tap=self.open_procedure_popup)
            card.apply_scale(self._scale)
            row = i // 2
            col = i % 2
            self.grid_cal.addWidget(card, row, col)
            self.cal_cards.append(card)

    def open_procedure_popup(self, item: dict):
        main_win = self.window()
        if item.get("id") == "bed_mesh":
            from .bed_mesh_page import BedMeshScreen
            view = BedMeshScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Bed Mesh", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") == "probe_acc":
            from .probe_accuracy_page import ProbeAccuracyScreen
            view = ProbeAccuracyScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Probe Accuracy", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") == "probe_settings":
            from .probe_settings_page import ProbeSettingsScreen
            view = ProbeSettingsScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Probe Speeds & Heights", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") == "z_offset":
            from .z_offset_page import ZOffsetScreen
            view = ZOffsetScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Z-Offset Calibration", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") in ("screws_tilt", "bed_screws"):
            from .bed_screws_page import BedScrewsScreen
            view = BedScrewsScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Bed Screws Adjust", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") == "pid_tune":
            from .pid_tune_page import PidTuneScreen
            view = PidTuneScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="PID Heater Autotune", return_page="settings")
            else:
                view.show()
            return
        if item.get("id") == "load_cell_weight_test":
            view = LoadCellWeightTestDialog(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Load Cell Weight Test", return_page="settings")
            else:
                view.show()
            return

        view = CalibrationDialog(item, scale=self._scale, parent=self)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=item.get("title", "Settings"), return_page="settings")
        else:
            view.show()

    def _on_printer_tests(self, tile):
        main_win = self.window()
        from .printer_tests_page import PrinterTestsScreen
        view = PrinterTestsScreen(scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="Printer Tests", return_page="settings")
        else:
            view.show()

    def _on_firmware_info(self, tile):
        main_win = self.window()
        view = LiveSystemLoadsView(scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="System Loads & Firmware", return_page="settings")
        else:
            view.show()

    def _on_restart_display_service(self, tile):
        tile.sub_label.setText("Restarting Klipper Display screen app...")
        tile.badge_lbl.setText("RESTARTING...")
        from .power_page import restart_display_app
        restart_display_app(self.window())

    @staticmethod
    def _sleep_badge_text() -> str:
        mins = int(load_display_settings().get("sleep_timeout_min", 10))
        return f"SLEEP: {mins} MIN" if mins > 0 else "SLEEP: NEVER (OFF)"

    def _on_display_info(self, tile):
        main_win = self.window()
        cfg = load_display_settings()
        cur_min = int(cfg.get("sleep_timeout_min", 10))

        view = QtWidgets.QFrame(main_win)
        view.setObjectName("SettingsInfoView")
        view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QtWidgets.QVBoxLayout(view)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QtWidgets.QFrame()
        card.setObjectName("DialogCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(card)

        lay = QtWidgets.QVBoxLayout(card)
        s = self._scale
        m = _s(14, s)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(_s(10, s))

        hdr = QtWidgets.QHBoxLayout()
        ico_lbl = QtWidgets.QLabel()
        ico_lbl.setPixmap(icons.pixmap("sun", _s(34, s)))
        ico_lbl.setFixedSize(_s(38, s), _s(38, s))
        hdr.addWidget(ico_lbl)

        title_col = QtWidgets.QVBoxLayout()
        t_lbl = QtWidgets.QLabel("Display & Screen Sleep Timer")
        t_lbl.setObjectName("DialogTitle")
        sub_lbl = QtWidgets.QLabel("Configure automatic low-power screen sleep timeout after inactivity")
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        title_col.addWidget(t_lbl)
        title_col.addWidget(sub_lbl)
        hdr.addLayout(title_col, 1)

        close_x = QtWidgets.QPushButton("✕")
        close_x.setObjectName("DialogCloseX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(lambda: main_win.close_sub_screen() if hasattr(main_win, "close_sub_screen") else view.close())
        hdr.addWidget(close_x)
        lay.addLayout(hdr)

        # Sleep Timer Selection Box
        sleep_box = QtWidgets.QFrame()
        sleep_box.setObjectName("DialogStepsBox")
        sleep_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sb_lay = QtWidgets.QVBoxLayout(sleep_box)
        sb_lay.setContentsMargins(_s(12, s), _s(10, s), _s(12, s), _s(10, s))
        sb_lay.setSpacing(_s(8, s))

        sb_hdr = QtWidgets.QLabel("SCREEN SLEEP TIMEOUT (USER CONFIG)")
        sb_hdr.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: 900; letter-spacing: 0.6px;")
        sb_lay.addWidget(sb_hdr)

        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(_s(8, s))
        opts = [(0, "Never (Off)"), (2, "2 Minutes"), (5, "5 Minutes"), (10, "10 Minutes"), (15, "15 Minutes"), (30, "30 Minutes")]
        opt_btns = {}

        def _select_min(val: int):
            cfg["sleep_timeout_min"] = val
            save_display_settings(cfg)
            self.disp_card.badge_lbl.setText(self._sleep_badge_text())
            if hasattr(main_win, "reload_sleep_settings"):
                main_win.reload_sleep_settings()
            for v_k, b_w in opt_btns.items():
                if v_k == val:
                    b_w.setStyleSheet(
                        "QPushButton { background: #00E5FF; color: #0F172A; border: 1.5px solid #FFFFFF; "
                        "border-radius: 8px; font-size: 12px; font-weight: 900; padding: 8px; }"
                    )
                else:
                    b_w.setStyleSheet(
                        "QPushButton { background: #1E293B; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.16); "
                        "border-radius: 8px; font-size: 12px; font-weight: 700; padding: 8px; }"
                    )

        for idx, (m_val, m_lbl) in enumerate(opts):
            b = QtWidgets.QPushButton(m_lbl)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(38, s))
            b.clicked.connect(lambda _c=False, v=m_val: _select_min(v))
            btn_grid.addWidget(b, idx // 3, idx % 3)
            opt_btns[m_val] = b

        sb_lay.addLayout(btn_grid)
        _select_min(cur_min)

        info_lbl = QtWidgets.QLabel(
            "• Display: 5-inch Touchscreen (800×480 Base, Dynamic Scale "
            f"{self._scale:.2f}x)\n"
            "• Sleep mode enters a low-power dark screen showing live clock, temperatures, and print progress. Touch anywhere to wake."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        sb_lay.addWidget(info_lbl)
        lay.addWidget(sleep_box, 1)

        bot = QtWidgets.QHBoxLayout()
        test_btn = QtWidgets.QPushButton("🌙  Test Sleep Screen Now")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(
            "QPushButton { background: #1E293B; color: #38BDF8; border: 1px solid #38BDF8; "
            "border-radius: 8px; font-size: 12px; font-weight: 800; padding: 6px 14px; }"
        )
        test_btn.clicked.connect(lambda: main_win.enter_sleep_mode() if hasattr(main_win, "enter_sleep_mode") else None)
        bot.addWidget(test_btn)
        bot.addStretch(1)

        back_btn = QtWidgets.QPushButton("‹  Save & Return to Settings")
        back_btn.setObjectName("DialogStartBtn")
        back_btn.setStyleSheet("font-size: 12px; font-weight: 800; padding: 6px 18px;")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: main_win.close_sub_screen() if hasattr(main_win, "close_sub_screen") else view.close())
        bot.addWidget(back_btn)
        lay.addLayout(bot)

        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="Display & Sleep Timer", return_page="settings")
        else:
            view.show()

    def _on_wifi_settings(self, tile):
        main_win = self.window()
        from .wifi_page import WifiScreen
        view = WifiScreen(scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="Wi-Fi Settings", return_page="settings")
        else:
            view.show()

    def update_wifi_badge(self, force: bool = False):
        now = time.monotonic()
        if not force and self._wifi_status_ts > 0.0 and (now - self._wifi_status_ts) < 15.0:
            return
        if self._wifi_status_inflight:
            return
        self._wifi_status_inflight = True

        def _worker():
            st = None
            try:
                from .wifi_page import WifiManager
                st = WifiManager.get_status()
            except Exception:
                st = None
            try:
                self._wifi_status_ready.emit(st or {})
            except Exception:
                self._wifi_status_inflight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_wifi_status(self, st: dict):
        self._wifi_status_inflight = False
        self._wifi_status_ts = time.monotonic()
        try:
            if st.get("connected"):
                ssid = st.get("ssid", "Connected")
                ip = st.get("ip", "")
                self.wifi_card.badge_lbl.setText(f"WLAN: {ssid.upper()[:14]}")
                if ip and ip != "--.--.--.--":
                    self.wifi_card.sub_label.setText(f"IP: {ip} • Signal: {st.get('signal_pct', 80)}%")
            else:
                self.wifi_card.badge_lbl.setText("WLAN: DISCONNECTED")
                self.wifi_card.sub_label.setText("Scan & connect to Wi-Fi networks")
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.update_wifi_badge()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(14, s)
        self.vbox.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self.vbox.setSpacing(_s(5, s))
        self.grid_cal.setHorizontalSpacing(_s(12, s))
        self.grid_cal.setVerticalSpacing(_s(8, s))
        self.grid_sys.setHorizontalSpacing(_s(12, s))
        self.grid_sys.setVerticalSpacing(_s(8, s))
        for h in self.headers:
            h.setStyleSheet(f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8; margin-top: {_s(2, s)}px; margin-bottom: {_s(1, s)}px;")
        for card in self.cal_cards:
            card.apply_scale(s)
        for card in self.sys_cards:
            card.apply_scale(s)
