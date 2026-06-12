"""
Producer agent — script → video tự động.

Pipeline 6 bước, mỗi bước log rõ ràng với prefix `[N/6] step_name`:
  [1/6] tts        — ElevenLabs TTS sinh voice MP3
  [2/6] llm-pick   — VNGCloud AI Platform chọn clip theo script + metadata
  [3/6] concat     — ffmpeg ghép clip đã chọn (muted)
  [4/6] align      — cân duration video ↔ voice (trim hoặc speedup)
  [5/6] mux        — dán voice MP3 lên silent video → final MP4
  [6/6] upload     — upload 3 file lên MinIO outputs bucket

Cuối pipeline in summary table per-step timing.

Endpoint: POST /api/produce  body: {"script": "..."}
"""
from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import (
    AI_PLATFORM_API_KEY,
    AI_PLATFORM_BASE_URL,
    AI_PLATFORM_MODEL,
    BUCKET_OUTPUTS,
    ELEVENLABS_API_KEY,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_VOICE_ID,
    MINIO_ENDPOINT,
)

from . import tts_cache
from .db import pg
from .editor import concat_to_local
from .ffprobe import ffprobe_metadata
from .storage import minio_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["producer"])

TOTAL_STEPS = 6

# ─── Job store (in-memory) ──────────────────────────────────────────────────
# Single-process demo: job state giữ trong dict, mất khi restart server.
# Mỗi job: {status: queued|running|done|error, percent, message, result, error}
JOBS: dict[str, dict] = {}
_JOBS_MAX = 50  # giữ tối đa N job gần nhất, tránh phình memory


def _jobs_evict() -> None:
    if len(JOBS) > _JOBS_MAX:
        for k in list(JOBS.keys())[: len(JOBS) - _JOBS_MAX]:
            JOBS.pop(k, None)


def _step(step: int, name: str, msg: str) -> None:
    """Log per-step message với prefix nhất quán [N/6] step_name · ..."""
    log.info("[%d/%d] %-10s · %s", step, TOTAL_STEPS, name, msg)


def _step_done(step: int, name: str, elapsed: float, summary: str = "") -> None:
    suffix = f" · {summary}" if summary else ""
    log.info("[%d/%d] %-10s · ✓ done (%.2fs)%s", step, TOTAL_STEPS, name, elapsed, suffix)


# ─── System prompt cho LLM ──────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = """\
Bạn là Producer agent của VNG Insider (TikTok kênh đời sống ở VNG).
Cho 1 đoạn kịch bản voice-over Việt + catalog các clip kho, chọn các clip
visual khớp nội dung kịch bản, sắp theo thứ tự kể chuyện.

