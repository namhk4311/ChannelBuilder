"""Clip CRUD — feature upload / list / patch / delete video."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from minio.error import S3Error
from pydantic import BaseModel

from config import BUCKET_SOURCES

from .db import pg
from .ffprobe import ffprobe_metadata
from .storage import minio_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["clips"])


# ─── Upload ──────────────────────────────────────────────────────────────────

@router.post("/api/videos")
async def upload_video(
    file: UploadFile = File(...),
    category: str = Form(...),
    description: str = Form(""),
    mood: str = Form(""),
    has_people: str = Form("false"),
    notes: str = Form(""),
    clip_tag: Optional[str] = Form(None),   # nội bộ, auto-derive nếu không truyền
    people_note_raw: str = Form(""),         # legacy import field, không expose UI
):
    # Validate FK + lấy default_tag của category nếu user không cung cấp clip_tag
    with pg() as conn:
        cat = conn.execute(
            "SELECT default_tag FROM categories WHERE name = %s", (category,)
        ).fetchone()
        if not cat:
            log.warning("upload rejected: category '%s' not found", category)
            raise HTTPException(
                400,
                f"Category '{category}' chưa tồn tại. Tạo trước qua POST /api/categories.",
            )
        if not clip_tag:
            clip_tag = cat["default_tag"] or category   # fallback tuyệt đối

    log.info("upload start: file=%s size_hint=%s category=%s tag=%s (auto=%s)",
             file.filename, file.size, category, clip_tag, "yes" if not clip_tag else "no")

    video_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename or "").suffix or ".mp4"
    object_name = f"{video_id}{ext}"

    # Lưu temp trước để ffprobe được
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    duration, resolution = ffprobe_metadata(tmp_path)
    has_people_bool = has_people.lower() in ("true", "1", "yes", "on")

    try:
        minio_client.fput_object(
            BUCKET_SOURCES, object_name, tmp_path,
            content_type=file.content_type or "video/mp4",
        )
        log.info("upload minio ok: object=%s size=%.1fKB", object_name, len(content)/1024)
    finally:
        os.unlink(tmp_path)

    with pg() as conn:
        conn.execute("""
            INSERT INTO videos
              (id, file, category, clip_tag, description, mood, duration_sec,
               has_people, people_note_raw, resolution, notes, object_name, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (video_id, f"upload/{file.filename}", category, clip_tag,
              description, mood, duration, has_people_bool, people_note_raw,
              resolution, notes, object_name, len(content)))

    log.info("upload done: id=%s duration=%.2fs resolution=%s",
             video_id, duration, resolution)
    return {
        "id": video_id,
        "filename": file.filename,
        "duration_sec": duration,
        "resolution": resolution,
    }


# ─── List ────────────────────────────────────────────────────────────────────

@router.get("/api/videos")
def list_videos(category: Optional[str] = None):
    with pg() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM videos WHERE category = %s ORDER BY uploaded_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM videos ORDER BY uploaded_at DESC"
            ).fetchall()
    for r in rows:
        if r.get("uploaded_at"):
            r["uploaded_at"] = r["uploaded_at"].isoformat()
    return rows


MOODS = [
    "yên tĩnh",
    "năng động",
    "thư giãn",
    "vui tươi",
    "chuyên nghiệp",
    "ấm cúng",
    "sang trọng",
    "hài hước",
    "trang trọng",
    "trẻ trung",
]


@router.get("/api/moods")
def list_moods():
    """Hardcoded list mood cho dropdown UI — không query DB."""
    return {"moods": MOODS}


# ─── Patch ───────────────────────────────────────────────────────────────────

class VideoUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    mood: Optional[str] = None
    has_people: Optional[bool] = None
    notes: Optional[str] = None
    # clip_tag không expose qua PATCH — auto theo category
    # people_note_raw bỏ khỏi UI — redundant với has_people boolean
    #   (cột DB giữ để compat với data import từ INDEX.json)


@router.patch("/api/videos/{video_id}")
def update_video(video_id: str, body: VideoUpdate):
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "Không có field nào để cập nhật")
    log.info("patch video %s: fields=%s", video_id, list(payload.keys()))

    if "category" in payload:
        with pg() as conn:
            row = conn.execute(
                "SELECT default_tag FROM categories WHERE name = %s",
                (payload["category"],),
            ).fetchone()
            if not row:
                raise HTTPException(400, f"Category '{payload['category']}' chưa tồn tại")
            # Đổi category → đồng bộ clip_tag theo default_tag mới (auto nội bộ)
            payload["clip_tag"] = row["default_tag"] or payload["category"]

    set_clause = ", ".join(f"{k} = %s" for k in payload.keys())
    values = list(payload.values()) + [video_id]

    with pg() as conn:
        cur = conn.execute(
            f"UPDATE videos SET {set_clause} WHERE id = %s",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Video không tồn tại")
    return {"ok": True, "updated": list(payload.keys())}


# ─── Delete ──────────────────────────────────────────────────────────────────

@router.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    with pg() as conn:
        row = conn.execute(
            "SELECT object_name FROM videos WHERE id = %s", (video_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Video không tồn tại")
        try:
            minio_client.remove_object(BUCKET_SOURCES, row["object_name"])
        except S3Error as e:
            log.warning("delete %s: MinIO remove failed (ignored): %s", video_id, e)
        conn.execute("DELETE FROM videos WHERE id = %s", (video_id,))
    log.info("delete video: id=%s object=%s", video_id, row["object_name"])
    return {"ok": True}
