# -*- coding: utf-8 -*-
"""Event game producer: storyboard → gen ảnh + render + ghép + lồng nhạc → upload MinIO.

`produce(run, storyboard, progress_cb)` chạy trong thread của workflow runner. Trả
{output_url, caption, hashtags, script, duration_sec, scenes} — cùng "hình dạng" producer
vlog để human gate + publisher dùng nguyên.
"""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from . import compose_scenes, imagegen, render_capture, tts
from .captions import build_caption_cues
from .content_presets import get_preset
from .visual_styles import brand_theme_to_scene_theme, get_visual_style

log = logging.getLogger("event_game.pipeline")

FPS = 24
VOICE_SPEED = 1.3          # fallback nếu preset thiếu speed
SCENE_GAP = 0.8            # cảnh dài hơn voice ~0.8s → giọng gần như liền mạch (chỉ ~0.2s "lấy hơi"
                           # giữa cảnh, vì TD=0.6s đã trùng phần đuôi). Đặt 0.6 = liền mạch hẳn; tăng = nghỉ lâu hơn.
MUSIC_VOLUME = 0.45        # fallback nếu preset/run thiếu
TTS_CONCURRENCY = 2        # ElevenLabs cap 2 đồng thời
MAX_PARALLEL_SCENES = 3    # render chromium đồng thời

TEMPLATE_MAP = {
    # Ảnh AI (gen)
    "epic": "template_01_epic", "esports": "template_02_esports",
    "poster": "template_03_poster", "editorial": "template_04_editorial",
    # Đơn sắc (không gen ảnh, nền brand)
    "listicle": "template_05_listicle", "news": "template_06_news",
    "corporate": "template_07_corporate", "slide": "template_08_slide",
}


