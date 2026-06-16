# -*- coding: utf-8 -*-
"""Render banner: fill template HTML → Playwright seek(t) screenshots → silent.mp4.

DETERMINISTIC: drive animation qua window.seek(t) (KHÔNG wall-clock). Chụp từng
frame ở t = i/fps, ghép bằng ffmpeg. silent.mp4 dài đúng `duration` giây.
"""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("banner_proto.render")

TEMPLATES_DIR = Path(__file__).parent / "templates"
W, H = 1080, 1920

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".gif": "image/gif"}

# Cụm số/đơn vị (tự nhấn nếu LLM quên *..*). Bắt đầu bằng chữ số.
_NUM_RE = re.compile(r"(\d[\d.,]*(?:\s?(?:%|tỷ|triệu|nghìn|x|K|M|GB|MB))?)", re.IGNORECASE)
_SPAN_SPLIT_RE = re.compile(r'(<span class="hl-key">.*?</span>)')


def _emphasize(text: str) -> str:
    """Escape + làm NỔI BẬT dữ kiện: cụm trong *..* → <span class="hl-key">; số/% trần
    cũng được nhấn (fallback khi LLM quên đánh dấu). quote=False vì là text content
    (không escape ' " → tránh sinh entity có chữ số làm _NUM_RE bắt nhầm)."""
    safe = html.escape(text or "", quote=False)
    safe = re.sub(r"\*([^*]+)\*", r'<span class="hl-key">\1</span>', safe)  # cụm LLM đánh dấu
    # Nhấn số/đơn vị ở các đoạn NGOÀI span đã có (chỉ số chẵn sau khi split).
    parts = _SPAN_SPLIT_RE.split(safe)
    for i in range(0, len(parts), 2):
        parts[i] = _NUM_RE.sub(r'<span class="hl-key">\1</span>', parts[i])
    return "".join(parts).replace("*", "")  # bỏ dấu * lẻ (cap cắt giữa cặp)


def _bg_style(theme: dict, image_path: Optional[Path]) -> str:
    if image_path and image_path.exists():
        mime = _MIME.get(image_path.suffix.lower(), "image/jpeg")
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"background-image:url('data:{mime};base64,{b64}');"
    # Fallback: gradient từ theme khi không có ảnh
    return (f"background:radial-gradient(120% 90% at 50% 28%,"
            f"{theme['secondary']} 0%, {theme['primary']} 78%);")


def _fill_template(obj: dict, image_path: Optional[Path], duration: float,
                   template_name: str = "template_01_epic", reveal: float = 0.9,
                   cues: Optional[list] = None, index: int = 1, total: int = 1) -> str:
    """Thay placeholder @@..@@ trong template bằng dữ liệu (đã HTML-escape)."""
    esc = html.escape
    theme = obj["theme"]

    sub = obj.get("event_subtitle") or ""
    subtitle_block = f'<p id="subtitle" class="subtitle">{_emphasize(sub)}</p>' if sub else ""

    chips = []
    if obj.get("period"):
        chips.append(f'<div class="chip"><b>{esc(obj["period"])}</b></div>')
    if obj.get("time_detail"):
        chips.append(f'<div class="chip">{esc(obj["time_detail"])}</div>')
    meta_block = f'<div id="period" class="meta">{"".join(chips)}</div>' if chips else ""

    hls = obj.get("highlights") or []
    if hls:
        rows = "".join(f'<div class="hl"><span class="dot"></span><span>{_emphasize(h)}</span></div>'
                       for h in hls)
        highlights_block = f'<div class="highlights" id="highlights">{rows}</div>'
    else:
        highlights_block = ""

    template = (TEMPLATES_DIR / f"{template_name}.html").read_text(encoding="utf-8")
    timeline_js = (TEMPLATES_DIR / "timeline.js").read_text(encoding="utf-8")
    # inject reveal cho scene (scene>0 dùng reveal ~0 vì xfade đã lo chuyển cảnh)
    timeline_js = f"window.REVEAL={reveal:.3f};\n" + timeline_js
    treatments_css = (TEMPLATES_DIR / "treatments.css").read_text(encoding="utf-8")

    # Brand vars cho template Đơn sắc (nền đơn sắc + pattern chéo). Image templates
    # bỏ qua các var này (không tham chiếu) — default theo theme cho an toàn.
    repl = {
        "@@PRIMARY@@": theme["primary"],
        "@@SECONDARY@@": theme["secondary"],
        "@@ACCENT@@": theme["accent"],
        "@@BG@@": theme.get("bg") or theme["primary"],
        "@@TEXT@@": theme.get("text") or "#ffffff",
        "@@MUTED@@": theme.get("muted") or "rgba(255,255,255,0.62)",
        "@@PATTERN@@": theme.get("pattern") or "rgba(255,255,255,0.05)",
        "@@BG_STYLE@@": _bg_style(theme, image_path),
        "@@KICKER@@": esc(obj.get("subject") or ""),
        "@@TITLE@@": esc(obj["event_title"]),
        "@@SUBTITLE_BLOCK@@": subtitle_block,
        "@@META_BLOCK@@": meta_block,
        "@@HIGHLIGHTS_BLOCK@@": highlights_block,
        "@@CTA@@": esc(obj["cta"]),
        "@@DURATION_SEC@@": f"{duration:.3f}",
        "@@INDEX@@": str(index),
        "@@INDEX_TOTAL@@": str(total),
        "@@CAPTIONS_JSON@@": json.dumps(cues or [], ensure_ascii=False),
        "@@TIMELINE_JS@@": timeline_js,
        "@@TREATMENTS_CSS@@": treatments_css,
    }
    for k, v in repl.items():
        template = template.replace(k, v)
    return template


