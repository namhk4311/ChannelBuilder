# -*- coding: utf-8 -*-
"""Conductor — bộ não hội thoại điều khiển pipeline bằng ngôn ngữ tự nhiên.

Mỗi lượt user nhắn → gọi LLM (CHAT_MODEL) sinh 1 JSON envelope
{reply, action, field, options, spec_patch, approve, ready}. Backend bóc `action`
để THỰC THI (start_run / decide_gate) nhưng phần TRẢ LỜI luôn 100% do LLM sinh.

State lưu Postgres (bảng chat_sessions, migration 0004) qua module `store` —
survive reload trình duyệt + restart server. Lịch sử nhiều cuộc chat (sidebar).

Reuse:
  workflow.runner.start_run / decide_gate          — pipeline thật + human gate
  agents.producer.libraries.list_libraries         — option thư viện
  agents.producer.music.list_music                 — option nhạc nền
  OpenAI SDK (như pipeline.py) + reasoning fallback — gọi MaaS
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Optional

from json_repair import repair_json

from config import AI_PLATFORM_API_KEY, AI_PLATFORM_BASE_URL, CHAT_MAX_TOKENS, CHAT_MODEL

from . import store
from .prompts import SYSTEM_CONDUCTOR

log = logging.getLogger(__name__)

# Chỉ gửi K message gần nhất cho LLM (chống phình token khi hội thoại dài). DB +
# UI vẫn giữ full; spec re-inject mỗi lượt nên cắt chatter cũ không mất quyết định.
_LLM_HISTORY_WINDOW = 24

GREETING = (
    "Chào bạn 👋 Mình là Đạo diễn AI của VNG Insider. Bạn muốn làm loại video nào?\n\n"
    "🎬 **Vlog clip** — ghép clip có sẵn trong thư viện.\n"
    "📢 **Video thông tin** — đưa tin/thông báo/3 điều cần biết… (tự gen ảnh hoặc nền brand + banner động + nhạc)."
)

ALLOWED_FIELDS = {
    "topic", "library", "n_ideas", "subtitles",
    "music_track_id", "beat_sync", "music_volume",
    "publish_mode", "scheduled_for",
    # Video thông tin mode (content_type tự detect — KHÔNG là field)
    "mode", "event_text", "n_scenes", "visual_style", "brand",
}


def _new_spec() -> dict:
    return {
        "topic": None, "library": None, "n_ideas": 5, "subtitles": True,
        "music_track_id": None, "beat_sync": True, "music_volume": 0.3,
        # Chế độ đăng: 'review_publish' (đăng ngay sau duyệt) | 'schedule' (lên lịch).
        # scheduled_for = ISO giờ hẹn khi schedule; None → dùng slot mặc định.
        "publish_mode": "review_publish", "scheduled_for": None,
        # mode: 'vlog' (clip có sẵn) | 'info' (video thông tin).
        # event_text = đoạn mô tả nội dung; visual_style = 'image'|'solid' (chip);
        # brand = theme nền cho solid (chip); n_scenes co theo visual_style (image 1-3 / solid 3-5).
        "mode": None, "event_text": None, "n_scenes": None,
        "visual_style": None, "brand": None,
        # music_track_id=None mơ hồ (chưa hỏi vs chọn 'không nhạc') → cờ riêng để biết đã chọn.
        "music_decided": False,
        # publish_mode mặc định 'review_publish' (non-null) → cần cờ riêng để biết user ĐÃ chọn
        # qua chip chưa. schedule_time_decided: đã hỏi giờ hẹn (khi publish_mode='schedule') chưa.
        "publish_decided": False, "schedule_time_decided": False,
    }


# ----------------------------------------------------------------- options
def _libraries() -> list[dict]:
    """Danh sách thư viện rút gọn cho LLM + chips. Lỗi DB → list rỗng (không crash)."""
    try:
        from agents.producer.libraries import list_libraries
        return [
            {"value": r["name"],
             "label": r.get("label") or r["name"],
             "hint": f"{r.get('video_count', 0)} clip",
             "count": int(r.get("video_count", 0) or 0)}
            for r in list_libraries()
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · không tải được libraries: %s", e)
        return []


def _usable_libs(libs: list[dict]) -> list[dict]:
    """Chỉ thư viện CÓ clip — thư viện rỗng không dựng được nên không cho chọn."""
    return [l for l in libs if l.get("count", 0) > 0]


def _fmt_dur(sec: Any) -> str:
    if not sec:
        return "?:??"
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def _music() -> list[dict]:
    """Danh sách nhạc rút gọn. Luôn kèm option 'Không nhạc' (value=null)."""
    opts: list[dict] = [{"value": None, "label": "Không nhạc", "hint": "chỉ giọng đọc"}]
    try:
        from agents.producer.music import list_music
        for r in list_music():
            bpm = r.get("bpm")
            hint = f"{bpm:.0f} BPM · {_fmt_dur(r.get('duration_sec'))}" if bpm else _fmt_dur(r.get("duration_sec"))
            opts.append({"value": r["id"],
                         "label": r.get("label") or r.get("file") or r["id"],
                         "hint": hint})
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · không tải được music: %s", e)
    return opts


def _options_for_field(field: Optional[str], libs: list[dict], music: list[dict],
                       spec: Optional[dict] = None) -> list[dict]:
    if field == "library":
        return _usable_libs(libs)   # chỉ thư viện có clip
    if field == "music_track_id":
        return music
    if field == "mode":
        return [
            {"value": "vlog", "label": "🎬 Vlog clip", "hint": "ghép clip có sẵn trong thư viện"},
            {"value": "info", "label": "📢 Video thông tin", "hint": "đưa tin/thông báo (gen ảnh hoặc nền brand)"},
        ]
    if field == "visual_style":
        from agents.event_game.visual_styles import VISUAL_STYLES
        return [{"value": k, "label": v["label"], "hint": v["hint"]} for k, v in VISUAL_STYLES.items()]
    if field == "brand":
        from agents.event_game.visual_styles import BRAND_THEMES
        return [{"value": k, "label": v["label"], "hint": ""} for k, v in BRAND_THEMES.items()]
    if field == "n_scenes":
        from agents.event_game.visual_styles import scene_options
        opts = scene_options((spec or {}).get("visual_style"))
        return [{"value": n, "label": f"{n} cảnh",
                 "hint": "1 banner" if n == 1 else f"{n} cảnh + chuyển cảnh"} for n in opts]
    if field == "publish_mode":
        return [
            {"value": "review_publish", "label": "🚀 Đăng ngay", "hint": "duyệt xong đăng liền"},
            {"value": "schedule", "label": "🗓️ Lên lịch", "hint": "hẹn giờ, tự đăng tới giờ"},
        ]
    if field == "confirm":
        return [{"value": "run", "label": "🚀 Tạo video luôn"},
                {"value": "edit", "label": "✏️ Chỉnh thông tin"}]
    return []


# Các field có CHIP (options từ backend) — dùng để đảm bảo chip không bị mất.
_CHIP_FIELDS = {"mode", "visual_style", "brand", "n_scenes", "library", "music_track_id",
                "publish_mode", "confirm"}


def _publish_awaited(spec: dict) -> Optional[str]:
    """Đuôi gom CHUNG cho cả vlog & info: chế độ đăng (chip) → giờ hẹn (text, nếu lên lịch).
    Trả None khi đã chốt cách đăng (review_publish, hoặc schedule đã hỏi giờ)."""
    if not spec.get("publish_decided"):
        return "publish_mode"
    if spec.get("publish_mode") == "schedule" and not spec.get("schedule_time_decided"):
        return "scheduled_for"   # TEXT tự do — LLM parse "9h sáng mai" → ISO
    return None


def _awaited_field(spec: dict) -> Optional[str]:
    """Field đang thu thập (CHIP hoặc TEXT) suy ra từ spec — ghi spec deterministic + ép chip.
    Trả None khi đã thu đủ (→ bước confirm xử riêng theo trạng thái video)."""
    mode = spec.get("mode")
    if not mode:
        return "mode"
    if mode in ("info", "event_game"):
        if spec.get("visual_style") not in ("image", "solid"):
            return "visual_style"
        if spec.get("visual_style") == "solid" and not spec.get("brand"):
            return "brand"
        if len((spec.get("event_text") or "").strip()) < 20:
            return "event_text"   # TEXT tự do
        from agents.event_game.visual_styles import scene_options
        if spec.get("n_scenes") not in scene_options(spec.get("visual_style")):
            return "n_scenes"
        if not spec.get("music_decided"):
            return "music_track_id"
        return _publish_awaited(spec)   # chế độ đăng → giờ hẹn → xác nhận
    # vlog: topic (text, HỎI ĐẦU TIÊN) → library (chip bắt buộc) → nhạc → cách đăng → xác nhận.
    # topic phải gom TRƯỚC: scout/generate_ideas bám topic → ý tưởng đúng chủ đề.
    if len((spec.get("topic") or "").strip()) < 2:
        return "topic"   # TEXT tự do — không phải chip (LLM dẫn prose)
    if not spec.get("library"):
        return "library"
    if not spec.get("music_decided"):
        return "music_track_id"
    return _publish_awaited(spec)


def _next_chip_field(spec: dict) -> Optional[str]:
    """Bước CHIP kế tiếp (con của _awaited_field, bỏ field text) — để backend luôn hiện chip
    dù LLM trả 'ask'/chitchat/thiếu options."""
    f = _awaited_field(spec)
    return f if f in _CHIP_FIELDS else None


def _confirm_ready(conv: dict) -> bool:
    """Đã thu đủ thông tin + CHƯA có video đang chạy/chờ duyệt → hiện chip xác nhận (Tạo/Chỉnh)."""
    if _awaited_field(conv["spec"]) is not None:
        return False
    return _video_status(conv) in ("none", "done", "rejected", "failed")


def _match_option(text: str, opts: list[dict]):
    """Khớp câu trả lời user với 1 option (chip gửi LABEL). Trả (matched, value)."""
    t = (text or "").strip().lower()
    if not t:
        return (False, None)
    for o in opts:  # khớp chính xác label / value
        val = o.get("value")
        lbl = str(o.get("label") or "").strip().lower()
        if t == lbl or (val is not None and t == str(val).lower()):
            return (True, val)
    for o in opts:  # starter/label chứa thêm chữ → substring (label đủ đặc trưng)
        lbl = str(o.get("label") or "").strip().lower()
        if len(lbl) >= 4 and lbl in t:
            return (True, o.get("value"))
    return (False, None)


# Nhận diện khẳng định / phủ định tự do (cho bước xác nhận — không cần bấm chip).
_AFFIRM = ("oke", "ok", "okê", "okie", "okay", "ừ", "uh", "um", "có", "đồng ý", "dong y",
           "tạo", "tao ", "làm", "lam ", "chạy", "chay", "duyệt", "duyet", "yes", "go",
           "start", "được", "duoc", "ờ", "uki", "uhm", "chốt", "chot")
_NEGATE = ("không", "khong", "ko ", "đừng", "khoan", "chưa", "chua", "sửa", "sua", "chỉnh",
           "chinh", "đổi", "doi", "edit", "thêm", "them", "wait", "khác", "khac", "hủy", "huy", "đợi")


def _is_affirmative(text: str) -> bool:
    """Câu khẳng định 'làm đi' tự do — chặn nếu có ý phủ định/sửa/đổi."""
    t = f" {(text or '').strip().lower()} "
    if any(neg in t for neg in _NEGATE):
        return False
    return any(a in t for a in _AFFIRM)


def _wants_start(text: str, libs: list[dict], music: list[dict], spec: dict) -> bool:
    """User muốn TẠO ngay? Chip 'run' → True, chip 'edit' → False; còn lại xét khẳng định."""
    ok, val = _match_option(text, _options_for_field("confirm", libs, music, spec))
    if ok:
        return val == "run"
    return _is_affirmative(text)


def _apply_chip_answer(conv: dict, text: str, libs: list[dict], music: list[dict]) -> None:
    """Ghi spec DETERMINISTIC từ câu trả lời (theo field đang chờ) — KHÔNG phụ thuộc LLM nhớ
    echo spec_patch. Nhờ vậy mode/visual_style/brand/event_text/n_scenes luôn đúng → chip kế
    đúng + start_pipeline route đúng mode. Không khớp → để LLM hiểu."""
    spec = conv["spec"]
    f = _awaited_field(spec)
    if not f:
        return
    if f in _CHIP_FIELDS:
        ok, val = _match_option(text, _options_for_field(f, libs, music, spec))
        if ok:
            spec[f] = val
            if f == "music_track_id":
                spec["music_decided"] = True   # gồm cả 'Không nhạc' (val=None)
            elif f == "publish_mode":
                spec["publish_decided"] = True   # 'Đăng ngay' → khỏi hỏi giờ; 'Lên lịch' → hỏi giờ
            log.info("conductor · chip → spec[%s]=%r", f, val)
    elif f == "scheduled_for" and (text or "").strip():
        # Đang chờ giờ hẹn (publish_mode=schedule) → đánh dấu đã hỏi. ISO giờ cụ thể do LLM
        # parse vào spec_patch.scheduled_for (vd "9h sáng mai" → ISO); không parse được → slot mặc định.
        spec["schedule_time_decided"] = True
        log.info("conductor · text → schedule_time_decided (raw=%r)", text.strip()[:40])
    elif f == "topic" and len((text or "").strip()) >= 2:
        # Đang chờ chủ đề (vlog) → câu user CHÍNH LÀ topic (LLM hay quên ghi spec_patch.topic
        # → topic kẹt null, đẩy thẳng tới chip xác nhận mà chưa hỏi chủ đề bao giờ).
        spec["topic"] = text.strip()
        log.info("conductor · text → spec[topic] (%dc)", len(text.strip()))
    elif f == "event_text" and len((text or "").strip()) >= 20:
        # Đang chờ nội dung → đoạn text dài user gửi CHÍNH LÀ event_text (LLM hay quên ghi).
        spec["event_text"] = text.strip()
        log.info("conductor · text → spec[event_text] (%dc)", len(text.strip()))


def _resolve_slot(raw: Any):
    """ISO string giờ hẹn → datetime aware. Thiếu/sai → slot mặc định (9h mai, Asia/Saigon)."""
    from agents.publisher.scheduler import default_schedule_slot
    if isinstance(raw, str) and raw.strip():
        try:
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo
            from config import SCHEDULE_TZ
            dt = _dt.fromisoformat(raw.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:   # naive → hiểu là giờ địa phương Asia/Saigon
                dt = dt.replace(tzinfo=ZoneInfo(SCHEDULE_TZ))
            return dt
        except Exception:  # noqa: BLE001
            log.warning("conductor · scheduled_for không parse được (%r) — dùng slot mặc định", raw)
    return default_schedule_slot()


# ----------------------------------------------------------------- LLM call
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 120


_LLM_CLIENT = None  # singleton — tái dùng kết nối keep-alive giữa các lượt (đỡ bắt tay TLS lại)


def _client():
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        if not AI_PLATFORM_API_KEY:
            raise RuntimeError("AI_PLATFORM_API_KEY chưa set trong .env")
        from openai import OpenAI
        _LLM_CLIENT = OpenAI(base_url=AI_PLATFORM_BASE_URL, api_key=AI_PLATFORM_API_KEY,
                             timeout=READ_TIMEOUT)
    return _LLM_CLIENT


_VIDEO_STATUS_NOTE = {
    "none": "Chưa có video nào. 'ok/tạo đi/đồng ý' = xác nhận tạo → action=start_pipeline.",
    "running": "Đang dựng video — KHÔNG start_pipeline lần nữa, KHÔNG decide_publish (chưa tới bước duyệt).",
    "awaiting_approval": "Có video ĐANG CHỜ DUYỆT — 'đăng/duyệt/ok' → decide_publish approve=true; 'huỷ/không' → approve=false.",
    "done": "Video trước ĐÃ XONG. 'làm tiếp/chủ đề mới/ok tạo' = video MỚI → start_pipeline (run mới), KHÔNG decide_publish.",
    "rejected": "Video trước ĐÃ HUỶ. 'thử lại/chủ đề mới/ok' = video MỚI → start_pipeline (run mới), KHÔNG decide_publish.",
    "failed": "Video trước LỖI. 'thử lại/ok' = chạy lại video MỚI → start_pipeline (run mới).",
}


# ----------------------------------------------------------------- trend Q&A (Scout)
# Detector câu hỏi xu hướng → quyết khi nào nạp digest + trả bảng trend. Loại trừ câu gom
# spec ("mấy cảnh") để không bắt nhầm giữa luồng tạo video.
_TREND_KW = (
    "trend", "xu hướng", "xu huong", "format", "hook", "chủ đề", "chu de", "đang hot", "dang hot",
    "thịnh hành", "thinh hanh", "đang thịnh", "viral", "nên làm", "nen lam", "kiểu video", "kieu video",
    "độ dài", "do dai", "ngưỡng", "nguong", "retention", "scout", "đang chạy nhất", "ăn nhất",
)
_TREND_NEG = ("mấy cảnh", "may canh", "bao nhiêu cảnh", "số cảnh", "so canh")


def _is_trend_question(text: str) -> bool:
    """Câu hỏi về xu hướng/Scout (format/hook/chủ đề/độ dài/ngưỡng…)?"""
    t = f" {(text or '').strip().lower()} "
    if any(neg in t for neg in _TREND_NEG):
        return False
    return any(kw in t for kw in _TREND_KW)


def _run_trend_digest(conv: dict) -> Optional[dict]:
    """Digest trend từ run hiện tại — CHỈ run vlog mới có (scan_trends thật). Info → None."""
    rid = conv.get("run_id")
    if not rid:
        return None
    try:
        from workflow.runner import get_run
        run = get_run(rid)
    except Exception:  # noqa: BLE001
        run = None
    if not run:
        return None
    step = next((s for s in run.get("steps", []) if s.get("id") == "scan_trends"), None)
    out = (step or {}).get("output") or {}
    if out.get("digest"):
        return {"digest": out["digest"], "source": out.get("source") or "seed"}
    return None


def _get_trend_digest(conv: dict) -> Optional[dict]:
    """Ưu tiên digest run hiện tại (vlog); fallback cache đã quét trong cuộc chat."""
    return _run_trend_digest(conv) or conv.get("trend_digest")


def _fetch_trend_digest(conv: dict) -> Optional[dict]:
    """Quét NHANH Scout (dataset seed, tức thì — KHÔNG network/LLM) khi chưa có digest. Cache vào conv."""
    try:
        from agents.scout import run_scout
        res = run_scout(top_n=3, prefer_live=False)
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · run_scout (chat) lỗi: %s", e)
        return None
    if res.get("status") != "ok" or not res.get("digest"):
        return None
    payload = {"digest": res["digest"], "source": res.get("source") or "seed"}
    conv["trend_digest"] = payload
    log.info("conductor · quét trend (chat, seed) → %d video", res["digest"].get("so_video_quet", 0))
    return payload


def _trend_block(payload: Optional[dict]) -> str:
    """Format digest gọn để bơm vào system prompt — LLM trả lời câu hỏi trend DỰA TRÊN đây."""
    if not payload:
        return ""
    d = payload.get("digest") or {}
    top = d.get("top_format") or []
    top_line = ", ".join(f"{f.get('format')} ({f.get('so_video')} video)" for f in top[:3]) or "—"
    hooks = ", ".join(d.get("hook_pattern_thang") or []) or "—"
    topics = ", ".join(d.get("chu_de_hot") or []) or "—"
    nguong = (d.get("benchmark_khoi_tao") or {}).get("nguong")
    src = "TikTok thật (LLM)" if payload.get("source") == "llm" else "dataset mẫu"
    return (
        "\n\n# DỮ LIỆU TREND (Scout) — trả lời câu hỏi xu hướng DỰA TRÊN đây, KHÔNG bịa số:\n"
        f"- Nguồn: {src} • {d.get('so_video_quet', 0)} video • metric: {d.get('metric')}\n"
        f"- Format thắng: {top_line}\n"
        f"- Độ dài tối ưu: {d.get('do_dai_toi_uu') or '—'}\n"
        f"- Hook ăn khách: {hooks}\n"
        f"- Chủ đề hot: {topics}\n"
        f"- Ngưỡng ({d.get('metric')}): {nguong if nguong is not None else '—'}\n"
        f"- Format yếu cần tránh: {d.get('format_yeu') or '—'}"
    )


# ----------------------------------------------------------------- Analyst Q&A (hiệu suất video đã đăng)
# Detector câu hỏi hiệu suất/phân tích → nạp digest Analyst (insight + bảng video đã chấm).
_ANALYST_KW = (
    "performance", "hiệu suất", "hieu suat", "hiệu quả", "hieu qua", "kết quả", "ket qua",
    "phân tích", "phan tich", "analyst", "metric", "số liệu", "so lieu", "views", "lượt xem",
    "luot xem", "retention", "giữ chân", "giu chan", "ăn nhất", "an nhat", "thống kê", "thong ke",
    "scale", "insight", "đánh giá video", "danh gia video", "video đã đăng", "video da dang",
    "đã đăng thế nào", "da dang the nao", "video nào tốt", "video nao tot",
)


def _is_analyst_question(text: str) -> bool:
    """Câu hỏi về hiệu suất / phân tích video đã đăng (Analyst)?"""
    t = f" {(text or '').strip().lower()} "
    return any(kw in t for kw in _ANALYST_KW)


def _fetch_analyst_digest(conv: dict) -> Optional[dict]:
    """Chấm batch Analyst (thuần Python, tức thì — KHÔNG network/LLM) → insight + bảng video.
    Cache vào conv (best-effort; conv chỉ persist spec/messages nên lượt sau có thể nạp lại)."""
    cached = conv.get("analyst_digest")
    if cached:
        return cached
    try:
        from agents.analyst import run_analyst
        res = run_analyst()   # batch dummy mặc định
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · run_analyst (chat) lỗi: %s", e)
        return None
    if res.get("status") != "ok":
        return None
    payload = {
        "insight": res.get("insight_digest") or {},
        "videos": res.get("videos") or [],
        "batch": res.get("batch"),
        "scale_ids": res.get("scale_ids") or [],
    }
    conv["analyst_digest"] = payload
    log.info("conductor · chấm Analyst (chat) → %d video", len(payload["videos"]))
    return payload


def _analyst_block(payload: Optional[dict]) -> str:
    """Format digest Analyst gọn để bơm vào system prompt — LLM trả lời DỰA TRÊN đây, không bịa."""
    if not payload:
        return ""
    ins = payload.get("insight") or {}
    vids = payload.get("videos") or []
    n_scale = sum(1 for v in vids if v.get("label") == "SCALE")
    n_monitor = sum(1 for v in vids if v.get("label") == "MONITOR")
    n_kill = sum(1 for v in vids if v.get("label") == "KILL")
    thang = ins.get("thang") or {}
    thang_hook = ", ".join(thang.get("hook_type") or []) or "—"
    thua_hook = ", ".join((ins.get("thua") or {}).get("hook_type") or []) or "—"
    return (
        "\n\n# DỮ LIỆU ANALYST (hiệu suất video đã đăng) — trả lời câu hỏi hiệu suất DỰA TRÊN đây, KHÔNG bịa số:\n"
        f"- Lô: {payload.get('batch') or '—'} • {len(vids)} video • SCALE {n_scale} / MONITOR {n_monitor} / KILL {n_kill}\n"
        f"- Hook thắng: {thang_hook}\n"
        f"- Độ dài tốt: {thang.get('do_dai') or '—'}\n"
        f"- Hook thua (nên tránh): {thua_hook}\n"
        f"- Đề xuất vòng sau: {ins.get('de_xuat_vong_sau') or '—'}"
    )


# ----------------------------------------------------------------- Schedule Q&A (video chờ đăng)
# Detector câu hỏi về lịch đăng / video đang chờ → list bảng (giống tab Lịch đăng).
_SCHEDULE_KW = (
    "chờ đăng", "cho dang", "đang chờ", "dang cho", "lịch đăng", "lich dang", "sắp đăng",
    "sap dang", "hẹn đăng", "hen dang", "chưa đăng", "chua dang", "lịch hẹn", "lich hen",
    "queue", "hàng chờ", "hang cho", "pending", "scheduled", "đăng hôm nay", "dang hom nay",
)
_TODAY_KW = ("hôm nay", "hom nay", "today", "bữa nay", "bua nay", "ngày nay", "ngay nay")


def _is_schedule_question(text: str) -> bool:
    """Câu hỏi về lịch đăng / video đang chờ đăng?"""
    t = f" {(text or '').strip().lower()} "
    return any(kw in t for kw in _SCHEDULE_KW)


def _mentions_today(text: str) -> bool:
    t = f" {(text or '').strip().lower()} "
    return any(kw in t for kw in _TODAY_KW)


def _today_window_utc():
    """Mốc đầu/cuối ngày hôm nay theo SCHEDULE_TZ, quy về UTC (so với scheduled_for lưu UTC)."""
    from datetime import datetime as _dt, time as _time, timezone as _tz
    from zoneinfo import ZoneInfo
    from config import SCHEDULE_TZ
    tz = ZoneInfo(SCHEDULE_TZ)
    today = _dt.now(tz).date()
    start = _dt.combine(today, _time.min, tzinfo=tz).astimezone(_tz.utc)
    end = _dt.combine(today, _time.max, tzinfo=tz).astimezone(_tz.utc)
    return start, end


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return None


def _fetch_schedule(today_only: bool) -> Optional[dict]:
    """Liệt kê video đang chờ đăng (status pending/publishing). today_only → lọc hẹn trong hôm nay."""
    try:
        from agents.publisher import scheduled_posts
        rows = scheduled_posts.list_posts(limit=200)
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · list_posts (chat) lỗi: %s", e)
        return None
    pending = [r for r in rows if r.get("status") in ("pending", "publishing")]
    if today_only:
        from datetime import timezone as _tz
        start, end = _today_window_utc()

        def _in_today(r: dict) -> bool:
            sf = r.get("scheduled_for")
            if sf is None or isinstance(sf, str):
                return False
            if sf.tzinfo is None:
                sf = sf.replace(tzinfo=_tz.utc)
            return start <= sf <= end

        pending = [r for r in pending if _in_today(r)]
    posts = [{
        "id": r.get("id"),
        "caption": r.get("caption"),
        "library": r.get("library"),
        "trigger": r.get("trigger"),
        "status": r.get("status"),
        "scheduled_for": _iso(r.get("scheduled_for")),
        "published_at": _iso(r.get("published_at")),
    } for r in pending]
    return {"posts": posts, "today_only": today_only, "count": len(posts)}


def _schedule_block(payload: Optional[dict]) -> str:
    """Format danh sách lịch đăng gọn để bơm vào system prompt — LLM trả lời DỰA TRÊN đây."""
    if not payload:
        return ""
    posts = payload.get("posts") or []
    scope = "hẹn đăng hôm nay" if payload.get("today_only") else "đang chờ đăng"
    if not posts:
        return f"\n\n# DỮ LIỆU LỊCH ĐĂNG: Không có video nào {scope}."
    lines = "\n".join(
        f"- #{p['id']} • {p.get('scheduled_for') or '—'} • "
        f"{(p.get('caption') or '')[:50]} • {p.get('status')}"
        for p in posts[:10]
    )
    return (
        f"\n\n# DỮ LIỆU LỊCH ĐĂNG (video {scope}) — trả lời DỰA TRÊN đây, KHÔNG bịa:\n"
        f"- Phạm vi: {scope} • {len(posts)} video\n{lines}"
    )


def _context_block(spec: dict, libs: list[dict], music: list[dict], video_status: str = "none",
                   trend: Optional[dict] = None, analyst: Optional[dict] = None,
                   schedule: Optional[dict] = None) -> str:
    """Snapshot động bơm vào cuối system prompt mỗi lượt — option hợp lệ + spec + trạng thái video + trend."""
    lib_lines = "\n".join(f"- {o['value']} — \"{o['label']}\" ({o['hint']})" for o in libs) or "- (chưa có thư viện nào)"
    music_lines = "\n".join(
        f"- {('null' if o['value'] is None else o['value'])} — \"{o['label']}\" {('· ' + o['hint']) if o.get('hint') else ''}"
        for o in music
    )
    missing = [] if spec.get("library") else ["library (bắt buộc)"]
    return (
        "\n\n# NGỮ CẢNH HIỆN TẠI (cập nhật mỗi lượt)\n"
        "Thư viện khả dụng — chọn `library` đúng value bên dưới:\n"
        f"{lib_lines}\n\n"
        "Nhạc khả dụng — chọn `music_track_id` đúng value (null = không nhạc):\n"
        f"{music_lines}\n\n"
        f"Spec đã chốt: {json.dumps(spec, ensure_ascii=False)}\n"
        f"Còn thiếu bắt buộc: {', '.join(missing) if missing else '(đủ — có thể xác nhận chạy)'}\n"
        f"TRẠNG THÁI VIDEO: {video_status} → {_VIDEO_STATUS_NOTE.get(video_status, '')}"
        + _trend_block(trend) + _analyst_block(analyst) + _schedule_block(schedule)
    )


def _llm_raw(spec: dict, messages: list[dict], libs: list[dict], music: list[dict],
             video_status: str = "none", trend: Optional[dict] = None,
             analyst: Optional[dict] = None, schedule: Optional[dict] = None) -> str:
    """Gọi MaaS non-stream, trả raw text. Fallback content rỗng → reasoning_content."""
    system = SYSTEM_CONDUCTOR + _context_block(spec, libs, music, video_status, trend, analyst, schedule)
    # Chỉ gửi K message gần nhất — chống phình token (DB vẫn giữ full).
    recent = messages[-_LLM_HISTORY_WINDOW:]
    payload = [{"role": "system", "content": system}, *recent]
    t0 = time.monotonic()
    log.info("conductor · POST %s · model=%s · %d msg", AI_PLATFORM_BASE_URL, CHAT_MODEL, len(messages))

    def _create(json_mode: bool):
        kwargs: dict = dict(
            model=CHAT_MODEL, messages=payload,
            # Budget thấp = model suy luận "nghĩ ít" → trả lời nhanh hơn (đủ cho 1 JSON envelope).
            # Nếu bị cắt cụt thì có fallback reasoning_content + parse-fallback bên dưới.
            max_tokens=CHAT_MAX_TOKENS,
            temperature=0.3,
        )
        if json_mode:
            # Ép model trả JSON object — không có cái này minimax/deepseek hay
            # "quên" envelope và chat thẳng bằng text.
            kwargs["response_format"] = {"type": "json_object"}
        return _client().chat.completions.create(**kwargs)

    try:
        resp = _create(json_mode=True)
    except Exception as e:  # noqa: BLE001 — model không hỗ trợ json_object → retry không có
        if "response_format" in str(e).lower() or "json" in str(e).lower():
            log.warning("conductor · model từ chối response_format json_object (%s) — retry không có", e)
            resp = _create(json_mode=False)
        else:
            raise
    choice = resp.choices[0]
    raw = (choice.message.content or "").strip()
    if not raw:
        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        if reasoning.strip():
            log.warning("conductor · content rỗng — fallback reasoning_content (%dc)", len(reasoning))
            raw = reasoning.strip()
    log.info("conductor · done %.1fs · finish=%s · %dc",
             time.monotonic() - t0, choice.finish_reason, len(raw))
    return raw


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    """Bỏ khối <think>...</think> (suy luận của model reasoning như minimax) lọt vào output —
    tránh lộ 'rác' suy luận + dump field nội bộ ra reply. Cũng bỏ thẻ <think> mở chưa đóng
    (bị max_tokens cắt). JSON envelope nằm SAU </think> vẫn parse bình thường."""
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


def _parse_envelope(raw: str) -> dict:
    """Bóc JSON envelope. Lỗi parse → fallback {action:chitchat, reply:<nguyên text>}."""
    text = _strip_think((raw or "").strip())
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        blob = text[start:end + 1]
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            try:
                data = json.loads(repair_json(blob))
            except Exception:  # noqa: BLE001
                data = None
        if isinstance(data, dict) and data.get("reply"):
            return data
    # Fallback — không vỡ trải nghiệm: text ĐÃ strip <think> thành câu trả lời
    log.warning("conductor · không parse được envelope (%dc) — fallback chitchat", len(raw or ""))
    return {"reply": text or "Mình chưa rõ ý bạn, nói lại giúp mình nhé.",
            "action": "chitchat", "spec_patch": {}}


# ----------------------------------------------------------------- spec merge
def _merge_spec(spec: dict, patch: dict, libs: list[dict], music: list[dict]) -> None:
    """Merge spec_patch — clamp + guard chống LLM bịa library/music không có thật."""
    if not isinstance(patch, dict):
        return
    lib_values = {o["value"] for o in _usable_libs(libs)}  # chỉ chấp nhận thư viện có clip
    music_values = {o["value"] for o in music}  # gồm None (không nhạc)
    for k, v in patch.items():
        if k not in ALLOWED_FIELDS:
            continue
        if k == "library" and v not in lib_values:
            log.warning("conductor · bỏ library không hợp lệ/rỗng: %r", v)
            continue
        if k == "music_track_id" and v not in music_values:
            log.warning("conductor · bỏ music_track_id bịa: %r", v)
            continue
        if k == "music_volume":
            try:
                v = max(0.3, min(0.5, float(v)))
            except (TypeError, ValueError):
                continue
        if k == "n_ideas":
            try:
                v = max(1, min(10, int(v)))
            except (TypeError, ValueError):
                continue
        if k in ("subtitles", "beat_sync"):
            v = bool(v)
        if k == "publish_mode" and v not in ("review_publish", "schedule"):
            log.warning("conductor · bỏ publish_mode không hợp lệ: %r", v)
            continue
        if k == "scheduled_for" and v is not None and not isinstance(v, str):
            continue  # chỉ nhận ISO string; giờ không hợp lệ → fallback slot mặc định
        spec[k] = v


# ----------------------------------------------------------------- public API
def create_session() -> dict:
    conv_id = f"chat_{uuid.uuid4().hex[:12]}"   # uuid → không đụng PK qua restart
    conv = {
        "id": conv_id,
        "title": None,
        "messages": [{"role": "assistant", "content": GREETING}],
        "spec": _new_spec(),
        "run_id": None,
    }
    store.create(conv)
    log.info("conductor · session %s tạo mới", conv_id)
    return _public(store.get(conv_id), ui={"kind": "ask", "field": "topic", "options": []})


def get_session(conv_id: str) -> Optional[dict]:
    conv = store.get(conv_id)
    return _public(conv) if conv else None


def list_sessions() -> list[dict]:
    return store.list_recent()


def delete_session(conv_id: str) -> bool:
    return store.delete(conv_id)


# ---------- narrate: biến metadata từng step thành đoạn tự thoại dễ hiểu --------
def _narrate_scout(out: dict) -> Optional[str]:
    d = out.get("digest") or {}
    n = d.get("so_video_quet")
    top = (d.get("top_format") or [{}])[0].get("format")
    dur = d.get("do_dai_toi_uu")
    if dur:
        dur = dur.split("(")[0].strip()   # bỏ jargon "(retention_3s_pct...)"
    hooks = d.get("hook_pattern_thang") or []
    chu_de = d.get("chu_de_hot") or []
    if not n and not top:
        return None
    parts = [f"📊 Mình vừa lướt qua {n} video TikTok đang hot về mảng đi làm / công sở."
             if n else "📊 Mình vừa khảo sát các video TikTok đang hot."]
    obs = []
    if top:
        obs.append(f"kiểu video **{top}** đang giữ chân người xem tốt nhất")
    if dur:
        obs.append(f"nên làm dài tầm **{dur}**")
    if hooks:
        obs.append("mở đầu nên đánh kiểu " + " hoặc ".join(f"“{h}”" for h in hooks[:2]))
    if obs:
        parts.append("Mình nhận thấy: " + "; ".join(obs) + ".")
    if chu_de:
        parts.append("Chủ đề khán giả đang thích: " + ", ".join(chu_de) + ".")
    parts.append("Mình sẽ bám mấy điểm này để nghĩ ý tưởng cho bạn nha! ✨")
    return " ".join(parts)


def _narrate_ideas(out: dict) -> Optional[str]:
    ideas = out.get("ideas") or []
    if not ideas:
        return None
    return (f"💡 Mình đã nghĩ ra {len(ideas)} ý tưởng video. "
            "Bạn chọn 1 ý ở dưới để mình viết kịch bản nhé 👇")


def _narrate_script(out: dict) -> Optional[str]:
    pkg = out.get("package") or {}
    title = (pkg.get("idea") or {}).get("title")
    words = len((pkg.get("script") or "").split())
    t = f" “{title}”" if title else ""
    return (f"✍️ Mình đã chọn ý tưởng{t} và viết xong kịch bản (~{words} từ). "
            "Mời bạn đọc & chỉnh ngay bên dưới trước khi mình dựng video nhé 👇")


def _narrate_event_scout(out: dict) -> Optional[str]:
    insight = out.get("insight")
    return f"🔍 Mình đã phân tích nội dung — góc nhìn: {insight}" if insight else None


def _narrate_storyboard(out: dict) -> Optional[str]:
    scenes = out.get("scenes") or []
    if not scenes:
        return None
    flow = " → ".join(s.get("title") or "?" for s in scenes)
    return (f"📝 Mình đã dựng storyboard {len(scenes)} cảnh: **{flow}**. "
            "Mời bạn xem & chỉnh kịch bản / caption / hashtag bên dưới, rồi bấm dựng video nhé 👇")


def record_run_events(conv_id: str) -> Optional[dict]:
    """Ghi các mốc pipeline (video dựng xong / đăng xong / huỷ / lỗi) thành tin nhắn
    assistant trong hội thoại — lưu DB nên xem lại được. Idempotent: mỗi message gắn
    khoá `event` (vd 'produced:run_0007'), chỉ thêm mốc chưa có. FE gọi khi run đổi mốc."""
    conv = store.get(conv_id)
    if conv is None:
        return None
    rid = conv.get("run_id")
    if not rid:
        return _public(conv)
    try:
        from workflow.runner import get_run
        run = get_run(rid)
    except Exception as e:  # noqa: BLE001
        log.warning("conductor · get_run lỗi: %s", e)
        run = None
    if run is None:
        return _public(conv)  # run đã mất (restart) — messages cũ vẫn còn

    done = {m.get("event") for m in conv["messages"] if isinstance(m, dict)}
    steps = {s["id"]: s for s in run.get("steps", [])}
    added = False

    # narrate từng bước "phân tích" thành đoạn tự thoại (post live khi step xong)
    # narrate map theo mode: video thông tin chỉ narrate phân tích + storyboard
    # (scan_trends/generate_script dùng id chuẩn nhưng nội dung info → fn riêng)
    if (run.get("mode") or "vlog") in ("info", "event_game"):
        narrate_specs = (
            ("scan_trends", "ev_scout", _narrate_event_scout),
            ("generate_script", "ev_story", _narrate_storyboard),
        )
    else:
        narrate_specs = (
            ("scan_trends", "scout", _narrate_scout),
            ("generate_ideas", "ideas", _narrate_ideas),
            ("generate_script", "script", _narrate_script),
        )
    for sid, key, fn in narrate_specs:
        st = steps.get(sid) or {}
        if st.get("status") == "ok" and f"{key}:{rid}" not in done:
            msg = fn(st.get("output") or {})
            if msg:
                conv["messages"].append({"role": "assistant", "event": f"{key}:{rid}", "content": msg})
                added = True

    # produced — CHỈ post video thành tin nhắn SAU khi user đã quyết (duyệt/từ chối)
    # ở gate (human_approval.status ∈ ok/rejected). Lúc đang chờ (awaiting) thì block
    # confirm (ApprovalGate) đã hiện video → không post để tránh trùng.
    gate = steps.get("human_approval") or {}
    gate_out = gate.get("output") or {}
    video_url = gate_out.get("video_url")
    if (video_url and gate.get("status") in ("ok", "rejected")
            and f"produced:{rid}" not in done):
        dur = gate_out.get("duration_sec")
        dur_txt = f"(~{int(dur)}s) " if dur else ""
        conv["messages"].append({
            "role": "assistant", "event": f"produced:{rid}", "video_url": video_url,
            "content": f"🎬 Video đã dựng xong {dur_txt}:".replace("  ", " "),
        })
        added = True

    # published
    pub = steps.get("publish_video") or {}
    if pub.get("status") == "ok" and f"published:{rid}" not in done:
        pout = pub.get("output") or {}
        vid = pout.get("video_id")
        link = pout.get("share_url") or pout.get("url")
        tail = f" • video_id `{vid}`" if vid else (f" • {link}" if link else "")
        conv["messages"].append({
            "role": "assistant", "event": f"published:{rid}",
            "content": f"✅ Đã đăng TikTok thành công (SELF_ONLY){tail}.\n\n"
                       "Muốn làm video tiếp thì cứ nói chủ đề mới nha 👍",
        })
        added = True

    if run.get("status") == "rejected" and f"rejected:{rid}" not in done:
        conv["messages"].append({
            "role": "assistant", "event": f"rejected:{rid}",
            "content": "Đã huỷ — video không được đăng. Bạn muốn thử lại với chủ đề / kịch bản khác không?",
        })
        added = True

    if run.get("status") == "failed" and f"failed:{rid}" not in done:
        err = next((s.get("error") for s in run.get("steps", [])
                    if s.get("status") == "failed" and s.get("error")), None)
        conv["messages"].append({
            "role": "assistant", "event": f"failed:{rid}",
            "content": f"⚠️ Pipeline gặp lỗi{(': ' + err) if err else ''}. Bạn thử chạy lại nhé.",
        })
        added = True

    if added:
        store.save(conv)
        conv = store.get(conv_id)
    return _public(conv)


def _video_status(conv: dict) -> str:
    """Trạng thái video gần nhất của hội thoại → giúp conductor phân biệt decide_publish
    (chỉ khi đang chờ duyệt) vs start_pipeline (làm video mới khi video cũ đã xong/huỷ)."""
    rid = conv.get("run_id")
    if not rid:
        return "none"
    try:
        from workflow.runner import get_run
        run = get_run(rid)
    except Exception:  # noqa: BLE001
        run = None
    if not run:
        return "none"
    st = run.get("status")
    if st == "awaiting_approval":
        return "awaiting_approval"
    if st in ("running", "awaiting_idea", "awaiting_script"):
        return "running"
    if st in ("rejected", "failed"):
        return st
    return "done"


def _set_title(conv: dict, fallback_text: str) -> None:
    """Title cho sidebar — set 1 lần: ưu tiên topic, fallback câu user đầu tiên."""
    if conv.get("title"):
        return
    candidate = (conv["spec"].get("topic") or fallback_text or "").strip()
    if candidate:
        conv["title"] = candidate[:60]


def send_message(conv_id: str, text: str) -> Optional[dict]:
    conv = store.get(conv_id)
    if conv is None:
        return None
    text = (text or "").strip()
    if not text:
        return _public(conv)

    conv["messages"].append({"role": "user", "content": text})
    libs, music = _libraries(), _music()
    # Ghi spec từ chip vừa chọn TRƯỚC khi gọi LLM → spec luôn đúng (mode/visual_style/…),
    # LLM vẫn chạy để sinh reply + hiểu câu trả lời tự do.
    _apply_chip_answer(conv, text, libs, music)

    # Trend digest: ưu tiên run hiện tại (vlog); chưa có + user hỏi xu hướng → quét seed tức thì.
    # Bơm vào context để LLM trả lời câu hỏi trend grounded (không bịa).
    trend = _get_trend_digest(conv)
    if trend is None and _is_trend_question(text):
        trend = _fetch_trend_digest(conv)

    # Analyst (hiệu suất video đã đăng) + Schedule (video chờ đăng): nạp khi user hỏi → vừa bơm
    # vào context cho LLM trả lời grounded, vừa kèm payload để FE render bảng (insight / lịch).
    analyst = _fetch_analyst_digest(conv) if _is_analyst_question(text) else None
    schedule = _fetch_schedule(_mentions_today(text)) if _is_schedule_question(text) else None

    # --- gọi LLM (không bao giờ để exception làm sập 1 lượt chat) -----------
    try:
        raw = _llm_raw(conv["spec"], conv["messages"], libs, music, _video_status(conv),
                       trend, analyst, schedule)
        env = _parse_envelope(raw)
    except Exception as e:  # noqa: BLE001 — 429 / network / gateway
        log.exception("conductor · LLM lỗi: %s", e)
        reply = f"Xin lỗi, mình đang gặp sự cố khi gọi AI ({e}). Bạn thử lại giúp mình nhé."
        conv["messages"].append({"role": "assistant", "content": reply})
        _set_title(conv, text)
        store.save(conv)
        return _public(store.get(conv_id), ui={"kind": "chitchat", "field": None, "options": []})

    action = env.get("action") or "chitchat"
    reply = (env.get("reply") or "").strip()
    field = env.get("field")
    _merge_spec(conv["spec"], env.get("spec_patch") or {}, libs, music)

    # ÉP start_pipeline khi user xác nhận tạo — bằng CHIP "🚀 Tạo video luôn" HOẶC câu khẳng định
    # tự do ("oke", "tạo đi", "làm luôn"…). Bất kể LLM trả gì (prose/decide_publish) miễn là đã đủ
    # info + chưa có video đang chạy/chờ duyệt. (Phủ định/sửa → không ép, để LLM xử.)
    if action != "start_pipeline" and _confirm_ready(conv) and _wants_start(text, libs, music, conv["spec"]):
        action = "start_pipeline"
        log.info("conductor · %s ÉP start_pipeline (xác nhận: %r)", conv_id, (text or "")[:40])

    ui_kind, ui_options = action, []

    # --- action=start_pipeline → validate rồi khởi động run thật -----------
    if action == "start_pipeline":
        spec = conv["spec"]
        mode = spec.get("mode") or "vlog"
        usable = _usable_libs(libs)

        def _kick(run, msg):
            conv["run_id"] = run["id"]
            log.info("conductor · %s start pipeline (mode=%s) → %s", conv_id, mode, run["id"])
            return msg

        try:
            from workflow.runner import start_run
            if mode in ("info", "event_game"):
                # Video thông tin KHÔNG dùng clip → KHÔNG hỏi thư viện. library chỉ để
                # routing đăng → default thư viện đầu tiên (hoặc vng_insider).
                # Thu thập theo chip: visual_style → (brand nếu solid) → event_text → n_scenes.
                from agents.event_game.visual_styles import BRAND_THEMES, clamp_scenes, scene_options
                vstyle = spec.get("visual_style")
                if vstyle not in ("image", "solid"):
                    action, ui_kind, field = "present_choices", "choices", "visual_style"
                    ui_options = _options_for_field("visual_style", libs, music, spec)
                    if not reply:
                        reply = "Bạn muốn phong cách nền nào — 🖼️ Ảnh AI hay 🎨 Đơn sắc (theo brand)?"
                elif vstyle == "solid" and spec.get("brand") not in BRAND_THEMES:
                    action, ui_kind, field = "present_choices", "choices", "brand"
                    ui_options = _options_for_field("brand", libs, music, spec)
                    if not reply:
                        reply = "Chọn thương hiệu (màu nền) cho video nhé."
                elif len((spec.get("event_text") or "").strip()) < 20:
                    action, ui_kind, field = "ask", "ask", "event_text"
                    if not reply:
                        reply = "Gửi mình đoạn thông tin cần làm video nhé (nội dung tin/thông báo…)."
                elif spec.get("n_scenes") not in scene_options(vstyle):
                    action, ui_kind, field = "present_choices", "choices", "n_scenes"
                    ui_options = _options_for_field("n_scenes", libs, music, spec)
                    if not reply:
                        rng = scene_options(vstyle)
                        reply = f"Bạn muốn mấy cảnh? ({rng[0]}–{rng[-1]})"
                elif not spec.get("music_decided"):
                    # Khớp _awaited_field — đảm bảo hỏi nhạc trước khi chạy (kể cả LLM rogue-start sớm).
                    action, ui_kind, field = "present_choices", "choices", "music_track_id"
                    ui_options = _options_for_field("music_track_id", libs, music, spec)
                    if not reply:
                        reply = "Chọn nhạc nền nhé (hoặc không nhạc cũng được)."
                elif not spec.get("publish_decided"):
                    action, ui_kind, field = "present_choices", "choices", "publish_mode"
                    ui_options = _options_for_field("publish_mode", libs, music, spec)
                    if not reply:
                        reply = "Bạn muốn đăng video thế nào — đăng ngay sau duyệt hay lên lịch?"
                elif spec.get("publish_mode") == "schedule" and not spec.get("schedule_time_decided"):
                    action, ui_kind, field = "ask", "ask", "scheduled_for"
                    if not reply:
                        reply = "Bạn muốn hẹn đăng vào lúc nào? (vd “9h sáng mai”, “20h tối nay”)"
                else:
                    lib = spec.get("library") or (usable[0]["value"] if usable else "vng_insider")
                    run = start_run(
                        mode="info", event_text=spec.get("event_text"),
                        n_scenes=clamp_scenes(vstyle, spec.get("n_scenes")), library=lib,
                        visual_style=vstyle, brand=spec.get("brand") or "vng",
                        music_track_id=spec.get("music_track_id"),
                        music_volume=None,   # → produce dùng music_volume của preset (content_type)
                        review_script=True,  # dừng cho user duyệt/sửa kịch bản + caption + hashtag
                        publish_mode=spec.get("publish_mode", "review_publish"))
                    ui_kind = "running"
                    reply = _kick(run, reply or "Bắt đầu nha 🚀 Mình phân tích nội dung → dựng "
                                  "storyboard → render → ghép + lồng nhạc. Khoảng 1-2 phút nhé.")
            else:
                lib = spec.get("library")
                if len((spec.get("topic") or "").strip()) < 2:
                    # Chưa có chủ đề → hỏi topic trước (kể cả khi LLM rogue-start sớm).
                    action, ui_kind, field = "ask", "ask", "topic"
                    if not reply:
                        reply = "Bạn muốn làm video về chủ đề gì? (vd: một ngày ở canteen VNG, tour văn phòng…)"
                elif not lib or lib not in {o["value"] for o in usable}:
                    action, ui_kind, field = "present_choices", "choices", "library"
                    ui_options = usable
                    if not reply:
                        reply = "Cho mình biết dựng video trong thư viện clip nào nhé."
                elif not spec.get("music_decided"):
                    # Khớp _awaited_field — hỏi nhạc trước khi chạy (kể cả LLM rogue-start sớm).
                    action, ui_kind, field = "present_choices", "choices", "music_track_id"
                    ui_options = _options_for_field("music_track_id", libs, music, spec)
                    if not reply:
                        reply = "Thêm nhạc nền cho video không? (hoặc chọn không nhạc)"
                elif not spec.get("publish_decided"):
                    action, ui_kind, field = "present_choices", "choices", "publish_mode"
                    ui_options = _options_for_field("publish_mode", libs, music, spec)
                    if not reply:
                        reply = "Bạn muốn đăng video thế nào — đăng ngay sau duyệt hay lên lịch?"
                elif spec.get("publish_mode") == "schedule" and not spec.get("schedule_time_decided"):
                    action, ui_kind, field = "ask", "ask", "scheduled_for"
                    if not reply:
                        reply = "Bạn muốn hẹn đăng vào lúc nào? (vd “9h sáng mai”, “20h tối nay”)"
                else:
                    run = start_run(
                        topic=spec.get("topic"), library=lib,
                        subtitles=bool(spec.get("subtitles", True)),
                        n_ideas=int(spec.get("n_ideas", 5)),
                        music_track_id=spec.get("music_track_id"),
                        beat_sync=bool(spec.get("beat_sync", True)),
                        music_volume=float(spec.get("music_volume", 0.3)),
                        pick_idea=True, review_script=True,
                        publish_mode=spec.get("publish_mode", "review_publish"))
                    ui_kind = "running"
                    reply = _kick(run, reply or "Đang tạo video nha 🚀 Mình sẽ lên ý tưởng & viết "
                                  "kịch bản, rồi đưa bạn đọc/chỉnh trước khi dựng video nhé.")
        except Exception as e:  # noqa: BLE001
            log.exception("conductor · start_run lỗi")
            reply = reply or f"Không tạo được video: {e}"
            ui_kind = "chitchat"

    # --- action=decide_publish → human gate -------------------------------
    elif action == "decide_publish":
        approve = bool(env.get("approve", True))
        run_id = conv.get("run_id")
        # CHỈ quyết gate khi đang THỰC SỰ có video chờ duyệt. Nếu video đã xong/huỷ/lỗi,
        # 'ok/đồng ý' KHÔNG phải để đăng → hướng user cho chủ đề mới (LLM lượt sau start_pipeline).
        if run_id and _video_status(conv) == "awaiting_approval":
            try:
                from workflow.runner import decide_gate
                if not approve:
                    decide_gate(run_id, decision="reject")
                    log.info("conductor · %s gate REJECTED", conv_id)
                elif conv["spec"].get("publish_mode") == "schedule":
                    # Lên lịch — giờ hẹn từ spec (LLM bắt) hoặc slot mặc định.
                    slot = _resolve_slot(conv["spec"].get("scheduled_for"))
                    decide_gate(run_id, decision="schedule", scheduled_for=slot)
                    log.info("conductor · %s gate SCHEDULED @ %s", conv_id, slot.isoformat())
                else:
                    decide_gate(run_id, decision="now")
                    log.info("conductor · %s gate APPROVED (now)", conv_id)
            except Exception as e:  # noqa: BLE001
                log.warning("conductor · decide_gate lỗi: %s", e)
            ui_kind = "running"
            if not reply:
                reply = "Đã ghi nhận quyết định của bạn."
        else:
            ui_kind = "chitchat"
            if not reply:
                reply = "Hiện không có video nào đang chờ duyệt. Bạn cho mình chủ đề/nội dung để làm video mới nhé 👍"

    # --- present_choices: với library/music dùng options backend-derived
    # (chính xác + đã lọc thư viện rỗng); field khác mới fallback options của LLM.
    elif action == "present_choices":
        ui_kind = "choices"
        ui_options = _options_for_field(field, libs, music, conv["spec"]) or env.get("options") or []

    # --- thẻ trả lời chuyên biệt (grounded, KHÔNG ép chip): lịch đăng > hiệu suất > xu hướng.
    # Mỗi câu chỉ hiện 1 thẻ; ưu tiên schedule (cụ thể nhất) rồi analyst rồi trend. Chỉ hiện khi
    # đã nạp được data tương ứng; thiếu thì để LLM nói thật (chưa lấy được). Bắt cả khi LLM trả
    # action chuyên biệt LẪN khi LLM trả 'ask'/chitchat mà detector keyword khớp.
    trend_payload = analyst_payload = schedule_payload = None
    _CARD_ACTS = ("answer_trend", "answer_analyst", "answer_schedule")
    if schedule is not None and (action == "answer_schedule"
                                 or (action in ("chitchat", "ask") and _is_schedule_question(text))):
        ui_kind, field, schedule_payload = "schedule", None, schedule
    elif analyst is not None and (action == "answer_analyst"
                                  or (action in ("chitchat", "ask") and _is_analyst_question(text))):
        ui_kind, field, analyst_payload = "analyst", None, analyst
    elif trend is not None and (action == "answer_trend"
                                or (action in ("chitchat", "ask") and _is_trend_question(text))):
        ui_kind, field, trend_payload = "trend", None, trend

    # --- ĐẢM BẢO CHIP: backend tự đính chip cho bước chip kế tiếp dù LLM trả 'ask'/chitchat
    # /thiếu options/parse-fallback (mất field). KHÔNG ép khi đang start/decide hoặc đang trả
    # 1 thẻ chuyên biệt (trend/analyst/schedule). LLM vẫn sinh reply + hiểu câu trả lời tự do.
    if (action not in ("start_pipeline", "decide_publish", *_CARD_ACTS)
            and ui_kind not in ("trend", "analyst", "schedule")):
        nf = _next_chip_field(conv["spec"])
        chosen = nf or (field if field in _CHIP_FIELDS else None)
        if not chosen and _confirm_ready(conv):
            chosen = "confirm"   # đủ info, chưa chạy → chip Tạo/Chỉnh
        if chosen:
            opts = _options_for_field(chosen, libs, music, conv["spec"])
            if opts:
                field, ui_kind, ui_options = chosen, "choices", opts

    if not reply:
        reply = "Mình nghe đây 🙂"
    conv["messages"].append({"role": "assistant", "content": reply})
    first_user = next((m["content"] for m in conv["messages"] if m["role"] == "user"), "")
    _set_title(conv, first_user)
    store.save(conv)
    return _public(store.get(conv_id),
                   ui={"kind": ui_kind, "field": field, "options": ui_options,
                       "trend": trend_payload, "analyst": analyst_payload,
                       "schedule": schedule_payload})


# ----------------------------------------------------------------- serialize
def _public(conv: dict, ui: Optional[dict] = None) -> dict:
    return {
        "id": conv["id"],
        "title": conv.get("title"),
        "messages": conv["messages"],
        "spec": conv["spec"],
        "run_id": conv["run_id"],
        "ui": ui or {"kind": "ask", "field": None, "options": []},
        "updated_at": conv.get("updated_at"),
    }
