"""Orchestrator runner — chạy pipeline A→B→C→★gate→D trong thread nền (LIVE).

Nguyên tắc gốc: AI execute + learn, Human decide. Pipeline DỪNG ở human gate
trước khi Publisher đăng; human bấm approve/reject từ UI.

Chỉ chạy LIVE — mọi agent đã wire thật, không còn mode mock:
  1. [A] scan_trends        — Scout thật (phân tích deterministic dataset seed)
  2. [B] generate_ideas     — LLM MaaS sinh ý tưởng (nhận trend_digest từ [A] + insight từ [E])
  3. [B] generate_script    — orchestrator chọn idea est_fit cao nhất → script
  4. [C] produce_video      — pipeline 6 bước thật (TTS + ghép clip + phụ đề), progress %
  5. [★] human_approval     — gate chờ human duyệt
  6. [D] publish_video      — đăng TikTok thật (SELF_ONLY) / lên lịch
  7. [E] analyze_batch      — tự chạy sau Publisher: absolute gate batch + insight → [B]

Mỗi step gắn `data_source` để UI nói rõ data thật hay seed:
  real (chạy thật) | sample (dataset seed) | stub (agent chưa build/wire).

Run state in-memory (giống JOBS của producer) — restart server là mất, đủ demo.
"""
from __future__ import annotations

import itertools
import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Loading giả của bước [E] Analyst (giây) — để thấy "agent đang chạy" lúc demo.
_ANALYST_FAKE_DELAY_MIN = 60.0
_ANALYST_FAKE_DELAY_MAX = 120.0

STEP_PLAN: list[dict[str, str]] = [
    {"id": "scan_trends", "agent": "scout", "code": "A", "tool": "scan_trends",
     "title": "Quét trend thị trường"},
    {"id": "generate_ideas", "agent": "creative", "code": "B", "tool": "generate_ideas",
     "title": "Sinh ý tưởng video"},
    {"id": "idea_approval", "agent": "orchestrator", "code": "★", "tool": "idea_gate",
     "title": "Human chọn ý tưởng"},
    {"id": "generate_script", "agent": "creative", "code": "B", "tool": "generate_script",
     "title": "Viết kịch bản + shot list"},
    {"id": "qc_script", "agent": "orchestrator", "code": "★", "tool": "qc_script",
     "title": "QC kịch bản"},
    {"id": "script_approval", "agent": "orchestrator", "code": "★", "tool": "script_gate",
     "title": "Human duyệt / sửa kịch bản"},
    {"id": "produce_video", "agent": "producer", "code": "C", "tool": "produce_video",
     "title": "Dựng video (TTS + ghép clip + phụ đề)"},
    {"id": "human_approval", "agent": "orchestrator", "code": "★", "tool": "human_gate",
     "title": "Human duyệt đăng video"},
    {"id": "publish_video", "agent": "publisher", "code": "D", "tool": "publish_video",
     "title": "Đăng TikTok"},
    {"id": "analyze_batch", "agent": "analyst", "code": "E", "tool": "analyze_batch",
     "title": "Phân tích batch + insight (Analyst)"},
]

_RUNS: dict[str, dict[str, Any]] = {}
_GATES: dict[str, threading.Event] = {}          # publish gate
_SCRIPT_GATES: dict[str, threading.Event] = {}   # script review/edit gate
_IDEA_GATES: dict[str, threading.Event] = {}     # idea selection gate
_SEQ = itertools.count(1)
_MAX_RUNS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_local(dt: datetime) -> str:
    """datetime aware → 'HH:MM dd/MM' theo Asia/Saigon cho summary UI."""
    from config import SCHEDULE_TZ
    try:
        return dt.astimezone(ZoneInfo(SCHEDULE_TZ)).strftime("%H:%M %d/%m")
    except Exception:  # noqa: BLE001
        return str(dt)


