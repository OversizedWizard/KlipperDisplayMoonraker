import sys
"""Base screen widgets: left sidebar, top bar, placeholder pages, main window."""

from datetime import datetime

from . import icons
from .home_page import HomePage
from .calibrate_page import CalibratePage
from .power_page import PowerPage
from .spool_page import SpoolPage
from .moonraker import MoonrakerClient
from .settings_page import SettingsPage
from .qt import QtCore, QtWidgets, Qt, Signal
from .theme import BASE_W, BASE_H, build_stylesheet

# key, sidebar label, page title, page description
NAV_ITEMS = [
    ("home", "Home", "Home", "Printer dashboard - temperatures, job progress and quick controls."),
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
        self.buttons[key].setChecked(True)

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
            short_host = host.split(":")[0]
            self.status.setText(f"\u25CF  CONNECTED ({short_host})")
            state = "connected"
        elif connected:
            short_host = host.split(":")[0]
            self.status.setText(f"\u25CF  {klippy_state.upper()} ({short_host})")
            state = "standby"
        else:
            self.status.setText("\u25CF  NOT CONNECTED")
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
        self.moonraker.coords_updated.connect(self.pages["home"].update_coords)
        self.moonraker.load_cell_updated.connect(self.topbar.set_probe_force)

        # Debounce re-scaling while the window is being resized.
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self.apply_scale)

        self.show_page("home")
        self.apply_scale()
        for page in self.pages.values():
            page.moonraker = self.moonraker
        self.moonraker.start()

    def _on_connection_changed(self, connected: bool, host: str, klippy_state: str):
        self.topbar.set_connection(connected, host, klippy_state)
        if hasattr(self.pages["settings"], "update_connection"):
            self.pages["settings"].update_connection(connected, host, klippy_state)
        if not connected:
            self.topbar.set_load_cell_visible(False)

    def _on_config_loaded(self, config: dict, objects: list):
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

        if hasattr(widget, "apply_scale") and self._scale:
            widget.apply_scale(self._scale)

        self.stack.setCurrentWidget(self.sub_screen_page)

    def close_sub_screen(self):
        """Close the active sub-screen and return to the previous main page."""
        target_page = getattr(self, "_sub_return_page", "home") or "home"
        self._clear_sub_screen()
        self.show_page(target_page)

    def _clear_sub_screen(self):
        if hasattr(self, "_active_sub_widget") and self._active_sub_widget:
            w = self._active_sub_widget
            self._active_sub_widget = None
            if hasattr(w, "close"):
                try:
                    w.close()
                except Exception:
                    pass
            self.sub_screen_layout.removeWidget(w)
            w.setParent(None)

    def show_page(self, key: str):
        if hasattr(self, "_active_sub_widget") and self._active_sub_widget:
            self._clear_sub_screen()
        self._current_page = key
        self.stack.setCurrentWidget(self.pages[key])
        self.sidebar.set_active(key)
        title = next(t for k, _l, t, _d in NAV_ITEMS if k == key)
        self.topbar.set_title(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

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
