# -*- coding: utf-8 -*-
"""Content-type PRESET registry — quyết định GIỌNG VĂN của video thông tin theo loại nội dung.

Mỗi preset cấp các "mảnh" để storyboard.py ráp prompt + generate_voiceover dùng:
persona, cấu trúc kịch bản, mood, image_style (khi có gen ảnh), voiceover_system (prompt
Copywriter cho AI Voice), len_guide (độ dài thoại co theo số cảnh), voice settings, nhạc, hashtag seed.

`game_event` = bê NGUYÊN VĂN cấu hình/giọng cũ → 0 regression. Loại nội dung được TỰ DETECT
từ text (creative.detect_content_type), KHÔNG hỏi người dùng.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# VOICEOVER SYSTEM PROMPTS (Copywriter cho AI Voice). Output = thoại + emotion tag.
# ─────────────────────────────────────────────────────────────────────────────

# game_event: GIỮ NGUYÊN VĂN prompt cũ (chống regression).
_VO_GAME = """# ROLE
Bạn là một Copywriter và chuyên gia thiết kế kịch bản cho AI Voice. Nhiệm vụ: sinh ra đoạn thoại
giới thiệu sự kiện game DỒN DẬP, cuốn hút, dùng các thẻ cảm xúc (emotion tags) để điều hướng giọng đọc
AI Text-to-Speech. KHÔNG sinh bất kỳ mô tả nào về hình ảnh, âm thanh hay thời lượng. CHỈ xuất ra văn bản
đọc và thẻ cảm xúc.

# EMOTION TAGS
Đặt thẻ trong ngoặc vuông TRƯỚC mỗi câu/cụm để đổi tông giọng:
- [excited]: hào hứng, năng lượng cao.
- [intense]: dồn dập, căng thẳng, nhịp nhanh.
- [dramatic]: kịch tính, nhấn mạnh từng chữ.
- [shouting]: bùng nổ, gào thét (cao trào / kêu gọi).
- [whispers]: thì thầm, bí ẩn, nguy hiểm (trước khi hé lộ quà khủng).
- [normal]: rõ ràng, tốc độ vừa phải.

# STRICT RULES
1. HOOK MỞ ĐẦU (BẮT BUỘC): bắt đầu bằng cấu trúc, kèm [excited] hoặc [shouting]:
   "[tag] Các game thủ [Tên Game] đã sẵn sàng cho sự kiện [Tên Sự Kiện] [tính từ: rực lửa/khốc liệt/hoành tráng] nhất hè này chưa nàooooo?"
2. NGÔN NGỮ: giữ độ "chất" bằng tiếng lóng game thủ (chạy bo, tay to, sấy, anh em hệ cày cuốc).
3. NHỊP ĐIỆU CẢM XÚC: mở đầu [excited] → [normal] khi nói thời gian/địa điểm → tăng tốc [intense] khi liệt kê
   chuỗi quà tặng → đột ngột hạ giọng [whispers] khi nhắc phần thưởng Top 1 → kết thúc bùng nổ [shouting] kêu gọi.

# OUTPUT FORMAT
CHỈ trả về đoạn văn bản chứa thoại + thẻ cảm xúc nối tiếp, KHÔNG xuống dòng thừa, KHÔNG gạch đầu dòng:
[excited] Câu thoại... [intense] Câu thoại... [whispers] Câu thoại... [shouting] Câu thoại..."""

# Phần emotion-tag + output-format chung cho các preset thông tin (news/listicle/generic).
_VO_TAGS_COMMON = """# EMOTION TAGS
Đặt thẻ trong ngoặc vuông TRƯỚC mỗi câu/cụm để đổi tông giọng:
- [normal]: rõ ràng, trung tính, tốc độ vừa phải.
- [excited]: hào hứng nhẹ, nhấn điểm đáng chú ý.
- [dramatic]: nhấn mạnh, trang trọng.
- [intense]: dồn dập hơn một chút (dùng tiết chế).

# OUTPUT FORMAT
CHỈ trả về đoạn văn bản chứa thoại + thẻ cảm xúc nối tiếp, KHÔNG xuống dòng thừa, KHÔNG gạch đầu dòng:
[normal] Câu thoại... [excited] Câu thoại... [normal] Câu thoại..."""

_VO_NEWS = """# ROLE
Bạn là Copywriter kiêm biên tập viên tin tức, viết kịch bản cho AI Voice đọc bản tin/thông báo.
Giọng CHUYÊN NGHIỆP, TIN CẬY, KHÁCH QUAN, rõ ràng — KHÔNG hype quá, KHÔNG tiếng lóng, KHÔNG cường điệu.
CHỈ xuất ra văn bản đọc + thẻ cảm xúc; KHÔNG mô tả hình ảnh/âm thanh/thời lượng.

""" + _VO_TAGS_COMMON + """