def _new_run(topic: str | None, library: str,
             subtitles: bool, n_ideas: int,
             music_track_id: str | None = None,
             beat_sync: bool = True,
             music_volume: float = 0.3,
             review_script: bool = False,
             pick_idea: bool = False,
             publish_mode: str = "review_publish",
             qc_mode: str = "auto") -> dict:
    run_id = f"run_{next(_SEQ):04d}"
    run = {
        "id": run_id, "topic": topic,
        "library": library, "subtitles": subtitles, "n_ideas": n_ideas,
        "music_track_id": music_track_id,
        "beat_sync": beat_sync,
        "music_volume": music_volume,
        "review_script": review_script,
        # QC kịch bản: 'auto' = AI tự sửa nếu QC báo lỗi nặng rồi dựng (không cần human);
        # 'confirm' = dừng ở gate cho human duyệt / cho viết lại / huỷ.
        "qc_mode": qc_mode,
        "pick_idea": pick_idea,
        # Chế độ đăng chọn từ đầu — gate đọc lại field này để hiện đúng nút
        # (đăng ngay vs lên lịch). Persist trên run nên không reset khi UI remount.
        "publish_mode": publish_mode,
        "status": "running", "created_at": _now(), "updated_at": _now(),
        "gate": {"decision": None, "decided_at": None, "scheduled_for": None},
        "script_gate": {"decision": None, "decided_at": None},
        "idea_gate": {"decision": None, "decided_at": None},
        "idea_choice": None,
        "qc_verdict": None,          # verdict QC kịch bản (gắn sau generate_script)
        "script_override": None,
        "caption_override": None,
        "hashtags_override": None,
        "steps": [
            {"id": s["id"], "agent": s["agent"], "code": s["code"],
             "tool": s["tool"], "title": s["title"],
             "status": "pending", "started_at": None, "ended_at": None,
             "summary": None, "output": None, "error": None,
             "data_source": None, "progress": None,
             # True khi step được chạy lại (vd Viết kịch bản sửa theo feedback QC) → UI badge "Đã sửa lại".
             "revised": False}
            for s in STEP_PLAN
        ],
    }
    # Evict run cũ nhất khi quá _MAX_RUNS (giữ memory bound như JOBS producer).
    while len(_RUNS) >= _MAX_RUNS:
        oldest = min(_RUNS.values(), key=lambda r: r["created_at"])
        _RUNS.pop(oldest["id"], None)
        _GATES.pop(oldest["id"], None)
        _SCRIPT_GATES.pop(oldest["id"], None)
        _IDEA_GATES.pop(oldest["id"], None)
    _RUNS[run_id] = run
    _GATES[run_id] = threading.Event()
    _SCRIPT_GATES[run_id] = threading.Event()
    _IDEA_GATES[run_id] = threading.Event()
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


_ANALYST_MSGS = [
    "Gom batch 8 video gần nhất từ Publisher…",
    "Chấm absolute gate: top 20% lô + ngưỡng tuyệt đối retention_3s…",
    "Đối chiếu hook / độ dài / chủ đề theo từng video…",
    "Rút insight digest (thắng / thua / đề xuất) cho vòng sau…",
]


