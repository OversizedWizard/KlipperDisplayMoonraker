"""Touch kinetic scrolling and touch gesture management for 800x480 touchscreen displays.

Ensures pages and lists (Settings, Calibration, Power, Files, Wi-Fi, etc.) can be
scrolled smoothly by dragging fingers without accidentally selecting or clicking items.
Supports natural touch-drag scrolling with smooth momentum/kinetic flick deceleration.
"""

from __future__ import annotations

import time
from PySide6 import QtCore, QtGui, QtWidgets

_is_dragging_globally: bool = False
_last_drag_ended_time: float = 0.0


def is_drag_active() -> bool:
    """Returns True if a kinetic scroll drag is currently active or just finished (< 280ms ago)."""
    return _is_dragging_globally or (time.time() - _last_drag_ended_time < 0.28)


def _gpos(event) -> QtCore.QPoint:
    """Extract global position as QPoint safely across Qt6 versions."""
    try:
        return event.globalPosition().toPoint()
    except AttributeError:
        return event.globalPos()


def _find_scroll_area(w: QtWidgets.QWidget | None) -> QtWidgets.QScrollArea | None:
    """Traverse up the widget hierarchy to find the enclosing QScrollArea."""
    while w is not None:
        if isinstance(w, QtWidgets.QScrollArea):
            return w
        w = w.parentWidget()
    return None


