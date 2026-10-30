"""Power Page: Klipper service restart, MCU firmware restart, host reboot/shutdown, and emergency stop."""

from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class PowerActionCard(QtWidgets.QFrame):
    """Touch card for power actions (Klipper Restart, Firmware Restart, Shutdown, Reboot, M112)."""

    def __init__(self, icon_name: str, title: str, subtitle: str, badge: str, on_click=None, is_danger: bool = False, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.default_title = title
        self.default_subtitle = subtitle
        self.default_badge = badge
        self.on_click = on_click
        self.is_danger = is_danger

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
        if is_danger:
            self.title_label.setStyleSheet("color: #F87171; font-weight: 800;")
        mid.addWidget(self.title_label)

        self.sub_label = QtWidgets.QLabel(subtitle)
        self.sub_label.setObjectName("CalDesc")
        mid.addWidget(self.sub_label)

        cmd_row = QtWidgets.QHBoxLayout()
        self.badge_lbl = QtWidgets.QLabel(badge)
        self.badge_lbl.setObjectName("CalCmdBadge")
        if is_danger:
            self.badge_lbl.setStyleSheet(
                "background: rgba(239, 68, 68, 0.22); color: #FCA5A5; "
                "border: 1px solid rgba(239, 68, 68, 0.55); font-weight: 800; border-radius: 6px;"
            )
        cmd_row.addWidget(self.badge_lbl)
        cmd_row.addStretch(1)
        mid.addLayout(cmd_row)

        self._layout.addLayout(mid, 1)

        self.arrow = QtWidgets.QLabel("\u203A")
        self.arrow.setObjectName("CalCardArrow")
        if is_danger:
            self.arrow.setStyleSheet("color: #EF4444; font-weight: 800;")
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


class PowerPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "power"
        self._scale = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for touch scrolling
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
        self.cards = []

        # --- Section 1: Klipper Restarts ---
        sec1 = QtWidgets.QLabel("KLIPPER SERVICE & FIRMWARE RESTART")
        sec1.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(sec1)
        self.headers.append(sec1)

        grid1 = QtWidgets.QGridLayout()
        grid1.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.klipper_restart_card = PowerActionCard(
            "reload", "Klipper Restart",
            "Reload Python host service & config without resetting MCU.",
            "RESTART",
            on_click=self._on_klipper_restart
        )
        grid1.addWidget(self.klipper_restart_card, 0, 0)
        self.cards.append(self.klipper_restart_card)

        self.fw_restart_card = PowerActionCard(
            "restart", "Firmware Restart",
            "Reload Klipper config and reconnect MCU hardware.",
            "FIRMWARE_RESTART",
            on_click=self._on_fw_restart
        )
        grid1.addWidget(self.fw_restart_card, 0, 1)
        self.cards.append(self.fw_restart_card)

        grid1.setColumnStretch(0, 1)
        grid1.setColumnStretch(1, 1)
        self.vbox.addLayout(grid1)
        self.grid1 = grid1

        self.vbox.addSpacing(8)

        # --- Section 2: Host System & Emergency Stop ---
        sec2 = QtWidgets.QLabel("HOST SYSTEM & EMERGENCY STOP")
        sec2.setObjectName("SettingsSecHeader")
        self.vbox.addWidget(sec2)
        self.headers.append(sec2)

        grid2 = QtWidgets.QGridLayout()
        grid2.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.m112_card = PowerActionCard(
            "power", "Emergency Stop",
            "Immediately halt all motors and shut down all heaters.",
            "M112",
            on_click=self._on_emergency_stop,
            is_danger=True
        )
        grid2.addWidget(self.m112_card, 0, 0)
        self.cards.append(self.m112_card)

        self.reboot_card = PowerActionCard(
            "restart", "Reboot Host (Pi)",
            "Safely reboot Raspberry Pi system OS.",
            "REBOOT",
            on_click=self._on_host_reboot
        )
        grid2.addWidget(self.reboot_card, 0, 1)
        self.cards.append(self.reboot_card)

        self.shutdown_card = PowerActionCard(
            "power", "Shutdown Host (Pi)",
            "Safely power down Raspberry Pi system OS.",
            "SHUTDOWN",
            on_click=self._on_host_shutdown
        )
        grid2.addWidget(self.shutdown_card, 1, 0)
        self.cards.append(self.shutdown_card)

        grid2.setColumnStretch(0, 1)
        grid2.setColumnStretch(1, 1)
        self.vbox.addLayout(grid2)
        self.grid2 = grid2

        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    def _on_klipper_restart(self, tile: PowerActionCard):
        tile.sub_label.setText("Restarting Klipper host service...")
        tile.badge_lbl.setText("RESTARTING...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected:
            def on_done(ok):
                if ok:
                    tile.sub_label.setText("Klipper restart command sent.")
                    tile.badge_lbl.setText("SENT")
                else:
                    tile.sub_label.setText("Failed to send RESTART command.")
                    tile.badge_lbl.setText("ERROR")
                QtCore.QTimer.singleShot(2500, lambda: self._reset_card(tile))
            mr.send_gcode("RESTART", on_done=on_done, timeout=15.0)
        else:
            QtCore.QTimer.singleShot(900, lambda: [
                tile.sub_label.setText("Klipper restarted (offline mode)."),
                QtCore.QTimer.singleShot(2000, lambda: self._reset_card(tile))
            ])

    def _on_fw_restart(self, tile: PowerActionCard):
        tile.sub_label.setText("Restarting Klipper MCU hardware...")
        tile.badge_lbl.setText("RESTARTING...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected:
            def on_done(ok):
                if ok:
                    tile.sub_label.setText("FIRMWARE_RESTART sent to MCU.")
                    tile.badge_lbl.setText("SENT")
                else:
                    tile.sub_label.setText("Failed to restart MCU.")
                    tile.badge_lbl.setText("ERROR")
                QtCore.QTimer.singleShot(2500, lambda: self._reset_card(tile))
            mr.send_gcode("FIRMWARE_RESTART", on_done=on_done, timeout=15.0)
        else:
            QtCore.QTimer.singleShot(900, lambda: [
                tile.sub_label.setText("Firmware restarted (offline mode)."),
                QtCore.QTimer.singleShot(2000, lambda: self._reset_card(tile))
            ])

    def _on_emergency_stop(self, tile: PowerActionCard):
        tile.sub_label.setText("TRIGGERING EMERGENCY STOP (M112)...")
        tile.badge_lbl.setText("HALTING...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected:
            def on_done(ok):
                tile.sub_label.setText("EMERGENCY STOP executed. Heaters off.")
                tile.badge_lbl.setText("HALTED")
                QtCore.QTimer.singleShot(3500, lambda: self._reset_card(tile))
            mr.send_gcode("M112", on_done=on_done, timeout=10.0)
        else:
            QtCore.QTimer.singleShot(800, lambda: [
                tile.sub_label.setText("Emergency stop triggered (offline mode)."),
                QtCore.QTimer.singleShot(2500, lambda: self._reset_card(tile))
            ])

    def _on_host_reboot(self, tile: PowerActionCard):
        tile.sub_label.setText("Sending host reboot command...")
        tile.badge_lbl.setText("REBOOTING...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected and hasattr(mr, "post_endpoint"):
            def on_done(ok):
                tile.sub_label.setText("System rebooting now..." if ok else "Failed to reboot host.")
                tile.badge_lbl.setText("SENT" if ok else "ERROR")
                QtCore.QTimer.singleShot(3000, lambda: self._reset_card(tile))
            mr.post_endpoint("/machine/reboot", on_done=on_done, timeout=10.0)
        else:
            QtCore.QTimer.singleShot(900, lambda: [
                tile.sub_label.setText("Host reboot simulated (offline mode)."),
                QtCore.QTimer.singleShot(2000, lambda: self._reset_card(tile))
            ])

    def _on_host_shutdown(self, tile: PowerActionCard):
        tile.sub_label.setText("Sending host shutdown command...")
        tile.badge_lbl.setText("SHUTTING DOWN...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected and hasattr(mr, "post_endpoint"):
            def on_done(ok):
                tile.sub_label.setText("System powering down safely..." if ok else "Failed to shut down host.")
                tile.badge_lbl.setText("SENT" if ok else "ERROR")
                QtCore.QTimer.singleShot(3000, lambda: self._reset_card(tile))
            mr.post_endpoint("/machine/shutdown", on_done=on_done, timeout=10.0)
        else:
            QtCore.QTimer.singleShot(900, lambda: [
                tile.sub_label.setText("Host shutdown simulated (offline mode)."),
                QtCore.QTimer.singleShot(2000, lambda: self._reset_card(tile))
            ])

    def _reset_card(self, tile: PowerActionCard):
        tile.title_label.setText(tile.default_title)
        tile.sub_label.setText(tile.default_subtitle)
        tile.badge_lbl.setText(tile.default_badge)

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(14, s)
        self.vbox.setContentsMargins(m, m, m, m)
        self.vbox.setSpacing(_s(8, s))
        self.grid1.setHorizontalSpacing(_s(12, s))
        self.grid1.setVerticalSpacing(_s(10, s))
        self.grid2.setHorizontalSpacing(_s(12, s))
        self.grid2.setVerticalSpacing(_s(10, s))
        for h in self.headers:
            h.setStyleSheet(f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8; margin-top: {_s(6, s)}px; margin-bottom: {_s(2, s)}px;")
        for card in self.cards:
            card.apply_scale(s)

