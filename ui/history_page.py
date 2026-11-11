"""Print History page for Klipper display: browse past prints, view full print statistics,
prevent accidental touch selection while scrolling, clear history with confirmation, and Print Again.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional

from .qt import QtWidgets, QtCore, QtGui, Qt, Signal
from . import icons
from .touch_scroll import touch_press, touch_move, touch_release, is_drag_active


def _s(v: float, s: float) -> int:
    return max(1, round(v * s))


def format_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def format_date(epoch: float) -> str:
    if not epoch or epoch <= 0:
        return "Unknown"
    try:
        dt = datetime.fromtimestamp(epoch)
        return dt.strftime("%b %d, %Y %H:%M:%S")
    except Exception:
        return "Unknown"


def format_date_short(epoch: float) -> str:
    if not epoch or epoch <= 0:
        return "Unknown"
    try:
        dt = datetime.fromtimestamp(epoch)
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return "Unknown"


def format_filament(mm: float) -> str:
    if not mm or mm <= 0:
        return "0 mm"
    m = mm / 1000.0
    # Approximate PLA grams for 1.75mm: density ~1.24 g/cm3 => ~2.98 g/m
    g = m * 2.98
    if mm >= 1000.0:
        return f"{m:.2f} m ({g:.1f} g)"
    return f"{mm:.0f} mm ({g:.1f} g)"


def detect_bed_mesh(job: dict) -> str:
    meta = job.get("metadata", {}) or {}
    if meta.get("bed_mesh"):
        return str(meta["bed_mesh"])
    if meta.get("adaptive_mesh"):
        return "Adaptive (KAMP)"
    if meta.get("first_layer_bed_temp") and meta["first_layer_bed_temp"] > 0:
        return "default (Active)"
    return "None / Off"


def is_job_successful(job: dict) -> bool:
    return job.get("status") == "completed"


def is_job_failed(job: dict) -> bool:
    st = job.get("status", "")
    return st in ("cancelled", "error", "klippy_shutdown")


class HistoryDetailsDialog(QtWidgets.QFrame):
    """Touch modal dialog displaying exhaustive stats for a historical print job."""
    print_again_requested = Signal(dict)
    closed = Signal()

    def __init__(self, job: dict, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.job = dict(job)
        self.scale = scale

        self.setObjectName("HistoryDetailsOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#HistoryDetailsOverlay { background: rgba(5, 10, 20, 0.88); }")

        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("HistoryDetailsCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setStyleSheet(f"""
            QFrame#HistoryDetailsCard {{
                background: #0F172A;
                border: 2px solid #00E5FF;
                border-radius: {_s(14, scale)}px;
            }}
        """)
        self.card.setFixedWidth(_s(540, scale))
        outer.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)

        card_layout = QtWidgets.QVBoxLayout(self.card)
        card_layout.setContentsMargins(_s(16, scale), _s(14, scale), _s(16, scale), _s(14, scale))
        card_layout.setSpacing(_s(10, scale))

        # Header: status icon, title, close X
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(_s(10, scale))

        success = is_job_successful(job)
        st_color = "#10B981" if success else "#EF4444"
        st_bg = "rgba(16, 185, 129, 0.16)" if success else "rgba(239, 68, 68, 0.18)"
        st_border = "rgba(16, 185, 129, 0.45)" if success else "rgba(239, 68, 68, 0.5)"
        st_icon = "✔" if success else "✖"
        st_label = "SUCCESSFUL" if success else (job.get("status", "FAILED").upper())

        icon_lbl = QtWidgets.QLabel(st_icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFixedSize(_s(36, scale), _s(36, scale))
        icon_lbl.setStyleSheet(f"""
            background: {st_bg};
            color: {st_color};
            border: 1.5px solid {st_border};
            border-radius: {_s(8, scale)}px;
            font-size: {_s(18, scale)}px;
            font-weight: 900;
        """)
        top_row.addWidget(icon_lbl)

        mid_box = QtWidgets.QVBoxLayout()
        mid_box.setSpacing(_s(2, scale))

        badge_row = QtWidgets.QHBoxLayout()
        badge_row.setSpacing(_s(8, scale))

        status_badge = QtWidgets.QLabel(st_label)
        status_badge.setStyleSheet(f"""
            background: {st_bg};
            color: {st_color};
            border: 1px solid {st_border};
            border-radius: {_s(4, scale)}px;
            padding: {_s(1, scale)}px {_s(6, scale)}px;
            font-size: {_s(10, scale)}px;
            font-weight: 800;
        """)
        badge_row.addWidget(status_badge)

        jid_lbl = QtWidgets.QLabel(f"ID: {job.get('job_id', '--')}")
        jid_lbl.setStyleSheet(f"color: #64748B; font-size: {_s(10, scale)}px; font-weight: 700;")
        badge_row.addWidget(jid_lbl)
        badge_row.addStretch(1)
        mid_box.addLayout(badge_row)

        fn = job.get("filename", "Unknown")
        clean_fn = fn.split("/")[-1]
        name_lbl = QtWidgets.QLabel(clean_fn)
        name_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(14, scale)}px; font-weight: 800;")
        mid_box.addWidget(name_lbl)

        sub_path = QtWidgets.QLabel(fn)
        sub_path.setStyleSheet(f"color: #94A3B8; font-size: {_s(10, scale)}px;")
        mid_box.addWidget(sub_path)

        top_row.addLayout(mid_box, 1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(_s(28, scale), _s(28, scale))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: #94A3B8;
                font-size: {_s(16, scale)}px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                color: #F8FAFC;
            }}
        """)
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)

        card_layout.addLayout(top_row)

        # Section 1: Timing & Filament
        meta = job.get("metadata", {}) or {}
        sec1 = QtWidgets.QFrame()
        sec1.setObjectName("DetailSec")
        sec1.setStyleSheet(f"""
            QFrame#DetailSec {{
                background: #131D33;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {_s(8, scale)}px;
            }}
            QFrame#DetailSec QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        s1_lay = QtWidgets.QVBoxLayout(sec1)
        s1_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        s1_lay.setSpacing(_s(6, scale))

        t1_hdr = QtWidgets.QLabel("PRINT TIMING & STATISTICS")
        t1_hdr.setStyleSheet(f"color: #00E5FF; font-size: {_s(10, scale)}px; font-weight: 800; letter-spacing: 1px;")
        s1_lay.addWidget(t1_hdr)

        grid1 = QtWidgets.QGridLayout()
        grid1.setSpacing(_s(6, scale))

        grid1.addWidget(QtWidgets.QLabel("Start Time:"), 0, 0)
        grid1.addWidget(QtWidgets.QLabel("End Time:"), 0, 1)
        val_start = QtWidgets.QLabel(format_date(job.get("start_time", 0)))
        val_start.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        val_end = QtWidgets.QLabel(format_date(job.get("end_time", 0)))
        val_end.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        grid1.addWidget(val_start, 1, 0)
        grid1.addWidget(val_end, 1, 1)

        grid1.addWidget(QtWidgets.QLabel("Print Duration:"), 2, 0)
        grid1.addWidget(QtWidgets.QLabel("Total Duration:"), 2, 1)
        val_pdur = QtWidgets.QLabel(format_duration(job.get("print_duration", 0)))
        val_pdur.setStyleSheet("color: #00E5FF; font-weight: 800;")
        val_tdur = QtWidgets.QLabel(format_duration(job.get("total_duration", 0)))
        val_tdur.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        grid1.addWidget(val_pdur, 3, 0)
        grid1.addWidget(val_tdur, 3, 1)

        grid1.addWidget(QtWidgets.QLabel("Filament Used:"), 4, 0)
        grid1.addWidget(QtWidgets.QLabel("Filament Total:"), 4, 1)
        val_fuse = QtWidgets.QLabel(format_filament(job.get("filament_used", 0)))
        val_fuse.setStyleSheet("color: #38BDF8; font-weight: 800;")
        tot_fil = meta.get("filament_total")
        val_ftot = QtWidgets.QLabel(format_filament(tot_fil) if tot_fil else "N/A")
        val_ftot.setStyleSheet("color: #94A3B8; font-weight: 700;")
        grid1.addWidget(val_fuse, 5, 0)
        grid1.addWidget(val_ftot, 5, 1)

        s1_lay.addLayout(grid1)
        card_layout.addWidget(sec1)

        # Section 2: Calibration & Slicer
        sec2 = QtWidgets.QFrame()
        sec2.setObjectName("DetailSec")
        sec2.setStyleSheet(f"""
            QFrame#DetailSec {{
                background: #131D33;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {_s(8, scale)}px;
            }}
            QFrame#DetailSec QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        s2_lay = QtWidgets.QVBoxLayout(sec2)
        s2_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        s2_lay.setSpacing(_s(6, scale))

        t2_hdr = QtWidgets.QLabel("CALIBRATION & SLICER SPECS")
        t2_hdr.setStyleSheet(f"color: #00E5FF; font-size: {_s(10, scale)}px; font-weight: 800; letter-spacing: 1px;")
        s2_lay.addWidget(t2_hdr)

        grid2 = QtWidgets.QGridLayout()
        grid2.setSpacing(_s(6, scale))

        mesh_name = detect_bed_mesh(job)
        mesh_col = "#94A3B8" if "None" in mesh_name else "#34D399"
        grid2.addWidget(QtWidgets.QLabel("Bed Mesh:"), 0, 0)
        val_mesh = QtWidgets.QLabel(mesh_name)
        val_mesh.setStyleSheet(f"color: {mesh_col}; font-weight: 800;")
        grid2.addWidget(val_mesh, 0, 1)

        slicer_name = f"{meta.get('slicer', 'Unknown')} {meta.get('slicer_version', '')}".strip()
        grid2.addWidget(QtWidgets.QLabel("Slicer:"), 1, 0)
        val_slicer = QtWidgets.QLabel(slicer_name)
        val_slicer.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        grid2.addWidget(val_slicer, 1, 1)

        l_cnt = meta.get("layer_count")
        grid2.addWidget(QtWidgets.QLabel("Layer Count:"), 2, 0)
        val_lcnt = QtWidgets.QLabel(f"{l_cnt} layers" if l_cnt else "Unknown")
        val_lcnt.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        grid2.addWidget(val_lcnt, 2, 1)

        l_h = meta.get("layer_height")
        grid2.addWidget(QtWidgets.QLabel("Layer Height:"), 3, 0)
        val_lh = QtWidgets.QLabel(f"{l_h} mm" if l_h else "Unknown")
        val_lh.setStyleSheet("color: #F1F5F9; font-weight: 700;")
        grid2.addWidget(val_lh, 3, 1)

        s2_lay.addLayout(grid2)
        card_layout.addWidget(sec2)

        # Action Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(_s(10, scale))

        cancel_btn = QtWidgets.QPushButton("Close")
        cancel_btn.setFixedHeight(_s(42, scale))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #F8FAFC;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(12, scale)}px;
                font-weight: 700;
                padding: 0 {_s(16, scale)}px;
            }}
            QPushButton:hover {{
                background: #334155;
            }}
        """)
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)

        self.reprint_btn = QtWidgets.QPushButton("▶ Print Again")
        self.reprint_btn.setFixedHeight(_s(42, scale))
        self.reprint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reprint_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00E5FF, stop:1 #0284C7);
                border: none;
                color: #020617;
                border-radius: {_s(8, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 900;
                padding: 0 {_s(20, scale)}px;
            }}
            QPushButton:hover {{
                background: #38BDF8;
            }}
        """)
        self.reprint_btn.clicked.connect(self._on_print_again)
        btn_row.addWidget(self.reprint_btn, 1)

        card_layout.addLayout(btn_row)

    def _on_print_again(self):
        self.print_again_requested.emit(self.job)
        self.close()

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()


