import sys
"""Base screen widgets: left sidebar, top bar, placeholder pages, main window."""

from datetime import datetime

from . import icons
from .home_page import HomePage
from .files_page import FilesPage
from .printing_page import PrintingPage
from .calibrate_page import CalibratePage
from .power_page import PowerPage
from .spool_page import SpoolPage
from .moonraker import MoonrakerClient
from .settings_page import SettingsPage, load_display_settings
from .qt import QtCore, QtWidgets, Qt, Signal
from .theme import BASE_W, BASE_H, build_stylesheet

# key, sidebar label, page title, page description
NAV_ITEMS = [
    ("home", "Home", "Home", "Printer dashboard - temperatures, job progress and quick controls."),
    ("files", "Print", "Print Files", "Browse local gcode files and start 3D prints."),
    ("spool", "Spool", "Spool", "Filament load / unload and spool management."),
    ("settings", "Settings", "Settings", "Printer, network, display and system configuration."),
    ("calibrate", "Calibrate", "Calibration", "Klipper hardware calibration and machine tuning."),
    ("power", "Power", "Power", "Restart, shutdown, firmware restart and emergency stop."),
]


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class Sidebar(QtWidgets.QFrame):
    page_selected = Signal(str)

    def __init__(self, host: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")

        self._layout = QtWidgets.QVBoxLayout(self)

        self.logo = QtWidgets.QLabel()
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.logo)
        self._layout.addSpacing(4)

        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}

        for key, label, _title, _desc in NAV_ITEMS:
            if key == "calibrate":
                self._layout.addStretch(1)  # Calibrate & Power sit at the bottom
            btn = QtWidgets.QToolButton()
            btn.setObjectName("NavButton")
            btn.setText(label)
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                              QtWidgets.QSizePolicy.Policy.Fixed)
            if key == "power":
                btn.setProperty("accent", "danger")
            btn.clicked.connect(lambda _checked=False, k=key: self.page_selected.emit(k))
            self.group.addButton(btn)
            self._layout.addWidget(btn)
            self.buttons[key] = btn

    def set_active(self, key: str):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def set_print_state(self, state: str):
        if "files" in self.buttons:
            btn = self.buttons["files"]
            if state in ("printing", "paused"):
                btn.setText("Printing")
            else:
                btn.setText("Print")

    def apply_scale(self, s: float):
        self.setFixedWidth(_s(86, s))
        m = _s(8, s)
        self._layout.setContentsMargins(m, _s(10, s), m, _s(10, s))
        self._layout.setSpacing(_s(6, s))
        self.logo.setPixmap(icons.pixmap("logo", _s(40, s)))
        size = _s(26, s)
        for key, btn in self.buttons.items():
            btn.setIcon(icons.icon(key, size))
            btn.setIconSize(QtCore.QSize(size, size))
            btn.setFixedHeight(_s(54, s))


