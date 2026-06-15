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

# Output chuẩn TikTok dọc — mọi clip được normalize về đây trước khi nối,
# tránh vỡ hình tại điểm chuyển cảnh do clip nguồn khác fps/codec/resolution.
TARGET_W, TARGET_H, TARGET_FPS = 1080, 1920, 30


def _has_audio_stream(path: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=10,
    )
    return bool(r.stdout.strip())


class ConcatRequest(BaseModel):
    video_ids: list[str]
    output_name: Optional[str] = None
    # Brand guide VNG Insider: chỉ 1 lớp giọng lồng tiếng, KHÔNG nhạc nền,
    # tắt hết tiếng clip gốc. Default True để khớp spec; cho phép override
    # nếu sau này cần giữ tiếng gốc (vd: clip có lời người thật).
    mute_source: bool = True


def concat_to_local(
    video_ids: list[str],
    workdir: Path,
    mute_source: bool = True,
    output_name: Optional[str] = None,
) -> tuple[Path, float]:
    """
    Download clip từ MinIO + ffmpeg concat → local file. KHÔNG upload.

    Caller (endpoint /api/concat hoặc producer) quyết định upload/dùng tiếp.

    Trả về (local_output_path, duration_sec).
    Raises HTTPException 400/404/500 nếu input lỗi hoặc ffmpeg fail.
    """
    if len(video_ids) < 2:
        raise HTTPException(400, "Cần chọn ít nhất 2 video")

    # 1. Lookup object_name cho từng id
    with pg() as conn:
        placeholders = ", ".join(["%s"] * len(video_ids))
        rows = conn.execute(
            f"SELECT id, object_name FROM videos WHERE id IN ({placeholders})",
            video_ids,
        ).fetchall()

    by_id = {r["id"]: r["object_name"] for r in rows}
    missing = [v for v in video_ids if v not in by_id]
    if missing:
        log.warning("concat rejected: missing video ids %s", missing)
        raise HTTPException(404, f"Không tìm thấy video: {missing}")

    # 2. Download theo đúng thứ tự
    t0 = time.monotonic()
    local_paths = []
    for idx, vid in enumerate(video_ids):
        obj = by_id[vid]
        local = workdir / f"{idx:03d}_{obj}"
        minio_client.fget_object(BUCKET_SOURCES, obj, str(local))
        local_paths.append(local)
    log.debug("concat: downloaded %d files in %.2fs",
              len(local_paths), time.monotonic() - t0)

    # 3. Build ffmpeg concat FILTER (không dùng concat demuxer).
    #    Demuxer (-f concat) nối ở mức packet, yêu cầu mọi clip giống hệt
    #    codec/resolution/fps/timebase — clip iPhone .MOV không đồng nhất
    #    → vỡ hình tại điểm chuyển cảnh. Concat filter decode từng input
    #    riêng, normalize về 1080x1920 / 30fps / yuv420p rồi mới nối frame.
    n = len(local_paths)
    filters = []
    for i in range(n):
        filters.append(
            f"[{i}:v]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
            f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={TARGET_FPS},format=yuv420p[v{i}]"
        )

    keep_audio = not mute_source
    if keep_audio:
        # Concat filter cần mọi input có audio track — clip thiếu audio sẽ
        # làm filter graph fail. Probe trước; thiếu thì fallback mute.
        silent = [p.name for p in local_paths if not _has_audio_stream(p)]
        if silent:
            log.warning("concat: %d clip không có audio (%s) → fallback mute",
                        len(silent), silent)
            keep_audio = False

    if keep_audio:
        for i in range(n):
            filters.append(f"[{i}:a]aresample=48000[a{i}]")
        pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
        filters.append(f"{pairs}concat=n={n}:v=1:a=1[outv][outa]")
        map_args = ["-map", "[outv]", "-map", "[outa]",
                    "-c:a", "aac", "-b:a", "128k"]
    else:
        chain = "".join(f"[v{i}]" for i in range(n))
        filters.append(f"{chain}concat=n={n}:v=1:a=0[outv]")
        map_args = ["-map", "[outv]", "-an"]

    output_basename = output_name or f"concat_{uuid.uuid4().hex[:8]}.mp4"
    if not output_basename.endswith(".mp4"):
        output_basename += ".mp4"
    output_path = workdir / output_basename

    cmd = ["ffmpeg", "-y"]
    for p in local_paths:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex", ";".join(filters),
        *map_args,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        str(output_path),
    ]
    log.debug("concat cmd: %s", " ".join(cmd))
    t_ffmpeg = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg failed (rc=%d): %s",
                  result.returncode, result.stderr[-300:])
        raise HTTPException(500, f"FFmpeg failed: {result.stderr[-500:]}")
    log.info("ffmpeg done in %.2fs (concat filter, %dx%d@%dfps, audio: %s)",
             time.monotonic() - t_ffmpeg, TARGET_W, TARGET_H, TARGET_FPS,
             "kept" if keep_audio else "muted")

    out_duration, _ = ffprobe_metadata(str(output_path))
    return output_path, out_duration