class ClearConfirmDialog(QtWidgets.QFrame):
    """Modal confirmation dialog for clearing print history."""
    confirmed = Signal()
    closed = Signal()

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.setObjectName("ClearConfirmOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#ClearConfirmOverlay { background: rgba(5, 10, 20, 0.88); }")

        if parent:
            self.setGeometry(parent.rect())

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QtWidgets.QFrame(self)
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            background: #0F172A;
            border: 2px solid #EF4444;
            border-radius: {_s(14, scale)}px;
        """)
        card.setFixedWidth(_s(420, scale))
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(_s(20, scale), _s(20, scale), _s(20, scale), _s(20, scale))
        layout.setSpacing(_s(14, scale))

        ti = QtWidgets.QLabel("Clear All Print History?")
        ti.setStyleSheet(f"color: #F87171; font-size: {_s(16, scale)}px; font-weight: 900;")
        layout.addWidget(ti)

        msg = QtWidgets.QLabel("Are you sure you want to delete all past print history records?\nThis cannot be undone.")
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: #CBD5E1; font-size: {_s(12, scale)}px; line-height: 1.4;")
        layout.addWidget(msg)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(_s(10, scale))

        can_btn = QtWidgets.QPushButton("Cancel")
        can_btn.setFixedHeight(_s(40, scale))
        can_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        can_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.15);
                color: #F8FAFC;
                border-radius: {_s(8, scale)}px;
                font-weight: 700;
            }}
        """)
        can_btn.clicked.connect(self.close)
        btn_row.addWidget(can_btn, 1)

        ok_btn = QtWidgets.QPushButton("Clear All History")
        ok_btn.setFixedHeight(_s(40, scale))
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: #EF4444;
                border: none;
                color: #FFFFFF;
                border-radius: {_s(8, scale)}px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: #DC2626;
            }}
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn, 1)

        layout.addLayout(btn_row)

    def _on_ok(self):
        self.confirmed.emit()
        self.close()

    def close(self):
        super().close()
        self.closed.emit()

    def mousePressEvent(self, event):
        event.accept()