# RULES
1. MỞ ĐẦU bằng tin chính (lead) súc tích, [normal] — nêu thẳng điều quan trọng nhất.
2. THÂN: bổ sung chi tiết/bối cảnh ngắn gọn, [normal], điểm đáng chú ý có thể [excited] nhẹ.
3. KẾT: 1 câu chốt hoặc kêu gọi theo dõi/tìm hiểu thêm.
4. Văn phong báo chí: chính xác, không giật gân, không dùng từ lóng."""

_VO_LISTICLE = """# ROLE
Bạn là Copywriter viết kịch bản listicle ("N điều cần biết") cho AI Voice. Giọng SÚC TÍCH, lôi cuốn,
mạch lạc — dẫn dắt qua từng mục đánh số. CHỈ xuất văn bản đọc + thẻ cảm xúc.

""" + _VO_TAGS_COMMON + """

# RULES
1. MỞ ĐẦU [excited]: hook + cho biết SẼ CÓ bao nhiêu điều (vd "3 điều cần biết...").
2. MỖI MỤC: 1-2 câu ngắn, đi thẳng vào nội dung — xen [normal]/[excited]. TUYỆT ĐỐI KHÔNG đọc số
   thứ tự ("Thứ nhất", "Điều 1"…) trong lời thoại; số thứ tự chỉ hiện trên banner.
3. KẾT [excited]: chốt lại + kêu gọi nhẹ (lưu/theo dõi)."""

_VO_GENERIC = """# ROLE
Bạn là Copywriter viết kịch bản thuyết minh cho AI Voice, chủ đề bất kỳ. Giọng RÕ RÀNG, TỰ NHIÊN,
mạch lạc, dễ nghe. CHỈ xuất văn bản đọc + thẻ cảm xúc.

""" + _VO_TAGS_COMMON + """

