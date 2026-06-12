"""Orchestrator runner — chạy pipeline A→B→C→★gate→D trong thread nền.

Nguyên tắc gốc: AI execute + learn, Human decide. Pipeline DỪNG ở human gate
trước khi Publisher đăng; human bấm approve/reject từ UI.

Steps:
  1. [A] scan_trends        — Scout chưa wire → trend digest mock (stub)
  2. [B] generate_ideas     — live: LLM MaaS thật | mock: sample có sẵn
  3. [B] generate_script    — orchestrator chọn idea est_fit cao nhất
  4. [C] produce_video      — live: pipeline 6 bước thật (progress %) | mock: simulate
  5. [★] human_approval     — gate chờ human duyệt
  6. [D] publish_video      — live: đăng TikTok thật (SELF_ONLY) | mock: giả lập
  7. [D] get_video_metrics  — live: metric thật (cần video_id) | mock: số giả lập

Mỗi step gắn `data_source` để UI nói rõ data thật hay giả:
  real | sample (output mẫu) | mock (giả lập) | stub (agent chưa build/wire).

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

from . import mock_data

log = logging.getLogger(__name__)

STEP_PLAN: list[dict[str, str]] = [
    {"id": "scan_trends", "agent": "scout", "code": "A", "tool": "scan_trends",
     "title": "Quét trend thị trường"},
    {"id": "generate_ideas", "agent": "creative", "code": "B", "tool": "generate_ideas",
     "title": "Sinh ý tưởng video"},
    {"id": "generate_script", "agent": "creative", "code": "B", "tool": "generate_script",
     "title": "Viết kịch bản + shot list"},
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
_GATES: dict[str, threading.Event] = {}
_SEQ = itertools.count(1)
_MAX_RUNS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run(mode: str, topic: str | None, library: str,
             subtitles: bool, n_ideas: int) -> dict:
    run_id = f"run_{next(_SEQ):04d}"
    run = {
        "id": run_id, "mode": mode, "topic": topic,
        "library": library, "subtitles": subtitles, "n_ideas": n_ideas,
        "status": "running", "created_at": _now(), "updated_at": _now(),
        "gate": {"decision": None, "decided_at": None},
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
    _RUNS[run_id] = run
    _GATES[run_id] = threading.Event()
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
    mock = run["mode"] == "mock"

    # ---- 1. [A] scan_trends — Scout chưa wire vào ChannelBuilder
    s = _start_step(run, "scan_trends")
    trend = mock_data.TREND_DIGEST
    _finish_step(run, s, "stub", trend,
                 "Scout chưa wire — dùng trend digest mock seed hook + benchmark",
                 data_source="stub")

    # ---- 2. [B] generate_ideas
    s = _start_step(run, "generate_ideas")
    if mock:
        time.sleep(0.6)  # cho UI kịp thấy step chạy
        result = mock_data.IDEAS_RESULT
    else:
        from agents.creative import generate_ideas
        result = generate_ideas(topic=run["topic"], n_ideas=run["n_ideas"])
    ideas = result.get("ideas") or []
    if result.get("status") != "ok" or not ideas:
        return _fail_run(run, s, result.get("error") or "Không sinh được idea", result)
    pillars = ", ".join(sorted({str(i.get("pillar", "?")) for i in ideas}))
    _finish_step(run, s, "ok", result,
                 f"{len(ideas)} ý tưởng (pillar: {pillars})"
                 + (" • sample có sẵn" if mock else " • LLM MaaS sinh thật"),
                 data_source="sample" if mock else "real")

    # ---- 3. [B] generate_script — orchestrator chọn idea est_fit cao nhất
    s = _start_step(run, "generate_script")
    best = max(ideas, key=lambda i: i.get("est_fit") or 0)
    if mock:
        time.sleep(0.6)
        result = mock_data.SCRIPT_RESULT
    else:
        from agents.creative import generate_script
        result = generate_script(idea=best)
    package = result.get("package")
    if result.get("status") != "ok" or not package:
        return _fail_run(run, s, result.get("error") or "Không sinh được script", result)
    n_words = len((package.get("script") or "").split())
    _finish_step(run, s, "ok", result,
                 f"Chọn “{best.get('title')}” (est_fit {best.get('est_fit')}) • "
                 f"script {n_words} từ • {len(package.get('shot_list') or [])} câu"
                 + (" • sample có sẵn" if mock else " • LLM MaaS sinh thật"),
                 data_source="sample" if mock else "real")

    # ---- 4. [C] produce_video — pipeline 6 bước, progress % thật
    s = _start_step(run, "produce_video")
    if mock:
        for pct, msg in mock_data.PRODUCE_PROGRESS:
            s["progress"] = pct
            s["summary"] = msg
            run["updated_at"] = _now()
            time.sleep(0.5)
        produce_result = mock_data.PRODUCE_RESULT
    else:
        def cb(percent: int, message: str) -> None:
            s["progress"] = percent
            s["summary"] = message
            run["updated_at"] = _now()

        try:
            from agents.producer.pipeline import produce_from_script
            produce_result = produce_from_script(
                package.get("script") or "", progress_cb=cb,
                subtitles=run["subtitles"], library=run["library"])
        except Exception as e:  # noqa: BLE001 — producer raise HTTPException/Exception
            return _fail_run(run, s, f"Producer lỗi: {e}")
    s["progress"] = 100
    video_url = produce_result.get("output_url")
    _finish_step(run, s, "ok", produce_result,
                 f"{produce_result.get('final_duration_sec')}s • "
                 f"{len(produce_result.get('selected_clips') or [])} clip • "
                 f"TTS {'cache' if produce_result.get('tts_cache_hit') else 'mới'}"
                 + (" • giả lập, KHÔNG render thật" if mock else " • render thật + MinIO"),
                 data_source="mock" if mock else "real")

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
    if mock:
        time.sleep(0.5)
        result = mock_data.PUBLISH_RESULT
    else:
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
                 + (" • giả lập, KHÔNG đăng thật" if mock else " • đăng TikTok THẬT"),
                 data_source="mock" if mock else "real")

    # ---- 7. [D] get_video_metrics
    s = _start_step(run, "get_video_metrics")
    if mock:
        result = mock_data.METRICS_RESULT
    elif not video_id:
        # Sandbox không trả video_id ngay (cần scope video.list — việc còn mở của [D]).
        _finish_step(run, s, "skipped", None,
                     "Không có video_id từ sandbox — cần scope video.list, bỏ qua kéo metric")
        run["status"] = "completed"
        run["updated_at"] = _now()
        return None
    else:
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
                     f"{m.get('comment_count', 0)} comment • {m.get('share_count', 0)} share"
                     + (" • số giả lập" if mock else " • metric TikTok thật"),
                     data_source="mock" if mock else "real")
    run["status"] = "completed"
    run["updated_at"] = _now()
    return None


# ------------------------------------------------------------------ public API

def start_run(mode: str = "mock", topic: str | None = None,
              library: str = "vng_insider", subtitles: bool = True,
              n_ideas: int = 5) -> dict:
    run = _new_run(mode, topic, library, subtitles, n_ideas)

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
    log.info("workflow %s started (mode=%s topic=%r library=%s)",
             run["id"], mode, topic, library)
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


def get_run(run_id: str) -> dict | None:
    return _RUNS.get(run_id)


def list_runs() -> list[dict]:
    """Danh sách run (mới nhất trước), không kèm output nặng."""
    out = []
    for run in sorted(_RUNS.values(), key=lambda r: r["created_at"], reverse=True):
        out.append({
            "id": run["id"], "mode": run["mode"], "topic": run["topic"],
            "status": run["status"], "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "steps": [{"id": s["id"], "agent": s["agent"], "code": s["code"],
                       "title": s["title"], "status": s["status"]}
                      for s in run["steps"]],
        })
    return out
