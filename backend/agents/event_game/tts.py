# -*- coding: utf-8 -*-
"""TTS: voiceover text → voice.mp3 (ElevenLabs trực tiếp, KHÔNG cache/DB).

Prototype dùng convert() thường (không cần timestamps vì chữ nằm trên banner,
không phải phụ đề). ffprobe đo duration để render banner đúng độ dài voice.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL_ID, ELEVENLABS_VOICE_ID

log = logging.getLogger("banner_proto.tts")

# voice_settings cho giọng "hùng hổ": stability THẤP = cảm xúc/biến hoá mạnh,
# style CAO = phóng đại ngữ điệu, speaker_boost = rõ & dày hơn. Chỉnh tự do.
VOICE_STABILITY = 0.30
VOICE_STYLE = 0.70
VOICE_SIMILARITY = 0.75


def synthesize(text: str, out_path: Path, speed: float = 1.0,
               stability: float = None, style: float = None, similarity: float = None) -> Path:
    """Voiceover text → mp3 file tại out_path.

    speed > 1.0 → tăng tốc voice (giữ cao độ) bằng ffmpeg atempo. VD speed=1.3 = nhanh 30%
    → voice ngắn lại ~23% → cảnh ngắn + nhịp nhanh hơn.

    stability/style/similarity: voice_settings theo preset (None → giá trị mặc định "hùng hổ"
    của game_event). stability THẤP = cảm xúc mạnh; style CAO = phóng đại ngữ điệu.
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("Thiếu ELEVENLABS_API_KEY trong .env")

    stab = VOICE_STABILITY if stability is None else float(stability)
    sty = VOICE_STYLE if style is None else float(style)
    sim = VOICE_SIMILARITY if similarity is None else float(similarity)

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    log.info("tts · voice=%s model=%s chars=%d speed=%.2f stab=%.2f style=%.2f",
             ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID, len(text), speed, stab, sty)

    kwargs = dict(text=text, voice_id=ELEVENLABS_VOICE_ID,
                  model_id=ELEVENLABS_MODEL_ID, output_format="mp3_44100_128")
    try:  # voice_settings — bọc try vì tuỳ version SDK
        from elevenlabs import VoiceSettings
        kwargs["voice_settings"] = VoiceSettings(
            stability=stab, similarity_boost=sim, style=sty, use_speaker_boost=True,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("tts · không set được voice_settings (%s) — dùng mặc định", e)

    audio_bytes = b"".join(client.text_to_speech.convert(**kwargs))

    speed = max(0.5, min(float(speed), 2.0))  # atempo hợp lệ 0.5–2.0
    if abs(speed - 1.0) < 1e-3:
        out_path.write_bytes(audio_bytes)
        log.info("tts · wrote %s (%d bytes)", out_path.name, len(audio_bytes))
        return out_path

    # tăng tốc qua ffmpeg atempo (giữ cao độ)
    raw = out_path.with_name(out_path.stem + "_raw.mp3")
    raw.write_bytes(audio_bytes)
    cmd = ["ffmpeg", "-y", "-i", str(raw), "-filter:a", f"atempo={speed:.3f}",
           "-c:a", "libmp3lame", str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw.unlink(missing_ok=True)
    if result.returncode != 0:
        log.warning("tts · atempo failed, dùng voice gốc: %s", result.stderr[-200:])
        out_path.write_bytes(audio_bytes)
    else:
        log.info("tts · wrote %s (speed=%.2f)", out_path.name, speed)
    return out_path


def probe_duration(media_path: Path) -> float:
    """Đọc duration (giây) của file audio/video bằng ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(media_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[-200:]}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe duration không parse được: {result.stdout!r}")