class HistoryItemCard(QtWidgets.QFrame):
    """Touch card representing a past print job in the history list."""
    clicked = Signal(dict)
    reprint_requested = Signal(dict)

    def __init__(self, job: dict, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.job = dict(job)
        self.scale = scale

        self.setObjectName("HistoryItemCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        layout.setSpacing(_s(10, scale))

        success = is_job_successful(job)
        ok_prop = "true" if success else "false"
        st_icon = "✔" if success else "✖"
        st_label = "SUCCESS" if success else (job.get("status", "FAILED").upper())

        # Status icon circle (styled via parent HistoryPage QSS)
        icon_lbl = QtWidgets.QLabel(st_icon)
        icon_lbl.setObjectName("HistIcon")
        icon_lbl.setProperty("ok", ok_prop)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setFixedSize(_s(36, scale), _s(36, scale))
        layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # Center info block
        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(_s(2, scale))

        tag_row = QtWidgets.QHBoxLayout()
        tag_row.setSpacing(_s(8, scale))

        st_tag = QtWidgets.QLabel(st_label)
        st_tag.setObjectName("HistTag")
        st_tag.setProperty("ok", ok_prop)
        tag_row.addWidget(st_tag)

        date_lbl = QtWidgets.QLabel(format_date_short(job.get("start_time", 0)))
        date_lbl.setObjectName("HistDate")
        tag_row.addWidget(date_lbl)

        mesh_str = detect_bed_mesh(job)
        mesh_tag = QtWidgets.QLabel(f"Mesh: {mesh_str}")
        mesh_tag.setObjectName("HistMesh")
        tag_row.addWidget(mesh_tag)
        tag_row.addStretch(1)
        mid.addLayout(tag_row)

        fn = job.get("filename", "Unknown")
        clean_fn = fn.split("/")[-1]
        if len(clean_fn) > 30:
            clean_fn = clean_fn[:27] + "..."
        name_lbl = QtWidgets.QLabel(clean_fn)
        name_lbl.setObjectName("HistName")
        name_lbl.setMinimumWidth(0)
        mid.addWidget(name_lbl)

        dur_str = format_duration(job.get("total_duration") or job.get("print_duration", 0))
        fil_str = format_filament(job.get("filament_used", 0))
        stat_lbl = QtWidgets.QLabel(f"Time: {dur_str}   •   Fil: {fil_str}")
        stat_lbl.setObjectName("HistStat")
        stat_lbl.setMinimumWidth(0)
        mid.addWidget(stat_lbl)

        layout.addLayout(mid, 1)

        # Right actions: Print Again + Arrow
        reprint_btn = QtWidgets.QPushButton("▶ Print Again")
        reprint_btn.setObjectName("HistReprintBtn")
        reprint_btn.setFixedHeight(_s(32, scale))
        reprint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reprint_btn.clicked.connect(self._on_reprint)
        layout.addWidget(reprint_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        arrow_lbl = QtWidgets.QLabel("›")
        arrow_lbl.setObjectName("HistArrow")
        layout.addWidget(arrow_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

    def _on_reprint(self):
        self.reprint_requested.emit(self.job)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            touch_press(self, event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not touch_move(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if touch_release(self):
                self.clicked.emit(self.job)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class HistoryPage(QtWidgets.QWidget):
    """Print History Page: displays successful and failed prints, stats modal, kinetic scrolling, clear all."""
    start_print_requested = Signal(str)
    PAGE_SIZE = 20

    def __init__(self, moonraker=None, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.key = "history"
        self.moonraker = moonraker
        self.scale = scale
        self.jobs: List[dict] = []
        self.active_filter = "all"  # "all", "completed", "failed"
        self._active_dialog = None
        self._cache_sub_screen = True
        self._filtered_jobs: List[dict] = []
        self._rendered_count = 0
        self._load_more_btn = None
        self._last_render_sig = None

        self.setObjectName("HistoryPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_list_stylesheet(scale)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header toolbar (2 rows: Row 1 = Stats & Actions, Row 2 = Filter Tabs)
        hdr = QtWidgets.QFrame()
        hdr.setObjectName("HistoryToolbar")
        hdr.setStyleSheet(f"""
            QFrame#HistoryToolbar {{
                background: #0B1220;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }}
        """)
        hdr_lay = QtWidgets.QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(_s(14, scale), _s(6, scale), _s(14, scale), _s(6, scale))
        hdr_lay.setSpacing(_s(6, scale))

        row1 = QtWidgets.QHBoxLayout()
        row1.setSpacing(_s(8, scale))

        title_lbl = QtWidgets.QLabel("PRINT HISTORY")
        title_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(13, scale)}px; font-weight: 900; letter-spacing: 1px;")
        row1.addWidget(title_lbl)

        self.badge_tot = QtWidgets.QLabel("TOTAL: 0")
        self.badge_tot.setStyleSheet(f"""
            background: rgba(0, 229, 255, 0.12);
            color: #00E5FF;
            border: 1px solid rgba(0, 229, 255, 0.3);
            border-radius: {_s(10, scale)}px;
            padding: {_s(2, scale)}px {_s(7, scale)}px;
            font-size: {_s(9, scale)}px;
            font-weight: 800;
        """)
        row1.addWidget(self.badge_tot)

        self.badge_succ = QtWidgets.QLabel("✔ 0")
        self.badge_succ.setStyleSheet(f"""
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-radius: {_s(10, scale)}px;
            padding: {_s(2, scale)}px {_s(7, scale)}px;
            font-size: {_s(9, scale)}px;
            font-weight: 800;
        """)
        row1.addWidget(self.badge_succ)

        self.badge_fail = QtWidgets.QLabel("✖ 0")
        self.badge_fail.setStyleSheet(f"""
            background: rgba(239, 68, 68, 0.15);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.35);
            border-radius: {_s(10, scale)}px;
            padding: {_s(2, scale)}px {_s(7, scale)}px;
            font-size: {_s(9, scale)}px;
            font-weight: 800;
        """)
        row1.addWidget(self.badge_fail)
        row1.addStretch(1)

        # Refresh button
        self.refresh_btn = QtWidgets.QPushButton("⟳")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setFixedSize(_s(28, scale), _s(28, scale))
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #F8FAFC;
                border-radius: {_s(6, scale)}px;
                font-size: {_s(13, scale)}px;
                font-weight: 800;
            }}
        """)
        self.refresh_btn.clicked.connect(lambda: self.reload_history(force=True))
        row1.addWidget(self.refresh_btn)

        # Clear All button
        self.clear_btn = QtWidgets.QPushButton("✕ Clear All")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setFixedHeight(_s(28, scale))
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(239, 68, 68, 0.16);
                border: 1px solid rgba(239, 68, 68, 0.45);
                color: #FCA5A5;
                border-radius: {_s(6, scale)}px;
                font-size: {_s(10, scale)}px;
                font-weight: 800;
                padding: 0 {_s(10, scale)}px;
            }}
            QPushButton:hover {{
                background: #EF4444;
                color: #FFFFFF;
            }}
        """)
        self.clear_btn.clicked.connect(self._prompt_clear_all)
        row1.addWidget(self.clear_btn)
        hdr_lay.addLayout(row1)

        # Row 2: Filter tabs
        row2 = QtWidgets.QHBoxLayout()
        row2.setSpacing(_s(8, scale))

        self.flt_group = QtWidgets.QButtonGroup(self)
        self.flt_all = QtWidgets.QPushButton("All")
        self.flt_all.setCheckable(True)
        self.flt_all.setChecked(True)
        self.flt_succ = QtWidgets.QPushButton("✔ Successful")
        self.flt_succ.setCheckable(True)
        self.flt_fail = QtWidgets.QPushButton("✖ Failed")
        self.flt_fail.setCheckable(True)

        for b, flt_val in [(self.flt_all, "all"), (self.flt_succ, "completed"), (self.flt_fail, "failed")]:
            b.setObjectName("HistFilterBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(_s(28, scale))
            b.clicked.connect(lambda _c=False, f=flt_val: self._on_filter_changed(f))
            self.flt_group.addButton(b)
            row2.addWidget(b)

        row2.addStretch(1)
        hdr_lay.addLayout(row2)

        main_layout.addWidget(hdr)

        # Scroll Area for print jobs
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("CalScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.list_container = QtWidgets.QWidget()
        self.list_container.setObjectName("CalContainer")
        self.list_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.list_layout = QtWidgets.QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(10, scale))
        self.list_layout.setSpacing(_s(8, scale))
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.list_container)
        main_layout.addWidget(self.scroll, 1)

    def _apply_list_stylesheet(self, s: float):
        self.setStyleSheet(f"""
            QPushButton#HistFilterBtn {{
                background: #1E293B;
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #94A3B8;
                border-radius: {_s(6, s)}px;
                font-size: {_s(10, s)}px;
                font-weight: 800;
                padding: 0 {_s(12, s)}px;
            }}
            QPushButton#HistFilterBtn:checked {{
                background: #00E5FF;
                color: #020617;
                border-color: #00E5FF;
            }}
            QFrame#HistoryItemCard {{
                background: #0F172A;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: {_s(10, s)}px;
            }}
            QFrame#HistoryItemCard:hover {{
                border-color: #00E5FF;
                background: #17233B;
            }}
            QLabel#HistIcon {{
                border-radius: {_s(8, s)}px;
                font-size: {_s(16, s)}px;
                font-weight: 900;
            }}
            QLabel#HistIcon[ok="true"] {{
                background: rgba(16, 185, 129, 0.16);
                color: #10B981;
                border: 1.5px solid rgba(16, 185, 129, 0.45);
            }}
            QLabel#HistIcon[ok="false"] {{
                background: rgba(239, 68, 68, 0.18);
                color: #EF4444;
                border: 1.5px solid rgba(239, 68, 68, 0.5);
            }}
            QLabel#HistTag {{
                border-radius: {_s(4, s)}px;
                padding: {_s(1, s)}px {_s(6, s)}px;
                font-size: {_s(9, s)}px;
                font-weight: 800;
            }}
            QLabel#HistTag[ok="true"] {{
                background: rgba(16, 185, 129, 0.16);
                color: #10B981;
                border: 1px solid rgba(16, 185, 129, 0.45);
            }}
            QLabel#HistTag[ok="false"] {{
                background: rgba(239, 68, 68, 0.18);
                color: #EF4444;
                border: 1px solid rgba(239, 68, 68, 0.5);
            }}
            QLabel#HistDate {{
                color: #94A3B8;
                font-size: {_s(10, s)}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#HistMesh {{
                background: rgba(56, 189, 248, 0.12);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: {_s(4, s)}px;
                padding: {_s(1, s)}px {_s(6, s)}px;
                font-size: {_s(9, s)}px;
                font-weight: 700;
            }}
            QLabel#HistName {{
                color: #F8FAFC;
                font-size: {_s(13, s)}px;
                font-weight: 800;
                background: transparent;
                border: none;
            }}
            QLabel#HistStat {{
                color: #94A3B8;
                font-size: {_s(10, s)}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QPushButton#HistReprintBtn {{
                background: rgba(0, 229, 255, 0.14);
                border: 1px solid rgba(0, 229, 255, 0.45);
                color: #00E5FF;
                border-radius: {_s(6, s)}px;
                font-size: {_s(10, s)}px;
                font-weight: 800;
                padding: 0 {_s(10, s)}px;
            }}
            QPushButton#HistReprintBtn:hover {{
                background: #00E5FF;
                color: #020617;
            }}
            QLabel#HistArrow {{
                color: #64748B;
                font-size: {_s(18, s)}px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QPushButton#HistLoadMoreBtn {{
                background: #1E293B;
                border: 1px solid rgba(0, 229, 255, 0.35);
                color: #7DD3FC;
                border-radius: {_s(8, s)}px;
                font-size: {_s(11, s)}px;
                font-weight: 800;
                padding: {_s(8, s)}px {_s(16, s)}px;
            }}
            QPushButton#HistLoadMoreBtn:hover {{
                background: rgba(0, 229, 255, 0.18);
                color: #FFFFFF;
            }}
        """)

    def set_moonraker(self, mr):
        self.moonraker = mr
        self.reload_history()

    def reload_history(self, force: bool = False):
        if not self.moonraker:
            return
        if force:
            self.moonraker.get_history(limit=100, on_done=self._on_history_loaded, force=True)
        else:
            self.moonraker.get_history(limit=100, on_done=self._on_history_loaded)

    def _on_history_loaded(self, jobs: list):
        self.jobs = list(jobs) if jobs else []
        self._update_badges()
        self._populate_list()

    def _update_badges(self):
        tot = len(self.jobs)
        succ = sum(1 for j in self.jobs if is_job_successful(j))
        fail = sum(1 for j in self.jobs if is_job_failed(j))
        self.badge_tot.setText(f"TOTAL: {tot}")
        self.badge_succ.setText(f"✔ {succ}")
        self.badge_fail.setText(f"✖ {fail}")

    def _on_filter_changed(self, flt: str):
        if flt == self.active_filter and self._last_render_sig is not None:
            return
        self.active_filter = flt
        self._populate_list()

    def _clear_list_items(self):
        self._load_more_btn = None
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setUpdatesEnabled(False)
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _populate_list(self):
        filtered = self.jobs
        if self.active_filter == "completed":
            filtered = [j for j in self.jobs if is_job_successful(j)]
        elif self.active_filter == "failed":
            filtered = [j for j in self.jobs if is_job_failed(j)]

        sig = (
            self.active_filter,
            round(self.scale, 2),
            tuple((j.get("job_id"), j.get("status"), j.get("end_time"), j.get("total_duration")) for j in filtered),
        )
        if sig == self._last_render_sig and self.list_layout.count() > 0:
            return
        self._last_render_sig = sig
        self._filtered_jobs = filtered
        self._rendered_count = 0

        self.list_container.setUpdatesEnabled(False)
        try:
            self._clear_list_items()
            self.scroll.verticalScrollBar().setValue(0)

            if not filtered:
                empty_box = QtWidgets.QFrame()
                empty_box.setStyleSheet(f"""
                    background: #0D1527;
                    border: 1px dashed rgba(255, 255, 255, 0.1);
                    border-radius: {_s(12, self.scale)}px;
                    padding: {_s(40, self.scale)}px;
                """)
                e_lay = QtWidgets.QVBoxLayout(empty_box)
                e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                e_lbl = QtWidgets.QLabel("No print history found")
                e_lbl.setStyleSheet(f"color: #F8FAFC; font-size: {_s(14, self.scale)}px; font-weight: 800;")
                e_lay.addWidget(e_lbl, 0, Qt.AlignmentFlag.AlignCenter)
                e_sub = QtWidgets.QLabel("Completed and cancelled print jobs will show up here.")
                e_sub.setStyleSheet(f"color: #64748B; font-size: {_s(11, self.scale)}px;")
                e_lay.addWidget(e_sub, 0, Qt.AlignmentFlag.AlignCenter)
                self.list_layout.addWidget(empty_box)
                return

            self._append_next_batch()
        finally:
            self.list_container.setUpdatesEnabled(True)
            self.list_layout.activate()
            self.list_container.adjustSize()

    def _append_next_batch(self):
        if self._load_more_btn is not None:
            btn = self._load_more_btn
            self._load_more_btn = None
            self.list_layout.removeWidget(btn)
            btn.hide()
            btn.setParent(None)
            btn.deleteLater()

        end = min(len(self._filtered_jobs), self._rendered_count + self.PAGE_SIZE)
        for job in self._filtered_jobs[self._rendered_count:end]:
            card = HistoryItemCard(job, scale=self.scale, parent=self.list_container)
            card.clicked.connect(self._open_job_details)
            card.reprint_requested.connect(self._on_reprint_requested)
            self.list_layout.addWidget(card)
        self._rendered_count = end

        remaining = len(self._filtered_jobs) - self._rendered_count
        if remaining > 0:
            btn = QtWidgets.QPushButton(f"Load More ({remaining} older prints)")
            btn.setObjectName("HistLoadMoreBtn")
            btn.setFixedHeight(_s(36, self.scale))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self._on_load_more)
            self._load_more_btn = btn
            self.list_layout.addWidget(btn)

    def _on_load_more(self):
        self.list_container.setUpdatesEnabled(False)
        try:
            self._append_next_batch()
        finally:
            self.list_container.setUpdatesEnabled(True)
            self.list_layout.activate()
            self.list_container.adjustSize()
            self.list_layout.activate()
            self.list_container.adjustSize()

    def _open_job_details(self, job: dict):
        if is_drag_active():
            return
        if self._active_dialog:
            try:
                self._active_dialog.close()
            except Exception:
                pass
        top_window = self.window()
        dlg = HistoryDetailsDialog(job, scale=self.scale, parent=top_window)
        self._active_dialog = dlg
        dlg.print_again_requested.connect(self._on_reprint_requested)
        dlg.show()
        dlg.raise_()

    def _prompt_clear_all(self):
        if self._active_dialog:
            try:
                self._active_dialog.close()
            except Exception:
                pass
        top_window = self.window()
        dlg = ClearConfirmDialog(scale=self.scale, parent=top_window)
        self._active_dialog = dlg
        dlg.confirmed.connect(self._do_clear_all)
        dlg.show()
        dlg.raise_()

    def _do_clear_all(self):
        if self.moonraker:
            self.moonraker.delete_all_history(on_done=lambda _ok: self.reload_history(force=True))

    def _on_reprint_requested(self, job: dict):
        fn = job.get("filename")
        if not fn:
            return
        if self.moonraker:
            self.moonraker.start_print(fn)
        # Notify MainWindow to switch to printing page
        win = self.window()
        if hasattr(win, "show_page"):
            win.show_page("printing")

    def _cleanup(self):
        if self._active_dialog:
            try:
                self._active_dialog.close()
                self._active_dialog.setParent(None)
                self._active_dialog.deleteLater()
            except Exception:
                pass
            self._active_dialog = None

    def apply_scale(self, s: float):
        if s == self.scale:
            return
        self.scale = s
        self._apply_list_stylesheet(s)
        if self.jobs:
            self._populate_list()
