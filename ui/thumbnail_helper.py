"""Helper for loading and caching Moonraker gcode thumbnails asynchronously.

Supports:
1. Moonraker extracted thumbnails (/server/files/gcodes/[path]/.thumbs/...)
2. Slicer-embedded base64 thumbnails inside .gcode headers (OrcaSlicer, Cura, PrusaSlicer, BambuStudio)
3. Slicer 3MF project containers (.gcode.3mf, .3mf) containing embedded preview PNGs (OrcaSlicer, BambuStudio)
4. Local gcode file parsing on the Raspberry Pi (/home/pi/printer_data/gcodes)
5. Cross-thread Qt QueuedConnection dispatch guaranteeing thread-safe QPixmap rendering on the GUI main thread
"""

import base64
import io
import os
import re
import threading
import urllib.parse
import urllib.request
import zipfile
from typing import Optional, Dict, List, Callable

from .qt import QtWidgets, QtGui, QtCore, Qt, Signal
from . import icons

# Global memory cache: key -> QPixmap
_THUMB_CACHE: Dict[str, QtGui.QPixmap] = {}
_PENDING_CALLBACKS: Dict[str, List[Callable[[QtGui.QPixmap], None]]] = {}
_PENDING_LOCK = threading.Lock()

# Common local gcode directories on Linux / Raspberry Pi
LOCAL_GCODE_DIRS = [
    os.path.expanduser("~/printer_data/gcodes"),
    "/home/pi/printer_data/gcodes",
    "/root/printer_data/gcodes",
]


class _ThumbDispatcher(QtCore.QObject):
    """Queued dispatcher that ensures callbacks execute on the Qt main GUI thread."""
    dispatch = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dispatch.connect(self._run_on_main, Qt.ConnectionType.QueuedConnection)

    @QtCore.Slot(object)
    def _run_on_main(self, fn):
        try:
            fn()
        except Exception:
            pass


_DISPATCHER: Optional[_ThumbDispatcher] = None


def init_dispatcher():
    """Ensure dispatcher is instantiated and owned by the Qt GUI main thread."""
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = _ThumbDispatcher()
        app = QtWidgets.QApplication.instance()
        if app:
            _DISPATCHER.moveToThread(app.thread())
    return _DISPATCHER


def _safe_call(cb: Callable, *args):
    """Safely execute a UI callback, ignoring dead C++ widget references."""
    try:
        cb(*args)
    except (RuntimeError, ReferenceError):
        pass
    except Exception:
        pass


def get_default_thumbnail(size: int = 120) -> QtGui.QPixmap:
    return icons.pixmap("files", size)


def extract_embedded_thumbnail_from_bytes(raw_bytes: bytes) -> Optional[QtGui.QImage]:
    """Parse embedded base64 PNG/JPG thumbnail from gcode bytes (OrcaSlicer, Cura, PrusaSlicer, BambuStudio)."""
    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
        # Match standard thumbnail blocks:
        # ; thumbnail begin 300x300 2508 ... ; thumbnail end
        # ; thumbnail_JPG begin 300 300 ... ; thumbnail_JPG end
        # ; cura thumbnail begin ...
        pattern = r"(?:;|\/\/)?\s*thumbnail(?:_[a-zA-Z0-9]+)?\s+begin\s+(\d+)[x\s]+(\d+).*?\n(.*?)(?:;|\/\/)?\s*thumbnail(?:_[a-zA-Z0-9]+)?\s+end"
        matches = list(re.finditer(pattern, text, re.DOTALL | re.IGNORECASE))
        if not matches:
            return None

        # Pick largest resolution thumbnail
        best_match = None
        best_area = 0
        for m in matches:
            try:
                w, h = int(m.group(1)), int(m.group(2))
                if w * h > best_area:
                    best_area = w * h
                    best_match = m
            except Exception:
                best_match = m

        if best_match:
            b64_lines = [
                line.strip().lstrip(";").lstrip("/").lstrip("#").strip()
                for line in best_match.group(3).splitlines()
            ]
            raw_b64 = "".join(b64_lines)
            if not raw_b64:
                return None
            img_bytes = base64.b64decode(raw_b64)
            img = QtGui.QImage()
            if img.loadFromData(img_bytes) and not img.isNull():
                return img
    except Exception:
        pass
    return None


