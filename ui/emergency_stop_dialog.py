"""Touch-friendly in-window overlay for Emergency Stop (M112) confirmation.

Designed for embedded touchscreens and kiosk mode (framebuffer, X11, Wayland).
Renders directly within the MainWindow as a dimmed modal overlay with zero window-manager dependencies.
"""

from .qt import QtWidgets, QtCore, Qt
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class EmergencyStopOverlay(QtWidgets.QFrame):
    """Full-screen darkened modal overlay with touch-friendly Emergency Stop confirmation."""

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("EstopOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#EstopOverlay { background: rgba(5, 10, 20, 0.82); }")

        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Main alert card
        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("EmergencyStopCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet(f"""
            QFrame#EmergencyStopCard {{
                background: #0F172A;
                border: 2px solid #EF4444;
                border-radius: {_s(14, scale)}px;
            }}
        """)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setContentsMargins(_s(24, scale), _s(22, scale), _s(24, scale), _s(22, scale))
        card_layout.setSpacing(_s(16, scale))

        # Header with icon and title
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(_s(12, scale))

        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setPixmap(icons.pixmap("estop", _s(36, scale)))
        header_layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QtWidgets.QLabel("EMERGENCY STOP")
        title_lbl.setStyleSheet(f"color: #EF4444; font-size: {_s(17, scale)}px; font-weight: 900; letter-spacing: 0.8px;")
        sub_title = QtWidgets.QLabel("Klipper Firmware Halt (M112)")
        sub_title.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 700;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_title)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)

        card_layout.addLayout(header_layout)

        # Message
        msg_lbl = QtWidgets.QLabel(
            "Are you sure you want to trigger an immediate emergency stop?\n\n"
            "This will instantly cut off all heaters, halt all stepper motors, "
            "and terminate the current print job."
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: #E2E8F0; font-size: {_s(12, scale)}px; line-height: 1.45;")
        card_layout.addWidget(msg_lbl)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(_s(12, scale))

        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(_s(44, scale))
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 700;
                padding: 0 {_s(20, scale)}px;
            }}
            QPushButton:hover {{
                background: #475569;
                border-color: #64748B;
            }}
            QPushButton:pressed {{
                background: #1E293B;
            }}
        """)
        self.btn_cancel.clicked.connect(self.close)

        self.btn_halt = QtWidgets.QPushButton("HALT PRINTER NOW")
        self.btn_halt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_halt.setFixedHeight(_s(44, scale))
        self.btn_halt.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF4444, stop:1 #B91C1C);
                color: #FFFFFF;
                border: 1px solid #F87171;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 900;
                letter-spacing: 0.5px;
                padding: 0 {_s(22, scale)}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F87171, stop:1 #DC2626);
                border: 1px solid #FCA5A5;
            }}
            QPushButton:pressed {{
                background: #7F1D1D;
                border: 1px solid #DC2626;
            }}
        """)
        self.btn_halt.clicked.connect(self._on_halt_clicked)

        btn_layout.addWidget(self.btn_cancel, 1)
        btn_layout.addWidget(self.btn_halt, 2)
        card_layout.addLayout(btn_layout)

        outer.addWidget(self.card)
        self.card.setFixedWidth(_s(450, scale))

    def _on_halt_clicked(self):
        win = self.window()
        mr = getattr(win, "moonraker", None)
        if mr:
            mr.emergency_stop()
        self.close()

    def mousePressEvent(self, event):
        # Prevent click-through to widgets underneath
        event.accept()