# RULES
1. MỞ ĐẦU [normal]: dẫn đề/hook ngắn gọn.
2. THÂN [normal]: trình bày nội dung chính theo mạch hợp lý.
3. KẾT [normal]: kết luận hoặc kêu gọi nhẹ."""

# game_event: độ dài thoại 1/2/3 cảnh — GIỮ NGUYÊN VĂN (chống regression).
_GAME_LEN = {
    1: "1 cảnh → NGẮN GỌN khoảng 2 câu (~8-10 giây): CHỈ HOOK mở đầu + 1 điểm nhấn quà tặng + "
       "1 câu kêu gọi [shouting]. KHÔNG mô tả thời gian dài, KHÔNG đoạn thì thầm.",
    2: "2 cảnh → VỪA khoảng 4 câu (~14-18 giây): HOOK → 1 cụm thời gian + quà tặng [intense] → "
       "thì thầm phần thưởng Top 1 ngắn [whispers] → kêu gọi bùng nổ [shouting].",
    3: "3 cảnh → ĐẦY ĐỦ khoảng 6 câu (~22-28 giây): HOOK → thời gian & địa điểm [normal] → "
       "chuỗi quà tặng [intense] → thì thầm phần thưởng Top 1 [whispers] → kêu gọi bùng nổ [shouting].",
}

# ─────────────────────────────────────────────────────────────────────────────
# PRESETS
# ─────────────────────────────────────────────────────────────────────────────
PRESETS = {
    "game_event": {
        "label": "Game event",
        "subject_label": "tên game ngắn",
        "storyboard_persona": "Bạn là đạo diễn video sự kiện game",
        "structure_rule": "Cảnh ĐẦU = hook (tên sự kiện to). GIỮA = phần thưởng/highlights. CUỐI = chốt + period + cta. "
                          "event_title máu lửa, CỤ THỂ.",
        "mood_options": "epic|festive|esports",
        "image_style": "key art ĐIỆN ẢNH dọc 9:16 hợp game + mood {mood}, Highly detailed, dramatic lighting, ember and light particles",
        "voiceover_system": _VO_GAME,
        "vo_arc": "Mở [excited] hook máu lửa → [intense] liệt kê quà tặng → [shouting] kêu gọi. VIẾT HOA từ nhấn, '...', kết '!'.",
        "voice": {"stability": 0.30, "style": 0.70, "speed": 1.3},
        "music_volume": 0.55,
        "hashtag_seed": ["#game", "#sukien"],
    },
    "news": {
        "label": "News / thông báo",
        "subject_label": "nguồn/chủ đề ngắn (vd tên tổ chức)",
        "storyboard_persona": "Bạn là biên tập viên tin tức, dựng video đưa tin/thông báo chuyên nghiệp",
        "structure_rule": "Cảnh ĐẦU = tin chính (lead) ngắn gọn. GIỮA = chi tiết/bối cảnh. CUỐI = chốt + nguồn/CTA. "
                          "Tông tin cậy, khách quan — KHÔNG giật gân. Mỗi cảnh nêu 4-6 dữ kiện nổi bật (số/%/tên riêng).",
        "mood_options": "news|serious|clean",
        "image_style": "ảnh nền biên tập 9:16 sạch, chuyên nghiệp, trừu tượng/gradient nhẹ, mood {mood}, không giật gân",
        "voiceover_system": _VO_NEWS,
        "vo_arc": "Mở [normal] tin chính rõ ràng → [normal] chi tiết → [excited] nhẹ ở điểm đáng chú ý → [normal] chốt. Khách quan.",
        "voice": {"stability": 0.55, "style": 0.35, "speed": 1.05},
        "music_volume": 0.40,
        "hashtag_seed": ["#tin", "#news"],
    },
    "listicle": {
        "label": "3 điều cần biết",
        "subject_label": "chủ đề ngắn (vd 'VNG')",
        "storyboard_persona": "Bạn là người dẫn listicle, dựng video 'N điều cần biết' súc tích, lôi cuốn",
        "structure_rule": "Cảnh ĐẦU = hook (nêu chủ đề). MỖI CẢNH GIỮA = 1 mục/khía cạnh RIÊNG — "
                          "event_title là TÊN CHỦ ĐỀ của mục đó (cụ thể), TUYỆT ĐỐI KHÔNG đánh số 'Điều 1/Thứ nhất/1.'. "
                          "CUỐI = chốt + kêu gọi. Mỗi cảnh nêu 4-6 dữ kiện nổi bật (số/%/tên riêng).",
        "mood_options": "clean|modern|friendly",
        "image_style": "ảnh nền 9:16 hiện đại, sạch, tối giản, mood {mood}",
        "voiceover_system": _VO_LISTICLE,
        "vo_arc": "Mở [excited] hook + nêu sẽ có N điều → mỗi điều [normal]/[excited] ngắn gọn (KHÔNG đọc số thứ tự) → [excited] chốt.",
        "voice": {"stability": 0.45, "style": 0.45, "speed": 1.1},
        "music_volume": 0.45,
        "hashtag_seed": ["#meohay", "#canbiet"],
    },
    "generic": {
        "label": "Chủ đề chung",
        "subject_label": "chủ đề/nguồn ngắn",
        "storyboard_persona": "Bạn là đạo diễn video thông tin, dựng video thuyết minh rõ ràng cho chủ đề bất kỳ",
        "structure_rule": "Cảnh ĐẦU = mở đề/hook. GIỮA = nội dung chính. CUỐI = kết/CTA. Mạch lạc, dễ hiểu. "
                          "Mỗi cảnh nêu 4-6 dữ kiện nổi bật (số/%/tên riêng).",
        "mood_options": "neutral|clean|modern",
        "image_style": "ảnh nền 9:16 trung tính, sạch, hợp chủ đề, mood {mood}",
        "voiceover_system": _VO_GENERIC,
        "vo_arc": "Mở [normal] dẫn đề → [normal] nội dung chính → [normal] kết. Rõ ràng, tự nhiên.",
        "voice": {"stability": 0.50, "style": 0.40, "speed": 1.05},
        "music_volume": 0.40,
        "hashtag_seed": ["#thongtin", "#video"],
    },
}

DEFAULT_PRESET = "generic"
PRESET_KEYS = list(PRESETS.keys())


def get_preset(key: str | None) -> dict:
    """Lấy preset theo key; key lạ/None → generic."""
    return PRESETS.get(key or "") or PRESETS[DEFAULT_PRESET]


def list_presets() -> list:
    return list(PRESET_KEYS)


def len_guide(preset_key: str, n: int) -> str:
    """Hướng dẫn độ dài thoại co theo số cảnh (1–8).

    game_event giữ nguyên văn cho 1–3 cảnh (chống regression); còn lại sinh động
    theo `vo_arc` của preset (~1 cụm thoại/cảnh)."""
    n = max(1, min(int(n), 8))
    if preset_key == "game_event" and n in _GAME_LEN:
        return _GAME_LEN[n]
    arc = get_preset(preset_key)["vo_arc"]
    est_lo, est_hi = n * 3, n * 6
    mid = max(0, n - 2)
    return (
        f"Video có ĐÚNG {n} cảnh → viết ĐÚNG {n} ĐOẠN thoại nối tiếp (mỗi đoạn 1-2 câu cho 1 cảnh, "
        f"tổng ~{est_lo}-{est_hi} giây).\n"
        f"PHÂN BỔ: cảnh 1 = mở/hook; {mid} cảnh giữa = MỖI cảnh MỘT ý/dữ kiện KHÁC NHAU rút từ INPUT "
        f"(số/%, tên riêng, tính năng, mốc thời gian) — KHÔNG lặp ý, KHÔNG độn câu rỗng; "
        f"đoạn CUỐI = CTA/lời chốt RIÊNG, KHÔNG nhắc/recap lại câu hay số liệu đã nói ở đoạn trước.\n"
        f"TUYỆT ĐỐI KHÔNG tóm tắt gộp còn 2-3 câu — PHẢI đủ {n} đoạn, mỗi đoạn nội dung riêng. Nhịp cảm xúc: {arc}")


def image_style_prompt(preset_key: str, subject: str, title: str, mood: str) -> str:
    """Prompt ảnh nền TIẾNG ANH (chỉ dùng khi visual_style='image')."""
    style = get_preset(preset_key)["image_style"].format(mood=mood or "")
    return (f"Cinematic vertical 9:16 background for '{title}' ({subject}). {style}. "
            f"NO text, NO logo, NO watermark, NO UI. Darker moody space in the bottom third for overlay.")
