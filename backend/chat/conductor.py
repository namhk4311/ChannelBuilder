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

from config import AI_PLATFORM_API_KEY, AI_PLATFORM_BASE_URL, CHAT_MODEL

from . import store
from .prompts import SYSTEM_CONDUCTOR

log = logging.getLogger(__name__)

# Chỉ gửi K message gần nhất cho LLM (chống phình token khi hội thoại dài). DB +
# UI vẫn giữ full; spec re-inject mỗi lượt nên cắt chatter cũ không mất quyết định.
_LLM_HISTORY_WINDOW = 24

GREETING = (
    "Chào bạn 👋 Mình là Đạo diễn AI của VNG Insider. "
    "Bạn muốn làm video TikTok về chủ đề gì? "
    "(vd: một ngày ở canteen VNG, góc học tập ở campus, phỏng vấn intern…)"
)

ALLOWED_FIELDS = {
    "topic", "library", "n_ideas", "subtitles",
    "music_track_id", "beat_sync", "music_volume",
    "publish_mode", "scheduled_for",
}


def _new_spec() -> dict:
    return {
        "topic": None, "library": None, "n_ideas": 5, "subtitles": True,
        "music_track_id": None, "beat_sync": True, "music_volume": 0.3,
        # Chế độ đăng: 'review_publish' (đăng ngay sau duyệt) | 'schedule' (lên lịch).
        # scheduled_for = ISO giờ hẹn khi schedule; None → dùng slot mặc định.
        "publish_mode": "review_publish", "scheduled_for": None,
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


def _options_for_field(field: Optional[str], libs: list[dict], music: list[dict]) -> list[dict]:
    if field == "library":
        return _usable_libs(libs)   # chỉ thư viện có clip
    if field == "music_track_id":
        return music
    return []


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


def _client():
    if not AI_PLATFORM_API_KEY:
        raise RuntimeError("AI_PLATFORM_API_KEY chưa set trong .env")
    from openai import OpenAI
    return OpenAI(base_url=AI_PLATFORM_BASE_URL, api_key=AI_PLATFORM_API_KEY,
                  timeout=READ_TIMEOUT)


def _context_block(spec: dict, libs: list[dict], music: list[dict]) -> str:
    """Snapshot động bơm vào cuối system prompt mỗi lượt — option hợp lệ + spec hiện tại."""
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
        f"Còn thiếu bắt buộc: {', '.join(missing) if missing else '(đủ — có thể xác nhận chạy)'}"
    )


def _llm_raw(spec: dict, messages: list[dict], libs: list[dict], music: list[dict]) -> str:
    """Gọi MaaS non-stream, trả raw text. Fallback content rỗng → reasoning_content."""
    system = SYSTEM_CONDUCTOR + _context_block(spec, libs, music)
    # Chỉ gửi K message gần nhất — chống phình token (DB vẫn giữ full).
    recent = messages[-_LLM_HISTORY_WINDOW:]
    payload = [{"role": "system", "content": system}, *recent]
    t0 = time.monotonic()
    log.info("conductor · POST %s · model=%s · %d msg", AI_PLATFORM_BASE_URL, CHAT_MODEL, len(messages))

    def _create(json_mode: bool):
        kwargs: dict = dict(
            model=CHAT_MODEL, messages=payload,
            max_tokens=8000,   # reasoning mode đốt token trước khi emit content
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


def _parse_envelope(raw: str) -> dict:
    """Bóc JSON envelope. Lỗi parse → fallback {action:chitchat, reply:<nguyên text>}."""
    text = (raw or "").strip()
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
    # Fallback — không vỡ trải nghiệm: nguyên text thành câu trả lời
    log.warning("conductor · không parse được envelope (%dc) — fallback chitchat", len(raw or ""))
    return {"reply": raw.strip() or "Mình chưa rõ ý bạn, nói lại giúp mình nhé.",
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

    # --- gọi LLM (không bao giờ để exception làm sập 1 lượt chat) -----------
    try:
        raw = _llm_raw(conv["spec"], conv["messages"], libs, music)
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

    ui_kind, ui_options = action, []

    # --- action=start_pipeline → validate rồi khởi động run thật -----------
    if action == "start_pipeline":
        lib = conv["spec"].get("library")
        usable = _usable_libs(libs)
        if not lib or lib not in {o["value"] for o in usable}:
            action, ui_kind, field = "present_choices", "choices", "library"
            ui_options = usable
            if not reply:
                reply = "Trước tiên cho mình biết bạn muốn dựng video trong thư viện clip nào nhé."
        else:
            try:
                from workflow.runner import start_run
                run = start_run(
                    topic=conv["spec"].get("topic"),
                    library=lib,
                    subtitles=bool(conv["spec"].get("subtitles", True)),
                    n_ideas=int(conv["spec"].get("n_ideas", 5)),
                    music_track_id=conv["spec"].get("music_track_id"),
                    beat_sync=bool(conv["spec"].get("beat_sync", True)),
                    music_volume=float(conv["spec"].get("music_volume", 0.3)),
                    review_script=True,   # tab Chat: dừng cho user duyệt/sửa kịch bản
                    publish_mode=conv["spec"].get("publish_mode", "review_publish"),
                )
                conv["run_id"] = run["id"]
                ui_kind = "running"
                log.info("conductor · %s start pipeline → %s", conv_id, run["id"])
                if not reply:
                    reply = ("Đang tạo video nha 🚀 Mình sẽ lên ý tưởng & viết kịch bản, rồi "
                             "đưa bạn đọc/chỉnh kịch bản trước khi dựng video nhé.")
            except Exception as e:  # noqa: BLE001
                log.exception("conductor · start_run lỗi")
                reply = reply or f"Không tạo được video: {e}"
                ui_kind = "chitchat"

    # --- action=decide_publish → human gate -------------------------------
    elif action == "decide_publish":
        approve = bool(env.get("approve", True))
        run_id = conv.get("run_id")
        if run_id:
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
            reply = "Đã ghi nhận quyết định của bạn." if run_id else "Chưa có video nào đang chờ duyệt."

    # --- present_choices: với library/music dùng options backend-derived
    # (chính xác + đã lọc thư viện rỗng); field khác mới fallback options của LLM.
    elif action == "present_choices":
        ui_kind = "choices"
        ui_options = _options_for_field(field, libs, music) or env.get("options") or []

    if not reply:
        reply = "Mình nghe đây 🙂"
    conv["messages"].append({"role": "assistant", "content": reply})
    first_user = next((m["content"] for m in conv["messages"] if m["role"] == "user"), "")
    _set_title(conv, first_user)
    store.save(conv)
    return _public(store.get(conv_id), ui={"kind": ui_kind, "field": field, "options": ui_options})


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
