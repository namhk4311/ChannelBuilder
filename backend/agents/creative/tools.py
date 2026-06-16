# -*- coding: utf-8 -*-
"""
[B] Creative Brain — tools cho Orchestrator (VNG Insider / Claw-a-thon).

Usage:
    from agents.creative.tools import TOOL_DEFINITIONS, execute_tool
Tools KHÔNG BAO GIỜ raise — lỗi trả {"status": "failed", "error": "..."}.

Shot list match theo clip_tag (9 nhóm trong 00_INDEX.xlsx của Nghi),
KHÔNG theo file/thư mục. Kho clip đã bake sẵn trong prompts.CLIP_TAGS.

Env vars đọc qua root config.py (single source of truth):
    AI_PLATFORM_BASE_URL  — share endpoint với Producer
    AI_PLATFORM_API_KEY   — share API key với Producer
    CREATIVE_MODEL        — model riêng (minimax/minimax-m2.5 default)
"""

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from json_repair import repair_json

from config import AI_PLATFORM_API_KEY, AI_PLATFORM_BASE_URL, CREATIVE_MODEL

from .prompts import CLIP_TAGS, SINGLE_CLIP_TAGS, SYSTEM_IDEAS, SYSTEM_SCRIPT

log = logging.getLogger(__name__)

# ----------------------------- Pre-gen script cache -------------------------
# Khi router gọi /ideas xong, nó kick off generate_script song song cho TỪNG
# idea (5-10 task). Khi user pick + bấm "Viết kịch bản", /script tra cache:
#   • hit + done  → instant return
#   • hit + still running → await Future (giảm tổng wall-clock)
#   • miss        → fallback chạy thẳng như cũ
#
# Trade-off: user "không tiếc token" — burn 5-10x API call (chỉ pick 1) để
# đổi lấy zero-wait UX ở bước Viết kịch bản.

_PREGEN_EXECUTOR = ThreadPoolExecutor(max_workers=10, thread_name_prefix="creative-pregen")
_pregen_lock = threading.Lock()
_pregen_cache: dict = {}   # key: idea hash → {"future": Future, "ts": float}
_PREGEN_TTL_SEC = 600      # 10 phút


