"""Orchestrator runner — chạy pipeline A→B→C→★gate→D trong thread nền (LIVE).

Nguyên tắc gốc: AI execute + learn, Human decide. Pipeline DỪNG ở human gate
trước khi Publisher đăng; human bấm approve/reject từ UI.

Chỉ chạy LIVE — mọi agent đã wire thật, không còn mode mock:
  1. [A] scan_trends        — Scout thật (phân tích deterministic dataset seed)
  2. [B] generate_ideas     — LLM MaaS sinh ý tưởng (nhận trend_digest từ [A])
  3. [B] generate_script    — orchestrator chọn idea est_fit cao nhất → script
  4. [C] produce_video      — pipeline 6 bước thật (TTS + ghép clip + phụ đề), progress %
  5. [★] human_approval     — gate chờ human duyệt
  6. [D] publish_video      — đăng TikTok thật (SELF_ONLY)
  7. [D] get_video_metrics  — metric thật (cần video_id)

Mỗi step gắn `data_source` để UI nói rõ data thật hay seed:
  real (chạy thật) | sample (dataset seed) | stub (agent chưa build/wire).

Run state in-memory (giống JOBS của producer) — restart server là mất, đủ demo.
"""
from __future__ import annotations

import itertools
import logging
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

STEP_PLAN: list[dict[str, str]] = [
    {"id": "scan_trends", "agent": "scout", "code": "A", "tool": "scan_trends",
     "title": "Quét trend thị trường"},
    {"id": "generate_ideas", "agent": "creative", "code": "B", "tool": "generate_ideas",
     "title": "Sinh ý tưởng video"},
    {"id": "generate_script", "agent": "creative", "code": "B", "tool": "generate_script",
     "title": "Viết kịch bản + shot list"},
    {"id": "script_approval", "agent": "orchestrator", "code": "★", "tool": "script_gate",
     "title": "Human duyệt / sửa kịch bản"},
    {"id": "produce_video", "agent": "producer", "code": "C", "tool": "produce_video",
     "title": "Dựng video (TTS + ghép clip + phụ đề)"},
    {"id": "human_approval", "agent": "orchestrator", "code": "★", "tool": "human_gate",
     "title": "Human duyệt đăng video"},
    {"id": "publish_video", "agent": "publisher", "code": "D", "tool": "publish_video",
     "title": "Đăng TikTok"},
    {"id": "get_video_metrics", "agent": "publisher", "code": "D", "tool": "get_video_metrics",
     "title": "Kéo metric"},
]

_RUNS: dict[str, dict[str, Any]] = {}
_GATES: dict[str, threading.Event] = {}          # publish gate
_SCRIPT_GATES: dict[str, threading.Event] = {}   # script review/edit gate
_SEQ = itertools.count(1)
_MAX_RUNS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run(topic: str | None, library: str,
             subtitles: bool, n_ideas: int,
             music_track_id: str | None = None,
             beat_sync: bool = True,
             music_volume: float = 0.3,
             review_script: bool = False) -> dict:
    run_id = f"run_{next(_SEQ):04d}"
    run = {
        "id": run_id, "topic": topic,
        "library": library, "subtitles": subtitles, "n_ideas": n_ideas,
        "music_track_id": music_track_id,
        "beat_sync": beat_sync,
        "music_volume": music_volume,
        "review_script": review_script,
        "status": "running", "created_at": _now(), "updated_at": _now(),
        "gate": {"decision": None, "decided_at": None},
        "script_gate": {"decision": None, "decided_at": None},
        "script_override": None,
        "steps": [
            {"id": s["id"], "agent": s["agent"], "code": s["code"],
             "tool": s["tool"], "title": s["title"],
             "status": "pending", "started_at": None, "ended_at": None,
             "summary": None, "output": None, "error": None,
             "data_source": None, "progress": None}
            for s in STEP_PLAN
        ],
    }
    # Evict run cũ nhất khi quá _MAX_RUNS (giữ memory bound như JOBS producer).
    while len(_RUNS) >= _MAX_RUNS:
        oldest = min(_RUNS.values(), key=lambda r: r["created_at"])
        _RUNS.pop(oldest["id"], None)
        _GATES.pop(oldest["id"], None)
        _SCRIPT_GATES.pop(oldest["id"], None)
    _RUNS[run_id] = run
    _GATES[run_id] = threading.Event()
    _SCRIPT_GATES[run_id] = threading.Event()
    return run


