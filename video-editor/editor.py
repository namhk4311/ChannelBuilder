"""
Video editing — feature cắt ghép (concat).

Sau này sẽ mở rộng cho Producer agent C:
  • overlay text hook 2-3s đầu video
  • mix TTS voice track lên timeline
  • compose theo shot list của Creative Brain (B)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import BUCKET_OUTPUTS, BUCKET_SOURCES, MINIO_ENDPOINT

from .db import pg
from .ffprobe import ffprobe_metadata
from .storage import minio_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["editor"])


class ConcatRequest(BaseModel):
    video_ids: list[str]
    output_name: Optional[str] = None


@router.post("/api/concat")
def concat_videos(req: ConcatRequest):
    if len(req.video_ids) < 2:
        raise HTTPException(400, "Cần chọn ít nhất 2 video")

    log.info("concat begin: %d clips → %s",
             len(req.video_ids), req.output_name or "auto")

    # 1. Lookup object_name cho từng id
    with pg() as conn:
        placeholders = ", ".join(["%s"] * len(req.video_ids))
        rows = conn.execute(
            f"SELECT id, object_name FROM videos WHERE id IN ({placeholders})",
            req.video_ids,
        ).fetchall()

    by_id = {r["id"]: r["object_name"] for r in rows}
    missing = [v for v in req.video_ids if v not in by_id]
    if missing:
        log.warning("concat rejected: missing video ids %s", missing)
        raise HTTPException(404, f"Không tìm thấy video: {missing}")

    # 2. Work trong temp dir để cleanup chắc chắn
    workdir = Path(tempfile.mkdtemp(prefix="concat_"))
    t0 = time.monotonic()
    try:
        # Download theo đúng thứ tự client gửi
        local_paths = []
        for idx, vid in enumerate(req.video_ids):
            obj = by_id[vid]
            local = workdir / f"{idx:03d}_{obj}"
            minio_client.fget_object(BUCKET_SOURCES, obj, str(local))
            local_paths.append(local)
        log.debug("concat: downloaded %d files in %.2fs",
                  len(local_paths), time.monotonic() - t0)

        # 3. Concat demuxer list
        list_file = workdir / "list.txt"
        with open(list_file, "w") as f:
            for p in local_paths:
                f.write(f"file '{p.absolute()}'\n")

        # 4. ffmpeg re-encode để xử lý clip mixed codec/resolution
        output_basename = req.output_name or f"output_{uuid.uuid4().hex[:8]}"
        if not output_basename.endswith(".mp4"):
            output_basename += ".mp4"
        output_path = workdir / output_basename

        t_ffmpeg = time.monotonic()
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ], capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg failed (rc=%d): %s",
                      result.returncode, result.stderr[-300:])
            raise HTTPException(500, f"FFmpeg failed: {result.stderr[-500:]}")
        log.info("ffmpeg done in %.2fs", time.monotonic() - t_ffmpeg)

        # 5. Upload vào bucket outputs (public-read đã set ở init_buckets)
        minio_client.fput_object(
            BUCKET_OUTPUTS, output_basename, str(output_path),
            content_type="video/mp4",
        )

        out_duration, _ = ffprobe_metadata(str(output_path))
        public_url = f"http://{MINIO_ENDPOINT}/{BUCKET_OUTPUTS}/{output_basename}"

        log.info("concat done: %s duration=%.2fs total=%.2fs url=%s",
                 output_basename, out_duration, time.monotonic() - t0, public_url)
        return {
            "output_name": output_basename,
            "output_url": public_url,
            "source_count": len(req.video_ids),
            "duration_sec": out_duration,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