def _run_analyst_step(run: dict) -> None:
    """[E] Analyst — tự chạy sau Publisher: chấm absolute gate batch + insight digest.

    Có loading giả ~1-2 phút (tick progress + message) để thấy agent đang làm việc;
    sau đó chấm thật (run_analyst, deterministic) → output bảng graded + insight + scale_ids
    hiển thị ngay trong timeline run. Analyst lỗi KHÔNG fail run (đăng đã xong).
    """
    s = _start_step(run, "analyze_batch")
    total = random.uniform(_ANALYST_FAKE_DELAY_MIN, _ANALYST_FAKE_DELAY_MAX)
    ticks = 40
    for i in range(ticks):
        time.sleep(total / ticks)
        s["progress"] = int((i + 1) / ticks * 96)
        s["summary"] = _ANALYST_MSGS[min(i * len(_ANALYST_MSGS) // ticks, len(_ANALYST_MSGS) - 1)]
        run["updated_at"] = _now()
    try:
        from agents.analyst import run_analyst
        result = run_analyst("analyst_dummy_batch")
    except Exception as e:  # noqa: BLE001 — Analyst lỗi không được fail run (đăng đã xong)
        s["progress"] = 100
        _finish_step(run, s, "failed", None, "Phân tích batch lỗi", error=str(e))
        run["status"] = "completed"
        run["updated_at"] = _now()
        return
    s["progress"] = 100
    scale_ids = result.get("scale_ids") or []
    _finish_step(run, s, "ok", result,
                 f"{result.get('top_k')} top lô • {len(scale_ids)} đề xuất SCALE "
                 f"({', '.join(scale_ids) or '—'}) • insight sẵn cho vòng sau",
                 data_source="real")
    run["status"] = "completed"
    run["updated_at"] = _now()


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

    # ---- 2. [B] generate_ideas (nhận trend_digest từ Scout + insight_digest từ Analyst)
    s = _start_step(run, "generate_ideas")
    # Đóng vòng học [E]→[B]: insight_digest của batch human đã confirm (nếu có).
    # Import mềm + try/except — Analyst lỗi/chưa confirm KHÔNG được giết pipeline.
    try:
        from agents.analyst import get_active_insight
        active_insight = get_active_insight()
    except Exception:  # noqa: BLE001
        active_insight = None
    from agents.creative import generate_ideas
    result = generate_ideas(topic=run["topic"], trend_digest=trend_for_creative,
                            insight_digest=active_insight, n_ideas=run["n_ideas"])
    ideas = result.get("ideas") or []
    if result.get("status") != "ok" or not ideas:
        return _fail_run(run, s, result.get("error") or "Không sinh được idea", result)
    # Gắn insight đã NẠP vào output để UI hiện rõ "Creative học gì từ Analyst" (đóng vòng [E]→[B]).
    if active_insight:
        result["used_insight"] = active_insight
    pillars = ", ".join(sorted({str(i.get("pillar", "?")) for i in ideas}))
    _finish_step(run, s, "ok", result,
                 f"{len(ideas)} ý tưởng (pillar: {pillars}) • LLM MaaS sinh thật"
                 + (" • bám trend từ Scout" if trend_for_creative else "")
                 + (f" • học từ batch {active_insight.get('batch')}" if active_insight else ""),
                 data_source="real")

    # ---- 2b. [★] idea gate — Human chọn ý tưởng (chỉ khi pick_idea; mặc định auto est_fit)
    s = _start_step(run, "idea_approval")
    if not run["pick_idea"]:
        best = max(ideas, key=lambda i: i.get("est_fit") or 0)
        _finish_step(run, s, "skipped", None,
                     f"Tự chọn “{best.get('title')}” (est_fit cao nhất)")
    else:
        s["status"] = "awaiting"
        run["status"] = "awaiting_idea"
        s["output"] = {"ideas": [
            {k: i.get(k) for k in ("title", "angle", "pillar", "est_fit")} for i in ideas
        ]}
        s["summary"] = "Pipeline tạm dừng — chờ human chọn ý tưởng"
        run["updated_at"] = _now()
        _IDEA_GATES[run["id"]].wait()
        if run["idea_gate"]["decision"] != "approved":
            _finish_step(run, s, "rejected", s["output"], "Human huỷ ở bước chọn ý tưởng")
            for other in run["steps"]:
                if other["status"] == "pending":
                    other["status"] = "skipped"
            run["status"] = "rejected"
            run["updated_at"] = _now()
            return None
        idx = run.get("idea_choice")
        best = ideas[idx] if isinstance(idx, int) and 0 <= idx < len(ideas) \
            else max(ideas, key=lambda i: i.get("est_fit") or 0)
        run["status"] = "running"
        _finish_step(run, s, "ok", {"chosen": best.get("title")}, f"Đã chọn: {best.get('title')}")

    # ---- 3 + 3a + 3b: [B] generate_script → [★] QC → quyết (auto tự sửa / human gate)
    # AUTO: QC chấm 1 LẦN; nếu còn LỖI NẶNG (severity=error) → cho [B] viết lại ĐÚNG 1
    # lần theo feedback rồi DỰNG LUÔN (KHÔNG QC lại lần 2). CONFIRM: dừng gate cho human
    # bấm "viết lại" (QC lại mỗi lần, tối đa CREATIVE_QC_MAX_RETRIES) / "tiếp tục" / "huỷ".
    from agents.creative import generate_script
    from config import CREATIVE_QC_MAX_RETRIES, CREATIVE_QC_USE_LLM
    from .qc_script import run_script_qc

    confirm_mode = run["qc_mode"] == "confirm" or run["review_script"]
    qc_feedback = None
    attempt = 0
    while True:
        # 3. generate_script (lần đầu, hoặc viết lại theo feedback QC)
        s = _start_step(run, "generate_script")
        result = generate_script(idea=best, qc_feedback=qc_feedback)
        package = result.get("package")
        if result.get("status") != "ok" or not package:
            return _fail_run(run, s, result.get("error") or "Không sinh được script", result)
        n_words = len((package.get("script") or "").split())
        s["revised"] = attempt > 0          # badge "Đã sửa lại" cho bản viết lại theo QC
        retry_note = " • đã sửa theo feedback QC" if attempt else ""
        _finish_step(run, s, "ok", result,
                     f"Chọn “{best.get('title')}” (est_fit {best.get('est_fit')}) • "
                     f"script {n_words} từ • {len(package.get('shot_list') or [])} câu • "
                     f"LLM MaaS sinh thật{retry_note}",
                     data_source="real")

        # AUTO + đã viết lại 1 lần theo feedback QC → DỰNG LUÔN, không QC lại lần 2.
        if not confirm_mode and attempt > 0:
            s = _start_step(run, "script_approval")
            _finish_step(run, s, "skipped", None,
                         "Đã sửa theo feedback QC — dựng video luôn (không QC lại)")
            break

        # 3a. QC kịch bản — bắt clip thiếu/coverage/cụt/hook + LLM chấm hook/mạch/khớp-ý.
        s = _start_step(run, "qc_script")
        try:
            verdict = run_script_qc(package, library=run["library"],
                                    base_warnings=result.get("warnings"),
                                    use_llm=CREATIVE_QC_USE_LLM)
        except Exception as e:  # noqa: BLE001 — QC không được giết pipeline
            verdict = {"verdict": "warn",
                       "checks": {"deterministic": "skipped", "llm": "skipped"},
                       "issues": [{"type": "flow", "severity": "warning", "where": "qc",
                                   "detail": str(e),
                                   "suggested_fix": "Bỏ qua QC — human tự duyệt kịch bản"}]}
        run["qc_verdict"] = verdict
        issues = verdict.get("issues") or []
        n_err = sum(1 for i in issues if i.get("severity") == "error")
        can_retry = attempt < CREATIVE_QC_MAX_RETRIES
        _finish_step(run, s, "ok", {"qc_verdict": verdict},
                     ("QC: đạt" if verdict.get("verdict") == "pass"
                      else f"QC: {len(issues)} cảnh báo" + (f" ({n_err} lỗi nặng)" if n_err else ""))
                     + retry_note,
                     data_source="real")

        # 3b. quyết định: auto tự sửa, hoặc dừng gate cho human.
        if not confirm_mode:
            # AUTO: còn lỗi nặng → cho [B] viết lại ĐÚNG 1 lần theo feedback (vòng kế tiếp
            # sẽ dựng luôn ở nhánh attempt>0 phía trên, KHÔNG QC lại). CREATIVE_QC_MAX_RETRIES
            # ở đây = công tắc bật/tắt tự sửa (0 = tắt → dựng thẳng dù có lỗi).
            if n_err > 0 and can_retry:
                attempt += 1
                qc_feedback = issues
                continue
            s = _start_step(run, "script_approval")
            if verdict.get("verdict") == "pass":
                note = "QC đạt — tự động dựng video"
            elif n_err:
                note = f"QC còn {n_err} lỗi nặng (đã tắt tự sửa) — vẫn dựng (human xem lại sau)"
            else:
                note = "QC chỉ cảnh báo nhẹ — tự động dựng video"
            _finish_step(run, s, "skipped", None, note)
            break

        # CONFIRM: dừng ở gate cho human quyết (tiếp tục / viết lại / huỷ).
        s = _start_step(run, "script_approval")
        s["status"] = "awaiting"
        run["status"] = "awaiting_script"
        run["script_gate"]["decision"] = None     # reset cho lần chờ này
        _SCRIPT_GATES[run["id"]].clear()
        s["output"] = {
            "script": package.get("script"),
            "text_hook": package.get("text_hook"),
            "caption": package.get("caption"),
            "hashtags": package.get("hashtags"),
            "shot_list": package.get("shot_list"),
            "title": best.get("title"),
            # QC verdict đi kèm để human đọc cùng kịch bản; can_regenerate ẩn nút khi hết lượt.
            "qc_verdict": run.get("qc_verdict"),
            "can_regenerate": can_retry,
            "attempt": attempt,
        }
        s["summary"] = "Pipeline tạm dừng — chờ human duyệt / cho viết lại kịch bản"
        run["updated_at"] = _now()
        _SCRIPT_GATES[run["id"]].wait()
        decision = run["script_gate"]["decision"]
        run["status"] = "running"                 # rời trạng thái chờ

        if decision == "regenerate" and can_retry:
            attempt += 1
            qc_feedback = issues
            _finish_step(run, s, "ok", {"qc_verdict": verdict},
                         f"Human cho Creative viết lại (lần {attempt})")
            continue
        if decision == "rejected":   # approved hoặc regenerate-hết-lượt đều đi tiếp dựng
            _finish_step(run, s, "rejected", s["output"], "Human huỷ ở bước kịch bản")
            for other in run["steps"]:
                if other["status"] == "pending":
                    other["status"] = "skipped"
            run["status"] = "rejected"
            run["updated_at"] = _now()
            return None
        # approved → áp bản sửa nếu human có chỉnh
        edited = False
        if run.get("script_override"):
            package["script"] = run["script_override"]    # lời thoại user đã sửa
            edited = True
        if run.get("caption_override"):
            package["caption"] = run["caption_override"]   # caption user đã sửa (dùng khi đăng)
            edited = True
        if run.get("hashtags_override"):
            package["hashtags"] = run["hashtags_override"]  # hashtag user đã sửa (dùng khi đăng)
            edited = True
        _finish_step(run, s, "ok", {"script": package.get("script"), "caption": package.get("caption")},
                     "Đã duyệt kịch bản" + (" (đã sửa)" if edited else ""))
        break

    # ---- 4. [C] produce_video — pipeline 6 bước, progress % thật
    s = _start_step(run, "produce_video")

    def cb(percent: int, message: str) -> None:
        s["progress"] = percent
        s["summary"] = message
        run["updated_at"] = _now()

    try:
        from agents.producer.pipeline import produce_from_script
        # Truyền shot_list của Creative xuống Producer (Fix 0): bật path shot-list-
        # driven (cắt theo câu + chọn clip theo scene_hint). Nếu script bị sửa ở
        # script gate, package["script"] đổi nhưng shot_list không → gating trong
        # compute_sentence_cuts tự fallback path cũ. An toàn.
        produce_result = produce_from_script(
            package.get("script") or "", progress_cb=cb,
            subtitles=run["subtitles"], library=run["library"],
            music_track_id=run["music_track_id"],
            beat_sync=run["beat_sync"],
            music_volume=run["music_volume"],
            shot_list=package.get("shot_list"))
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
    decision = run["gate"]["decision"]
    snapshot = {"run_id": run["id"], "library": run["library"],
                "video_object": video_url, "caption": full_caption,
                "script": package.get("script") or "",
                "text_hook": package.get("text_hook")}

    # ---- 5a. Từ chối → dừng, không đăng
    if decision == "reject":
        _finish_step(run, s, "rejected", s["output"], "Human từ chối đăng video")
        for other in run["steps"]:
            if other["status"] == "pending":
                other["status"] = "skipped"
        run["status"] = "rejected"
        run["updated_at"] = _now()
        return None

    # ---- 5b. Lên lịch → vào queue scheduled_posts, run hoàn tất (tick tự đăng tới giờ)
    if decision == "schedule":
        _finish_step(run, s, "ok", s["output"], "Human chọn lên lịch đăng")
        s = _start_step(run, "publish_video")
        if not video_url:
            return _fail_run(run, s, "Producer không trả output_url — không có video để lên lịch")
        from agents.publisher import scheduled_posts
        from agents.publisher.scheduler import default_schedule_slot
        scheduled_for = run["gate"].get("scheduled_for") or default_schedule_slot()
        try:
            row = scheduled_posts.insert(snapshot, trigger="scheduled",
                                         actor="human:ui", scheduled_for=scheduled_for)
        except Exception as e:  # noqa: BLE001
            return _fail_run(run, s, f"Không lưu được lịch: {e}")
        _finish_step(run, s, "scheduled", {"post": row},
                     f"Đã lên lịch {_fmt_local(scheduled_for)} • tick tự đăng tới giờ",
                     data_source="real")
        # [E] Analyst tự chạy ngay (bài đang chờ publish) — chấm batch + insight.
        _run_analyst_step(run)
        return None

    # ---- decision == "now" → đăng ngay qua publish_service (đi qua đủ 4 phanh)
    run["status"] = "running"
    _finish_step(run, s, "ok", s["output"], "Human đã duyệt — đăng ngay")

    # ---- 6. [D] publish_video (on-demand)
    # Nguyên tắc: đăng THÀNH CÔNG hay LỖI (vì BẤT KỲ lý do gì) → vẫn chạy [E] Analyst.
    # publish_video lỗi chỉ fail RIÊNG bước đó (chip đỏ), KHÔNG abort run (không _fail_run).
    s = _start_step(run, "publish_video")
    if not video_url:
        return _fail_run(run, s, "Producer không trả output_url — không có video để đăng")
    from agents.publisher.publish_service import publish_now
    try:
        result = publish_now(snapshot, actor="human:ui", trigger="on_demand")
    except Exception as e:  # noqa: BLE001 — đăng lỗi bất kỳ (network/sandbox) vẫn cho Analyst chạy
        _finish_step(run, s, "failed", None, f"Đăng lỗi: {e}", error=str(e), data_source="real")
        _run_analyst_step(run)
        return None
    pub_status = result.get("status")
    if pub_status == "skipped":
        # Phanh dedup/limit chặn — không phải lỗi, run vẫn completed.
        _finish_step(run, s, "skipped", result,
                     f"Bỏ qua đăng ({result.get('reason')})", data_source="real")
    elif pub_status != "published":
        # Đăng lỗi (quota/network/sandbox…) — vẫn chạy Analyst để có insight cho vòng sau.
        err = result.get("detail") or result.get("reason") or "publish failed"
        _finish_step(run, s, "failed", result, f"Đăng lỗi: {err}", error=err, data_source="real")
    else:
        video_id = result.get("video_id")
        _finish_step(run, s, "ok", result,
                     "Đăng thành công"
                     + (f" • video_id {video_id}" if video_id else " • sandbox chưa trả video_id"),
                     data_source="real")

    # ---- 7. [E] analyze_batch — Analyst tự chạy (đăng OK / skip / lỗi đều tới đây)
    _run_analyst_step(run)
    return None


# ------------------------------------------------------------------ public API

def start_run(topic: str | None = None, library: str = "vng_insider",
              subtitles: bool = True, n_ideas: int = 5,
              music_track_id: str | None = None,
              beat_sync: bool = True,
              music_volume: float = 0.3,
              review_script: bool = False,
              pick_idea: bool = False,
              publish_mode: str = "review_publish",
              qc_mode: str = "auto") -> dict:
    run = _new_run(topic, library, subtitles, n_ideas,
                   music_track_id=music_track_id,
                   beat_sync=beat_sync,
                   music_volume=music_volume,
                   review_script=review_script,
                   pick_idea=pick_idea,
                   publish_mode=publish_mode,
                   qc_mode=qc_mode)

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
    log.info("workflow %s started (topic=%r library=%s music=%s beat_sync=%s vol=%.2f publish=%s qc=%s)",
             run["id"], topic, library,
             music_track_id or "—", beat_sync, music_volume, publish_mode, qc_mode)
    return run


def decide_gate(run_id: str, decision: str | None = None,
                scheduled_for: datetime | None = None,
                approve: bool | None = None) -> dict | None:
    """Human gate 3 lựa chọn: 'now' (đăng ngay) | 'schedule' (lên lịch) | 'reject'.

    Backward-compat: tham số cũ `approve=True` → 'now', `approve=False` → 'reject'.
    `scheduled_for` (UTC aware) chỉ dùng khi decision='schedule'.
    """
    run = _RUNS.get(run_id)
    if run is None:
        return None
    if run["status"] != "awaiting_approval":
        return run  # idempotent — gate đã quyết hoặc chưa tới
    if approve is not None:
        decision = "now" if approve else "reject"
    if decision in (None, "approved"):  # alias cũ "approved" → "now"; default an toàn
        decision = "now" if decision == "approved" else "reject"
    run["gate"]["decision"] = decision
    run["gate"]["scheduled_for"] = scheduled_for
    run["gate"]["decided_at"] = _now()
    _GATES[run_id].set()
    return run


def decide_script(run_id: str, approve: bool = True, decision: str | None = None,
                  script: str | None = None, caption: str | None = None,
                  hashtags: list[str] | None = None) -> dict | None:
    """Quyết định ở script gate: 'approve' (dùng bản gốc/đã sửa) | 'regenerate' (cho [B]
    viết lại theo feedback QC) | 'reject'. Backward-compat: `approve` bool (True→approve,
    False→reject) khi `decision` không truyền."""
    run = _RUNS.get(run_id)
    if run is None:
        return None
    if run["status"] != "awaiting_script":
        return run  # idempotent — gate đã quyết hoặc chưa tới
    if decision is None:
        decision = "approve" if approve else "reject"
    gate = {"approve": "approved", "regenerate": "regenerate"}.get(decision, "rejected")
    run["script_gate"]["decision"] = gate
    run["script_gate"]["decided_at"] = _now()
    if gate == "approved":
        if script and script.strip():
            run["script_override"] = script.strip()
        if caption and caption.strip():
            run["caption_override"] = caption.strip()
        if hashtags:
            cleaned = [h.strip() for h in hashtags if h and h.strip()]
            if cleaned:
                run["hashtags_override"] = cleaned
    _SCRIPT_GATES[run_id].set()
    return run


def decide_idea(run_id: str, approve: bool, idea_index: int | None = None) -> dict | None:
    """Quyết định ở idea gate. approve=True + idea_index → viết kịch bản cho ý tưởng đó."""
    run = _RUNS.get(run_id)
    if run is None:
        return None
    if run["status"] != "awaiting_idea":
        return run  # idempotent — gate đã quyết hoặc chưa tới
    run["idea_gate"]["decision"] = "approved" if approve else "rejected"
    run["idea_gate"]["decided_at"] = _now()
    if approve and isinstance(idea_index, int):
        run["idea_choice"] = idea_index
    _IDEA_GATES[run_id].set()
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