def _step(run: dict, step_id: str) -> dict:
    return next(s for s in run["steps"] if s["id"] == step_id)


def _start_step(run: dict, step_id: str) -> dict:
    s = _step(run, step_id)
    s["status"] = "running"
    s["started_at"] = _now()
    run["updated_at"] = _now()
    return s


def _finish_step(run: dict, s: dict, status: str, output: Any = None,
                 summary: str | None = None, error: str | None = None,
                 data_source: str | None = None) -> None:
    s["status"] = status
    s["ended_at"] = _now()
    s["output"] = output
    s["summary"] = summary
    s["error"] = error
    s["data_source"] = data_source
    run["updated_at"] = _now()


def _fail_run(run: dict, s: dict, error: str, output: Any = None) -> None:
    log.warning("workflow %s · step %s FAILED: %s", run["id"], s["id"], error)
    _finish_step(run, s, "failed", output=output, error=error)
    for other in run["steps"]:
        if other["status"] == "pending":
            other["status"] = "skipped"
    run["status"] = "failed"
    run["updated_at"] = _now()


def _download_to_tmp(url: str) -> str:
    """Tải video final từ MinIO outputs về file tạm cho publish_video (cần local path)."""
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="workflow_publish_")
    Path(path).unlink(missing_ok=True)
    urllib.request.urlretrieve(url, path)  # noqa: S310 — URL nội bộ MinIO outputs
    return path


