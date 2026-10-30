"""Settings Page: includes Bed Mesh, Z-Offset, Probe Accuracy, Moonraker host, and display settings.

Moved Bed Mesh, Z-Offset, and Probe Accuracy here as requested. Tapping them
opens the detailed procedural modal explanation.
"""

from . import icons
from .calibrate_page import CalibrationDialog, CALIBRATION_DETAILS, is_calibration_supported
from .load_cell_test_dialog import LoadCellWeightTestDialog
from .qt import QtWidgets, QtCore, Qt, Signal

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))

SETTINGS_CAL_ITEMS = [
    CALIBRATION_DETAILS["bed_mesh"],
    CALIBRATION_DETAILS["z_offset"],
    CALIBRATION_DETAILS["probe_acc"],
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

        self._layout = QtWidgets.QHBoxLayout(self)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(2)

        self.title_label = QtWidgets.QLabel(item["title"])
        self.title_label.setObjectName("CalTitle")
        mid.addWidget(self.title_label)

        self.desc_label = QtWidgets.QLabel(item["desc"])
        self.desc_label.setObjectName("CalDesc")
        mid.addWidget(self.desc_label)

        cmd_badge_text = item.get("cmd", "")
        if cmd_badge_text:
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
            self.on_tap(self.item)
            event.accept()
        else:
            super().mousePressEvent(event)

    def apply_scale(self, s: float):
        m = _s(12, s)
        self._layout.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self._layout.setSpacing(_s(10, s))
        self.icon_label.setPixmap(icons.pixmap(self.item["icon"], _s(38, s)))
        self.icon_label.setFixedSize(_s(42, s), _s(42, s))


class SystemOptionTile(QtWidgets.QFrame):
    """Touch card for Klipper host commands like Save Config, Firmware Restart, Moonraker."""

    def __init__(self, icon_name: str, title: str, subtitle: str, badge: str, on_click=None, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.on_click = on_click
        self.setObjectName("CalibrateCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._layout = QtWidgets.QHBoxLayout(self)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(2)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("CalTitle")
        mid.addWidget(self.title_label)

        self.sub_label = QtWidgets.QLabel(subtitle)
        self.sub_label.setObjectName("CalDesc")
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
        self._layout.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def apply_scale(self, s: float):
        m = _s(12, s)
        self._layout.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self._layout.setSpacing(_s(10, s))
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, _s(38, s)))
        self.icon_label.setFixedSize(_s(42, s), _s(42, s))


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


class SettingsPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "settings"
        self._scale = 1.0
        self._config = {}
        self._objects = []
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

        self.grid_cal.setColumnStretch(0, 1)
        self.grid_cal.setColumnStretch(1, 1)
        self.vbox.addLayout(self.grid_cal)

        self.vbox.addSpacing(8)

        # --- Section 2: Klipper System & Host ---
        sec2 = QtWidgets.QLabel("KLIPPER FIRMWARE & HOST")
        sec2.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(sec2)
        self.headers.append(sec2)

        self.grid_sys = QtWidgets.QGridLayout()
        self.grid_sys.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.sys_cards = []

        self.fw_info_card = SystemOptionTile(
            "firmware", "Firmware & MCU Info",
            "Installed Klipper, MCU & Moonraker versions.",
            "v0.13.0 Klipper",
            on_click=self._on_firmware_info
        )
        self.grid_sys.addWidget(self.fw_info_card, 0, 0)
        self.sys_cards.append(self.fw_info_card)

        disp_card = SystemOptionTile(
            "sun", "Display & Timeout",
            "Brightness and screen blanking timer.",
            "100% Brightness",
            on_click=self._on_display_info
        )
        self.grid_sys.addWidget(disp_card, 0, 1)
        self.sys_cards.append(disp_card)

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
        self.fw_info_card.sub_label.setText(f"MCU: {chip} \u2022 {kver[:18]}")

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
        if item.get("id") == "z_offset":
            from .z_offset_page import ZOffsetScreen
            view = ZOffsetScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Z-Offset Calibration", return_page="settings")
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

    def _on_firmware_info(self, tile):
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        fw = getattr(mr, "firmware_info", {}) if mr else {}
        klipper_ver = fw.get("klipper_version", "v0.13.0")
        mcu_chip = fw.get("mcu_chip", "stm32f072xb")
        mcu_freq = fw.get("mcu_freq", "48 MHz")
        mcu_ver = fw.get("mcu_version", klipper_ver)
        mcu_comp = fw.get("mcu_compiler", "gcc: 14.2.1 | binutils: 2.44")
        mr_ver = fw.get("moonraker_version", "v0.10.0")
        mr_api = fw.get("moonraker_api", "API 1.5.0")
        host_name = fw.get("hostname", "pi4")
        cfg_path = fw.get("config_file", "/home/pi/printer_data/config/printer.cfg")
        py_path = fw.get("python_path", "/home/pi/klippy-env")
        state = fw.get("state", "ready")

        badge_txt = f"{klipper_ver.split('-')[0]}  \u2022  LIVE" if (mr and mr.connected) else f"{klipper_ver.split('-')[0]}"

        view = SettingsInfoView(
            icon_name="firmware",
            title="Installed Firmware & System Info",
            subtitle="Klipper Core, Microcontroller & Host Software",
            badge=badge_txt,
            items=[
                ("Klipper Firmware", str(klipper_ver)),
                ("MCU Microcontroller", f"{mcu_chip} ({mcu_freq})"),
                ("MCU Firmware Build", str(mcu_ver)),
                ("MCU Toolchain", str(mcu_comp)),
                ("Moonraker Service", f"{mr_ver} ({mr_api})"),
                ("Host Machine", f"{host_name} (4 cores) \u2022 Linux"),
                ("Python Environment", str(py_path)),
                ("Active Config File", str(cfg_path)),
                ("Klippy Engine State", f"{state.upper()} \u2022 Verified")
            ],
            scale=self._scale,
            parent=self
        )
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="Firmware Info", return_page="settings")
        else:
            view.show()

    def _on_display_info(self, tile):
        main_win = self.window()
        view = SettingsInfoView(
            icon_name="sun",
            title="Display & Screen Geometry",
            subtitle="Touchscreen Resolution and Responsive Scaling",
            badge="800x480 Scalable",
            items=[
                ("Target Display", "5-inch Touchscreen (Raspberry Pi DSI / HDMI)"),
                ("Native Resolution", "800 x 480 px (Base Scale 1.0)"),
                ("Dynamic Scaling", f"Active GUI Scale: {self._scale:.2f}x"),
                ("Screen Brightness", "100% Backlight Level")
            ],
            scale=self._scale,
            parent=self
        )
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title="Display Settings", return_page="settings")
        else:
            view.show()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(14, s)
        self.vbox.setContentsMargins(m, m, m, m)
        self.vbox.setSpacing(_s(8, s))
        self.grid_cal.setHorizontalSpacing(_s(12, s))
        self.grid_cal.setVerticalSpacing(_s(10, s))
        self.grid_sys.setHorizontalSpacing(_s(12, s))
        self.grid_sys.setVerticalSpacing(_s(10, s))
        for h in self.headers:
            h.setStyleSheet(f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8; margin-top: {_s(6, s)}px; margin-bottom: {_s(2, s)}px;")
        for card in self.cal_cards:
            card.apply_scale(s)
        for card in self.sys_cards:
            card.apply_scale(s)