Rules:
- Output JSON NGHIÊM NGẶT: {"clips": ["clip_id_1", "clip_id_2", ...]}
- Chọn clip có description khớp ngữ nghĩa với đoạn script đang nói
- Match clip mood với tone script (năng động/yên tĩnh/...)
- TRÁNH clip has_people=true trừ khi script đề cập rõ ràng đến người thật
- Ưu tiên clip resolution dọc (TikTok 9:16)
- Tổng duration clips ≈ voice_duration (chấp nhận ±10s)
- Có thể reuse clip nếu cần, nhưng tránh nếu có thể
- Sắp clip đúng thứ tự kể chuyện theo flow script
- KHÔNG output gì ngoài JSON.
"""


# ─── Models ─────────────────────────────────────────────────────────────────

class ProduceRequest(BaseModel):
    script: str = Field(..., min_length=10, max_length=4000)
    subtitles: bool = True   # burn phụ đề theo giọng đọc vào final
    library: str = Field("vng_insider", min_length=1, max_length=80,
                         description="Library scope — LLM chỉ pick clip trong lib này")


# ─── Helpers ────────────────────────────────────────────────────────────────

def ffprobe_duration(path: Path) -> float:
    duration, _ = ffprobe_metadata(str(path))
    return duration


def _fmt_bytes(n: int) -> str:
    if n < 1024: return f"{n}B"
    if n < 1024 * 1024: return f"{n/1024:.1f}KB"
    return f"{n/(1024*1024):.2f}MB"


def public_url(object_name: str) -> str:
    return f"http://{MINIO_ENDPOINT}/{BUCKET_OUTPUTS}/{object_name}"


# ─── STEP 1: TTS (+ cache + timestamps cho phụ đề) ──────────────────────────

def _ffprobe_duration_bytes(audio_bytes: bytes) -> float:
    """Probe duration của mp3 bytes (pipe stdin, không file tạm)."""
    p = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         "-f", "mp3", "-i", "pipe:0"],
        input=audio_bytes, capture_output=True, timeout=10,
    )
    try:
        return float(p.stdout.decode().strip() or 0.0)
    except ValueError:
        return 0.0


def tts_generate(text: str):
    """
    ElevenLabs TTS với cache → (mp3_bytes, alignment | None, voice_url, cache_hit).

    Check tts_cache trước (key = sha256(voice|model|script)):
      - HIT  → tải mp3 từ MinIO + alignment từ DB, KHÔNG gọi ElevenLabs API
      - MISS → gọi API, lưu mp3 + alignment vào cache, trả URL stable

    Timestamps API ưu tiên; fallback convert thường nếu model không hỗ trợ
    (alignment=None, vẫn cache audio để lần sau khỏi gọi lại).
    """
    if not ELEVENLABS_API_KEY:
        raise HTTPException(500, "ELEVENLABS_API_KEY chưa set trong .env")

    _step(1, "tts", f"start · voice={ELEVENLABS_VOICE_ID} model={ELEVENLABS_MODEL_ID} script_chars={len(text)}")

    # ── Cache lookup ────────────────────────────────────────────────────────
    key = tts_cache.compute_key(text, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID)
    hit = tts_cache.lookup(key)
    if hit:
        _step(1, "tts", f"cache HIT key={key[:12]}... · ElevenLabs API SKIPPED "
                        f"(hit_count={hit['hit_count']})")
        t0 = time.monotonic()
        audio_bytes = tts_cache.download_audio(hit["object_name"])
        alignment = tts_cache.alignment_to_namespace(hit["alignment"])
        n_chars = len(alignment.characters) if alignment else 0
        _step(1, "tts", f"cache fetch: {_fmt_bytes(len(audio_bytes))} mp3 + "
                        f"{n_chars} chars aligned in {time.monotonic()-t0:.2f}s")
        return audio_bytes, alignment, hit["voice_url"], True

    _step(1, "tts", f"cache MISS key={key[:12]}... · calling ElevenLabs API")

    # ── Cache miss → gọi ElevenLabs ────────────────────────────────────────
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    t0 = time.monotonic()
    audio_bytes: Optional[bytes] = None
    alignment = None

    try:
        _step(1, "tts", "sending request (with timestamps)...")
        resp = client.text_to_speech.convert_with_timestamps(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id=ELEVENLABS_MODEL_ID,
            output_format="mp3_44100_128",
        )
        audio_bytes = base64.b64decode(resp.audio_base_64)
        alignment = resp.alignment
        n_chars = len(alignment.characters) if alignment else 0
        _step(1, "tts", f"received {_fmt_bytes(len(audio_bytes))} mp3 + "
                        f"{n_chars} chars aligned in {time.monotonic()-t0:.2f}s")
    except Exception as e:
        log.warning("[1/6] tts · timestamps API failed (%s) — fallback convert "
                    "thường, final sẽ KHÔNG có phụ đề", e)
        t0 = time.monotonic()
        try:
            _step(1, "tts", "sending request (plain convert, no timestamps)...")
            audio_iter = client.text_to_speech.convert(
                text=text,
                voice_id=ELEVENLABS_VOICE_ID,
                model_id=ELEVENLABS_MODEL_ID,
                output_format="mp3_44100_128",
            )
            audio_bytes = b"".join(audio_iter)
            alignment = None
            _step(1, "tts", f"received {_fmt_bytes(len(audio_bytes))} mp3 in "
                            f"{time.monotonic()-t0:.2f}s (no alignment)")
        except Exception as e2:
            log.exception("[1/6] tts FAILED")
            raise HTTPException(502, f"ElevenLabs TTS error: {e2}")

    # ── Save vào cache (idempotent qua ON CONFLICT trong tts_cache.save) ───
    duration_sec = _ffprobe_duration_bytes(audio_bytes)
    object_name, voice_url, _ = tts_cache.save(
        key, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID,
        text, audio_bytes, alignment, duration_sec,
    )
    _step(1, "tts", f"cached → {object_name} · gọi lại cùng script sẽ skip API")
    return audio_bytes, alignment, voice_url, False


# ─── Phụ đề: alignment → PNG overlays ───────────────────────────────────────
# ffmpeg build trên máy KHÔNG có libass/drawtext (thiếu libfreetype) — burn
# phụ đề bằng cách render từng cụm từ thành PNG (Pillow) rồi dùng filter
# `overlay` (luôn có trong core ffmpeg) với enable='between(t,start,end)'.

SUB_MAX_WORDS = 4      # tối đa từ / 1 dòng phụ đề
SUB_MAX_CHARS = 22     # hoặc tối đa ký tự
SUB_BREAK_PUNCT = ".,!?…;:"
SUB_PAD_SEC = 0.15     # giữ chữ thêm 1 nhịp sau khi đọc xong từ cuối
SUB_FONT_SIZE = 64
SUB_STROKE = 4         # viền đen quanh chữ
SUB_MARGIN_BOTTOM = 340  # khoảng cách từ mép dưới khung 1920

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # đậm, đủ dấu Việt
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _find_font(size: int):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    log.warning("subtitle font: không tìm thấy font nào trong candidates — dùng default")
    return ImageFont.load_default()


def _split_chunks(alignment) -> list[tuple[str, float, float]]:
    """Char-level alignment → list (text, start, end) theo cụm 3-4 từ TikTok-style."""
    chars = alignment.characters
    starts = alignment.character_start_times_seconds
    ends = alignment.character_end_times_seconds

    # 1. chars → words với timing
    words: list[tuple[str, float, float]] = []
    cur, cur_start, cur_end = "", None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append((cur, cur_start, cur_end))
                cur, cur_start, cur_end = "", None, None
            continue
        if cur_start is None:
            cur_start = st
        cur += ch
        cur_end = en
    if cur:
        words.append((cur, cur_start, cur_end))

    if not words:
        return []

    # 2. words → chunks (≤4 từ / ≤22 chars, force break tại dấu câu)
    chunks: list[tuple[str, float, float]] = []
    buf: list[tuple[str, float, float]] = []

    def flush():
        if buf:
            text = " ".join(w[0] for w in buf)
            chunks.append((text, buf[0][1], buf[-1][2]))
            buf.clear()

    for w in words:
        buf.append(w)
        text_len = len(" ".join(x[0] for x in buf))
        if (len(buf) >= SUB_MAX_WORDS
                or text_len >= SUB_MAX_CHARS
                or w[0][-1] in SUB_BREAK_PUNCT):
            flush()
    flush()

    # 3. Pad end mỗi chunk nhưng không đè chunk sau
    padded = []
    for i, (text, st, en) in enumerate(chunks):
        end = en + SUB_PAD_SEC
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][1])
        padded.append((text, st, end))
    return padded


def build_subtitle_overlays(alignment, workdir: Path) -> Optional[list[dict]]:
    """
    Render mỗi chunk phụ đề thành PNG trong suốt (chữ trắng đậm viền đen).
    Trả về [{png, start, end}] để mux overlay theo timing, None nếu không có từ.
    """
    from PIL import Image, ImageDraw

    chunks = _split_chunks(alignment)
    if not chunks:
        log.warning("[1/6] tts · alignment có nhưng 0 word — bỏ phụ đề")
        return None

    font = _find_font(SUB_FONT_SIZE)
    overlays = []
    pad = SUB_STROKE + 10

    for i, (text, st, en) in enumerate(chunks):
        # Đo kích thước text (kèm stroke)
        bbox = font.getbbox(text, stroke_width=SUB_STROKE)
        w = bbox[2] - bbox[0] + pad * 2
        h = bbox[3] - bbox[1] + pad * 2

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text(
            (pad - bbox[0], pad - bbox[1]), text,
            font=font,
            fill=(255, 255, 255, 255),          # trắng
            stroke_width=SUB_STROKE,
            stroke_fill=(0, 0, 0, 255),          # viền đen
        )
        png = workdir / f"sub_{i:03d}.png"
        img.save(png)
        overlays.append({"png": png, "start": st, "end": en, "text": text})

    _step(1, "tts", f"subtitles: {len(chunks)} chunks rendered → sub_*.png")
    return overlays


# ─── STEP 2: LLM clip selection ─────────────────────────────────────────────

def list_all_clips_for_llm(library: str) -> list[dict]:
    """Catalog clip cho LLM — chỉ video trong `library`. Bỏ field không cần."""
    with pg() as conn:
        rows = conn.execute("""
            SELECT id, category, clip_tag, description, mood, duration_sec,
                   has_people, resolution, notes
            FROM videos
            WHERE library = %s
            ORDER BY category, id
        """, (library,)).fetchall()
    return [dict(r) for r in rows]


def llm_select_clips(script: str, voice_duration: float,
                     clips: list[dict]) -> list[str]:
    """Gọi VNGCloud AI Platform để chọn clip theo thứ tự."""
    if not AI_PLATFORM_API_KEY:
        raise HTTPException(500, "AI_PLATFORM_API_KEY chưa set trong .env")

    from openai import OpenAI

    _step(2, "llm-pick", f"start · model={AI_PLATFORM_MODEL} url={AI_PLATFORM_BASE_URL}")
    catalog_json = json.dumps(clips, ensure_ascii=False, indent=2)
    user_msg = (
        f"SCRIPT (voice-over Việt):\n{script}\n\n"
        f"VOICE DURATION: {voice_duration:.1f}s\n\n"
        f"AVAILABLE CLIPS (JSON):\n{catalog_json}"
    )
    _step(2, "llm-pick", f"catalog: {len(clips)} clips · prompt {_fmt_bytes(len(user_msg))}")
    _step(2, "llm-pick", "sending request to AI Platform...")

    client = OpenAI(base_url=AI_PLATFORM_BASE_URL, api_key=AI_PLATFORM_API_KEY)
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(
            model=AI_PLATFORM_MODEL,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            # max_tokens cao vì DeepSeek có reasoning mode đốt token trước khi
            # output thật. Để 2000 thường bị cắt ngay khi đang "suy nghĩ".
            max_tokens=8000,
            temperature=1,
            top_p=0.7,
            presence_penalty=0,
        )
    except Exception as e:
        log.exception("[2/6] llm-pick FAILED")
        raise HTTPException(502, f"AI Platform error: {e}")
    elapsed_llm = time.monotonic() - t0

    choice = resp.choices[0]
    message = choice.message
    finish_reason = choice.finish_reason
    raw = (message.content or "").strip()

    usage = resp.usage
    tokens_info = (f"in={usage.prompt_tokens} out={usage.completion_tokens}"
                   if usage else "n/a")
    _step(2, "llm-pick",
          f"response: {elapsed_llm:.2f}s · raw {len(raw)} chars · "
          f"finish={finish_reason} · tokens {tokens_info}")
    log.debug("[2/6] llm-pick · raw[:500]=%s", raw[:500])

    # Fallback 1: DeepSeek thinking-mode đôi khi trả về content rỗng nhưng
    # đặt JSON trong reasoning_content (hoặc nó suy nghĩ ra JSON rồi không emit).
    if not raw:
        reasoning = getattr(message, "reasoning_content", None) or ""
        if reasoning:
            _step(2, "llm-pick",
                  f"content empty but reasoning_content={len(reasoning)} chars — using reasoning")
            log.debug("[2/6] llm-pick · reasoning[:500]=%s", reasoning[:500])
            raw = reasoning.strip()
        else:
            # Thật sự không có gì để parse
            hint = ""
            if finish_reason == "length":
                hint = " (finish_reason=length → max_tokens không đủ, model bị cắt khi đang reasoning)"
            elif finish_reason == "content_filter":
                hint = " (content_filter đã chặn)"
            log.error("[2/6] llm-pick · BOTH content and reasoning_content empty%s", hint)
            raise HTTPException(
                502,
                f"LLM trả về rỗng (finish_reason={finish_reason}, tokens {tokens_info}).{hint}"
            )

    # Fallback 2: nếu finish_reason=length → JSON có thể bị cụt
    if finish_reason == "length":
        log.warning("[2/6] llm-pick · finish_reason=length — JSON có thể không complete, sẽ thử parse")

    # DeepSeek wrap JSON trong ```json ... ``` → strip
    if raw.startswith("```"):
        _step(2, "llm-pick", "stripping markdown code fence")
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()

    # Fallback 3: nếu reasoning_content có nhiều text non-JSON, tìm JSON object
    # trong đó bằng cách bắt {...} đầu tiên
    if not raw.lstrip().startswith("{"):
        import re
        m = re.search(r"\{[^{}]*\"clips\"[^{}]*\[[^\]]*\][^{}]*\}", raw, re.DOTALL)
        if m:
            _step(2, "llm-pick", "extracted JSON object from surrounding text")
            raw = m.group(0)

    try:
        data = json.loads(raw)
        selected = data.get("clips") or []
    except json.JSONDecodeError as e:
        log.error("[2/6] llm-pick · output not JSON: %s", raw[:300])
        raise HTTPException(502, f"LLM returned non-JSON: {e}")

    _step(2, "llm-pick", f"parsed JSON · {len(selected)} clip_ids in response")

    # Validate clip_id tồn tại
    valid_ids = {c["id"] for c in clips}
    filtered = [c for c in selected if c in valid_ids]
    dropped = [c for c in selected if c not in valid_ids]
    if dropped:
        log.warning("[2/6] llm-pick · DROPPED %d invalid ids: %s", len(dropped), dropped)

    if len(filtered) < 2:
        raise HTTPException(
            422,
            f"LLM chỉ chọn được {len(filtered)} clip valid (cần ≥2). Selected: {selected}"
        )

    _step(2, "llm-pick", f"validated · {len(filtered)} clips chosen: {filtered}")
    return filtered


# ─── STEP 4: Align ──────────────────────────────────────────────────────────

def align_to_voice(
    video_path: Path,
    video_duration: float,
    voice_duration: float,
    workdir: Path,
) -> tuple[Path, dict]:
    """
    Cân duration video với voice:
      - |delta| < 0.5s → keep as-is (mux thẳng)
      - delta > 0 (video dài hơn voice) → cắt đuôi
      - delta < 0 (voice dài hơn video) → setpts slowdown
    """
    delta = video_duration - voice_duration
    _step(4, "align", f"start · video={video_duration:.2f}s voice={voice_duration:.2f}s delta={delta:+.2f}s")

    if abs(delta) < 0.5:
        _step(4, "align", "decision: NONE (|delta| < 0.5s threshold) → mux thẳng")
        return video_path, {"action": "none", "delta_sec": round(delta, 3)}

    if delta > 0:
        _step(4, "align", f"decision: TRIM (video dài hơn voice {delta:.2f}s) → cắt cuối tới {voice_duration:.3f}s")
        out = workdir / "aligned_trim.mp4"
        cmd_copy = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-t", f"{voice_duration:.3f}",
            "-c", "copy", "-an",
            str(out),
        ]
        log.debug("[4/6] align · cmd: %s", " ".join(cmd_copy))
        result = subprocess.run(cmd_copy, capture_output=True, text=True)
        if result.returncode != 0:
            _step(4, "align", "trim copy failed (keyframe issue) — fallback re-encode libx264")
            cmd_reenc = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-t", f"{voice_duration:.3f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-an",
                str(out),
            ]
            log.debug("[4/6] align · cmd: %s", " ".join(cmd_reenc))
            result = subprocess.run(cmd_reenc, capture_output=True, text=True)
            if result.returncode != 0:
                log.error("[4/6] align · trim re-encode FAILED: %s", result.stderr[-300:])
                raise HTTPException(500, f"Align trim failed: {result.stderr[-300:]}")
        return out, {
            "action": "trim",
            "trimmed_sec": round(delta, 3),
            "target_sec": round(voice_duration, 3),
        }

    # delta < 0: voice dài hơn video → slowdown video (PTS multiplier > 1)
    factor = video_duration / voice_duration  # < 1
    _step(4, "align",
          f"decision: SLOWDOWN (voice dài hơn video {-delta:.2f}s) · "
          f"setpts factor={factor:.4f} (video {video_duration:.2f}s → {voice_duration:.2f}s)")
    out = workdir / "aligned_speed.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-filter:v", f"setpts=PTS/{factor:.6f}",
        "-an",
        str(out),
    ]
    log.debug("[4/6] align · cmd: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("[4/6] align · slowdown FAILED: %s", result.stderr[-300:])
        raise HTTPException(500, f"Align slowdown failed: {result.stderr[-300:]}")

    return out, {
        "action": "speedup",   # giữ tên cũ cho FE backward-compat
        "factor": round(factor, 4),
        "stretched_sec": round(-delta, 3),
        "target_sec": round(voice_duration, 3),
    }


# ─── STEP 5: Mux ────────────────────────────────────────────────────────────

def mux_voice(video_path: Path, voice_path: Path, workdir: Path,
              overlays: Optional[list[dict]] = None) -> Path:
    """
    Dán voice mp3 lên silent video → final mp4.

    overlays=None → video copy stream (nhanh, không re-encode).
    overlays có   → chèn từng PNG phụ đề bằng filter `overlay` với
                    enable='between(t,start,end)' (re-encode libx264).
    """
    out = workdir / "final.mp4"
    _step(5, "mux", f"start · video={video_path.name} ({_fmt_bytes(video_path.stat().st_size)}) + "
                    f"voice={voice_path.name} ({_fmt_bytes(voice_path.stat().st_size)})"
                    + (f" + {len(overlays)} subtitle overlays" if overlays else ""))

    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(voice_path)]

    if overlays:
        _step(5, "mux", f"burning {len(overlays)} subtitle PNGs (overlay chain, re-encode libx264)")
        # Input 0 = video, 1 = voice, 2.. = PNG từng chunk
        for ov in overlays:
            cmd += ["-i", str(ov["png"])]

        # Chain: [0:v][2:v]overlay[v1]; [v1][3:v]overlay[v2]; ...
        # Vị trí: giữa ngang, cách mép dưới SUB_MARGIN_BOTTOM px.
        parts = []
        prev = "0:v"
        for i, ov in enumerate(overlays):
            label = f"v{i+1}"
            parts.append(
                f"[{prev}][{i+2}:v]overlay=(W-w)/2:H-h-{SUB_MARGIN_BOTTOM}"
                f":enable='between(t,{ov['start']:.3f},{ov['end']:.3f})'[{label}]"
            )
            prev = label
        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", f"[{prev}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        ]
    else:
        _step(5, "mux", "no subs → video copy stream")
        cmd += ["-map", "0:v:0", "-c:v", "copy"]

    cmd += [
        "-map", "1:a:0",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(out),
    ]
    log.debug("[5/6] mux · cmd: %s", " ".join(cmd))
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(workdir))
    if result.returncode != 0:
        log.error("[5/6] mux · FAILED: %s", result.stderr[-300:])
        raise HTTPException(500, f"Mux failed: {result.stderr[-300:]}")
    _step(5, "mux", f"output {out.name} ({_fmt_bytes(out.stat().st_size)}) in {time.monotonic()-t0:.2f}s")
    return out


# ─── STEP 6: Upload ─────────────────────────────────────────────────────────

def upload_to_outputs(path: Path, object_name: str, content_type: str) -> str:
    """Upload 1 file lên MinIO outputs bucket + log."""
    size = path.stat().st_size
    minio_client.fput_object(
        BUCKET_OUTPUTS, object_name, str(path),
        content_type=content_type,
    )
    url = public_url(object_name)
    _step(6, "upload", f"{object_name} ({_fmt_bytes(size)}) → {url}")
    return url


# ─── Orchestrator ───────────────────────────────────────────────────────────

def produce_from_script(
    script: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    subtitles: bool = True,
) -> dict:
    """
    Pipeline full 6 bước với log step-by-step + summary timing cuối.

    progress_cb(percent, message) — gọi tại mỗi mốc để UI vẽ progress bar.
    subtitles — burn phụ đề theo giọng đọc vào final (cần timestamps từ TTS).
    """
    run_id = uuid.uuid4().hex[:12]
    workdir = Path(tempfile.mkdtemp(prefix=f"produce_{run_id}_"))

    def _p(percent: int, message: str) -> None:
        if progress_cb:
            progress_cb(percent, message)

    log.info("")
    log.info("═════════ PRODUCE run_id=%s BEGIN ═════════", run_id)
    log.info("script preview: %s",
             script[:140].replace("\n", " ") + ("..." if len(script) > 140 else ""))
    log.info("workdir: %s", workdir)

    timings: dict[str, float] = {}
    summaries: dict[str, str] = {}
    t_total = time.monotonic()

    try:
        # ── STEP 1: TTS (+ timestamps → phụ đề) ─────────────────────────────
        _p(2, "[1/6] Đang sinh giọng đọc (ElevenLabs TTS)...")
        t = time.monotonic()
        voice_bytes, alignment, voice_url_cached, cache_hit = tts_generate(script)
        voice_path = workdir / "voice.mp3"
        voice_path.write_bytes(voice_bytes)
        _step(1, "tts", f"wrote {voice_path.name} ({_fmt_bytes(len(voice_bytes))})")
        voice_duration = ffprobe_duration(voice_path)
        _step(1, "tts", f"ffprobe → voice_duration={voice_duration:.2f}s")

        overlays: Optional[list[dict]] = None
        if subtitles and alignment is not None:
            overlays = build_subtitle_overlays(alignment, workdir)
        elif subtitles:
            log.warning("[1/6] tts · phụ đề được yêu cầu nhưng không có alignment — bỏ qua")

        timings["1 tts"] = time.monotonic() - t
        summaries["1 tts"] = f"voice {voice_duration:.2f}s" + (" + subs" if overlays else "")
        _step_done(1, "tts", timings["1 tts"], summaries["1 tts"])
        _p(20, f"[1/6] Giọng đọc xong ({voice_duration:.1f}s)")

        # ── STEP 2: LLM clip pick (scope theo library) ──────────────────────
        _p(22, f"[2/6] LLM đang chọn clip phù hợp kịch bản (library={library})...")
        t = time.monotonic()
        clips_catalog = list_all_clips_for_llm(library)
        if not clips_catalog:
            raise HTTPException(400,
                f"Library '{library}' không có video nào — upload trước hoặc đổi library.")
        _step(2, "llm-pick", f"library={library} · catalog={len(clips_catalog)} clip")
        selected_ids = llm_select_clips(script, voice_duration, clips_catalog)
        timings["2 llm-pick"] = time.monotonic() - t
        summaries["2 llm-pick"] = f"{len(selected_ids)} clips picked"
        _step_done(2, "llm-pick", timings["2 llm-pick"], summaries["2 llm-pick"])
        _p(45, f"[2/6] LLM chọn xong {len(selected_ids)} clip")

        # ── STEP 3: Concat ──────────────────────────────────────────────────
        _p(47, f"[3/6] Đang ghép {len(selected_ids)} clip (ffmpeg)...")
        t = time.monotonic()
        _step(3, "concat", f"start · {len(selected_ids)} clips (mute_source=True)")
        raw_path, video_duration = concat_to_local(
            selected_ids, workdir=workdir, mute_source=True,
        )
        timings["3 concat"] = time.monotonic() - t
        summaries["3 concat"] = f"raw video {video_duration:.2f}s"
        _step_done(3, "concat", timings["3 concat"], summaries["3 concat"])
        _p(72, f"[3/6] Ghép xong ({video_duration:.1f}s)")

        # ── STEP 4: Align ───────────────────────────────────────────────────
        _p(75, "[4/6] Đang cân thời lượng video ↔ voice...")
        t = time.monotonic()
        silent_path, align_meta = align_to_voice(
            raw_path, video_duration, voice_duration, workdir=workdir,
        )
        silent_duration = ffprobe_duration(silent_path)
        timings["4 align"] = time.monotonic() - t
        summaries["4 align"] = f"{align_meta['action']} → {silent_duration:.2f}s"
        _step_done(4, "align", timings["4 align"], summaries["4 align"])
        _p(85, f"[4/6] Align xong ({align_meta['action']})")

        # ── STEP 5: Mux (+ burn phụ đề nếu có) ──────────────────────────────
        _p(87, "[5/6] Đang lồng tiếng + phụ đề..." if overlays
               else "[5/6] Đang lồng tiếng vào video...")
        t = time.monotonic()
        final_path = mux_voice(silent_path, voice_path, workdir=workdir,
                               overlays=overlays)
        final_duration = ffprobe_duration(final_path)
        timings["5 mux"] = time.monotonic() - t
        summaries["5 mux"] = f"final {final_duration:.2f}s" + (" + subs" if overlays else "")
        _step_done(5, "mux", timings["5 mux"], summaries["5 mux"])
        _p(92, "[5/6] Lồng tiếng xong")

        # ── STEP 6: Upload (voice đã có URL từ cache, chỉ upload silent + final) ─
        _p(94, "[6/6] Đang upload silent + final lên MinIO...")
        t = time.monotonic()
        _step(6, "upload",
              f"start · voice từ cache ({'HIT' if cache_hit else 'just saved'}: "
              f"{voice_url_cached.split('/')[-1]}); upload silent + final")
        silent_name = f"silent_{run_id}.mp4"
        final_name  = f"produced_{run_id}.mp4"
        voice_url  = voice_url_cached
        silent_url = upload_to_outputs(silent_path, silent_name, "video/mp4")
        final_url  = upload_to_outputs(final_path,  final_name,  "video/mp4")
        timings["6 upload"] = time.monotonic() - t
        summaries["6 upload"] = "3 URLs ready (voice cached)"
        _step_done(6, "upload", timings["6 upload"], summaries["6 upload"])
        _p(100, "Hoàn tất ✓")

        # ── Summary ─────────────────────────────────────────────────────────
        total = time.monotonic() - t_total
        log.info("")
        log.info("┌─────────── SUMMARY run_id=%s ───────────", run_id)
        log.info("│ %-12s  %8s   %s", "step", "elapsed", "output")
        log.info("│ %s", "─" * 56)
        for k in sorted(timings.keys()):
            log.info("│ %-12s  %7.2fs   %s", k, timings[k], summaries.get(k, ""))
        log.info("│ %s", "─" * 56)
        log.info("│ %-12s  %7.2fs", "TOTAL", total)
        log.info("└──────────────────────────────────────────────")
        log.info("voice : %s", voice_url)
        log.info("silent: %s", silent_url)
        log.info("final : %s", final_url)
        log.info("═════════ PRODUCE run_id=%s DONE ═════════", run_id)
        log.info("")

        return {
            "run_id": run_id,
            "voice_url":        voice_url,
            "silent_video_url": silent_url,
            "output_url":       final_url,
            "voice_duration_sec":        round(voice_duration, 2),
            "silent_video_duration_sec": round(silent_duration, 2),
            "final_duration_sec":        round(final_duration, 2),
            "selected_clips":            selected_ids,
            "alignment":                 align_meta,
            "subtitles":         overlays is not None,
            "subtitle_chunks":   len(overlays) if overlays else 0,
            "tts_cache_hit":     cache_hit,
            "stage_timings_sec": {k: round(v, 2) for k, v in timings.items()},
            "total_elapsed_sec": round(total, 2),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ─── Endpoints (job + polling cho progress bar) ─────────────────────────────

def _run_job(job_id: str, script: str, subtitles: bool = True,
             library: str = "vng_insider") -> None:
    """Chạy pipeline trong thread nền, cập nhật JOBS[job_id] theo tiến độ."""
    def cb(percent: int, message: str) -> None:
        job = JOBS.get(job_id)
        if job is not None:
            job["percent"] = percent
            job["message"] = message

    JOBS[job_id]["status"] = "running"
    try:
        result = produce_from_script(script, progress_cb=cb, subtitles=subtitles)
        JOBS[job_id].update(status="done", percent=100,
                            message="Hoàn tất ✓", result=result)
    except HTTPException as e:
        log.error("produce job %s failed: %s", job_id, e.detail)
        JOBS[job_id].update(status="error", error=str(e.detail))
    except Exception as e:
        log.exception("produce job %s crashed", job_id)
        JOBS[job_id].update(status="error", error=str(e))


@router.post("/api/produce")
def produce_endpoint(body: ProduceRequest):
    """Start job nền, trả job_id ngay. FE poll /api/produce/status/{job_id}."""
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "status": "queued",
        "percent": 0,
        "message": "Đang xếp hàng...",
        "result": None,
        "error": None,
    }
    _jobs_evict()
    threading.Thread(
        target=_run_job,
        args=(job_id, body.script, body.subtitles, body.library),
        daemon=True, name=f"produce-{job_id}",
    ).start()
    log.info("produce job %s queued (script %d chars, subtitles=%s, library=%s)",
             job_id, len(body.script), body.subtitles, body.library)
    return {"job_id": job_id}


@router.get("/api/produce/status/{job_id}")
def produce_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job không tồn tại (server restart?)")
    return job