def _run_pipeline(run: dict) -> None:  # noqa: PLR0915 — pipeline tuần tự, đọc từ trên xuống
    # ---- 1. [A] scan_trends — Scout Agent LLM extract TikTok thật (fallback seed)
    s = _start_step(run, "scan_trends")
    trend_for_creative = None
    try:
        from config import SCOUT_USE_LLM
        from agents.scout import run_scout
        scout_result = run_scout(top_n=3, prefer_live=SCOUT_USE_LLM)
    except Exception as e:  # noqa: BLE001 — Scout lỗi không được giết pipeline
        scout_result = {"status": "failed", "error": str(e), "digest": None, "source": "seed"}
    if scout_result.get("status") == "ok":
        trend_for_creative = scout_result.get("day_cho_creative")
        digest = scout_result.get("digest") or {}
        is_llm = scout_result.get("source") == "llm"
        hooks = ", ".join((trend_for_creative or {}).get("hook_pattern_thang") or []) or "—"
        src_note = ("LLM extract trang search TikTok (data thật, metric=likes)" if is_llm
                    else "fallback dataset seed (Scout LLM fetch lỗi)")
        _finish_step(run, s, "ok", scout_result,
                     f"{digest.get('so_video_quet', 0)} video • hook thắng: {hooks} • "
                     f"ngưỡng {digest.get('benchmark_khoi_tao', {}).get('nguong')} "
                     f"{digest.get('metric')} • {src_note}",
                     data_source="real" if is_llm else "sample")
    else:
        # Creative degrade được khi không có trend — không abort run.
        _finish_step(run, s, "failed", scout_result,
                     "Scout lỗi — Creative chạy không có trend digest",
                     error=scout_result.get("error"), data_source="sample")

    # ---- 2. [B] generate_ideas (nhận trend_digest từ Scout)
    s = _start_step(run, "generate_ideas")
    from agents.creative import generate_ideas
    result = generate_ideas(topic=run["topic"], trend_digest=trend_for_creative,
                            n_ideas=run["n_ideas"])
    ideas = result.get("ideas") or []
    if result.get("status") != "ok" or not ideas:
        return _fail_run(run, s, result.get("error") or "Không sinh được idea", result)
    pillars = ", ".join(sorted({str(i.get("pillar", "?")) for i in ideas}))
    _finish_step(run, s, "ok", result,
                 f"{len(ideas)} ý tưởng (pillar: {pillars}) • LLM MaaS sinh thật"
                 + (" • bám trend từ Scout" if trend_for_creative else ""),
                 data_source="real")

    # ---- 3. [B] generate_script — orchestrator chọn idea est_fit cao nhất
    s = _start_step(run, "generate_script")
    best = max(ideas, key=lambda i: i.get("est_fit") or 0)
    from agents.creative import generate_script
    result = generate_script(idea=best)
    package = result.get("package")
    if result.get("status") != "ok" or not package:
        return _fail_run(run, s, result.get("error") or "Không sinh được script", result)
    n_words = len((package.get("script") or "").split())
    _finish_step(run, s, "ok", result,
                 f"Chọn “{best.get('title')}” (est_fit {best.get('est_fit')}) • "
                 f"script {n_words} từ • {len(package.get('shot_list') or [])} câu • LLM MaaS sinh thật",
                 data_source="real")

    # ---- 3b. [★] script gate — Human duyệt/sửa kịch bản (chỉ khi review_script)
    s = _start_step(run, "script_approval")
    if not run["review_script"]:
        _finish_step(run, s, "skipped", None, "Không bật duyệt kịch bản (full-auto)")
    else:
        s["status"] = "awaiting"
        run["status"] = "awaiting_script"
        s["output"] = {
            "script": package.get("script"),
            "text_hook": package.get("text_hook"),
            "caption": package.get("caption"),
            "hashtags": package.get("hashtags"),
            "shot_list": package.get("shot_list"),
            "title": best.get("title"),
        }
        s["summary"] = "Pipeline tạm dừng — chờ human duyệt/sửa kịch bản"
        run["updated_at"] = _now()
        _SCRIPT_GATES[run["id"]].wait()
        if run["script_gate"]["decision"] != "approved":
            _finish_step(run, s, "rejected", s["output"], "Human huỷ ở bước kịch bản")
            for other in run["steps"]:
                if other["status"] == "pending":
                    other["status"] = "skipped"
            run["status"] = "rejected"
            run["updated_at"] = _now()
            return None
        if run.get("script_override"):
            package["script"] = run["script_override"]   # bản kịch bản user đã sửa
        run["status"] = "running"
        _finish_step(run, s, "ok", {"script": package.get("script")},
                     "Đã duyệt kịch bản" + (" (đã sửa)" if run.get("script_override") else ""))

    # ---- 4. [C] produce_video — pipeline 6 bước, progress % thật
    s = _start_step(run, "produce_video")

    def cb(percent: int, message: str) -> None:
        s["progress"] = percent
        s["summary"] = message
        run["updated_at"] = _now()

    try:
        from agents.producer.pipeline import produce_from_script
        produce_result = produce_from_script(
            package.get("script") or "", progress_cb=cb,
            subtitles=run["subtitles"], library=run["library"],
            music_track_id=run["music_track_id"],
            beat_sync=run["beat_sync"],
            music_volume=run["music_volume"])
    except Exception as e:  # noqa: BLE001 — producer raise HTTPException/Exception
        return _fail_run(run, s, f"Producer lỗi: {e}")
    s["progress"] = 100
    video_url = produce_result.get("output_url")
    _finish_step(run, s, "ok", produce_result,
                 f"{produce_result.get('final_duration_sec')}s • "
                 f"{len(produce_result.get('selected_clips') or [])} clip • "
                 f"TTS {'cache' if produce_result.get('tts_cache_hit') else 'mới'} • render thật + MinIO",
                 data_source="real")

    # ---- 5. [★] human gate — Human decide
    s = _start_step(run, "human_approval")
    s["status"] = "awaiting"
    run["status"] = "awaiting_approval"
    caption = (package.get("caption") or "").strip()
    hashtags = " ".join(package.get("hashtags") or [])
    full_caption = f"{caption} {hashtags}".strip()
    s["output"] = {"video_url": video_url, "caption": full_caption,
                   "text_hook": package.get("text_hook"),
                   "duration_sec": produce_result.get("final_duration_sec")}
    s["summary"] = "Pipeline tạm dừng — chờ human duyệt trước khi đăng"
    run["updated_at"] = _now()
    _GATES[run["id"]].wait()
    if run["gate"]["decision"] != "approved":
        _finish_step(run, s, "rejected", s["output"], "Human từ chối đăng video")
        for other in run["steps"]:
            if other["status"] == "pending":
                other["status"] = "skipped"
        run["status"] = "rejected"
        run["updated_at"] = _now()
        return None
    run["status"] = "running"
    _finish_step(run, s, "ok", s["output"], "Human đã duyệt — tiếp tục đăng")

    # ---- 6. [D] publish_video
    s = _start_step(run, "publish_video")
    if not video_url:
        return _fail_run(run, s, "Producer không trả output_url — không có video để đăng")
    try:
        local_path = _download_to_tmp(video_url)
    except Exception as e:  # noqa: BLE001
        return _fail_run(run, s, f"Không tải được video từ MinIO: {e}")
    from agents.publisher.tools import publish_video
    result = publish_video(video_path=local_path, caption=full_caption)
    Path(local_path).unlink(missing_ok=True)
    if result.get("status") == "failed":
        return _fail_run(run, s, result.get("error") or "publish failed", result)
    video_id = result.get("video_id")
    _finish_step(run, s, "ok", result,
                 "Đăng thành công (SELF_ONLY)"
                 + (f" • video_id {video_id}" if video_id else " • sandbox chưa trả video_id")
                 + " • đăng TikTok THẬT",
                 data_source="real")

    # ---- 7. [D] get_video_metrics
    s = _start_step(run, "get_video_metrics")
    if not video_id:
        # Sandbox không trả video_id ngay (cần scope video.list — việc còn mở của [D]).
        _finish_step(run, s, "skipped", None,
                     "Không có video_id từ sandbox — cần scope video.list, bỏ qua kéo metric")
        run["status"] = "completed"
        run["updated_at"] = _now()
        return None
    from agents.publisher.tools import get_video_metrics
    result = get_video_metrics(video_ids=[video_id])
    if result.get("status") != "ok":
        # Đăng đã thành công — metric lỗi chỉ fail step, run vẫn completed.
        _finish_step(run, s, "failed", result, error=result.get("error") or "metrics failed")
    else:
        videos = result.get("videos") or []
        m = videos[0] if videos else {}
        _finish_step(run, s, "ok", result,
                     f"{m.get('view_count', 0)} view • {m.get('like_count', 0)} like • "
                     f"{m.get('comment_count', 0)} comment • {m.get('share_count', 0)} share • metric TikTok thật",
                     data_source="real")
    run["status"] = "completed"
    run["updated_at"] = _now()
    return None


