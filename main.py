"""Klipper 3D Display Controller - entry point.

PC (windowed, 800x480):     python main.py
Custom window size:         python main.py --width 800 --height 600
Raspberry Pi touchscreen:   python main.py --fullscreen --hide-cursor
"""

import argparse
import sys

from ui.qt import QtWidgets, QtGui, Qt, BINDING
from ui.main_window import MainWindow


def parse_args():
    p = argparse.ArgumentParser(description="Klipper 3D Display Controller")
    p.add_argument("--fullscreen", action="store_true", help="fill the whole screen (Pi)")
    p.add_argument("--hide-cursor", action="store_true", help="hide mouse cursor (touchscreens)")
    p.add_argument("--width", type=int, default=800, help="window width (default 800)")
    p.add_argument("--height", type=int, default=480, help="window height (default 480)")
    return p.parse_args()


def main():
    args = parse_args()

    QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Klipper 3D Display")

    win = MainWindow()
    if args.hide_cursor:
        app.setOverrideCursor(Qt.CursorShape.BlankCursor)
    if args.fullscreen:
        win.showFullScreen()
    else:
        win.resize(args.width, args.height)
        win.show()

    print(f"Klipper 3D Display running on {BINDING}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