class TopBar(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self._layout = QtWidgets.QHBoxLayout(self)

        self.back_btn = QtWidgets.QPushButton("‹ Back")
        self.back_btn.setObjectName("TopBackBtn")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._on_back_click)
        self._layout.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(0)
        self.title = QtWidgets.QLabel("Home")
        self.title.setObjectName("PageTitle")
        self.printer = QtWidgets.QLabel("KLIPPER PRINTER")
        self.printer.setObjectName("PrinterName")
        titles.addWidget(self.printer)
        titles.addWidget(self.title)
        titles.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._layout.addLayout(titles)
        self._layout.addStretch(1)

        self.estop_btn = QtWidgets.QPushButton("EMERGENCY STOP")
        self.estop_btn.setObjectName("EmergencyStopBtn")
        self.estop_btn.setToolTip("Emergency Stop - Immediately halt motors and heaters (M112)")
        self.estop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.estop_btn.clicked.connect(self._on_estop_click)
        self._layout.addWidget(self.estop_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.status = QtWidgets.QLabel("\u25CF  NOT CONNECTED")
        self.status.setObjectName("StatusPill")
        self._layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignVCenter)

        self.probe_force = QtWidgets.QLabel("0.0 g")
        self.probe_force.setObjectName("ProbePill")
        self.probe_force.setToolTip("Live Load Cell Probe Force (tap for Weight Test)")
        self.probe_force.setCursor(Qt.CursorShape.PointingHandCursor)
        self.probe_force.mousePressEvent = self._on_probe_click
        self.probe_force.setVisible(False)
        self._layout.addWidget(self.probe_force, 0, Qt.AlignmentFlag.AlignVCenter)

        self.clock = QtWidgets.QLabel()
        self.clock.setObjectName("Clock")
        self._layout.addWidget(self.clock, 0, Qt.AlignmentFlag.AlignVCenter)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _on_back_click(self):
        main_win = self.window()
        if hasattr(main_win, "close_sub_screen"):
            main_win.close_sub_screen()

    def set_back_visible(self, visible: bool):
        self.back_btn.setVisible(visible)

    def _on_estop_click(self):
        main_win = self.window()
        from .emergency_stop_dialog import EmergencyStopOverlay
        if getattr(main_win, "_estop_overlay", None) and main_win._estop_overlay.isVisible():
            return
        overlay = EmergencyStopOverlay(parent=main_win, scale=getattr(self, "_scale", 1.0))
        main_win._estop_overlay = overlay
        overlay.setGeometry(main_win.rect())
        overlay.show()
        overlay.raise_()

    def _on_probe_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            main_win = self.window()
            from .load_cell_test_dialog import LoadCellWeightTestDialog
            view = LoadCellWeightTestDialog(scale=getattr(self, "_scale", 1.0), parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Load Cell Weight Test", return_page=getattr(main_win, "_current_page", "home"))
            else:
                view.show()
            event.accept()
        else:
            super(QtWidgets.QLabel, self.probe_force).mousePressEvent(event)

    def set_probe_force(self, grams: float):
        sign = "+" if grams > 0 else ""
        self.probe_force.setText(f"{sign}{grams:.1f} g")
        state = "alert" if abs(grams) > 20.0 else "normal"
        if self.probe_force.property("state") != state:
            self.probe_force.setProperty("state", state)
            self.probe_force.style().unpolish(self.probe_force)
            self.probe_force.style().polish(self.probe_force)

    def set_load_cell_visible(self, visible: bool):
        self.probe_force.setVisible(visible)

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%H:%M"))

    def set_title(self, text: str):
        self.title.setText(text)

    def set_connection(self, connected: bool, host: str, klippy_state: str):
        if connected and klippy_state == "ready":
            self.status.setText("\u25CF  CONNECTED")
            self.status.setToolTip(f"Connected to {host}")
            state = "connected"
        elif connected:
            self.status.setText(f"\u25CF  {klippy_state.upper()}")
            self.status.setToolTip(f"State: {klippy_state} ({host})")
            state = "standby"
        else:
            self.status.setText("\u25CF  NOT CONNECTED")
            self.status.setToolTip("Disconnected from Moonraker")
            state = "disconnected"
        if self.status.property("state") != state:
            self.status.setProperty("state", state)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    def apply_scale(self, s: float):
        self._scale = s
        self.setFixedHeight(_s(50, s))
        self._layout.setContentsMargins(_s(18, s), 0, _s(16, s), 0)
        self._layout.setSpacing(_s(10, s))
        self.estop_btn.setFixedHeight(_s(30, s))
        icon_sz = _s(16, s)
        self.estop_btn.setIcon(icons.icon("estop", icon_sz))
        self.estop_btn.setIconSize(QtCore.QSize(icon_sz, icon_sz))

class PlaceholderPage(QtWidgets.QWidget):
    """Empty page shell - real content gets built per page later."""

    def __init__(self, key: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._outer = QtWidgets.QVBoxLayout(self)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("Card")
        self._outer.addWidget(self.card)

        self._inner = QtWidgets.QVBoxLayout(self.card)
        self._inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon = QtWidgets.QLabel()
        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName("Hero")
        self.desc = QtWidgets.QLabel(desc)
        self.desc.setObjectName("Subtitle")
        self.desc.setWordWrap(True)
        self.chip = QtWidgets.QLabel("INTERFACE COMING NEXT")
        self.chip.setObjectName("Chip")

        for w in (self.icon, self.title, self.desc, self.chip):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._inner.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)

    def apply_scale(self, s: float):
        m = _s(16, s)
        self._outer.setContentsMargins(m, m, m, m)
        self._inner.setContentsMargins(_s(24, s), _s(24, s), _s(24, s), _s(24, s))
        self._inner.setSpacing(_s(12, s))
        self.icon.setPixmap(icons.pixmap(self.key, _s(128, s)))
        self.desc.setMaximumWidth(_s(460, s))


class MainWindow(QtWidgets.QWidget):
    def __init__(self, host: str = None):
        super().__init__()
        self.setObjectName("Root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Klipper 3D Display")
        self.setMinimumSize(400, 240)
        self._scale = None

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self.topbar = TopBar()
        main.addWidget(self.topbar)
        self.stack = QtWidgets.QStackedWidget()
        main.addWidget(self.stack, 1)
        root.addLayout(main, 1)

        self.pages = {}
        for key, _label, title, desc in NAV_ITEMS:
            if key == "home":
                page = HomePage()
            elif key == "files":
                page = FilesPage()
            elif key == "spool":
                page = SpoolPage()
            elif key == "calibrate":
                page = CalibratePage()
            elif key == "settings":
                page = SettingsPage()
            elif key == "power":
                page = PowerPage()
            else:
                page = PlaceholderPage(key, title, desc)
            self.stack.addWidget(page)
            self.pages[key] = page

        # Dedicated live printing page
        self.printing_page = PrintingPage()
        self.stack.addWidget(self.printing_page)
        self.pages["printing"] = self.printing_page

        # Embedded in-window screen container for full-page procedures & settings
        self.sub_screen_page = QtWidgets.QWidget()
        self.sub_screen_layout = QtWidgets.QVBoxLayout(self.sub_screen_page)
        self.sub_screen_layout.setContentsMargins(6, 4, 6, 6)
        self.sub_screen_layout.setSpacing(0)
        self.stack.addWidget(self.sub_screen_page)
        self._active_sub_widget = None
        self._sub_return_page = "home"
        self._current_page = "home"

        self.sidebar.page_selected.connect(self.show_page)

        # Live Moonraker client: on Windows PC, allow LAN printer testing (192.168.0.99);
        # on Linux/Raspberry Pi (Git release), strictly use local 127.0.0.1:7125.
        if host:
            hosts = [host]
        elif sys.platform.startswith("win"):
            hosts = ["127.0.0.1:7125", "192.168.0.99:7125"]
        else:
            hosts = ["127.0.0.1:7125"]
        self.moonraker = MoonrakerClient(hosts=hosts, parent=self)
        self.moonraker.connection_changed.connect(self._on_connection_changed)
        self.moonraker.config_loaded.connect(self._on_config_loaded)
        self.moonraker.firmware_info_updated.connect(self.pages["settings"].update_firmware_info)
        self.moonraker.temps_updated.connect(self.pages["home"].update_temps)
        if "spool" in self.pages and hasattr(self.pages["spool"], "update_temps"):
            self.moonraker.temps_updated.connect(self.pages["spool"].update_temps)
        if "printing" in self.pages and hasattr(self.pages["printing"], "update_temps"):
            self.moonraker.temps_updated.connect(self.pages["printing"].update_temps)
        self.moonraker.coords_updated.connect(self.pages["home"].update_coords)
        self.moonraker.load_cell_updated.connect(self.topbar.set_probe_force)
        self.moonraker.print_stats_updated.connect(self._on_print_stats_updated)
        if hasattr(self.pages.get("home"), "update_bed_mesh"):
            self.moonraker.bed_mesh_updated.connect(self.pages["home"].update_bed_mesh)

        # Debounce re-scaling while the window is being resized.
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self.apply_scale)

        self.show_page("home")
        self.apply_scale()
        for page in self.pages.values():
            page.moonraker = self.moonraker

        # Screen Sleep Timer & Inactivity Monitor (user config in ~/.klipper_display_settings.json)
        self._sleeping = False
        self._sleep_overlay = None
        self._last_filament_used_mm = 0.0
        self._sleep_timer = QtCore.QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self.enter_sleep_mode)
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)
        self.reload_sleep_settings()

        self.moonraker.start()

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.TouchBegin,
            QtCore.QEvent.Type.KeyPress,
            QtCore.QEvent.Type.Wheel,
        ):
            if getattr(self, "_sleeping", False):
                self.wake_from_sleep()
                return True
            self._reset_sleep_timer()
        return super().eventFilter(obj, event)

    def reload_sleep_settings(self):
        cfg = load_display_settings()
        self._sleep_timeout_min = int(cfg.get("sleep_timeout_min", 10))
        self._reset_sleep_timer()

    def _reset_sleep_timer(self):
        if not hasattr(self, "_sleep_timer"):
            return
        self._sleep_timer.stop()
        mins = getattr(self, "_sleep_timeout_min", 10)
        if mins > 0 and not getattr(self, "_sleeping", False):
            self._sleep_timer.start(mins * 60 * 1000)

    def enter_sleep_mode(self):
        if getattr(self, "_sleeping", False):
            return
        self._sleeping = True
        self._sleep_timer.stop()
        if not self._sleep_overlay:
            ov = QtWidgets.QFrame(self)
            ov.setObjectName("SleepOverlay")
            ov.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            ov.setStyleSheet("QFrame#SleepOverlay { background: #020409; } QLabel { background: transparent; border: none; }")
            lay = QtWidgets.QVBoxLayout(ov)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.setSpacing(10)

            self._slp_clock = QtWidgets.QLabel(datetime.now().strftime("%H:%M"))
            self._slp_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._slp_clock.setStyleSheet("color: rgba(248, 250, 252, 0.28); font-size: 64px; font-weight: 900; font-family: monospace;")
            lay.addWidget(self._slp_clock)

            self._slp_info = QtWidgets.QLabel("Nozzle: --°C  •  Bed: --°C  •  STANDBY")
            self._slp_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._slp_info.setStyleSheet("color: rgba(148, 163, 184, 0.45); font-size: 15px; font-weight: 800; font-family: monospace;")
            lay.addWidget(self._slp_info)

            hint = QtWidgets.QLabel("🌙 LOW-POWER SLEEP MODE  •  TOUCH ANYWHERE TO WAKE")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet("color: rgba(100, 116, 139, 0.38); font-size: 11px; font-weight: 800; letter-spacing: 1.2px; margin-top: 18px;")
            lay.addWidget(hint)
            self._sleep_overlay = ov

        self._update_sleep_overlay_text()
        self._sleep_overlay.setGeometry(self.rect())
        self._sleep_overlay.show()
        self._sleep_overlay.raise_()

    def _update_sleep_overlay_text(self):
        if not getattr(self, "_sleeping", False) or not self._sleep_overlay:
            return
        self._slp_clock.setText(datetime.now().strftime("%H:%M"))
        mr = getattr(self, "moonraker", None)
        if mr:
            st = mr.last_print_stats or {}
            p_st = str(st.get("state", "standby")).upper()
            pct = int(float(st.get("progress", 0.0)) * 100)
            p_txt = f"{p_st} ({pct}%)" if p_st == "PRINTING" else p_st
            self._slp_info.setText(f"🔥 Nozzle {mr.nozzle_temp:.0f}°C   •   🛏 Bed {mr.bed_temp:.0f}°C   •   {p_txt}")

    def wake_from_sleep(self):
        if getattr(self, "_sleeping", False):
            self._sleeping = False
            if self._sleep_overlay:
                self._sleep_overlay.hide()
        self._reset_sleep_timer()

    def _on_print_stats_updated(self, st: dict):
        state = st.get("state", "standby")
        prev_state = getattr(self, "_last_raw_print_state", None)
        self._last_raw_print_state = state
        filename = st.get("filename", "") or ""
        prev_file = getattr(self, "_last_raw_print_file", None)
        self._last_raw_print_file = filename

        # Auto-deduct filament used during print from active spool
        used_mm = float(st.get("filament_used", 0.0) or 0.0)
        if used_mm < getattr(self, "_last_filament_used_mm", 0.0):
            self._last_filament_used_mm = 0.0
        if state == "printing" and used_mm > self._last_filament_used_mm + 20.0:
            delta_mm = used_mm - self._last_filament_used_mm
            self._last_filament_used_mm = used_mm
            if "spool" in self.pages and hasattr(self.pages["spool"], "deduct_filament_mm"):
                self.pages["spool"].deduct_filament_mm(delta_mm)

        if getattr(self, "_sleeping", False):
            self._update_sleep_overlay_text()
            if prev_state is not None and state != prev_state and state in ("printing", "complete", "error", "paused"):
                self.wake_from_sleep()

        if "printing" in self.pages:
            pp = self.pages["printing"]
            if state == "printing" and (prev_state != "printing" or filename != prev_file):
                pp._print_state = "printing"
            pp.update_print_stats(st)

        if hasattr(self.sidebar, "set_print_state"):
            self.sidebar.set_print_state(state)

        # Automatically switch to printing screen when a print starts (locally or remotely from Orca/Mainsail)
        just_started = (
            state in ("printing", "paused")
            and (prev_state not in ("printing", "paused") or (filename and filename != prev_file))
        )
        if just_started or (state == "printing" and getattr(self, "_current_page", "") == "files"):
            if getattr(self.pages.get("printing"), "_print_state", "") != "cancelled":
                if getattr(self, "_current_page", "") != "printing":
                    self.show_page("printing")
        # If print has cancelled while on printing page, set cooldown and return to home page
        elif state in ("cancelled", "cancelling") and getattr(self, "_current_page", "") == "printing":
            if hasattr(self, "moonraker") and self.moonraker:
                self.moonraker.cooldown()
            self.show_page("home")

    def _on_connection_changed(self, connected: bool, host: str, klippy_state: str):
        self.topbar.set_connection(connected, host, klippy_state)
        if hasattr(self.pages["settings"], "update_connection"):
            self.pages["settings"].update_connection(connected, host, klippy_state)
        if connected and klippy_state == "ready":
            last_state = getattr(self, "_last_klippy_state", "")
            if last_state != "ready":
                if hasattr(self.pages.get("home"), "_check_mesh_config"):
                    self.pages["home"]._check_mesh_config()
            self._last_klippy_state = "ready"
        else:
            self._last_klippy_state = klippy_state
        if not connected:
            self.topbar.set_load_cell_visible(False)

    def _on_config_loaded(self, config: dict, objects: list):
        if hasattr(self.pages.get("home"), "update_config"):
            self.pages["home"].update_config(config, objects)
        if hasattr(self.pages.get("calibrate"), "update_config"):
            self.pages["calibrate"].update_config(config, objects)
        if hasattr(self.pages.get("settings"), "update_config"):
            self.pages["settings"].update_config(config, objects)
        if hasattr(self.pages.get("spool"), "update_config"):
            self.pages["spool"].update_config(config, objects)
        has_lc = self.moonraker.has_load_cell(config, objects)
        self.topbar.set_load_cell_visible(has_lc)

    def open_sub_screen(self, widget: QtWidgets.QWidget, title: str = "", return_page: str = None):
        """Show a calibration, setting, preheat, or info screen as the main screen
        in the window itself, instead of popping up a dialog window."""
        self._clear_sub_screen()
        self._active_sub_widget = widget
        self._sub_return_page = return_page or getattr(self, "_current_page", "home") or "home"

        self.sub_screen_layout.addWidget(widget)

        if hasattr(widget, "closed"):
            widget.closed.connect(self.close_sub_screen)

        if title:
            self.topbar.set_title(title)
        self.topbar.set_back_visible(True)

        if hasattr(widget, "apply_scale") and self._scale:
            widget.apply_scale(self._scale)

        self.stack.setCurrentWidget(self.sub_screen_page)

    def close_sub_screen(self):
        """Close the active sub-screen and return to the previous main page."""
        target_page = getattr(self, "_sub_return_page", "home") or "home"
        self._sub_return_page = "home"
        self._clear_sub_screen()
        self.topbar.set_back_visible(False)
        self._current_page = None  # Reset so show_page won't skip!
        self.show_page(target_page)

    def _clear_sub_screen(self):
        if hasattr(self, "_active_sub_widget") and self._active_sub_widget:
            w = self._active_sub_widget
            self._active_sub_widget = None
            if hasattr(w, "closed"):
                try:
                    w.closed.disconnect(self.close_sub_screen)
                except Exception:
                    pass
            if hasattr(w, "_cleanup"):
                try:
                    w._cleanup()
                except Exception:
                    pass
            if hasattr(w, "close"):
                try:
                    w.close()
                except Exception:
                    pass
            self.sub_screen_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()

    def show_page(self, key: str):
        if hasattr(self, "_active_sub_widget") and self._active_sub_widget:
            self._clear_sub_screen()
            self.topbar.set_back_visible(False)
        elif key == getattr(self, "_current_page", "") and self.stack.currentWidget() == self.pages.get(key):
            # Already on the requested page and showing it; ignore redundant rapid clicks
            return
        # If user taps Print in sidebar while actively printing, show the live print page
        if key == "files":
            mr = getattr(self, "moonraker", None)
            if mr and hasattr(mr, "last_print_stats") and mr.last_print_stats:
                st = mr.last_print_stats.get("state", "standby")
                if st in ("printing", "paused"):
                    key = "printing"
        self._current_page = key
        self.stack.setCurrentWidget(self.pages[key])
        sidebar_key = "files" if key == "printing" else key
        if sidebar_key in self.sidebar.buttons:
            self.sidebar.set_active(sidebar_key)
        if key == "printing":
            self.topbar.set_title("Active Print")
        else:
            title = next((t for k, _l, t, _d in NAV_ITEMS if k == key), "Klipper")
            self.topbar.set_title(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()
        if hasattr(self, "_estop_overlay") and self._estop_overlay and self._estop_overlay.isVisible():
            self._estop_overlay.setGeometry(self.rect())
        if hasattr(self, "_sleep_overlay") and self._sleep_overlay and self._sleep_overlay.isVisible():
            self._sleep_overlay.setGeometry(self.rect())

    def apply_scale(self):
        s = min(self.width() / BASE_W, self.height() / BASE_H)
        s = max(0.5, round(s, 2))
        if s == self._scale:
            return
        self._scale = s
        self.setStyleSheet(build_stylesheet(s))
        self.sidebar.apply_scale(s)
        self.topbar.apply_scale(s)
        for page in self.pages.values():
            page.apply_scale(s)
        if hasattr(self, "_active_sub_widget") and self._active_sub_widget:
            if hasattr(self._active_sub_widget, "apply_scale"):
                self._active_sub_widget.apply_scale(s)
