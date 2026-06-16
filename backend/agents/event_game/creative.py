# -*- coding: utf-8 -*-
"""Event/Info Creative — detect loại nội dung + bước [A] phân tích + [B] sinh góc dựng.

Để video thông tin đi qua đủ workflow như vlog: detect_content_type (chọn preset) →
analyze_event (~Scout) → generate_angles (~Creative ideas) → build_storyboard bám góc.
Dùng model FLASH cho nhanh. Persona/mood lấy theo preset (content_type tự detect).
"""
from __future__ import annotations

import logging

from config import AI_PLATFORM_MODEL

from .content_presets import PRESET_KEYS, get_preset
from .storyboard import _cap, _chat, _extract_json

log = logging.getLogger("event_game.creative")

SYSTEM_DETECT = """Phân loại đoạn thông tin sau vào ĐÚNG 1 loại video. Trả về DUY NHẤT JSON (không markdown):
{"content_type": "game_event | news | listicle | generic"}
- game_event: sự kiện/khuyến mãi/giải đấu game (game thủ, phần thưởng in-game, update game).
- news: tin tức, thông báo, ra mắt sản phẩm, sự kiện công ty (đưa tin khách quan).
- listicle: dạng liệt kê "N điều/cách/lý do/mẹo cần biết", top list.
- generic: còn lại / không rõ.
Chỉ JSON."""

SYSTEM_ANALYZE_TMPL = """{persona}. Đọc thông tin và phân tích nhanh.
Trả về DUY NHẤT JSON (không markdown):
{{
  "insight": "1 câu cốt lõi: điều hấp dẫn/quan trọng NHẤT",
  "mood": "{mood_options}",
  "angle_hint": "1 câu gợi ý góc dựng video nổi bật nhất",
  "key_points": ["2-4 điểm chính, cực ngắn"]
}}
Tiếng Việt có dấu. KHÔNG escape nháy kép. Chỉ JSON."""

SYSTEM_ANGLES_TMPL = """{persona}. Từ thông tin + phân tích, đề xuất {{n}} GÓC DỰNG video khác nhau
(mỗi góc 1 cách kể chuyện riêng). Trả về DUY NHẤT JSON:
{{{{
  "ideas": [
    {{{{"title": "tên góc ngắn", "angle": "1 câu mô tả góc dựng", "est_fit": 0-100}}}}
  ]
}}}}
Đúng {{n}} góc, est_fit = độ phù hợp ước lượng (góc mạnh nhất điểm cao nhất).
Tiếng Việt có dấu. KHÔNG escape nháy kép. Chỉ JSON."""


def detect_content_type(event_text: str) -> str:
    """Tự phân loại text → 1 trong PRESET_KEYS. Lỗi/không rõ → 'generic'."""
    try:
        raw = _chat(SYSTEM_DETECT, f"Đoạn thông tin:\n\n{(event_text or '').strip()}",
                    model=AI_PLATFORM_MODEL, temperature=0.0, max_tokens=200)
        key = str(_extract_json(raw).get("content_type") or "").strip()
        if key in PRESET_KEYS:
            log.info("detect_content_type → %s", key)
            return key
    except Exception as e:  # noqa: BLE001 — không giết pipeline
        log.warning("detect_content_type lỗi (%s) → generic", e)
    return "generic"


def analyze_event(event_text: str, preset: str = "generic") -> dict:
    """[A] Phân tích nội dung → {insight, mood, angle_hint, key_points}. Lỗi → default an toàn."""
    p = get_preset(preset)
    default_mood = p["mood_options"].split("|")[0]
    try:
        sysmsg = SYSTEM_ANALYZE_TMPL.format(persona=p["storyboard_persona"], mood_options=p["mood_options"])
        raw = _chat(sysmsg, f"Thông tin:\n\n{(event_text or '').strip()}",
                    model=AI_PLATFORM_MODEL, temperature=0.5)
        obj = _extract_json(raw)
        kp = obj.get("key_points")
        return {
            "insight": _cap(obj.get("insight"), 160) or "Nội dung đáng chú ý.",
            "mood": str(obj.get("mood") or default_mood),
            "angle_hint": _cap(obj.get("angle_hint"), 160),
            "key_points": [_cap(x, 60) for x in kp[:4]] if isinstance(kp, list) else [],
        }
    except Exception as e:  # noqa: BLE001
        log.warning("analyze_event lỗi (%s) → default", e)
        return {"insight": "Nội dung đáng chú ý.", "mood": default_mood, "angle_hint": "", "key_points": []}


def generate_angles(event_text: str, analysis: dict, n: int = 3, preset: str = "generic") -> dict:
    """[B] Sinh n góc dựng → {ideas:[{title, angle, est_fit}]}. Lỗi → 1 góc mặc định."""
    n = max(1, min(int(n), 4))
    p = get_preset(preset)
    try:
        sysmsg = SYSTEM_ANGLES_TMPL.format(persona=p["storyboard_persona"]).format(n=n)
        user = (f"Phân tích: {analysis.get('insight')} (mood {analysis.get('mood')}; "
                f"gợi ý: {analysis.get('angle_hint')}).\n\nThông tin:\n\n{(event_text or '').strip()}")
        raw = _chat(sysmsg, user, model=AI_PLATFORM_MODEL, temperature=0.7)
        ideas = (_extract_json(raw).get("ideas") or [])
        out = []
        for i in ideas[:n]:
            out.append({"title": _cap(i.get("title"), 48) or "Góc dựng",
                        "angle": _cap(i.get("angle"), 160),
                        "est_fit": int(i.get("est_fit") or 0)})
        if out:
            return {"ideas": out}
    except Exception as e:  # noqa: BLE001
        log.warning("generate_angles lỗi (%s) → default", e)
    return {"ideas": [{"title": "Tổng quan",
                       "angle": analysis.get("angle_hint") or "Giới thiệu nội dung chính + CTA",
                       "est_fit": 80}]}