def concat_with_cut_timeline(
    video_ids: list[str],
    cuts: list[float],
    workdir: Path,
    output_name: Optional[str] = None,
) -> tuple[Path, float]:
    """Concat n clips theo timeline `cuts` (n+1 timestamps).

    Mỗi clip i fill đúng segment `cuts[i+1] - cuts[i]` sec:
      • src ≥ target → trim cắt phần thừa.
      • src < target → loop-fill 1x (`-stream_loop -1` + trim), KHÔNG slow-mo.
    Output length = `cuts[-1]` chính xác → KHÔNG cần STEP 4 align downstream.

    Dùng filter `trim+setpts` (không phải input `-ss/-t`) để giữ độ
    chính xác frame trên timeline filter graph. Vẫn normalize 1080x1920@30fps
    yuv420p như concat_to_local. Audio luôn muted (sidechain music sẽ mix
    sau ở STEP 5 mux).
    """
    n = len(video_ids)
    if n < 1:
        raise HTTPException(400, "Cần ít nhất 1 video")
    if len(cuts) != n + 1:
        raise HTTPException(500,
            f"cuts phải có {n + 1} timestamps cho {n} clip, nhận {len(cuts)}")

    # 1. Lookup object_name + duration của từng clip để cap trim_dur
    with pg() as conn:
        placeholders = ", ".join(["%s"] * n)
        rows = conn.execute(
            f"SELECT id, object_name, duration_sec FROM videos "
            f"WHERE id IN ({placeholders})",
            video_ids,
        ).fetchall()
    by_id = {r["id"]: r for r in rows}
    missing = [v for v in video_ids if v not in by_id]
    if missing:
        raise HTTPException(404, f"Không tìm thấy video: {missing}")

    # 2. Download theo thứ tự
    t0 = time.monotonic()
    local_paths = []
    for idx, vid in enumerate(video_ids):
        obj = by_id[vid]["object_name"]
        local = workdir / f"{idx:03d}_{obj}"
        minio_client.fget_object(BUCKET_SOURCES, obj, str(local))
        local_paths.append(local)
    log.debug("concat-cuts: downloaded %d files in %.2fs",
              n, time.monotonic() - t0)

    # 3. Build filter — trim/loop-fill + scale + pad + fps + concat
    #
    # INVARIANT: tổng segment phải = cuts[-1] = voice_duration.
    # Voice là bất khả xâm phạm, video phải khớp 100% — KHÔNG bao giờ cap
    # target_dur xuống src_dur (sẽ làm ffmpeg -shortest cắt voice).
    #
    # 2 case xử lý:
    #   • src ≥ target → trim: cắt phần thừa từ cuối clip
    #   • src < target → LOOP-FILL: lặp clip giữ tốc độ 1x (KHÔNG slow-mo) rồi
    #     trim đúng target_dur. Input dùng `-stream_loop -1` (lặp vô hạn ở
    #     decoder, copy pattern music-loop ở pipeline.mux_voice_with_music);
    #     `trim` chặn độ dài nên loop vô hạn an toàn. Phát 1x → effective fps
    #     giữ TARGET_FPS, hết giật/slow-mo.
    filters = []
    actual_cuts = [cuts[0]]
    loop_flags = [False] * n          # input nào cần prepend -stream_loop -1
    n_looped = 0
    for i in range(n):
        target_dur = cuts[i + 1] - cuts[i]
        src_dur = by_id[video_ids[i]]["duration_sec"] or 0

        if src_dur <= 0 or src_dur >= target_dur:
            # Không có metadata HOẶC source đủ dài → trim trực tiếp tới target.
            # (src<=0: ffmpeg tự xử; nếu clip thực ngắn hơn target sẽ ra segment
            #  ngắn — hiếm, vì hầu hết clip có duration_sec trong DB.)
            video_filter = f"trim=0:{target_dur:.3f},setpts=PTS-STARTPTS"
        else:
            # Source ngắn hơn → loop-fill 1x: -stream_loop -1 ở input + trim ở
            # filter. KHÔNG setpts stretch → không slow-mo.
            loop_flags[i] = True
            n_looped += 1
            loop_factor = target_dur / src_dur
            if loop_factor > 2.5:
                log.warning("concat-cuts: clip %s loop %.2fx (%.2fs → %.2fs) — "
                            "hình lặp nhiều lần, cân nhắc multi-clip cùng tag",
                            video_ids[i][:8], loop_factor, src_dur, target_dur)
            else:
                log.info("concat-cuts: clip %s loop %.2fx (%.2fs → %.2fs)",
                         video_ids[i][:8], loop_factor, src_dur, target_dur)
            video_filter = f"trim=0:{target_dur:.3f},setpts=PTS-STARTPTS"

        actual_cuts.append(round(actual_cuts[-1] + target_dur, 3))
        filters.append(
            f"[{i}:v]{video_filter},"
            f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
            f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={TARGET_FPS},format=yuv420p[v{i}]"
        )
    chain = "".join(f"[v{i}]" for i in range(n))
    filters.append(f"{chain}concat=n={n}:v=1:a=0[outv]")

    output_basename = output_name or f"concat_cuts_{uuid.uuid4().hex[:8]}.mp4"
    if not output_basename.endswith(".mp4"):
        output_basename += ".mp4"
    output_path = workdir / output_basename

    # `-stream_loop` là INPUT option → phải đặt TRƯỚC `-i` của clip đó. Mỗi clip
    # là 1 input riêng nên build list động: clip cần loop thì prepend.
    cmd = ["ffmpeg", "-y"]
    for i, p in enumerate(local_paths):
        if loop_flags[i]:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        str(output_path),
    ]
    log.info("concat-cuts: %d clips · target_cuts=%s · actual=%s · looped=%d (1x, no slow-mo)",
             n, [round(c, 2) for c in cuts], [round(c, 2) for c in actual_cuts],
             n_looped)
    log.debug("concat-cuts cmd: %s", " ".join(cmd))
    t_ffmpeg = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("concat-cuts ffmpeg fail (rc=%d): %s",
                  result.returncode, result.stderr[-300:])
        raise HTTPException(500, f"FFmpeg failed: {result.stderr[-500:]}")
    log.info("concat-cuts ffmpeg done in %.2fs", time.monotonic() - t_ffmpeg)

    out_duration, _ = ffprobe_metadata(str(output_path))
    return output_path, out_duration


@router.post("/api/concat")
def concat_videos(req: ConcatRequest):
    log.info("concat begin: %d clips → %s (mute_source=%s)",
             len(req.video_ids), req.output_name or "auto", req.mute_source)

    workdir = Path(tempfile.mkdtemp(prefix="concat_"))
    t0 = time.monotonic()
    try:
        output_path, out_duration = concat_to_local(
            req.video_ids,
            workdir=workdir,
            mute_source=req.mute_source,
            output_name=req.output_name,
        )
        output_basename = output_path.name

        # Upload vào bucket outputs (public-read đã set ở init_buckets)
        minio_client.fput_object(
            BUCKET_OUTPUTS, output_basename, str(output_path),
            content_type="video/mp4",
        )

        public_url = f"http://{MINIO_ENDPOINT}/{BUCKET_OUTPUTS}/{output_basename}"

        log.info("concat done: %s duration=%.2fs total=%.2fs url=%s",
                 output_basename, out_duration, time.monotonic() - t0, public_url)
        return {
            "output_name": output_basename,
            "output_url": public_url,
            "source_count": len(req.video_ids),
            "duration_sec": out_duration,
            "audio_muted": req.mute_source,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