def extract_thumbnail_from_3mf_bytes(raw_bytes: bytes) -> Optional[QtGui.QImage]:
    """Extract embedded preview PNG from OrcaSlicer or BambuStudio 3MF zip archive."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
        candidates = [
            "Metadata/plate_1.png",
            "Metadata/plate_1_small.png",
            "Metadata/top_1.png",
            "Metadata/pick_1.png",
            "thumbnail.png",
            ".thumbs/plate_1.png",
        ]
        names = zf.namelist()
        for c in candidates:
            if c in names:
                data = zf.read(c)
                qi = QtGui.QImage()
                if qi.loadFromData(data) and not qi.isNull():
                    return qi
        for n in names:
            if n.lower().endswith(".png"):
                data = zf.read(n)
                qi = QtGui.QImage()
                if qi.loadFromData(data) and not qi.isNull():
                    return qi
    except Exception:
        pass
    return None


def extract_embedded_thumbnail_from_file(filepath: str, max_bytes: int = 500000) -> Optional[QtGui.QImage]:
    """Parse embedded thumbnail from a local file on disk."""
    if not os.path.exists(filepath):
        return None
    try:
        if filepath.lower().endswith((".3mf", ".gcode.3mf")):
            with open(filepath, "rb") as f:
                return extract_thumbnail_from_3mf_bytes(f.read())
        with open(filepath, "rb") as f:
            raw = f.read(max_bytes)
        return extract_embedded_thumbnail_from_bytes(raw)
    except Exception:
        pass
    return None


def load_thumbnail_async(host: str, dir_path: str, thumb_rel_path: str, filename: str, target_size: int, on_loaded):
    """Load a thumbnail asynchronously from Moonraker or embedded gcode header.

    Calls on_loaded(pixmap) safely on the Qt GUI thread once ready.
    """
    clean_dir = (dir_path or "").replace("gcodes/", "").replace("gcodes", "").strip("/")
    cache_key = f"{host}_{clean_dir}_{filename}_{thumb_rel_path or 'embedded'}"
    fallback_key = f"{host}_{clean_dir}_{filename}"

    # Check cache
    if cache_key in _THUMB_CACHE:
        pix = _THUMB_CACHE[cache_key]
        if on_loaded:
            QtCore.QTimer.singleShot(0, lambda: _safe_call(on_loaded, pix))
        return
    if fallback_key in _THUMB_CACHE:
        pix = _THUMB_CACHE[fallback_key]
        if on_loaded:
            QtCore.QTimer.singleShot(0, lambda: _safe_call(on_loaded, pix))
        return

    # Thread-safe callback registration
    with _PENDING_LOCK:
        if cache_key in _PENDING_CALLBACKS:
            if on_loaded:
                _PENDING_CALLBACKS[cache_key].append(on_loaded)
            return
        _PENDING_CALLBACKS[cache_key] = [on_loaded] if on_loaded else []

    dispatcher = init_dispatcher()

    def _worker():
        img: Optional[QtGui.QImage] = None

        # --- Strategy 1: Check Moonraker .thumbs URL if thumb_rel_path is known ---
        if host and thumb_rel_path:
            try:
                clean_rel = thumb_rel_path.lstrip("/")
                full_rel = f"{clean_dir}/{clean_rel}" if clean_dir else clean_rel
                encoded_path = "/".join(urllib.parse.quote(seg) for seg in full_rel.split("/"))
                url = f"http://{host}/server/files/gcodes/{encoded_path}"
                req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    if resp.status == 200:
                        raw_data = resp.read()
                        qi = QtGui.QImage()
                        if qi.loadFromData(raw_data) and not qi.isNull():
                            img = qi
            except Exception:
                pass

        # Also check standard Moonraker thumbnail path if not specified
        if not img and host and filename and not filename.lower().endswith(".3mf"):
            name_base, _ = os.path.splitext(filename)
            for size_suffix in ("-300x300.png", "-48x48.png", "-32x32.png"):
                try:
                    rel = f".thumbs/{name_base}{size_suffix}"
                    full_rel = f"{clean_dir}/{rel}" if clean_dir else rel
                    encoded_path = "/".join(urllib.parse.quote(seg) for seg in full_rel.split("/"))
                    url = f"http://{host}/server/files/gcodes/{encoded_path}"
                    req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay"})
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        if resp.status == 200:
                            raw_data = resp.read()
                            qi = QtGui.QImage()
                            if qi.loadFromData(raw_data) and not qi.isNull():
                                img = qi
                                break
                except Exception:
                    pass

        # --- Strategy 2: Check local file on Raspberry Pi filesystem ---
        if not img and filename:
            for base_dir in LOCAL_GCODE_DIRS:
                candidate = os.path.join(base_dir, clean_dir, filename) if clean_dir else os.path.join(base_dir, filename)
                if os.path.exists(candidate):
                    name_base, _ = os.path.splitext(filename)
                    parent_dir = os.path.dirname(candidate)
                    for sz_suf in ("-300x300.png", "-48x48.png", "-32x32.png"):
                        thumb_candidate = os.path.join(parent_dir, ".thumbs", f"{name_base}{sz_suf}")
                        if os.path.exists(thumb_candidate):
                            qi = QtGui.QImage(thumb_candidate)
                            if not qi.isNull():
                                img = qi
                                break
                    if not img:
                        qi = extract_embedded_thumbnail_from_file(candidate)
                        if qi:
                            img = qi
                            break

        # --- Strategy 3: Stream from Moonraker for embedded slicer thumbnail ---
        if not img and host and filename:
            try:
                full_fn = f"{clean_dir}/{filename}" if clean_dir else filename
                encoded_fn = "/".join(urllib.parse.quote(seg) for seg in full_fn.split("/"))
                url = f"http://{host}/server/files/gcodes/{encoded_fn}"

                if filename.lower().endswith((".3mf", ".gcode.3mf")):
                    # Fetch 3mf file to extract plate thumbnail
                    req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay"})
                    with urllib.request.urlopen(req, timeout=4.0) as resp:
                        raw_data = resp.read()
                        qi = extract_thumbnail_from_3mf_bytes(raw_data)
                        if qi:
                            img = qi
                else:
                    # Request first 400KB of gcode (captures high-res 300x300 / 400x400 Orca/Cura thumbnails)
                    req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay", "Range": "bytes=0-409600"})
                    with urllib.request.urlopen(req, timeout=4.0) as resp:
                        raw_data = resp.read(409600)
                        qi = extract_embedded_thumbnail_from_bytes(raw_data)
                        if qi:
                            img = qi
            except Exception:
                pass

        # Dispatch back to Qt GUI main thread via queued signal
        def _finish_on_main():
            with _PENDING_LOCK:
                cbs = _PENDING_CALLBACKS.pop(cache_key, [])
            if img and not img.isNull():
                pm = QtGui.QPixmap.fromImage(img)
                if not pm.isNull():
                    _THUMB_CACHE[cache_key] = pm
                    _THUMB_CACHE[fallback_key] = pm
                    for cb in cbs:
                        _safe_call(cb, pm)

        dispatcher.dispatch.emit(_finish_on_main)

    threading.Thread(target=_worker, daemon=True).start()
