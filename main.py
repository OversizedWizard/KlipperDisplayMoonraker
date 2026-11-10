"""Klipper 3D Display Controller - entry point.

PC (windowed, 800x480):     python main.py
Custom window size:         python main.py --width 800 --height 600
Raspberry Pi touchscreen:   python main.py --fullscreen --hide-cursor
"""

import argparse
import os
import sys

from ui.qt import QtWidgets, QtGui, Qt, BINDING
from ui.main_window import MainWindow
from ui.touch_scroll import install_global_touch_scroller


def parse_args():
    p = argparse.ArgumentParser(description="Klipper 3D Display Controller")
    p.add_argument("--fullscreen", action="store_true", help="fill the whole screen (Pi)")
    p.add_argument("--hide-cursor", action="store_true", help="hide mouse cursor (touchscreens)")
    p.add_argument("--width", type=int, default=800, help="window width (default 800)")
    p.add_argument("--height", type=int, default=480, help="window height (default 480)")
    p.add_argument("--host", type=str, default=None, help="Moonraker host:port (default: 127.0.0.1:7125)")
    return p.parse_args()


def main():
    args = parse_args()

    QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Klipper 3D Display")
    install_global_touch_scroller(app)

    if args.hide_cursor:
        app.setOverrideCursor(Qt.CursorShape.BlankCursor)

    # Seamless splash screen while MainWindow initializes
    splash = None
    splash_candidates = [
        os.path.join(os.path.dirname(__file__), "splash.png"),
        os.path.join(os.path.dirname(__file__), "splash.jpg"),
    ]
    for sc in splash_candidates:
        if os.path.exists(sc):
            pix = QtGui.QPixmap(sc)
            if not pix.isNull():
                target_w = args.width
                target_h = args.height
                if args.fullscreen and app.primaryScreen():
                    s_size = app.primaryScreen().size()
                    target_w = s_size.width()
                    target_h = s_size.height()
                scaled = pix.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                canvas = QtGui.QPixmap(target_w, target_h)
                canvas.fill(QtGui.QColor("black"))
                painter = QtGui.QPainter(canvas)
                px = (target_w - scaled.width()) // 2
                py = (target_h - scaled.height()) // 2
                painter.drawPixmap(px, py, scaled)
                painter.end()
                splash = QtWidgets.QSplashScreen(canvas)
                splash.show()
                app.processEvents()
                break

    win = MainWindow(host=args.host)
    if args.fullscreen:
        win.showFullScreen()
    else:
        win.resize(args.width, args.height)
        win.show()

    if splash:
        splash.finish(win)

    print(f"Klipper 3D Display running on {BINDING}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