class KineticTouchFilter(QtCore.QObject):
    """Application-wide event filter that provides smooth kinetic drag-scrolling for all QScrollAreas.

    - Distinguishes intentional taps from drag-to-scroll gestures.
    - If the finger moves more than `threshold` pixels, drag scrolling begins immediately.
    - When dragging starts, any active button/tile down-state is cancelled.
    - When the drag finishes, the mouse release event is consumed so NO item is clicked or selected.
    - If released with flick velocity, smoothly glides the scrollbar to a stop with exponential deceleration.
    - If released without moving, passes the release event through so normal buttons and cards tap cleanly.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_scroll: QtWidgets.QScrollArea | None = None
        self.active_widget: QtWidgets.QWidget | None = None
        self.press_pos: QtCore.QPoint | None = None
        self.last_pos: QtCore.QPoint | None = None
        self.dragged: bool = False
        self.threshold: int = 8  # 8px jitter threshold for touchscreens
        self.samples: list[tuple[float, int]] = []
        self.velocity: float = 0.0

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)  # ~60 fps
        self.timer.timeout.connect(self._on_glide)

    def _on_glide(self):
        """Kinetic momentum glide step."""
        if not self.active_scroll or abs(self.velocity) < 0.5:
            self.velocity = 0.0
            self.timer.stop()
            self.active_scroll = None
            return

        sb = self.active_scroll.verticalScrollBar()
        if not sb or sb.maximum() <= sb.minimum():
            # If no vertical scrollbar, check horizontal
            sb = self.active_scroll.horizontalScrollBar()

        if not sb or sb.maximum() <= sb.minimum():
            self.velocity = 0.0
            self.timer.stop()
            self.active_scroll = None
            return

        old_val = sb.value()
        sb.setValue(int(old_val - self.velocity))
        if sb.value() == old_val:
            # Reached top or bottom boundary
            self.velocity = 0.0
            self.timer.stop()
            self.active_scroll = None
            return

        self.velocity *= 0.92  # Friction deceleration

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:
        global _is_dragging_globally, _last_drag_ended_time
        if not isinstance(obj, QtWidgets.QWidget):
            return False

        # Never intercept interactive sliders, scrollbars, or explicitly exempted widgets
        if isinstance(obj, (QtWidgets.QSlider, QtWidgets.QScrollBar)):
            return False
        if getattr(obj, "no_touch_scroll", False) or obj.property("no_touch_scroll"):
            return False

        t = ev.type()

        if t == QtCore.QEvent.Type.MouseButtonPress and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            _is_dragging_globally = False
            if self.timer.isActive():
                self.timer.stop()
                self.velocity = 0.0

            sa = _find_scroll_area(obj)
            if sa is not None:
                self.active_scroll = sa
                self.active_widget = obj
                self.press_pos = _gpos(ev)
                self.last_pos = self.press_pos
                self.dragged = False
                now = time.time()
                self.samples = [(now, self.press_pos.y())]

        elif t == QtCore.QEvent.Type.MouseMove and self.active_scroll is not None and self.press_pos is not None:
            pos = _gpos(ev)
            dy = pos.y() - self.last_pos.y()
            dx = pos.x() - self.last_pos.x()

            if not self.dragged:
                if abs(pos.y() - self.press_pos.y()) > self.threshold or abs(pos.x() - self.press_pos.x()) > self.threshold:
                    self.dragged = True
                    _is_dragging_globally = True
                    # Cancel pressed state on child widget if applicable
                    if self.active_widget and isinstance(self.active_widget, QtWidgets.QAbstractButton):
                        self.active_widget.setDown(False)

            if self.dragged:
                sb_v = self.active_scroll.verticalScrollBar()
                if sb_v and sb_v.maximum() > sb_v.minimum():
                    sb_v.setValue(sb_v.value() - dy)

                sb_h = self.active_scroll.horizontalScrollBar()
                if sb_h and sb_h.maximum() > sb_h.minimum():
                    sb_h.setValue(sb_h.value() - dx)

                self.last_pos = pos
                now = time.time()
                self.samples.append((now, pos.y()))
                # Keep samples from recent 120ms
                self.samples = [s for s in self.samples if now - s[0] <= 0.12]
                return True  # Swallow mouse move while dragging

        elif t == QtCore.QEvent.Type.MouseButtonRelease and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.active_scroll is not None:
                was_drag = self.dragged or _is_dragging_globally
                now = time.time()

                if was_drag:
                    _is_dragging_globally = False
                    _last_drag_ended_time = now

                # Calculate flick fling velocity
                if was_drag and len(self.samples) >= 2:
                    dt = self.samples[-1][0] - self.samples[0][0]
                    if dt > 0.01:
                        dy = self.samples[-1][1] - self.samples[0][1]
                        v = (dy / dt) * 0.016
                        self.velocity = max(-45.0, min(45.0, v))
                        if abs(self.velocity) > 1.2:
                            self.timer.start()

                self.press_pos = None
                self.dragged = False
                w = self.active_widget
                self.active_widget = None

                if not self.timer.isActive():
                    self.active_scroll = None

                if was_drag:
                    if w and isinstance(w, QtWidgets.QAbstractButton):
                        w.setDown(False)
                    return True  # SWALLOW RELEASE: Prevents button/card click after drag!

        return False


_global_scroller_installed = False
_global_scroller_instance: KineticTouchFilter | None = None


def install_global_touch_scroller(app: QtWidgets.QApplication | None = None) -> KineticTouchFilter:
    """Install touch kinetic drag-scrolling filter on the global application."""
    global _global_scroller_installed, _global_scroller_instance
    if _global_scroller_installed and _global_scroller_instance is not None:
        return _global_scroller_instance

    target_app = app or QtWidgets.QApplication.instance()
    if target_app is None:
        raise RuntimeError("QApplication instance must exist before installing touch scroller")

    _global_scroller_instance = KineticTouchFilter(target_app)
    target_app.installEventFilter(_global_scroller_instance)
    _global_scroller_installed = True
    return _global_scroller_instance


def touch_press(w: QtWidgets.QWidget, event: QtGui.QMouseEvent):
    """Helper for cards to initiate touch tracking."""
    w._touch_press_pos = _gpos(event)
    w._touch_last_pos = w._touch_press_pos
    w._touch_dragged = False


def touch_move(w: QtWidgets.QWidget, event: QtGui.QMouseEvent, threshold: int = 8) -> bool:
    """Helper for cards: returns True if a drag is underway."""
    if getattr(w, "_touch_press_pos", None) is None:
        return False
    pos = _gpos(event)
    if not getattr(w, "_touch_dragged", False):
        if abs(pos.y() - w._touch_press_pos.y()) > threshold or abs(pos.x() - w._touch_press_pos.x()) > threshold:
            w._touch_dragged = True
        else:
            return True
    return True


def touch_release(w: QtWidgets.QWidget) -> bool:
    """Helper for cards: returns True only if this was an intentional tap (no drag and scroller not active)."""
    was_pressed = getattr(w, "_touch_press_pos", None) is not None
    dragged = getattr(w, "_touch_dragged", False) or is_drag_active()
    w._touch_press_pos = None
    w._touch_dragged = False
    return was_pressed and not dragged
