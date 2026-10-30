"""Helper for loading and caching Moonraker gcode thumbnails asynchronously."""

import base64
import os
import re
import threading
import urllib.parse
import urllib.request
from typing import Optional, Dict

from .qt import QtGui, QtCore, Qt
from . import icons

# Global memory cache: key -> QPixmap
_THUMB_CACHE: Dict[str, QtGui.QPixmap] = {}
_ACTIVE_DOWNLOADS = set()


def get_default_thumbnail(size: int = 120) -> QtGui.QPixmap:
    return icons.pixmap("files", size)


def load_thumbnail_async(host: str, thumb_rel_path: str, cache_key: str, target_size: int, on_loaded):
    """Load a thumbnail from Moonraker HTTP asynchronously and notify via on_loaded(pixmap)."""
    if not thumb_rel_path or not host:
        return

    if cache_key in _THUMB_CACHE:
        pix = _THUMB_CACHE[cache_key]
        if on_loaded:
            QtCore.QTimer.singleShot(0, lambda: on_loaded(pix))
        return

    if cache_key in _ACTIVE_DOWNLOADS:
        return
    _ACTIVE_DOWNLOADS.add(cache_key)

    def _worker():
        pix = None
        try:
            # Moonraker serves thumbnails under /server/files/gcodes/<relative_path>
            # Ensure path is URL encoded
            encoded_path = "/".join(urllib.parse.quote(seg) for seg in thumb_rel_path.split("/"))
            url = f"http://{host}/server/files/gcodes/{encoded_path}"
            req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    raw_data = resp.read()
                    pm = QtGui.QPixmap()
                    if pm.loadFromData(raw_data):
                        # Cache scaled smooth pixmap
                        pix = pm
        except Exception:
            pass
        finally:
            _ACTIVE_DOWNLOADS.discard(cache_key)

        if pix and not pix.isNull():
            _THUMB_CACHE[cache_key] = pix
            if on_loaded:
                QtCore.QTimer.singleShot(0, lambda: on_loaded(pix))

    threading.Thread(target=_worker, daemon=True).start()


def extract_embedded_thumbnail_from_file(filepath: str, max_bytes: int = 400000) -> Optional[QtGui.QPixmap]:
    """Parse embedded base64 PNG thumbnail from gcode header (OrcaSlicer, PrusaSlicer, Cura, Bambu)."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(max_bytes)

        # Look for ; thumbnail begin WxH LEN
        # ...
        # ; thumbnail end
        matches = list(re.finditer(r";\s*thumbnail\s+begin\s+(\d+)x(\d+)\s+(\d+)\s*\n(.*?);\s*thumbnail\s+end", head, re.DOTALL))
        if not matches:
            return None

        # Choose the largest resolution thumbnail
        best_match = None
        best_area = 0
        for m in matches:
            w, h = int(m.group(1)), int(m.group(2))
            if w * h > best_area:
                best_area = w * h
                best_match = m

        if best_match:
            b64_lines = [line.strip().lstrip(";").strip() for line in best_match.group(4).splitlines()]
            raw_b64 = "".join(b64_lines)
            img_bytes = base64.b64decode(raw_b64)
            pm = QtGui.QPixmap()
            if pm.loadFromData(img_bytes):
                return pm
    except Exception:
        pass
    return None
