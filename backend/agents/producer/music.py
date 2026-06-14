"""Music library + beat detection + cut snapping helpers.

User upload mp3 → librosa detect (BPM + beat_times) → cache JSONB →
Producer pipeline dùng để snap cut transitions theo beat.
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import librosa
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from psycopg.types.json import Jsonb

from config import BUCKET_MUSIC, MINIO_ENDPOINT

from .db import pg
from .storage import minio_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["music"])


# ─── Beat detection ─────────────────────────────────────────────────────────

def detect_beats(path: str) -> tuple[float, list[float], float]:
    """Trả (bpm, beat_times_sec, duration_sec).

    Dùng librosa.beat.beat_track — onset detection + dynamic programming.
    Accuracy ~85-90% trên pop/EDM 4/4. Chạy ~1-2s/track 3 phút trên CPU.
    """
    y, sr = librosa.load(path, sr=None, mono=True)
    duration = float(len(y) / sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    log.info("beats · bpm=%.1f n=%d duration=%.2fs",
             float(tempo), len(beat_times), duration)
    return float(tempo), beat_times, duration


def beats_in_window(beat_times: list[float], end: float,
                    start: float = 0.0) -> list[float]:
    """Lọc beat trong [start, end] — dùng để align theo voice_duration."""
    return [b for b in beat_times if start <= b <= end]


def extend_beats_for_loop(beat_times: list[float], music_duration: float,
                          target_duration: float) -> list[float]:
    """Nếu music ngắn hơn target, lặp beat_times để phủ đủ target_duration.

    Beat lần loop k được offset = k * music_duration (giả định seamless loop).
    Khi music dài ≥ target, return nguyên bản (không động).

    Vd music 20s với 40 beats, target 35s:
      original:  [0.5, 1.0, ..., 20.0]                       (40 beats trong 0-20)
      extended:  [0.5, 1.0, ..., 20.0,
                  20.5, 21.0, ..., 35.0]                     (70 beats trong 0-35)
    """
    if music_duration <= 0 or not beat_times:
        return beat_times
    if music_duration >= target_duration:
        return beat_times
    extended = list(beat_times)
    n_loops = int(target_duration / music_duration) + 1
    for k in range(1, n_loops):
        offset = k * music_duration
        extended.extend(b + offset for b in beat_times)
    return [b for b in extended if b <= target_duration]


def snap_cuts_to_beats(n_clips: int, target_duration: float,
                       beat_times: list[float]) -> list[float]:
    """Sinh N+1 cut timestamps: [0.0, cut_1, ..., cut_n-1, target_duration].

    Chia đều target_duration thành N segment "lý tưởng", rồi snap mỗi
    internal cut tới beat gần nhất. Đảm bảo monotonic + last = target.

    Edge case: beat_times rỗng hoặc n_clips=0 → fallback chia đều.
    """
    if n_clips <= 0:
        return [0.0, round(target_duration, 3)]
    if n_clips == 1 or not beat_times:
        step = target_duration / n_clips
        return [round(step * i, 3) for i in range(n_clips + 1)]

    ideals = [target_duration * i / n_clips for i in range(n_clips + 1)]
    snapped: list[float] = [0.0]
    for i in range(1, n_clips):
        target = ideals[i]
        # Chỉ chọn beat > snapped[-1] + 0.3s để mỗi segment ≥ 0.3s, đảm bảo monotonic
        valid = [b for b in beat_times
                 if b > snapped[-1] + 0.3 and b < target_duration - 0.3]
        if not valid:
            snapped.append(round(target, 3))
            continue
        nearest = min(valid, key=lambda b: abs(b - target))
        snapped.append(round(nearest, 3))
    snapped.append(round(target_duration, 3))
    return snapped


# ─── CRUD endpoints ─────────────────────────────────────────────────────────

@router.get("/api/music")
def list_music():
    with pg() as conn:
        rows = conn.execute("""
            SELECT id, label, file, object_name, duration_sec, bpm, mood,
                   size_bytes, uploaded_at
            FROM music_tracks
            ORDER BY uploaded_at DESC
        """).fetchall()
    for r in rows:
        if r.get("uploaded_at"):
            r["uploaded_at"] = r["uploaded_at"].isoformat()
        r["preview_url"] = f"http://{MINIO_ENDPOINT}/{BUCKET_MUSIC}/{r['object_name']}"
    return rows


@router.post("/api/music")
async def upload_music(
    file: UploadFile = File(...),
    label: str = Form(""),
    mood: str = Form(""),
):
    """Upload mp3 → MinIO music bucket → detect beats → cache vào DB."""
    track_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename or "").suffix or ".mp3"
    object_name = f"{track_id}{ext}"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        log.info("music · upload start: file=%s size=%.1fKB",
                 file.filename, len(content) / 1024)
        bpm, beats, duration = detect_beats(tmp_path)
        minio_client.fput_object(
            BUCKET_MUSIC, object_name, tmp_path,
            content_type=file.content_type or "audio/mpeg",
        )
        log.info("music · uploaded to MinIO: object=%s", object_name)
    finally:
        os.unlink(tmp_path)

    with pg() as conn:
        conn.execute("""
            INSERT INTO music_tracks
              (id, label, file, object_name, duration_sec, bpm, beat_times,
               mood, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (track_id, label or (file.filename or track_id), file.filename or "",
              object_name, duration, bpm, Jsonb(beats), mood, len(content)))

    log.info("music · ready: id=%s bpm=%.1f beats=%d dur=%.1fs",
             track_id, bpm, len(beats), duration)
    return {
        "id": track_id,
        "bpm": round(bpm, 1),
        "duration_sec": round(duration, 2),
        "n_beats": len(beats),
    }


@router.delete("/api/music/{track_id}")
def delete_music(track_id: str):
    with pg() as conn:
        row = conn.execute(
            "SELECT object_name FROM music_tracks WHERE id = %s", (track_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Track không tồn tại")
        try:
            minio_client.remove_object(BUCKET_MUSIC, row["object_name"])
        except Exception as e:  # noqa: BLE001
            log.warning("delete music %s: MinIO remove failed (ignored): %s",
                        track_id, e)
        conn.execute("DELETE FROM music_tracks WHERE id = %s", (track_id,))
    log.info("music · deleted id=%s", track_id)
    return {"ok": True}


def fetch_music_for_pipeline(track_id: str, dest: Path) -> Optional[dict]:
    """Pull music mp3 từ MinIO về local + trả {beat_times, bpm, duration_sec}.

    Trả None nếu track không tồn tại. Caller phải tự handle.
    """
    with pg() as conn:
        row = conn.execute("""
            SELECT object_name, beat_times, bpm, duration_sec, label
            FROM music_tracks WHERE id = %s
        """, (track_id,)).fetchone()
    if not row:
        return None
    minio_client.fget_object(BUCKET_MUSIC, row["object_name"], str(dest))
    return {
        "beat_times": row["beat_times"],
        "bpm": row["bpm"],
        "duration_sec": row["duration_sec"],
        "label": row["label"],
    }
