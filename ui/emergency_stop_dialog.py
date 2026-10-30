"""Touch-friendly modal overlay for immediate emergency stop (M112) with green Firmware Restart action.

All elements (icons, titles, subtitles, messages, and action buttons) are completely centered.
Renders directly within the MainWindow as a dimmed modal overlay with zero window-manager dependencies.
"""

from .qt import QtWidgets, QtCore, Qt, Signal
from . import icons


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


class EmergencyStopOverlay(QtWidgets.QFrame):
    """Modal confirmation overlay for triggering immediate emergency stop (M112) and firmware restart."""
    closed = Signal()

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = scale
        self.setObjectName("EmergencyStopOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#EmergencyStopOverlay { background: rgba(5, 10, 20, 0.88); }")

        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Dialog Card Container
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
        card_layout.setContentsMargins(_s(24, scale), _s(24, scale), _s(24, scale), _s(24, scale))
        card_layout.setSpacing(_s(14, scale))
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Header with icon and title - ALL CENTERED
        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(icons.pixmap("estop", _s(40, scale)))
        card_layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.title_lbl = QtWidgets.QLabel("EMERGENCY STOP")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(f"color: #EF4444; font-size: {_s(18, scale)}px; font-weight: 900; letter-spacing: 0.8px;")
        card_layout.addWidget(self.title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.sub_title = QtWidgets.QLabel("Klipper Firmware Halt (M112)")
        self.sub_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_title.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 700;")
        card_layout.addWidget(self.sub_title, 0, Qt.AlignmentFlag.AlignCenter)

        # Message - ALL CENTERED
        self.msg_lbl = QtWidgets.QLabel(
            "Are you sure you want to trigger an immediate emergency stop?\n\n"
            "This will instantly cut off all heaters, halt all stepper motors, "
            "and terminate the current print job."
        )
        self.msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet(f"color: #E2E8F0; font-size: {_s(12, scale)}px; line-height: 1.5;")
        card_layout.addWidget(self.msg_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        # Buttons Row - CENTERED
        self.btn_layout = QtWidgets.QHBoxLayout()
        self.btn_layout.setSpacing(_s(12, scale))
        self.btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        self.btn_action = QtWidgets.QPushButton("HALT PRINTER NOW")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setFixedHeight(_s(44, scale))
        self.btn_action.setStyleSheet(f"""
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
        self.btn_action.clicked.connect(self._on_halt_clicked)

        self.btn_layout.addWidget(self.btn_cancel)
        self.btn_layout.addWidget(self.btn_action)
        card_layout.addLayout(self.btn_layout)

        outer.addWidget(self.card)
        self.card.setFixedWidth(_s(460, scale))

    def _on_halt_clicked(self):
        """Execute emergency stop immediately, then center green Restart Firmware button."""
        win = self.window()
        mr = getattr(win, "moonraker", None)
        if mr:
            mr.emergency_stop()

        # Update card to halted state with green restart button
        self.card.setStyleSheet(f"""
            QFrame#EmergencyStopCard {{
                background: #0F172A;
                border: 2px solid #10B981;
                border-radius: {_s(14, self.scale)}px;
            }}
        """)
        self.title_lbl.setText("PRINTER HALTED (M112)")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(f"color: #EF4444; font-size: {_s(18, self.scale)}px; font-weight: 900; letter-spacing: 0.8px;")

        self.sub_title.setText("All Heaters & Stepper Motors Cut Off")
        self.sub_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.msg_lbl.setText(
            "Emergency stop executed successfully.\n"
            "All heaters and stepper motors have been cut off.\n\n"
            "Tap the button below to restart Klipper firmware."
        )
        self.msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(13, self.scale)}px; font-weight: 600; line-height: 1.5;")

        # Remove the Cancel / Dismiss button
        self.btn_cancel.setVisible(False)
        self.btn_cancel.deleteLater()

        # Center the green Restart Firmware button at the bottom
        self.btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_action.setText("⟳  RESTART FIRMWARE")
        self.btn_action.setFixedHeight(_s(46, self.scale))
        self.btn_action.setFixedWidth(_s(300, self.scale))
        self.btn_action.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                border: 1.5px solid #34D399;
                border-radius: {_s(8, self.scale)}px;
                font-size: {_s(14, self.scale)}px;
                font-weight: 900;
                letter-spacing: 0.6px;
                padding: 0 {_s(20, self.scale)}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34D399, stop:1 #10B981);
                border-color: #6EE7B7;
            }}
            QPushButton:pressed {{
                background: #047857;
            }}
        """)
        # Disconnect old halt handler and connect restart handler
        self.btn_action.clicked.disconnect()
        self.btn_action.clicked.connect(self._on_restart_clicked)

    def _on_restart_clicked(self):
        """Trigger firmware restart when user taps the green button."""
        self.btn_action.setText("RESTARTING FIRMWARE...")
        self.btn_action.setEnabled(False)

        win = self.window()
        mr = getattr(win, "moonraker", None)
        if mr:
            mr.firmware_restart()

        QtCore.QTimer.singleShot(1200, self.close)

    def mousePressEvent(self, event):
        # Prevent click-through to widgets underneath
        event.accept()