def _strip_tags(s: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", s or "").strip()


def produce(run: dict, storyboard: dict, progress_cb: Optional[Callable] = None) -> dict:
    """run (id, content_type, visual_style, brand, music_track_id) + storyboard → video MinIO.

    content_type → giọng (voice settings/speed/nhạc); visual_style → gen ảnh / nền brand / phụ đề."""
    def prog(p, m):
        if progress_cb:
            progress_cb(p, m)

    scenes = storyboard["scenes"]
    n = len(scenes)
    run_id = run["id"]
    music_track_id = run.get("music_track_id")

    # Cấu hình theo preset (content_type) + visual_style + brand
    preset = get_preset(run.get("content_type"))
    vstyle = get_visual_style(run.get("visual_style"))
    voice = preset.get("voice") or {}
    speed = float(voice.get("speed") or VOICE_SPEED)
    stability, style = voice.get("stability"), voice.get("style")
    gen_images = bool(vstyle["gen_images"])
    do_captions = bool(vstyle["captions"])
    default_tpl = TEMPLATE_MAP.get(vstyle["default_template"], "template_03_poster")
    music_volume = float(run.get("music_volume") or preset.get("music_volume") or MUSIC_VOLUME)

    # Template Đơn sắc → nền màu brand (override theme LLM cho đồng nhất).
    if vstyle["theme"] == "brand":
        brand_theme = brand_theme_to_scene_theme(run.get("brand"))
        for s in scenes:
            s["theme"] = brand_theme

    workdir = Path(tempfile.mkdtemp(prefix=f"event_{run_id}_"))
    try:
        # ── PHA 1: TTS (cap 2 — ElevenLabs) ──
        prog(8, f"Tạo giọng đọc {n} cảnh…")
        vdata = [None] * n

        def tts_one(i):
            v = tts.synthesize(scenes[i]["voiceover"], workdir / f"voice_{i}.mp3",
                               speed=speed, stability=stability, style=style)
            return {"i": i, "voice": v, "voice_sec": tts.probe_duration(v)}

        with ThreadPoolExecutor(max_workers=min(n, TTS_CONCURRENCY)) as ex:
            for fut in as_completed([ex.submit(tts_one, i) for i in range(n)]):
                r = fut.result(); vdata[r["i"]] = r

        # ── PHA 2: (gen ảnh nếu Ảnh AI) + render chromium (cap 3) ──
        prog(35, ("Gen ảnh nền + render " if gen_images else "Render ") + f"{n} cảnh…")
        results = [None] * n

        def render_one(i):
            scene = scenes[i]
            vlen = vdata[i]["voice_sec"] + SCENE_GAP
            tpl = TEMPLATE_MAP.get(scene["template"], default_tpl)
            img = None
            if gen_images:
                try:
                    img = imagegen.generate_bg(scene.get("image_prompt") or "", workdir / f"bg_{i}.png")
                except Exception as e:  # noqa: BLE001 — gen lỗi → gradient
                    log.warning("scene %d gen ảnh lỗi (%s) → gradient", i, e)
            reveal = 0.9 if i == 0 else 0.05
            cues = build_caption_cues(scene["voiceover"], vdata[i]["voice_sec"]) if do_captions else None
            silent = render_capture.render_silent_video(
                scene, img, vlen, workdir, fps=FPS, template_name=tpl,
                reveal=reveal, out_name=f"silent_{i}.mp4", cues=cues, index=i + 1, total=n)
            return {"i": i, "silent": silent, "vlen": vlen,
                    "meta": {"template": scene["template"], "title": scene["event_title"],
                             "voice_sec": round(vdata[i]["voice_sec"], 2),
                             "image": "gen" if img else ("solid" if not gen_images else "gradient"),
                             "captions": len(cues) if cues else 0}}

        with ThreadPoolExecutor(max_workers=min(n, MAX_PARALLEL_SCENES)) as ex:
            done = 0
            for fut in as_completed([ex.submit(render_one, i) for i in range(n)]):
                r = fut.result(); results[r["i"]] = r; done += 1
                prog(35 + int(45 * done / n), f"Render xong {done}/{n} cảnh")

        silents = [results[i]["silent"] for i in range(n)]
        voices = [vdata[i]["voice"] for i in range(n)]
        vlens = [results[i]["vlen"] for i in range(n)]

        # ── PHA 3: ghép chuyển cảnh ──
        prog(82, "Ghép cảnh + chuyển cảnh…")
        composed = compose_scenes.compose(silents, voices, vlens, workdir / "composed.mp4", fps=FPS)

        # ── PHA 4: lồng nhạc nền (to hơn vlog) ──
        final = composed
        if music_track_id:
            try:
                from agents.producer.music import fetch_music_for_pipeline
                music_path = workdir / "music.mp3"
                if fetch_music_for_pipeline(music_track_id, music_path):
                    prog(90, "Lồng nhạc nền…")
                    final = compose_scenes.mux_music_over(
                        composed, music_path, workdir / "final.mp4", volume=music_volume)
                else:
                    log.warning("music_track_id=%s không thấy — bỏ nhạc", music_track_id)
            except Exception as e:  # noqa: BLE001
                log.warning("lồng nhạc lỗi (%s) → giữ video không nhạc", e)
                final = composed

        # ── PHA 5: upload MinIO outputs ──
        prog(95, "Upload video…")
        from agents.producer.pipeline import upload_to_outputs
        duration = tts.probe_duration(final)
        output_url = upload_to_outputs(final, f"event_{run_id}.mp4", "video/mp4")

        prog(100, "Xong!")
        script = " ".join(_strip_tags(s["voiceover"]) for s in scenes).strip()
        return {
            "output_url": output_url,
            "caption": storyboard.get("caption", ""),
            "hashtags": storyboard.get("hashtags", []),
            "script": script,
            "final_duration_sec": round(duration, 2),
            "n_scenes": n,
            "scenes": [results[i]["meta"] for i in range(n)],
            "music_track_id": music_track_id,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