def _idea_key(idea: dict) -> str:
    """Stable hash cho 1 idea dict — order-insensitive."""
    blob = json.dumps(idea or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _evict_stale_pregen() -> None:
    """Drop entries > TTL. Caller phải hold _pregen_lock."""
    now = time.time()
    stale = [k for k, v in _pregen_cache.items() if now - v["ts"] > _PREGEN_TTL_SEC]
    for k in stale:
        _pregen_cache.pop(k, None)
    if stale:
        log.info("pregen · evicted %d stale entry (TTL %ds)", len(stale), _PREGEN_TTL_SEC)


def pregen_scripts(ideas: list, target_duration_sec: int = 48) -> int:
    """Fire-and-forget: spawn `_do_generate_script` cho mỗi idea song song.

    Trả về số task vừa enqueue (skip nếu đã có trong cache). Không block.
    """
    enqueued = 0
    with _pregen_lock:
        _evict_stale_pregen()
        for idea in ideas:
            if not isinstance(idea, dict):
                continue
            key = _idea_key(idea)
            if key in _pregen_cache:
                continue  # đã pre-gen rồi
            future = _PREGEN_EXECUTOR.submit(
                _do_generate_script, idea, None, target_duration_sec
            )
            _pregen_cache[key] = {"future": future, "ts": time.time()}
            enqueued += 1
            log.info("pregen · queued idea=%r (key=%s, cache=%d)",
                     (idea.get("title") or "?")[:60], key, len(_pregen_cache))
    log.info("pregen · %d task mới được enqueue (song song, max %d worker)",
             enqueued, _PREGEN_EXECUTOR._max_workers)
    return enqueued

# Alias internal — share MaaS endpoint+key với Producer
AGENTBASE_BASE_URL = (AI_PLATFORM_BASE_URL or "").rstrip("/")
AGENTBASE_API_KEY = AI_PLATFORM_API_KEY or ""

FIXED_HASHTAGS = ["#VNG", "#VNGCampus", "#Starter"]
MIN_DURATION, MAX_DURATION = 40, 55
MIN_WORDS, MAX_WORDS = 110, 140  # spec Nghi mục 4

# Guardrail mục 7 — từ cấm tuyệt đối + từ cần human review
BANNED_WORDS = ["điên", "khùng", "ngu ", "dốt", "đần", "dở hơi"]
REVIEW_WORDS = ["lương", "thưởng", "đãi ngộ", "triệu"]  # hứa hẹn chế độ cụ thể


# ---------------------------------------------------------------- LLM client

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 300   # đọc stream: timeout này là khoảng lặng giữa 2 chunk, không phải tổng thời gian


class RateLimitError(RuntimeError):
    """429 từ gateway — KHÔNG retry, đốt quota vô ích. Caller chờ window reset."""


def _chat(system: str, user: str, temperature: float = 0.85, max_tokens: int = 8000, model=None) -> str:
    """Gọi AgentBase MaaS (OpenAI-compatible /chat/completions, STREAMING). Trả raw text.

    Dùng stream=True vì response non-stream không gửi byte nào cho tới khi model
    sinh xong toàn bộ → prompt dài + model to rất dễ dính read timeout ở gateway.
    Stream nhận token liên tục nên connection không bao giờ idle lâu.

    max_tokens=8000 vì minimax/deepseek có reasoning mode đốt token cho
    `reasoning_content` trước khi emit `content` thật. Để 2000 thường bị cắt
    ngay khi đang "suy nghĩ" → content rỗng.

    Fallback: nếu `content` rỗng nhưng `reasoning_content` có text (model
    thinking quá lâu / model output JSON ngay trong reasoning), dùng reasoning
    làm raw để _extract_json kéo {...} ra.

    KHÔNG tự retry: 1 lần gọi = đúng 1 request lên gateway. Lỗi raise thẳng để
    Orchestrator tự quyết định gọi lại — đếm được chính xác số request đốt quota.
    """
    model = model or CREATIVE_MODEL          # caller có thể override (vd QC dùng model riêng)
    if not AGENTBASE_BASE_URL or not AGENTBASE_API_KEY:
        raise RuntimeError("Thiếu AGENTBASE_BASE_URL / AGENTBASE_API_KEY trong env")
    if not model:
        raise RuntimeError("Thiếu CREATIVE_MODEL / model trong env")

    sys_chars = len(system or "")
    user_chars = len(user or "")
    log.info("chat · POST %s · model=%s temp=%.2f sys=%dc user=%dc max=%d",
             AGENTBASE_BASE_URL, model, temperature,
             sys_chars, user_chars, max_tokens)
    t0 = time.monotonic()

    resp = requests.post(
        f"{AGENTBASE_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {AGENTBASE_API_KEY}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        },
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        stream=True,
    )
    if resp.status_code == 429:
        log.warning("chat · 429 rate limit từ MaaS — KHÔNG retry")
        raise RateLimitError(
            "429 — AI rate limit exceeded. KHÔNG retry (đốt quota vô ích). "
            "Chờ window reset, tăng limit cho key trên portal MaaS (Protect & Govern), "
            "hoặc đổi CREATIVE_MODEL."
        )
    resp.raise_for_status()
    # Route Gemini của MaaS trả Content-Type 'text/event-stream' KHÔNG kèm charset →
    # requests đoán ISO-8859-1, khiến iter_lines(decode_unicode=True) decode UTF-8 thành
    # Latin-1 (mojibake kiểu "Tá»ng thá»i lÆ°á»£ng"). Ép utf-8 cho mọi model
    # (minimax đã 'charset=utf-8' sẵn nên dòng này vô hại với nó).
    resp.encoding = "utf-8"
    log.info("chat · stream open (HTTP %d, TTFB %.1fs) — bắt đầu nhận token",
             resp.status_code, time.monotonic() - t0)

    content_chunks: list[str] = []
    reasoning_chunks: list[str] = []
    finish_reason: str | None = None
    n_deltas = 0
    last_log = time.monotonic()
    saw_unknown_keys: set[str] = set()

    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line or not raw_line.startswith("data:"):
            continue
        data = raw_line[5:].strip()
        if data == "[DONE]":
            break
        try:
            choice = json.loads(data)["choices"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        delta = choice.get("delta") or {}
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]

        c = delta.get("content")
        r = delta.get("reasoning_content")
        if c:
            content_chunks.append(c)
            n_deltas += 1
        if r:
            reasoning_chunks.append(r)
            n_deltas += 1
        if not c and not r:
            # Bắt key lạ (vd model dùng `text` / `message_content` / …) — chỉ log 1 lần
            for k in delta.keys():
                if k not in ("role", "content", "reasoning_content") and k not in saw_unknown_keys:
                    saw_unknown_keys.add(k)
                    log.warning("chat · delta có key không xử lý: %r (sample=%r)", k, delta[k] if isinstance(delta[k], str) else delta[k])

        # Heartbeat 5s — stream LLM dài 30-60s, không log thì user tưởng đứng
        now = time.monotonic()
        if now - last_log >= 5.0:
            log.info("chat · streaming … %d deltas · content=%dc · reasoning=%dc · t+%.1fs",
                     n_deltas,
                     sum(len(x) for x in content_chunks),
                     sum(len(x) for x in reasoning_chunks),
                     now - t0)
            last_log = now

    content = "".join(content_chunks)
    reasoning = "".join(reasoning_chunks)
    elapsed = time.monotonic() - t0

    # Ưu tiên content; fallback reasoning_content
    if content.strip():
        log.info("chat · done · %d deltas → content=%dc reasoning=%dc finish=%s in %.1fs",
                 n_deltas, len(content), len(reasoning), finish_reason, elapsed)
        return content

    if reasoning.strip():
        log.warning("chat · content RỖNG — fallback dùng reasoning_content (%dc, finish=%s, %.1fs)",
                    len(reasoning), finish_reason, elapsed)
        return reasoning

    # Cả 2 rỗng — chẩn đoán nguyên nhân
    hint = ""
    if finish_reason == "length":
        hint = (f" finish_reason=length → max_tokens={max_tokens} không đủ, "
                "model bị cắt khi đang reasoning. Tăng max_tokens hoặc đổi sang non-thinking model.")
    elif finish_reason == "content_filter":
        hint = " finish_reason=content_filter → MaaS đã chặn."
    elif finish_reason:
        hint = f" finish_reason={finish_reason}."
    log.error("chat · stream xong nhưng CẢ content lẫn reasoning đều rỗng (%.1fs).%s", elapsed, hint)
    raise RuntimeError(f"Stream trả về rỗng (finish={finish_reason}).{hint}")


def _extract_json(text: str) -> dict:
    """Parse JSON từ output LLM, chịu được code fence / text thừa."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM không trả JSON: {text[:200]}")
    blob = text[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # JSON vỡ vặt vặt (nháy kép không escape trong lời thoại tiếng Việt,
        # trailing comma...) — repair tại chỗ thay vì vứt response, đỡ đốt 1 request.
        return json.loads(repair_json(blob))


# ---------------------------------------------------------------- validation

def _validate_script(pkg: dict) -> list:
    """Check theo spec Nghi (5b ngân sách tag, mục 4 cấu trúc, mục 7 guardrail, 7b caption).
    Trả list warning; tự sửa các lỗi sửa được."""
    warnings = []

    # 1. clip_tag hợp lệ + ngân sách giây mỗi tag
    for line in pkg.get("script", []):
        n, tag, alt = line.get("line"), line.get("clip_tag"), line.get("alt_tag")
        dur = line.get("duration_sec", 0)
        if tag not in CLIP_TAGS:
            warnings.append(f"line {n}: clip_tag '{tag}' không nằm trong 9 tag của kho")
            continue
        if alt and alt not in CLIP_TAGS:
            warnings.append(f"line {n}: alt_tag '{alt}' không hợp lệ")
        if dur > CLIP_TAGS[tag]["budget_sec"] and not alt:
            warnings.append(
                f"line {n}: {dur}s > ngân sách {CLIP_TAGS[tag]['budget_sec']}s của tag '{tag}' mà không có alt_tag"
            )
        if tag in SINGLE_CLIP_TAGS and dur > CLIP_TAGS[tag]["budget_sec"]:
            warnings.append(f"line {n}: tag '{tag}' chỉ có 1 clip ({CLIP_TAGS[tag]['budget_sec']}s) — câu phải ngắn hơn hoặc có alt_tag")

    # 2. Tổng thời lượng 40-55s + số từ 110-140
    total = sum(l.get("duration_sec", 0) for l in pkg.get("script", []))
    pkg["total_duration_sec"] = total
    if not (MIN_DURATION <= total <= MAX_DURATION):
        warnings.append(f"total_duration_sec={total}, ngoài khoảng {MIN_DURATION}-{MAX_DURATION}")
    n_words = len(" ".join(l.get("voiceover", "") for l in pkg.get("script", [])).split())
    if not (MIN_WORDS - 10 <= n_words <= MAX_WORDS + 10):
        warnings.append(f"lời thoại {n_words} từ, lệch chuẩn {MIN_WORDS}-{MAX_WORDS} từ")

    # 3. Hashtag: cố định bắt buộc + tổng 3-6 thẻ
    tags = pkg.get("hashtags", [])
    for t in FIXED_HASHTAGS:
        if t not in tags:
            tags.append(t)
            warnings.append(f"tự thêm hashtag cố định {t}")
    if len(tags) > 6:
        warnings.append(f"{len(tags)} hashtag, spec gợi ý 3-6")
    pkg["hashtags"] = tags

    # 4. Caption không lặp y nguyên hook (7b)
    cap = (pkg.get("caption") or "").strip().lower()
    hook = (pkg.get("text_hook") or "").strip().lower()
    if cap and hook and hook in cap:
        warnings.append("caption lặp lại text_hook — spec 7b yêu cầu caption mở rộng ý khác")

    # 5. Guardrail từ ngữ (mục 7)
    full_text = (
        " ".join(l.get("voiceover", "") for l in pkg.get("script", []))
        + " " + pkg.get("caption", "") + " " + pkg.get("text_hook", "")
    ).lower()
    for w in BANNED_WORDS:
        if w in full_text:
            warnings.append(f"GUARDRAIL CẤM: phát hiện từ '{w.strip()}' — phải sửa")
    for w in REVIEW_WORDS:
        if w in full_text:
            warnings.append(f"GUARDRAIL: có từ '{w}' (nguy cơ hứa hẹn chế độ) — cần human review")

    return warnings


# TTS tiếng Việt đọc viết tắt "ck" thành "xê-ca" → ép về chữ đầy đủ "chồng" trước khi
# đưa Producer/TTS. Prompt đã cấm viết tắt nhưng LLM phi tất định nên vẫn cần net này.
# Chỉ thay token đứng riêng (ck / Ck / CK), KHÔNG đụng "ck" nằm trong từ khác (vd "track").
_CK_TOKEN_RE = re.compile(r"\bck\b", re.IGNORECASE)


def _normalize_ck(text: str) -> str:
    if not text:
        return text
    return _CK_TOKEN_RE.sub(lambda m: "Chồng" if m.group(0)[0].isupper() else "chồng", text)


def _script_to_text(lines: list) -> str:
    """script = nguyên văn lời thoại liền mạch (Producer tự phân line/duration/voice)."""
    return " ".join(l.get("voiceover", "").strip() for l in lines if l.get("voiceover"))


# ---------------------------------------------------------------- tools

def generate_ideas(topic=None, trend_digest=None, insight_digest=None, n_ideas=5):
    """Sinh n ý tưởng video từ trend [A] + insight [E] (+ chủ đề nếu human giao)."""
    t0 = time.monotonic()
    log.info("ideas · BẮT ĐẦU · topic=%r n=%d trend=%s insight=%s",
             topic, n_ideas, bool(trend_digest), bool(insight_digest))
    try:
        user_parts = [f"Sinh {n_ideas} ý tưởng video."]
        if topic:
            user_parts.append(f"Chủ đề được giao: {topic}")
        if trend_digest:
            user_parts.append("trend_digest từ Scout:\n" + json.dumps(trend_digest, ensure_ascii=False, indent=2))
        if insight_digest:
            user_parts.append("insight_digest từ Analyst:\n" + json.dumps(insight_digest, ensure_ascii=False, indent=2))
        if not trend_digest and not insight_digest:
            user_parts.append("(Chưa có trend/insight — dựa vào brand guide, kiến thức nền và kho clip.)")

        raw = _chat(SYSTEM_IDEAS, "\n\n".join(user_parts))
        log.info("ideas · parse JSON (%d chars raw)", len(raw))
        data = _extract_json(raw)
        ideas = data.get("ideas", [])
        if not ideas:
            log.warning("ideas · LLM không trả ý tưởng nào (raw=%r…)", raw[:200])
            return {"status": "failed", "error": "LLM không trả ý tưởng nào", "ideas": []}
        log.info("ideas · XONG · %d idea trong %.1fs", len(ideas), time.monotonic() - t0)
        return {"status": "ok", "error": None, "ideas": ideas}
    except Exception as e:
        log.exception("ideas · LỖI sau %.1fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "error": str(e), "ideas": []}


def generate_script(idea, insight_digest=None, target_duration_sec=48, qc_feedback=None):
    """Public entry: kiểm cache pregen TRƯỚC, fallback gọi trực tiếp.

    Khi router /ideas đã kick off pregen_scripts, cache sẽ có Future tương ứng.
    Tra theo idea hash (insight_digest=None bỏ qua trong key vì pregen không
    truyền insight — nếu user truyền insight thì coi như cache miss).

    `qc_feedback` (list issue QC của bản trước) → BỎ QUA cache (bản cache không có
    feedback) + gọi thẳng để [B] viết lại khắc phục lỗi (QC retry loop ở orchestrator).
    """
    # Pregen chỉ track (idea, target_duration_sec) — có insight/feedback thì miss
    if insight_digest is None and not qc_feedback:
        key = _idea_key(idea or {})
        with _pregen_lock:
            entry = _pregen_cache.get(key)
        if entry is not None:
            future = entry["future"]
            t0 = time.monotonic()
            log.info("script · cache HIT key=%s (pre-gen %.1fs ago, done=%s) — await",
                     key, time.time() - entry["ts"], future.done())
            try:
                result = future.result(timeout=180)
                log.info("script · cache return %.1fs (status=%s)",
                         time.monotonic() - t0, result.get("status"))
                return result
            except Exception as e:
                log.warning("script · pre-gen Future raise (%s) — fallback gọi thẳng", e)
                with _pregen_lock:
                    if _pregen_cache.get(key) is entry:
                        _pregen_cache.pop(key, None)
            # rơi xuống direct call

    return _do_generate_script(idea, insight_digest, target_duration_sec, qc_feedback)


def _build_qc_feedback_block(qc_feedback) -> str:
    """QC issues → chỉ dẫn sửa cho [B] (viết lại khắc phục). '' nếu rỗng."""
    fb = []
    for it in qc_feedback or []:
        if not isinstance(it, dict):
            continue
        fb.append(f"- [{it.get('severity', 'warning')}] {it.get('where', '')}: "
                  f"{it.get('detail', '')} → SỬA: {it.get('suggested_fix', '')}")
    if not fb:
        return ""
    return ("Bản kịch bản TRƯỚC bị các lỗi QC sau. Viết LẠI để khắc phục HẾT các lỗi này, "
            "giữ đúng tone + cấu trúc + ràng buộc thời lượng/số từ:\n" + "\n".join(fb))


def _do_generate_script(idea, insight_digest=None, target_duration_sec=48, qc_feedback=None):
    """Implementation thật — gọi MaaS + parse + validate. Không check cache."""
    t0 = time.monotonic()
    log.info("script · BẮT ĐẦU · idea=%r dur=%ds insight=%s qc_fb=%s thread=%s",
             (idea or {}).get("title", "?"), target_duration_sec,
             bool(insight_digest), len(qc_feedback or []), threading.current_thread().name)
    try:
        user_parts = [
            "Viết trọn gói kịch bản cho ý tưởng sau:",
            json.dumps(idea, ensure_ascii=False, indent=2),
            f"Thời lượng mục tiêu: ~{target_duration_sec}s (bắt buộc {MIN_DURATION}-{MAX_DURATION}s, "
            f"lời thoại {MIN_WORDS}-{MAX_WORDS} từ).",
        ]
        if insight_digest:
            user_parts.append("Insight từ kênh (ưu tiên áp dụng):\n" + json.dumps(insight_digest, ensure_ascii=False, indent=2))
        fb_block = _build_qc_feedback_block(qc_feedback)
        if fb_block:
            user_parts.append(fb_block)

        raw = _chat(SYSTEM_SCRIPT, "\n\n".join(user_parts))
        log.info("script · parse JSON (%d chars raw)", len(raw))
        pkg = _extract_json(raw)
        pkg["idea"] = idea
        # TTS guard: ép "ck" → "chồng" trong lời thoại + hook + caption (model đôi khi vẫn viết tắt)
        for line in pkg.get("script", []):
            if isinstance(line, dict) and line.get("voiceover"):
                line["voiceover"] = _normalize_ck(line["voiceover"])
        for fld in ("text_hook", "caption"):
            if pkg.get(fld):
                pkg[fld] = _normalize_ck(pkg[fld])
        warnings = _validate_script(pkg)  # validate trên bản structured
        if warnings:
            log.warning("script · %d warnings từ validator: %s", len(warnings), warnings[:3])
        # Contract với Producer: script = nguyên văn lời thoại (string), không total_duration_sec.
        # Shot list (mapping câu→clip_tag) tách ra field riêng cho [C]/[E] dùng nếu cần.
        lines = pkg.get("script", [])
        pkg["script"] = _script_to_text(lines)
        pkg["shot_list"] = [
            {k: l.get(k) for k in ("line", "voiceover", "duration_sec", "clip_tag", "alt_tag", "scene_hint")}
            for l in lines
        ]
        pkg.pop("total_duration_sec", None)
        log.info("script · XONG · %d dòng, %d ký tự voiceover, %d warnings, %.1fs",
                 len(lines), len(pkg["script"]), len(warnings), time.monotonic() - t0)
        return {"status": "ok", "error": None, "package": pkg, "warnings": warnings}
    except Exception as e:
        log.exception("script · LỖI sau %.1fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "error": str(e), "package": None}


# ------------------------------------------------- contract với Orchestrator

TOOL_DEFINITIONS = [
    {
        "name": "generate_ideas",
        "description": (
            "Sinh ý tưởng video TikTok 40-55s cho kênh VNG Insider, dựa trên trend thị trường "
            "(từ Scout) và insight nội bộ (từ Analyst). Gọi trước generate_script."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Chủ đề được giao (optional)"},
                "trend_digest": {"type": "object", "description": "trend_digest JSON từ [A] Scout"},
                "insight_digest": {"type": "object", "description": "insight_digest JSON từ [E] Analyst"},
                "n_ideas": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "generate_script",
        "description": (
            "Từ 1 ý tưởng đã chọn, viết trọn gói: text hook 2-3s, kịch bản lồng tiếng 40-55s "
            "(110-140 từ), shot list theo clip_tag (9 nhóm kho clip — đã nạp sẵn, không cần truyền), "
            "caption + hashtag. Output cho Producer [C] render và Publisher [D] đăng."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "idea": {"type": "object", "description": "1 idea object từ generate_ideas"},
                "insight_digest": {"type": "object", "description": "insight_digest từ [E] (optional)"},
                "target_duration_sec": {"type": "integer", "default": 48},
            },
            "required": ["idea"],
        },
    },
]

_DISPATCH = {
    "generate_ideas": generate_ideas,
    "generate_script": generate_script,
}


def execute_tool(name: str, tool_input: dict) -> dict:
    """Entry point cho Orchestrator. Không bao giờ raise."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"status": "failed", "error": f"Tool không tồn tại: {name}"}
    try:
        return fn(**(tool_input or {}))
    except TypeError as e:
        return {"status": "failed", "error": f"Sai input: {e}"}


# ---------------------------------------------------------------- smoke test
if __name__ == "__main__":
    r1 = execute_tool("generate_ideas", {"topic": "canteen và café ở VNG Campus", "n_ideas": 3})
    print(json.dumps(r1, ensure_ascii=False, indent=2))
    if r1["status"] == "ok":
        r2 = execute_tool("generate_script", {"idea": r1["ideas"][0]})
        print(json.dumps(r2, ensure_ascii=False, indent=2))