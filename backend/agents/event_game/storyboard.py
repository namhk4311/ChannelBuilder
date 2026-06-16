# -*- coding: utf-8 -*-
"""Video thông tin — LLM storyboard: text → N cảnh (banner + voiceover [+ image_prompt])
+ caption + hashtags. Giọng văn theo PRESET (content_type); template/gen theo visual_style.

Gọi VNGCloud MaaS (OpenAI-compatible, STREAMING) qua config.py. Parse JSON chịu lỗi bằng
json_repair. KHÔNG raise lung tung — trả dict sạch, đã cap field. `subject` = nhãn KICKER
(tên game / nguồn tin / chủ đề — tuỳ preset).
"""
from __future__ import annotations

import json
import logging
import re

import requests
from json_repair import repair_json

from config import AI_PLATFORM_API_KEY, AI_PLATFORM_BASE_URL, AI_PLATFORM_MODEL, CREATIVE_MODEL

from .content_presets import get_preset, image_style_prompt
from .content_presets import len_guide as _len_guide

log = logging.getLogger("event_game.storyboard")

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 300

CAPS = {
    "subject": 40, "event_title": 48, "event_subtitle": 70,
    "period": 48, "time_detail": 48, "cta": 28, "highlight": 64,
    "voiceover": 600, "image_prompt": 700, "caption": 150,
}

DEFAULT_IMAGE_TEMPLATES = ["epic", "esports", "poster", "editorial"]