# ------------------------------------------------------------------ public API

def start_run(topic: str | None = None, library: str = "vng_insider",
              subtitles: bool = True, n_ideas: int = 5,
              music_track_id: str | None = None,
              beat_sync: bool = True,
              music_volume: float = 0.3,
              review_script: bool = False) -> dict:
    run = _new_run(topic, library, subtitles, n_ideas,
                   music_track_id=music_track_id,
                   beat_sync=beat_sync,
                   music_volume=music_volume,
                   review_script=review_script)

    def _wrapper() -> None:
        try:
            _run_pipeline(run)
        except Exception as e:  # noqa: BLE001 — run hỏng không được sập backend
            log.exception("workflow %s crashed", run["id"])
            active = next((st for st in run["steps"]
                           if st["status"] in ("running", "awaiting")), None)
            if active is not None:
                _fail_run(run, active, f"unexpected: {e}")
            else:
                run["status"] = "failed"
                run["updated_at"] = _now()

    threading.Thread(target=_wrapper, daemon=True,
                     name=f"workflow-{run['id']}").start()
    log.info("workflow %s started (topic=%r library=%s music=%s beat_sync=%s vol=%.2f)",
             run["id"], topic, library,
             music_track_id or "—", beat_sync, music_volume)
    return run


def decide_gate(run_id: str, approve: bool) -> dict | None:
    run = _RUNS.get(run_id)
    if run is None:
        return None
    if run["status"] != "awaiting_approval":
        return run  # idempotent — gate đã quyết hoặc chưa tới
    run["gate"]["decision"] = "approved" if approve else "rejected"
    run["gate"]["decided_at"] = _now()
    _GATES[run_id].set()
    return run


def decide_script(run_id: str, approve: bool, script: str | None = None) -> dict | None:
    """Quyết định ở script gate. approve=True + script (optional) → dùng bản đã sửa."""
    run = _RUNS.get(run_id)
    if run is None:
        return None
    if run["status"] != "awaiting_script":
        return run  # idempotent — gate đã quyết hoặc chưa tới
    run["script_gate"]["decision"] = "approved" if approve else "rejected"
    run["script_gate"]["decided_at"] = _now()
    if approve and script and script.strip():
        run["script_override"] = script.strip()
    _SCRIPT_GATES[run_id].set()
    return run


def get_run(run_id: str) -> dict | None:
    return _RUNS.get(run_id)


def list_runs() -> list[dict]:
    """Danh sách run (mới nhất trước), không kèm output nặng."""
    out = []
    for run in sorted(_RUNS.values(), key=lambda r: r["created_at"], reverse=True):
        out.append({
            "id": run["id"], "topic": run["topic"],
            "status": run["status"], "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "steps": [{"id": s["id"], "agent": s["agent"], "code": s["code"],
                       "title": s["title"], "status": s["status"]}
                      for s in run["steps"]],
        })
    return out
