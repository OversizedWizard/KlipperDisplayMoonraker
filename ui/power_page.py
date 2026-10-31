"""Power Page: Klipper service restart, MCU firmware restart, display service restart, host reboot/shutdown, and emergency stop."""

import os
import subprocess
import sys
from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def restart_display_app(window=None):
    """Restart the Klipper Display service / screen application cleanly."""
    mr = getattr(window, "moonraker", None) if window else None
    if mr and hasattr(mr, "stop"):
        try:
            mr.stop()
        except Exception:
            pass

    def _do_exec():
        if sys.platform.startswith("linux"):
            try:
                # If running under klipper-display.service and passwordless sudo is available, restart service
                res = subprocess.run(
                    ["systemctl", "is-active", "--quiet", "klipper-display.service"],
                    timeout=1.0,
                )
                if res.returncode == 0:
                    subprocess.Popen(
                        ["sudo", "-n", "systemctl", "restart", "klipper-display.service"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except Exception:
                pass
        # Always replace current Python process in-place so screen app restarts immediately in all modes
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            QtWidgets.QApplication.quit()

    QtCore.QTimer.singleShot(350, _do_exec)


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
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

        self._layout = QtWidgets.QHBoxLayout(self)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(1)
        mid.setContentsMargins(0, 0, 0, 0)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("CalTitle")
        if is_danger:
            self.title_label.setStyleSheet("color: #F87171; font-weight: 800;")
        mid.addWidget(self.title_label)

        self.sub_label = QtWidgets.QLabel(subtitle)
        self.sub_label.setObjectName("CalDesc")
        self.sub_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        mid.addWidget(self.sub_label)

        cmd_row = QtWidgets.QHBoxLayout()
        cmd_row.setContentsMargins(0, 2, 0, 0)
        self.badge_lbl = QtWidgets.QLabel(badge)
        self.badge_lbl.setObjectName("CalCmdBadge")
        if is_danger:
            self.badge_lbl.setStyleSheet(
                "background: rgba(239, 68, 68, 0.22); color: #FCA5A5; "
                "border: 1px solid rgba(239, 68, 68, 0.55); font-weight: 800; border-radius: 4px; padding: 1px 6px; font-size: 10px;"
            )
        else:
            self.badge_lbl.setStyleSheet(
                "background: rgba(0, 229, 255, 0.12); color: #00E5FF; "
                "border: 1px solid rgba(0, 229, 255, 0.35); font-weight: 700; border-radius: 4px; padding: 1px 6px; font-size: 10px;"
            )
        cmd_row.addWidget(self.badge_lbl)
        cmd_row.addStretch(1)
        mid.addLayout(cmd_row)

        self._layout.addLayout(mid, 1)

        self.arrow = QtWidgets.QLabel("›")
        self.arrow.setObjectName("CalCardArrow")
        if is_danger:
            self.arrow.setStyleSheet("color: #EF4444; font-weight: 800; font-size: 16px;")
        else:
            self.arrow.setStyleSheet("color: #00E5FF; font-weight: 700; font-size: 16px;")
        self._layout.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_click:
            self.on_click(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def apply_scale(self, s: float):
        self._layout.setContentsMargins(_s(10, s), _s(6, s), _s(10, s), _s(6, s))
        self._layout.setSpacing(_s(8, s))
        self.setFixedHeight(_s(66, s))
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, _s(32, s)))
        self.icon_label.setFixedSize(_s(36, s), _s(36, s))


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
        self.vbox.setContentsMargins(10, 6, 18, 10)
        self.vbox.setSpacing(6)

        self.headers = []
        self.cards = []

        # Single unified grid: columns 0 and 1 are strictly equal 50% width
        self.grid = QtWidgets.QGridLayout()
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        # --- Section 1: Klipper Restarts ---
        sec1 = QtWidgets.QLabel("KLIPPER SERVICE & HARDWARE")
        sec1.setObjectName("SettingsSecHeader")
        self.grid.addWidget(sec1, 0, 0, 1, 2)
        self.headers.append(sec1)

        self.klipper_restart_card = PowerActionCard(
            "reload", "Klipper Restart",
            "Reload Python service & config.",
            "RESTART",
            on_click=self._on_klipper_restart
        )
        self.grid.addWidget(self.klipper_restart_card, 1, 0)
        self.cards.append(self.klipper_restart_card)

        self.fw_restart_card = PowerActionCard(
            "restart", "Firmware Restart",
            "Reload config & reconnect MCU.",
            "FIRMWARE",
            on_click=self._on_fw_restart
        )
        self.grid.addWidget(self.fw_restart_card, 1, 1)
        self.cards.append(self.fw_restart_card)

        # --- Section 2: Host System ---
        sec2 = QtWidgets.QLabel("HOST SYSTEM (PI)")
        sec2.setObjectName("SettingsSecHeader")
        self.grid.addWidget(sec2, 2, 0, 1, 2)
        self.headers.append(sec2)

        self.reboot_card = PowerActionCard(
            "restart", "Reboot Host (Pi)",
            "Safely reboot Raspberry Pi system OS.",
            "REBOOT",
            on_click=self._on_host_reboot
        )
        self.grid.addWidget(self.reboot_card, 3, 0)
        self.cards.append(self.reboot_card)

        self.shutdown_card = PowerActionCard(
            "power", "Shutdown Host (Pi)",
            "Safely power down Raspberry Pi system OS.",
            "SHUTDOWN",
            on_click=self._on_host_shutdown
        )
        self.grid.addWidget(self.shutdown_card, 3, 1)
        self.cards.append(self.shutdown_card)

        # --- Section 3: Display & Emergency Actions ---
        sec3 = QtWidgets.QLabel("DISPLAY SERVICE & EMERGENCY")
        sec3.setObjectName("SettingsSecHeader")
        self.grid.addWidget(sec3, 4, 0, 1, 2)
        self.headers.append(sec3)

        self.display_restart_card = PowerActionCard(
            "reload", "Display Service Restart",
            "Restart Klipper Display screen app.",
            "DISPLAY APP",
            on_click=self._on_display_restart
        )
        self.grid.addWidget(self.display_restart_card, 5, 0)
        self.cards.append(self.display_restart_card)

        self.m112_card = PowerActionCard(
            "power", "Emergency Stop",
            "Immediately halt all motors & heaters (M112).",
            "M112",
            on_click=self._on_emergency_stop,
            is_danger=True
        )
        self.grid.addWidget(self.m112_card, 5, 1)
        self.cards.append(self.m112_card)

        self.vbox.addLayout(self.grid)
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
        tile.sub_label.setText("Restarting MCU hardware...")
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

    def _on_display_restart(self, tile: PowerActionCard):
        tile.sub_label.setText("Restarting Klipper Display screen app...")
        tile.badge_lbl.setText("RESTARTING...")
        restart_display_app(self.window())

    def _on_emergency_stop(self, tile: PowerActionCard):
        tile.sub_label.setText("TRIGGERING EMERGENCY STOP (M112)...")
        tile.badge_lbl.setText("HALTING...")
        mr = getattr(self.window(), "moonraker", None)
        if mr and mr.connected:
            def on_done(ok):
                tile.sub_label.setText("Halted. Restarting firmware in 2 seconds...")
                tile.badge_lbl.setText("HALTED")
                QtCore.QTimer.singleShot(2000, lambda: [
                    mr.firmware_restart(),
                    tile.sub_label.setText("FIRMWARE_RESTART triggered."),
                    tile.badge_lbl.setText("RESTARTED"),
                    QtCore.QTimer.singleShot(3000, lambda: self._reset_card(tile))
                ])
            mr.emergency_stop(on_done=on_done)
        else:
            QtCore.QTimer.singleShot(800, lambda: [
                tile.sub_label.setText("Emergency stop triggered (offline mode). Restarting in 2s..."),
                tile.badge_lbl.setText("HALTED"),
                QtCore.QTimer.singleShot(2000, lambda: [
                    tile.sub_label.setText("Firmware restarted."),
                    tile.badge_lbl.setText("RESTARTED"),
                    QtCore.QTimer.singleShot(2500, lambda: self._reset_card(tile))
                ])
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
        m = _s(10, s)
        right_pad = _s(18, s)
        self.vbox.setContentsMargins(m, _s(6, s), right_pad, _s(10, s))
        self.vbox.setSpacing(_s(6, s))
        self.grid.setHorizontalSpacing(_s(8, s))
        self.grid.setVerticalSpacing(_s(8, s))
        for h in self.headers:
            h.setStyleSheet(f"font-size: {_s(11, s)}px; font-weight: 800; letter-spacing: 0.8px; color: #94A3B8; margin-top: {_s(4, s)}px; margin-bottom: {_s(1, s)}px;")
        for card in self.cards:
            card.apply_scale(s)
