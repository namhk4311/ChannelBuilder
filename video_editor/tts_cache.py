"""
TTS cache — tránh gọi ElevenLabs lặp cho cùng (script, voice, model).

Key:  sha256("voice_id|model_id|stripped_script")
Path: bucket `outputs/tts_{hash[:16]}.mp3`  (public-read sẵn)
Meta: bảng tts_cache (hash PK + alignment JSONB + voice_url + duration + ...)

Public API:
  compute_key(text, voice_id, model_id) -> str
  lookup(key) -> Optional[dict]      # bumps hit_count + last_used_at nếu hit
  save(key, voice_id, model_id, text, audio_bytes, alignment_obj, duration)
      → (object_name, voice_url, alignment_dict)
  download_audio(object_name) -> bytes
  alignment_to_namespace(d) -> SimpleNamespace   # khôi phục attr access từ JSON
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from types import SimpleNamespace
from typing import Optional

from psycopg.types.json import Jsonb

from config import BUCKET_OUTPUTS, MINIO_ENDPOINT

from .db import pg
from .storage import minio_client

log = logging.getLogger(__name__)


def compute_key(text: str, voice_id: str, model_id: str) -> str:
    """sha256 hex của tuple (voice_id, model_id, stripped script)."""
    payload = f"{voice_id}|{model_id}|{text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public_url(object_name: str) -> str:
    return f"http://{MINIO_ENDPOINT}/{BUCKET_OUTPUTS}/{object_name}"


def lookup(key: str) -> Optional[dict]:
    """
    Trả về dict {object_name, voice_url, alignment, duration_sec, size_bytes}
    nếu cache hit, None nếu miss. Bump last_used_at + hit_count khi hit.
    """
    with pg() as conn:
        row = conn.execute("""
            UPDATE tts_cache
            SET hit_count = hit_count + 1, last_used_at = NOW()
            WHERE hash = %s
            RETURNING object_name, voice_url, alignment, duration_sec,
                      size_bytes, hit_count
        """, (key,)).fetchone()
    return dict(row) if row else None


def save(
    key: str,
    voice_id: str,
    model_id: str,
    text: str,
    audio_bytes: bytes,
    alignment_obj,
    duration_sec: float,
) -> tuple[str, str, Optional[dict]]:
    """
    Upload mp3 lên MinIO + ghi metadata vào tts_cache.

    alignment_obj: ElevenLabs response object có 3 attr characters /
    character_start_times_seconds / character_end_times_seconds, hoặc None
    (model không hỗ trợ timestamps).

    Trả về (object_name, voice_url, alignment_dict).
    """
    object_name = f"tts_{key[:16]}.mp3"
    voice_url = _public_url(object_name)

    # 1. Upload bytes lên MinIO (stable name → idempotent ghi đè OK)
    minio_client.put_object(
        BUCKET_OUTPUTS,
        object_name,
        io.BytesIO(audio_bytes),
        length=len(audio_bytes),
        content_type="audio/mpeg",
    )

    # 2. Chuyển alignment → dict serializable
    alignment_dict: Optional[dict] = None
    if alignment_obj is not None:
        alignment_dict = {
            "characters": list(alignment_obj.characters),
            "character_start_times_seconds": list(alignment_obj.character_start_times_seconds),
            "character_end_times_seconds":   list(alignment_obj.character_end_times_seconds),
        }

    # 3. Upsert row (race condition safe nếu 2 job song song cùng key)
    with pg() as conn:
        conn.execute("""
            INSERT INTO tts_cache
              (hash, voice_id, model_id, script, object_name, voice_url,
               alignment, duration_sec, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO UPDATE SET
              last_used_at = NOW()
        """, (key, voice_id, model_id, text.strip(), object_name, voice_url,
              Jsonb(alignment_dict) if alignment_dict is not None else None,
              duration_sec, len(audio_bytes)))

    log.info("tts_cache · saved key=%s... object=%s (%d bytes, %.2fs)",
             key[:12], object_name, len(audio_bytes), duration_sec)
    return object_name, voice_url, alignment_dict


def download_audio(object_name: str) -> bytes:
    """Đọc mp3 từ MinIO outputs bucket → bytes."""
    resp = minio_client.get_object(BUCKET_OUTPUTS, object_name)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def alignment_to_namespace(d: Optional[dict]):
    """JSONB dict → SimpleNamespace để downstream truy cập kiểu .characters."""
    if not d:
        return None
    return SimpleNamespace(
        characters=d["characters"],
        character_start_times_seconds=d["character_start_times_seconds"],
        character_end_times_seconds=d["character_end_times_seconds"],
    )