def _chat(system: str, user: str, temperature: float = 0.4, max_tokens: int = 4000,
          model: str = None) -> str:
    """MaaS streaming chat → raw text. model=None → CREATIVE_MODEL; truyền flash để nhanh."""
    if not AI_PLATFORM_API_KEY:
        raise RuntimeError("Thiếu AI_PLATFORM_API_KEY trong .env")
    model = model or CREATIVE_MODEL
    if not model:
        raise RuntimeError("Thiếu model (CREATIVE_MODEL) trong .env")

    log.info("chat · model=%s temp=%.2f user=%dc", model, temperature, len(user))
    resp = requests.post(
        f"{AI_PLATFORM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {AI_PLATFORM_API_KEY}"},
        json={"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}],
              "temperature": temperature, "max_tokens": max_tokens, "stream": True},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True,
    )
    resp.raise_for_status()
    content, reasoning = [], []
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        data = raw[5:].strip()
        if data == "[DONE]":
            break
        try:
            choice = json.loads(data)["choices"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        delta = choice.get("delta") or {}
        if delta.get("content"):
            content.append(delta["content"])
        elif delta.get("reasoning_content"):
            reasoning.append(delta["reasoning_content"])
    out = "".join(content).strip() or "".join(reasoning).strip()
    if not out:
        raise RuntimeError("MaaS trả về rỗng")
    return out


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM không trả JSON: {text[:200]}")
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return json.loads(repair_json(blob))


def _cap(s, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _slug_tag(s: str) -> str:
    return "#" + re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "", (s or ""))


def _norm_hashtags(raw, seed: list, subject: str = "", title: str = "") -> list:
    out = []
    if isinstance(raw, list):
        for h in raw[:6]:
            h = str(h).strip().replace(" ", "")
            if not h:
                continue
            out.append(h if h.startswith("#") else "#" + h)
    if not out:  # fallback: slug subject/title + seed của preset
        out = [_slug_tag(subject), _slug_tag(title)] + list(seed or [])
    return [t for t in out if len(t) > 1][:6]


def _default_caption(subject: str, title: str, cta: str) -> str:
    return _cap(f"{title} – {subject}! {cta}".strip(" -!") + "!", CAPS["caption"])


def _norm_theme(raw: dict, preset_key: str) -> dict:
    th = raw or {}
    default_mood = get_preset(preset_key)["mood_options"].split("|")[0]
    return {"primary": str(th.get("primary") or "#0b0e23"),
            "secondary": str(th.get("secondary") or "#1a1f4d"),
            "accent": str(th.get("accent") or "#ffcc4d"),
            "mood": str(th.get("mood") or default_mood)}


def _pick_template(raw, templates_allowed: list, default_template: str) -> str:
    t = str(raw or "").strip().lower()
    return t if t in templates_allowed else (default_template or templates_allowed[0])


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders (ráp từ preset)
# ─────────────────────────────────────────────────────────────────────────────
def _build_storyboard_system(p: dict, n: int, templates_allowed: list, gen_images: bool) -> str:
    tpl_opts = " | ".join(templates_allowed)
    if gen_images:
        scene_extra = (',\n      "voiceover": "1-2 câu (~4-6s)",'
                       '\n      "image_prompt": "prompt TIẾNG ANH tả ảnh nền"')
        image_rule = ("\n- ẢNH NỀN (image_prompt) TIẾNG ANH: " + p["image_style"].format(mood="theo theme") +
                      ". NO text/logo/watermark/UI. Chừa vùng tối 1/3 dưới cho chữ.")
    else:
        scene_extra = ',\n      "voiceover": "1-2 câu (~4-6s)"'
        image_rule = "\n- KHÔNG ảnh nền (nền là màu brand đơn sắc) → KHÔNG xuất image_prompt."
    return (
        p["storyboard_persona"] + ". Từ thông tin, dựng STORYBOARD gồm ĐÚNG " + str(n) +
        " cảnh, mỗi cảnh = 1 banner động + 1 đoạn voiceover. Các cảnh nối tiếp thành 1 video có chuyển cảnh.\n\n"
        "Trả về DUY NHẤT một JSON object (không markdown):\n"
        "{\n"
        '  "subject": "' + p["subject_label"] + ' (dùng chung mọi cảnh)",\n'
        '  "template": "chọn ĐÚNG 1 trong [' + tpl_opts + '] — DÙNG CHUNG mọi cảnh",\n'
        '  "theme": {"primary":"#hex","secondary":"#hex","accent":"#hex","mood":"' + p["mood_options"] + '"},\n'
        '  "caption": "1-2 câu caption hấp dẫn để đăng TikTok (có hook)",\n'
        '  "hashtags": ["#thẻ", "3-6 hashtag liên quan"],\n'
        '  "scenes": [\n'
        "    {\n"
        '      "event_title": "tiêu đề LỚN của cảnh, punchy, <= 6 từ",\n'
        "      \"event_subtitle\": \"1 câu phụ hoặc ''\",\n"
        "      \"period\": \"thời gian hoặc ''\",\n"
        "      \"time_detail\": \"giờ hoặc ''\",\n"
        '      "highlights": ["4-6 DỮ KIỆN cụ thể, mỗi điểm bọc cụm nổi bật trong *..* — hoặc []"],\n'
        "      \"cta\": \"lời kêu gọi hoặc ''\"" + scene_extra + "\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "NGUYÊN TẮC:\n"
        "- ĐÚNG " + str(n) + " scene. " + p["structure_rule"] + "\n"
        "- event_title MỖI cảnh CỤ THỂ — KHÔNG dùng từ chung chung ('SỰ KIỆN','GAME','EVENT').\n"
        "- Mỗi cảnh đủ nội dung (title + ít nhất subtitle HOẶC highlights HOẶC cta).\n"
        "- highlights = 4-6 DỮ KIỆN CỤ THỂ rút từ thông tin (số/%, tên sản phẩm/tính năng, mốc thời gian, "
        "kết quả đo lường). Bọc cụm NỔI BẬT NHẤT mỗi điểm trong dấu *..* (vd 'Giảm *40%* chi phí', "
        "'Xử lý *video + văn bản tiếng Việt*'). TUYỆT ĐỐI KHÔNG bịa số — chỉ lấy dữ kiện CÓ trong văn bản; "
        "thiếu dữ kiện thì để ít điểm, KHÔNG độn câu chung chung.\n"
        "- caption tiếng Việt có hook; hashtags 3-6 thẻ (không dấu cách)." + image_rule + "\n"
        "- theme + subject + template DÙNG CHUNG mọi cảnh. Tiếng Việt có dấu, KHÔNG escape nháy kép, "
        "không xuống dòng trong chuỗi. Chỉ JSON."
    )


def _build_extract_system(p: dict, gen_images: bool) -> str:
    img = '\n  "image_prompt": "prompt TIẾNG ANH tả ảnh nền (hoặc \'\')",' if gen_images else ""
    return (
        p["storyboard_persona"] + ". Từ thông tin, trích DỮ LIỆU CHUẨN để dựng 1 banner + 1 voiceover.\n"
        "Trả về DUY NHẤT một JSON object (không markdown):\n"
        "{\n"
        '  "subject": "' + p["subject_label"] + '",\n'
        '  "event_title": "tiêu đề punchy, <= 6 từ",\n'
        "  \"event_subtitle\": \"1 câu mô tả ngắn hoặc ''\",\n"
        "  \"period\": \"khoảng thời gian hoặc ''\",\n"
        "  \"time_detail\": \"giờ chi tiết hoặc ''\",\n"
        '  "highlights": ["4-6 DỮ KIỆN cụ thể, bọc cụm nổi bật trong *..*"],\n'
        '  "cta": "lời kêu gọi ngắn",\n'
        '  "theme": {"primary":"#hex","secondary":"#hex","accent":"#hex","mood":"' + p["mood_options"] + '"},'
        + img + '\n'
        '  "voiceover": "2-4 câu tiếng Việt"\n'
        "}\n"
        "Tiếng Việt có dấu. KHÔNG escape nháy kép. Không xuống dòng trong chuỗi. Chỉ JSON."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Normalize
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_scene(scene: dict, subject: str, theme: dict, tpl: str,
                     gen_images: bool, preset_key: str) -> dict:
    hls = scene.get("highlights") or []
    if not isinstance(hls, list):
        hls = []
    hls = [_cap(h, CAPS["highlight"]) for h in hls[:6] if str(h).strip()]
    title = _cap(scene.get("event_title"), CAPS["event_title"]) or "NỘI DUNG"
    out = {
        "template": tpl, "subject": subject, "event_title": title,
        "event_subtitle": _cap(scene.get("event_subtitle"), CAPS["event_subtitle"]),
        "period": _cap(scene.get("period"), CAPS["period"]),
        "time_detail": _cap(scene.get("time_detail"), CAPS["time_detail"]),
        "highlights": hls, "cta": _cap(scene.get("cta"), CAPS["cta"]), "theme": theme,
        "voiceover": _cap(scene.get("voiceover"), CAPS["voiceover"]) or "Cùng theo dõi nhé!",
    }
    if gen_images:
        out["image_prompt"] = _cap(scene.get("image_prompt"), CAPS["image_prompt"]) \
            or image_style_prompt(preset_key, subject, title, theme.get("mood", ""))
    return out


def _normalize_base(obj: dict, preset_key: str) -> dict:
    hls = obj.get("highlights") or []
    if not isinstance(hls, list):
        hls = []
    hls = [_cap(h, CAPS["highlight"]) for h in hls[:6] if str(h).strip()]
    return {
        "subject": _cap(obj.get("subject"), CAPS["subject"]) or "VIDEO",
        "event_title": _cap(obj.get("event_title"), CAPS["event_title"]) or "NỘI DUNG ĐÁNG CHÚ Ý",
        "event_subtitle": _cap(obj.get("event_subtitle"), CAPS["event_subtitle"]),
        "period": _cap(obj.get("period"), CAPS["period"]),
        "time_detail": _cap(obj.get("time_detail"), CAPS["time_detail"]),
        "highlights": hls,
        "cta": _cap(obj.get("cta"), CAPS["cta"]) or "Theo dõi ngay!",
        "theme": _norm_theme(obj.get("theme"), preset_key),
        "voiceover": _cap(obj.get("voiceover"), CAPS["voiceover"])
        or "Cùng theo dõi nội dung đáng chú ý ngay sau đây!",
        "image_prompt": _cap(obj.get("image_prompt"), CAPS["image_prompt"]),
    }


def _extract_base(raw_text: str, preset_key: str, gen_images: bool) -> dict:
    p = get_preset(preset_key)
    raw = _chat(_build_extract_system(p, gen_images),
                f"Thông tin:\n\n{raw_text.strip()}\n\nTrích xuất theo schema.")
    return _normalize_base(_extract_json(raw), preset_key)


def _split_sentences(text: str, n: int) -> list:
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", (text or "").strip()) if p.strip()]
    if not parts:
        return [""] * n
    out, per, i = [], max(1, round(len(parts) / n)), 0
    for s in range(n):
        chunk = parts[i:i + per] if s < n - 1 else parts[i:]
        out.append(" ".join(chunk) if chunk else parts[-1])
        i += per
    return out[:n] + [parts[-1]] * max(0, n - len(out))


def _fallback_storyboard(base: dict, n: int, tpl: str, gen_images: bool, preset_key: str) -> dict:
    chunks = _split_sentences(base["voiceover"], n)
    hls = base.get("highlights") or []
    scenes = []
    for i in range(n):
        first, last = (i == 0), (i == n - 1)
        sc = {
            "event_title": base["event_title"] if first else (base["cta"] if last else f"Điều {i}"),
            "event_subtitle": base["event_subtitle"] if first else "",
            "period": base["period"] if last else "",
            "time_detail": base["time_detail"] if last else "",
            "highlights": (hls if (not first and not last) else (hls[:1] if last else [])),
            "cta": base["cta"] if last else "",
            "voiceover": chunks[i] if i < len(chunks) else base["voiceover"],
            "image_prompt": base.get("image_prompt") or "",
        }
        scenes.append(_normalize_scene(sc, base["subject"], base["theme"], tpl, gen_images, preset_key))
    seed = get_preset(preset_key)["hashtag_seed"]
    return {"subject": base["subject"], "template": tpl, "theme": base["theme"], "scenes": scenes,
            "caption": _default_caption(base["subject"], base["event_title"], base["cta"]),
            "hashtags": _norm_hashtags(None, seed, base["subject"], base["event_title"])}


# ─────────────────────────────────────────────────────────────────────────────
# VOICEOVER chuyên dụng (prompt Copywriter cho AI Voice) — theo preset
# ─────────────────────────────────────────────────────────────────────────────
def _vo_valid(s: str) -> bool:
    """Thoại hợp lệ = đủ dài + có dấu kết câu (chống flash trả về cụt giữa chừng)."""
    return len(s) >= 40 and bool(re.search(r"[.!?…]", s))


def generate_voiceover(event_text: str, n_scenes: int = 2, preset: str = "game_event") -> str:
    """Sinh kịch bản thoại (emotion tags) theo preset — ĐỘ DÀI co theo số cảnh. Retry 1 lần."""
    n = max(1, min(int(n_scenes), 8))
    p = get_preset(preset)
    user = (f"# INPUT DATA\n{(event_text or '').strip()}\n\n"
            f"# ĐỘ DÀI BẮT BUỘC (số cảnh = {n})\n{_len_guide(preset, n)}")
    out = ""
    for temp in (0.85, 0.6):
        raw = _chat(p["voiceover_system"], user, model=AI_PLATFORM_MODEL,
                    temperature=temp, max_tokens=1500).strip()
        fence = re.search(r"```(?:\w+)?\s*(.*?)```", raw, re.DOTALL)
        if fence:
            raw = fence.group(1).strip()
        out = " ".join(raw.split())
        if _vo_valid(out):
            return out
        log.warning("voiceover cụt/ngắn (%dc) → thử lại", len(out))
    return out


def _apply_voiceover(scenes: list, raw_text: str, preset: str) -> None:
    """Sinh voiceover chuyên dụng (dài theo số cảnh) rồi chẻ cho từng cảnh.
    Nếu gen lỗi/cụt → GIỮ voiceover storyboard (không ghi đè bằng đoạn hỏng)."""
    try:
        vo = generate_voiceover(raw_text, len(scenes), preset)
    except Exception as e:  # noqa: BLE001
        log.warning("generate_voiceover lỗi (%s) → giữ voiceover storyboard", e)
        return
    if not _vo_valid(vo):
        log.warning("voiceover không hợp lệ → giữ voiceover storyboard")
        return
    chunks = _split_sentences(vo, len(scenes))
    for i, sc in enumerate(scenes):
        if i < len(chunks) and chunks[i].strip():
            sc["voiceover"] = _cap(chunks[i], CAPS["voiceover"])


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────
def build_storyboard(raw_text: str, n_scenes: int, angle: str = None,
                     preset: str = "game_event", templates_allowed: list = None,
                     default_template: str = None, gen_images: bool = True) -> dict:
    """text + số cảnh (1-8) + (optional) góc dựng → {subject, template, theme, caption, hashtags, scenes[n]}.

    `preset` (content_type) quyết định giọng/cấu trúc; `templates_allowed`/`gen_images` (visual_style)
    quyết định template + có gen ảnh. LLM chọn 1 template dùng chung mọi cảnh. Visual do storyboard LLM;
    LỜI THOẠI dùng generate_voiceover chuyên dụng theo preset."""
    n = max(1, min(int(n_scenes), 8))
    p = get_preset(preset)
    templates_allowed = list(templates_allowed or DEFAULT_IMAGE_TEMPLATES)
    default_template = default_template or templates_allowed[0]
    angle_note = f"\n\nGÓC DỰNG đã chọn (bám theo): {angle}" if angle else ""
    seed = p["hashtag_seed"]
    result = None
    try:
        raw = _chat(_build_storyboard_system(p, n, templates_allowed, gen_images),
                    f"Số cảnh cần dựng: {n}.{angle_note}\n\nThông tin:\n\n{raw_text.strip()}",
                    model=AI_PLATFORM_MODEL)  # flash cho nhanh
        sb = _extract_json(raw)
        scenes = sb.get("scenes") or []
        theme = _norm_theme(sb.get("theme"), preset)
        subject = _cap(sb.get("subject"), CAPS["subject"]) or "VIDEO"
        tpl = _pick_template(sb.get("template"), templates_allowed, default_template)
        if len(scenes) == n:
            norm = [_normalize_scene(s, subject, theme, tpl, gen_images, preset) for s in scenes]
            title0 = norm[0]["event_title"]
            result = {"subject": subject, "template": tpl, "theme": theme, "scenes": norm,
                      "caption": _cap(sb.get("caption"), CAPS["caption"])
                      or _default_caption(subject, title0, norm[-1].get("cta") or "Theo dõi ngay!"),
                      "hashtags": _norm_hashtags(sb.get("hashtags"), seed, subject, title0)}
        else:
            log.warning("storyboard: LLM trả %d scene (cần %d) → fallback", len(scenes), n)
    except Exception as e:  # noqa: BLE001
        log.warning("storyboard LLM lỗi (%s) → fallback", e)
    if result is None:
        tpl = default_template
        result = _fallback_storyboard(_extract_base(raw_text, preset, gen_images), n, tpl, gen_images, preset)

    # Thay lời thoại bằng kịch bản chuyên dụng (chẻ cho từng cảnh) theo preset
    _apply_voiceover(result["scenes"], raw_text, preset)
    return result
