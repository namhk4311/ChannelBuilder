"""Bulk import from data_raw/ → MinIO + Postgres. Function + endpoint."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException

from config import BUCKET_SOURCES, DATA_RAW_PATH

from .categories import default_tag_from_category, default_tag_from_clip_id
from .db import pg
from .storage import minio_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["importer"])


def import_from_data_raw(
    data_raw_path: Path,
    progress_cb: Optional[Callable[[int, int, str, str], None]] = None,
    dry_run: bool = False,
    library: str = "vng_insider",
) -> dict:
    """
    Đọc data_raw/00_INDEX.json → upsert categories + clips vào library `library`.
    Library mặc định 'vng_insider' (đã được migration seed).
    Idempotent: chạy lại bao nhiêu lần cũng không trùng.
    """
    index_path = data_raw_path / "00_INDEX.json"
    if not index_path.exists():
        log.error("import: %s not found", index_path)
        raise FileNotFoundError(f"Không tìm thấy {index_path}")
    log.info("import begin: source=%s library=%s dry_run=%s",
             index_path, library, dry_run)
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    # ── Bước 1: upsert categories ──
    categories_upserted = 0
    for cat_name, cat_info in index.get("categories", {}).items():
        clip_ids = cat_info.get("clip_ids") or []
        if clip_ids:
            default_tag = default_tag_from_clip_id(clip_ids[0])
        else:
            default_tag = default_tag_from_category(cat_name)

        if dry_run:
            categories_upserted += 1
            if progress_cb:
                progress_cb(0, 0, cat_name, "cat-dry")
            continue

        with pg() as conn:
            cur = conn.execute("""
                INSERT INTO categories (library, name, default_tag)
                VALUES (%s, %s, %s)
                ON CONFLICT (library, name) DO NOTHING
            """, (library, cat_name, default_tag))
            if cur.rowcount > 0:
                categories_upserted += 1
                log.info("category upsert: %s/%s (tag=%s)", library, cat_name, default_tag)

    # ── Bước 2: upsert clips ──
    clips = index.get("clips", [])
    total = len(clips)
    videos_imported = 0
    videos_skipped = 0
    missing_files: list[str] = []

    for idx, clip in enumerate(clips, start=1):
        clip_id = clip["id"]

        with pg() as conn:
            exists = conn.execute(
                "SELECT 1 FROM videos WHERE id = %s", (clip_id,)
            ).fetchone()
        if exists:
            videos_skipped += 1
            if progress_cb:
                progress_cb(idx, total, clip_id, "skip")
            continue

        rel_path = clip["file"]
        src_file = data_raw_path / rel_path
        if not src_file.exists():
            missing_files.append(rel_path)
            log.warning("import [%d/%d] missing file: %s", idx, total, rel_path)
            if progress_cb:
                progress_cb(idx, total, clip_id, "missing")
            continue

        ext = src_file.suffix
        object_name = f"{clip_id}{ext}"

        if dry_run:
            videos_imported += 1
            if progress_cb:
                progress_cb(idx, total, clip_id, "dry-run")
            continue

        minio_client.fput_object(
            BUCKET_SOURCES, object_name, str(src_file),
            content_type="video/quicktime" if ext.lower() == ".mov" else "video/mp4",
        )

        with pg() as conn:
            conn.execute("""
                INSERT INTO videos
                  (id, file, library, category, clip_tag, description, mood, duration_sec,
                   has_people, people_note_raw, resolution, notes, object_name, size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                clip_id,
                clip.get("file", ""),
                library,
                clip.get("category", ""),
                clip.get("clip_tag", ""),
                clip.get("description") or "",
                clip.get("mood") or "",
                clip.get("duration_sec") or 0,
                bool(clip.get("has_people")),
                clip.get("people_note_raw") or "",
                clip.get("resolution"),
                clip.get("notes") or "",
                object_name,
                src_file.stat().st_size,
            ))

        videos_imported += 1
        log.info("import [%d/%d] OK: %s (%.1fKB)", idx, total, clip_id,
                 src_file.stat().st_size / 1024)
        if progress_cb:
            progress_cb(idx, total, clip_id, "imported")

    log.info("import done: categories=+%d videos=+%d skipped=%d missing=%d",
             categories_upserted, videos_imported, videos_skipped, len(missing_files))
    return {
        "categories_upserted": categories_upserted,
        "videos_imported": videos_imported,
        "videos_skipped": videos_skipped,
        "missing_files": missing_files,
    }


@router.post("/api/import-data-raw")
def import_data_raw_endpoint():
    try:
        return import_from_data_raw(DATA_RAW_PATH)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
