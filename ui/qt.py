"""Qt binding shim.

Prefers PySide6, falls back to PyQt6 (on Raspberry Pi OS PyQt6 is available
via apt: `sudo apt install python3-pyqt6 python3-pyqt6.qtsvg`).

All code in this project uses fully-scoped enums (e.g. Qt.AlignmentFlag.AlignCenter)
so it works identically on both bindings.
"""

try:
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg  # noqa: F401
    Signal = QtCore.Signal
    BINDING = "PySide6"
except ImportError:  # pragma: no cover
    from PyQt6 import QtCore, QtGui, QtWidgets, QtSvg  # noqa: F401
    Signal = QtCore.pyqtSignal
    QtCore.Signal = QtCore.pyqtSignal
    if not hasattr(QtCore, "Slot") and hasattr(QtCore, "pyqtSlot"):
        QtCore.Slot = QtCore.pyqtSlot
    if not hasattr(QtCore, "Property") and hasattr(QtCore, "pyqtProperty"):
        QtCore.Property = QtCore.pyqtProperty
    BINDING = "PyQt6"

Qt = QtCore.Qt