def _capture_frames(html_path: Path, frames_dir: Path, duration: float, fps: int,
                    progress_cb: Optional[Callable] = None) -> int:
    """Mở headless chromium, seek(t) + screenshot từng frame. Trả số frame."""
    from playwright.sync_api import sync_playwright

    n_frames = max(1, round(duration * fps))
    frames_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--force-color-profile=srgb", "--hide-scrollbars",
            # Cần khi chạy trong container (AgentBase chạy root, /dev/shm nhỏ, không GPU):
            # thiếu --no-sandbox → chromium crash ngay (TargetClosedError);
            # --disable-dev-shm-usage tránh hết /dev/shm; --disable-gpu tránh GPU process crash.
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        ])
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(html_path.as_uri(), wait_until="networkidle")
        # Chờ font load xong → tránh frame đầu sai font (đúng dấu tiếng Việt)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(250)  # settle: để autofit-sau-font + layout ổn định trước frame đầu
        clip = {"x": 0, "y": 0, "width": W, "height": H}
        for i in range(n_frames):
            t = i / fps
            page.evaluate("(t) => window.seek(t)", t)
            page.screenshot(path=str(frames_dir / f"frame_{i:05d}.png"), clip=clip)
            if progress_cb and (i % 15 == 0 or i == n_frames - 1):
                pct = 40 + int(40 * (i + 1) / n_frames)   # render chiếm dải 40-80%
                progress_cb(pct, f"capture frame {i + 1}/{n_frames}")
        browser.close()
    return n_frames


def _frames_to_video(frames_dir: Path, out_path: Path, fps: int) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frames→video failed: {result.stderr[-300:]}")
    return out_path


def render_silent_video(obj: dict, image_path: Optional[Path], duration: float,
                        workdir: Path, fps: int = 30,
                        progress_cb: Optional[Callable] = None,
                        template_name: str = "template_01_epic",
                        reveal: float = 0.9, out_name: str = "silent.mp4",
                        cues: Optional[list] = None, index: int = 1, total: int = 1) -> Path:
    """object + ảnh nền + duration → silent mp4 (1080x1920, dài đúng duration).

    cues: phụ đề theo cụm [{t0,t1,text}] (template Đơn sắc) — None nếu không phụ đề.
    index/total: số thứ tự cảnh (1-based) cho template listicle (@@INDEX@@)."""
    html_path = workdir / (out_name.replace(".mp4", "") + ".html")
    html_path.write_text(
        _fill_template(obj, image_path, duration, template_name, reveal, cues, index, total),
        encoding="utf-8")
    log.info("render · template=%s reveal=%.2f dur=%.2fs fps=%d",
             template_name, reveal, duration, fps)

    stem = out_name.replace(".mp4", "")
    frames_dir = workdir / f"frames_{stem}"
    n = _capture_frames(html_path, frames_dir, duration, fps, progress_cb)
    log.info("render · captured %d frames", n)

    silent = _frames_to_video(frames_dir, workdir / out_name, fps)
    log.info("render · silent video %s", silent.name)
    return silent
