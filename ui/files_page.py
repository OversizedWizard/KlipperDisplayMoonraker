"""Print from File browser page for Klipper gcode storage.

Supports folder navigation, back navigation, grid (thumbnails) vs list view filtering,
asynchronous thumbnail loading, and touch-friendly file details dialog with print launch.
"""

from datetime import datetime
import os
from typing import List, Dict, Optional

from .qt import QtWidgets, QtCore, QtGui, Qt, Signal
from . import icons
from .thumbnail_helper import load_thumbnail_async, get_default_thumbnail


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def format_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "Unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def format_size(bytes_val: int) -> str:
    if not bytes_val or bytes_val <= 0:
        return "0 KB"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.0f} KB"
    return f"{bytes_val / (1024 * 1024):.1f} MB"


class FileDetailsDialog(QtWidgets.QFrame):
    """Modal overlay displaying detailed metadata and Start Print action for a gcode file."""
    start_print_requested = Signal(str)
    closed = Signal()

    def __init__(self, file_info: dict, moonraker=None, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.scale = scale
        self.file_info = dict(file_info)
        self.moonraker = moonraker
        self.host = (moonraker.active_host or (moonraker.hosts[0] if moonraker.hosts else "127.0.0.1:7125")) if moonraker else "127.0.0.1:7125"

        self.setObjectName("FileDetailsOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#FileDetailsOverlay { background: rgba(5, 10, 20, 0.88); }")

        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("FileDetailsCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet(f"""
            QFrame#FileDetailsCard {{
                background: #0F172A;
                border: 2px solid #00E5FF;
                border-radius: {_s(14, scale)}px;
            }}
        """)

        card_layout = QtWidgets.QHBoxLayout(self.card)
        card_layout.setContentsMargins(_s(20, scale), _s(20, scale), _s(20, scale), _s(20, scale))
        card_layout.setSpacing(_s(18, scale))

        # Left Column: Large Thumbnail
        left_box = QtWidgets.QVBoxLayout()
        left_box.setSpacing(_s(8, scale))
        left_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumb_lbl = QtWidgets.QLabel()
        self.thumb_lbl.setFixedSize(_s(180, scale), _s(180, scale))
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet(f"""
            background: #1E293B;
            border: 1.5px solid rgba(0, 229, 255, 0.3);
            border-radius: {_s(10, scale)}px;
        """)
        self.thumb_lbl.setPixmap(get_default_thumbnail(_s(110, scale)))
        left_box.addWidget(self.thumb_lbl)

        card_layout.addLayout(left_box)

        # Right Column: Details and Launch Button
        right_box = QtWidgets.QVBoxLayout()
        right_box.setSpacing(_s(10, scale))

        filename = self.file_info.get("filename", "")
        self.title_lbl = QtWidgets.QLabel(filename)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(14, scale)}px; font-weight: 800;")
        right_box.addWidget(self.title_lbl)

        # Meta tags
        meta_grid = QtWidgets.QGridLayout()
        meta_grid.setHorizontalSpacing(_s(12, scale))
        meta_grid.setVerticalSpacing(_s(4, scale))

        est_time = format_duration(self.file_info.get("estimated_time", 0))
        meta_grid.addWidget(QtWidgets.QLabel("Est. Time:"), 0, 0)
        self.time_val = QtWidgets.QLabel(est_time)
        self.time_val.setStyleSheet("color: #00E5FF; font-weight: 800;")
        meta_grid.addWidget(self.time_val, 0, 1)

        f_weight = self.file_info.get("filament_weight_total")
        f_len = self.file_info.get("filament_total")
        f_text = f"{f_weight:.1f} g" if f_weight else (f"{f_len/1000:.1f} m" if f_len else "Unknown")
        meta_grid.addWidget(QtWidgets.QLabel("Filament:"), 1, 0)
        self.f_val = QtWidgets.QLabel(f_text)
        self.f_val.setStyleSheet("color: #F8FAFC; font-weight: 700;")
        meta_grid.addWidget(self.f_val, 1, 1)

        l_count = self.file_info.get("layer_count")
        l_height = self.file_info.get("layer_height")
        l_text = f"{l_count} layers ({l_height}mm)" if l_count and l_height else (f"{l_height}mm" if l_height else "Standard")
        meta_grid.addWidget(QtWidgets.QLabel("Layers:"), 2, 0)
        self.l_val = QtWidgets.QLabel(l_text)
        self.l_val.setStyleSheet("color: #F8FAFC; font-weight: 700;")
        meta_grid.addWidget(self.l_val, 2, 1)

        slicer = self.file_info.get("slicer") or "Unknown"
        meta_grid.addWidget(QtWidgets.QLabel("Slicer:"), 3, 0)
        self.s_val = QtWidgets.QLabel(slicer)
        self.s_val.setStyleSheet("color: #94A3B8; font-weight: 600;")
        meta_grid.addWidget(self.s_val, 3, 1)

        for r in range(4):
            lbl = meta_grid.itemAtPosition(r, 0).widget()
            lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(11, scale)}px; font-weight: 600;")

        right_box.addLayout(meta_grid)
        right_box.addStretch(1)

        # Buttons Row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(_s(10, scale))

        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setFixedHeight(_s(42, scale))
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(12, scale)}px;
                font-weight: 700;
                padding: 0 {_s(16, scale)}px;
            }}
            QPushButton:hover {{ background: #475569; }}
        """)
        self.btn_cancel.clicked.connect(self.close)
        btn_row.addWidget(self.btn_cancel)

        self.btn_start = QtWidgets.QPushButton("🚀  START PRINT")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setFixedHeight(_s(42, scale))
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #3B82F6);
                color: #0F172A;
                border: 1px solid #00E5FF;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 900;
                letter-spacing: 0.5px;
                padding: 0 {_s(20, scale)}px;
            }}
            QPushButton:hover {{ background: #38BDF8; }}
        """)
        self.btn_start.clicked.connect(self._on_start_clicked)
        btn_row.addWidget(self.btn_start, 1)

        right_box.addLayout(btn_row)
        card_layout.addLayout(right_box)

        outer.addWidget(self.card)
        self.card.setFixedSize(_s(540, scale), _s(270, scale))

        # Asynchronously load large thumbnail
        thumbs = self.file_info.get("thumbnails", [])
        rel_p = thumbs[0].get("relative_path") if thumbs else None
        dir_p = self.file_info.get("dir_path", "gcodes")

        load_thumbnail_async(
            host=self.host,
            dir_path=dir_p,
            thumb_rel_path=rel_p,
            filename=filename,
            target_size=_s(170, scale),
            on_loaded=self._set_thumb_pixmap
        )

        # If metadata missing, fetch from Moonraker
        if not self.file_info.get("estimated_time") and self.moonraker:
            full_fn = self.file_info.get("full_path") or filename
            self.moonraker.get_file_metadata(full_fn, on_done=self._on_meta_loaded)

    def _on_meta_loaded(self, meta: dict):
        if not meta:
            return
        self.file_info.update(meta)
        est = meta.get("estimated_time")
        if est:
            self.time_val.setText(format_duration(est))
        f_weight = meta.get("filament_weight_total")
        f_len = meta.get("filament_total")
        if f_weight:
            self.f_val.setText(f"{f_weight:.1f} g")
        elif f_len:
            self.f_val.setText(f"{f_len/1000:.1f} m")
        l_count = meta.get("layer_count")
        l_height = meta.get("layer_height")
        if l_count and l_height:
            self.l_val.setText(f"{l_count} layers ({l_height}mm)")
        slicer = meta.get("slicer")
        if slicer:
            self.s_val.setText(slicer)
        thumbs = meta.get("thumbnails", [])
        if thumbs:
            best = max(thumbs, key=lambda t: t.get("width", 0) * t.get("height", 0))
            rel_p = best.get("relative_path")
            if rel_p:
                load_thumbnail_async(
                    host=self.host,
                    dir_path=self.file_info.get("dir_path", "gcodes"),
                    thumb_rel_path=rel_p,
                    filename=self.file_info.get("filename", ""),
                    target_size=_s(170, self.scale),
                    on_loaded=self._set_thumb_pixmap
                )

    def _set_thumb_pixmap(self, pm: QtGui.QPixmap):
        if pm and not pm.isNull():
            sz = _s(170, self.scale)
            scaled = pm.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumb_lbl.setPixmap(scaled)

    def _on_start_clicked(self):
        fn = self.file_info.get("filename", "")
        self.start_print_requested.emit(fn)
        self.close()

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()


class FileGridCard(QtWidgets.QFrame):
    """Square/vertical card for grid view displaying thumbnail and gcode details."""
    clicked = Signal(dict)

    def __init__(self, item: dict, is_dir: bool, dir_path: str, moonraker=None, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.item = dict(item)
        self.is_dir = is_dir
        self.dir_path = dir_path
        self.moonraker = moonraker
        self.scale = scale
        self.host = (moonraker.active_host or (moonraker.hosts[0] if moonraker.hosts else "127.0.0.1:7125")) if moonraker else "127.0.0.1:7125"

        self.setObjectName("FileGridCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame#FileGridCard {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: {_s(10, scale)}px;
            }}
            QFrame#FileGridCard:hover {{
                border-color: #00E5FF;
                background: #24344D;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(_s(8, scale), _s(8, scale), _s(8, scale), _s(8, scale))
        layout.setSpacing(_s(6, scale))
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Preview area
        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setFixedSize(_s(110, scale), _s(84, scale))
        self.icon_lbl.setStyleSheet(f"background: rgba(0, 0, 0, 0.25); border-radius: {_s(6, scale)}px;")

        name = self.item.get("dirname") if is_dir else self.item.get("filename", "")
        if is_dir:
            self.icon_lbl.setPixmap(icons.pixmap("folder", _s(48, scale)))
        else:
            self.icon_lbl.setPixmap(get_default_thumbnail(_s(48, scale)))
        layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        # Name label
        display_name = name
        if len(display_name) > 22:
            display_name = display_name[:19] + "..."
        self.name_lbl = QtWidgets.QLabel(display_name)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(11, scale)}px; font-weight: 700;")
        layout.addWidget(self.name_lbl)

        # Meta subtitle
        if is_dir:
            sub_text = "Folder"
            sub_col = "#FBBF24"
        else:
            est = self.item.get("estimated_time")
            sz = format_size(self.item.get("size", 0))
            sub_text = f"⏱ {format_duration(est)}" if est else sz
            sub_col = "#00E5FF" if est else "#94A3B8"

        self.sub_lbl = QtWidgets.QLabel(sub_text)
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(f"color: {sub_col}; font-size: {_s(10, scale)}px; font-weight: 600;")
        layout.addWidget(self.sub_lbl)

        self.setFixedSize(_s(132, scale), _s(142, scale))

        if not is_dir:
            # 1. Immediately request thumbnail (checks Moonraker, local file, or embedded slicer base64)
            thumbs = self.item.get("thumbnails", [])
            rel_p = thumbs[0].get("relative_path") if thumbs else None
            load_thumbnail_async(
                host=self.host,
                dir_path=self.dir_path,
                thumb_rel_path=rel_p,
                filename=name,
                target_size=_s(110, scale),
                on_loaded=self._set_thumb
            )

            # 2. If metadata not yet populated, fetch it asynchronously from Moonraker
            if self.moonraker and not self.item.get("estimated_time"):
                full_fn = f"{self.dir_path}/{name}" if self.dir_path != "gcodes" else name
                clean_fn = full_fn.replace("gcodes/", "")
                self.moonraker.get_file_metadata(clean_fn, on_done=self._on_metadata_loaded)

    def _on_metadata_loaded(self, meta: dict):
        if not meta:
            return
        self.item.update(meta)
        est = meta.get("estimated_time")
        if est:
            self.sub_lbl.setText(f"⏱ {format_duration(est)}")
            self.sub_lbl.setStyleSheet("color: #00E5FF; font-weight: 700;")
        thumbs = meta.get("thumbnails", [])
        if thumbs:
            best = max(thumbs, key=lambda t: t.get("width", 0) * t.get("height", 0))
            rel_p = best.get("relative_path")
            if rel_p:
                load_thumbnail_async(
                    host=self.host,
                    dir_path=self.dir_path,
                    thumb_rel_path=rel_p,
                    filename=self.item.get("filename", ""),
                    target_size=_s(110, self.scale),
                    on_loaded=self._set_thumb
                )

    def _set_thumb(self, pm: QtGui.QPixmap):
        if pm and not pm.isNull():
            sz_w = _s(106, self.scale)
            sz_h = _s(80, self.scale)
            scaled = pm.scaled(sz_w, sz_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_lbl.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
            event.accept()
        else:
            super().mousePressEvent(event)


class FileListRow(QtWidgets.QFrame):
    """Horizontal row for list view displaying icon/thumbnail, file info, and action."""
    clicked = Signal(dict)

    def __init__(self, item: dict, is_dir: bool, dir_path: str, moonraker=None, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.item = dict(item)
        self.is_dir = is_dir
        self.dir_path = dir_path
        self.moonraker = moonraker
        self.scale = scale
        self.host = (moonraker.active_host or (moonraker.hosts[0] if moonraker.hosts else "127.0.0.1:7125")) if moonraker else "127.0.0.1:7125"

        self.setObjectName("FileListRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame#FileListRow {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {_s(8, scale)}px;
            }}
            QFrame#FileListRow:hover {{
                border-color: #00E5FF;
                background: #24344D;
            }}
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(_s(10, scale), _s(6, scale), _s(12, scale), _s(6, scale))
        layout.setSpacing(_s(12, scale))

        # Icon / Thumbnail
        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setFixedSize(_s(42, scale), _s(42, scale))
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet(f"background: rgba(0, 0, 0, 0.25); border-radius: {_s(6, scale)}px;")

        name = self.item.get("dirname") if is_dir else self.item.get("filename", "")
        if is_dir:
            self.icon_lbl.setPixmap(icons.pixmap("folder", _s(28, scale)))
        else:
            self.icon_lbl.setPixmap(get_default_thumbnail(_s(28, scale)))
        layout.addWidget(self.icon_lbl)

        # Name & Info
        info_box = QtWidgets.QVBoxLayout()
        info_box.setSpacing(2)
        name_lbl = QtWidgets.QLabel(name)
        name_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(12, scale)}px; font-weight: 700;")
        info_box.addWidget(name_lbl)

        if is_dir:
            sub = "Directory"
            sub_col = "#FBBF24"
        else:
            est = self.item.get("estimated_time")
            sz = format_size(self.item.get("size", 0))
            sub = f"Estimated: {format_duration(est)}  •  {sz}" if est else f"Size: {sz}"
            sub_col = "#94A3B8"

        self.sub_lbl = QtWidgets.QLabel(sub)
        self.sub_lbl.setStyleSheet(f"color: {sub_col}; font-size: {_s(10, scale)}px; font-weight: 600;")
        info_box.addWidget(self.sub_lbl)
        layout.addLayout(info_box, 1)

        # Right arrow or folder badge
        arrow = QtWidgets.QLabel("📁 OPEN" if is_dir else "PRINT ›")
        arrow.setStyleSheet(f"color: {'#FBBF24' if is_dir else '#00E5FF'}; font-size: {_s(11, scale)}px; font-weight: 800;")
        layout.addWidget(arrow)

        self.setFixedHeight(_s(54, scale))

        if not is_dir:
            thumbs = self.item.get("thumbnails", [])
            rel_p = thumbs[0].get("relative_path") if thumbs else None
            load_thumbnail_async(
                host=self.host,
                dir_path=self.dir_path,
                thumb_rel_path=rel_p,
                filename=name,
                target_size=_s(42, scale),
                on_loaded=self._set_thumb
            )

            if self.moonraker and not self.item.get("estimated_time"):
                full_fn = f"{self.dir_path}/{name}" if self.dir_path != "gcodes" else name
                clean_fn = full_fn.replace("gcodes/", "")
                self.moonraker.get_file_metadata(clean_fn, on_done=self._on_metadata_loaded)

    def _on_metadata_loaded(self, meta: dict):
        if not meta:
            return
        self.item.update(meta)
        est = meta.get("estimated_time")
        sz = format_size(self.item.get("size", 0))
        if est:
            self.sub_lbl.setText(f"Estimated: {format_duration(est)}  •  {sz}")
        thumbs = meta.get("thumbnails", [])
        if thumbs:
            best = max(thumbs, key=lambda t: t.get("width", 0) * t.get("height", 0))
            rel_p = best.get("relative_path")
            if rel_p:
                load_thumbnail_async(
                    host=self.host,
                    dir_path=self.dir_path,
                    thumb_rel_path=rel_p,
                    filename=self.item.get("filename", ""),
                    target_size=_s(42, self.scale),
                    on_loaded=self._set_thumb
                )

    def _set_thumb(self, pm: QtGui.QPixmap):
        if pm and not pm.isNull():
            sz = _s(38, self.scale)
            scaled = pm.scaled(sz, sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_lbl.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
            event.accept()
        else:
            super().mousePressEvent(event)


class FilesPage(QtWidgets.QWidget):
    """File manager for Klipper gcodes: folder navigation, back icon, list/grid toggle, thumbnails."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FilesPage")
        self._scale = 1.0
        self.moonraker = None

        self.current_dir = "gcodes"
        self.dir_history: List[str] = []
        self.view_mode = "grid"  # "grid" or "list"

        self.dirs_data: List[dict] = []
        self.files_data: List[dict] = []

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 12)
        main_layout.setSpacing(10)

        # --- Top Navigation Bar ---
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setSpacing(8)

        # Back button (for navigating up directories)
        self.btn_back = QtWidgets.QPushButton(" ⬅ Back ")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.15);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 6px;
                font-weight: 800;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(56, 189, 248, 0.3); }
        """)
        self.btn_back.clicked.connect(self._on_back_clicked)
        self.btn_back.setVisible(False)
        top_bar.addWidget(self.btn_back)

        # Breadcrumb label
        self.path_lbl = QtWidgets.QLabel("📁  gcodes")
        self.path_lbl.setStyleSheet("color: #F8FAFC; font-weight: 800; font-size: 13px;")
        top_bar.addWidget(self.path_lbl)
        top_bar.addStretch(1)

        # View Mode Toggle: Grid vs List
        self.btn_toggle_view = QtWidgets.QPushButton(" ▦ Cards ")
        self.btn_toggle_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_view.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.16); color: #FFFFFF; }
        """)
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)
        top_bar.addWidget(self.btn_toggle_view)

        # Refresh button
        self.btn_refresh = QtWidgets.QPushButton(" ⟳ Refresh ")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.16); color: #FFFFFF; }
        """)
        self.btn_refresh.clicked.connect(self.refresh)
        top_bar.addWidget(self.btn_refresh)

        main_layout.addLayout(top_bar)

        # --- Content Area (Scrollable Stack) ---
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """Query Moonraker for current folder contents."""
        mr = getattr(self, "moonraker", None) or getattr(self.window(), "moonraker", None)
        if mr:
            self.moonraker = mr
            mr.list_files(self.current_dir, on_done=self._on_files_loaded)
        else:
            self._render_empty("Connecting to Moonraker...")

    def _on_files_loaded(self, res: dict):
        self.dirs_data = [d for d in res.get("dirs", []) if not d.get("dirname", "").startswith(".")]
        self.files_data = [f for f in res.get("files", []) if not f.get("filename", "").startswith(".")]
        self._render_view()

    def _render_view(self):
        old_w = self.scroll.takeWidget()
        if old_w:
            old_w.deleteLater()

        self.content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.scroll.setWidget(self.content_widget)

        is_sub = (self.current_dir != "gcodes")
        self.btn_back.setVisible(is_sub)
        self.path_lbl.setText(f"📁  {self.current_dir}")

        if not self.dirs_data and not self.files_data:
            self._render_empty("No G-Code files or folders found in this directory.")
            return

        if self.view_mode == "grid":
            self._render_grid()
        else:
            self._render_list()

    def _render_grid(self):
        grid_container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(_s(10, self._scale))
        grid.setVerticalSpacing(_s(10, self._scale))
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        cols = 4
        col_idx = 0
        row_idx = 0

        # Directories first
        for d in self.dirs_data:
            card = FileGridCard(d, is_dir=True, dir_path=self.current_dir, moonraker=self.moonraker, scale=self._scale)
            card.clicked.connect(self._on_dir_clicked)
            grid.addWidget(card, row_idx, col_idx)
            col_idx += 1
            if col_idx >= cols:
                col_idx = 0
                row_idx += 1

        # Then files
        for f in self.files_data:
            card = FileGridCard(f, is_dir=False, dir_path=self.current_dir, moonraker=self.moonraker, scale=self._scale)
            card.clicked.connect(self._on_file_clicked)
            grid.addWidget(card, row_idx, col_idx)
            col_idx += 1
            if col_idx >= cols:
                col_idx = 0
                row_idx += 1

        self.content_layout.addWidget(grid_container)
        self.content_layout.addStretch(1)

    def _render_list(self):
        # Directories first
        for d in self.dirs_data:
            row = FileListRow(d, is_dir=True, dir_path=self.current_dir, moonraker=self.moonraker, scale=self._scale)
            row.clicked.connect(self._on_dir_clicked)
            self.content_layout.addWidget(row)

        # Then files
        for f in self.files_data:
            row = FileListRow(f, is_dir=False, dir_path=self.current_dir, moonraker=self.moonraker, scale=self._scale)
            row.clicked.connect(self._on_file_clicked)
            self.content_layout.addWidget(row)

        self.content_layout.addStretch(1)

    def _render_empty(self, message: str):
        lbl = QtWidgets.QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: #94A3B8; font-size: {_s(13, self._scale)}px; padding: {_s(30, self._scale)}px;")
        self.content_layout.addWidget(lbl)

    def _toggle_view_mode(self):
        if self.view_mode == "grid":
            self.view_mode = "list"
            self.btn_toggle_view.setText(" ≡ List ")
        else:
            self.view_mode = "grid"
            self.btn_toggle_view.setText(" ▦ Cards ")
        self._render_view()

    def _on_dir_clicked(self, item: dict):
        dirname = item.get("dirname")
        if dirname:
            self.dir_history.append(self.current_dir)
            self.current_dir = f"{self.current_dir}/{dirname}"
            self.refresh()

    def _on_back_clicked(self):
        if self.dir_history:
            self.current_dir = self.dir_history.pop()
        else:
            self.current_dir = "gcodes"
        self.refresh()

    def _on_file_clicked(self, item: dict):
        main_win = self.window()
        full_path = f"{self.current_dir.replace('gcodes/', '')}/{item.get('filename')}" if self.current_dir != "gcodes" else item.get('filename')
        dlg_info = dict(item)
        dlg_info["full_path"] = full_path
        dlg_info["dir_path"] = self.current_dir

        dlg = FileDetailsDialog(dlg_info, moonraker=self.moonraker, scale=self._scale, parent=main_win)
        dlg.start_print_requested.connect(self._start_print)
        dlg.show()
        dlg.raise_()

    def _start_print(self, filename: str):
        mr = self.moonraker or getattr(self.window(), "moonraker", None)
        if mr:
            full_fn = f"{self.current_dir.replace('gcodes/', '')}/{filename}" if self.current_dir != "gcodes" else filename
            mr.start_print(full_fn)

        main_win = self.window()
        if hasattr(main_win, "show_page"):
            main_win.show_page("printing")

    def apply_scale(self, s: float):
        self._scale = s
        self._render_view()
