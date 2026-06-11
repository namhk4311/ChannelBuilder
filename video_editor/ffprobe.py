"""Đọc duration + resolution từ file video qua ffprobe."""
from __future__ import annotations

import logging
import math
import subprocess
from typing import Optional

log = logging.getLogger(__name__)


def ffprobe_metadata(path: str) -> tuple[float, Optional[str]]:
    """
    Trả về (duration_sec, resolution_str).
    resolution_str dạng "1080x1920 dọc (9:16)" hoặc None nếu probe fail.
    """
    try:
        d = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(d.stdout.strip() or 0.0)

        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", path],
            capture_output=True, text=True, timeout=10,
        )
        wh = r.stdout.strip()
        if not wh or "x" not in wh:
            return duration, None
        w_str, h_str = wh.split("x")[:2]
        w, h = int(w_str), int(h_str)

        if w < h:
            orient = "dọc"
        elif w > h:
            orient = "ngang"
        else:
            orient = "vuông"

        g = math.gcd(w, h)
        a, b = w // g, h // g
        resolution = f"{w}x{h} {orient} ({a}:{b})"
        log.debug("ffprobe: %s → %.2fs %s", path, duration, resolution)
        return duration, resolution
    except (subprocess.SubprocessError, ValueError) as e:
        log.warning("ffprobe failed for %s: %s", path, e)
        return 0.0, None
