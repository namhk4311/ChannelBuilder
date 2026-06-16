# -*- coding: utf-8 -*-
"""Visual style + brand theme — quyết định HÌNH ẢNH của video (độc lập với loại nội dung).

2 trục tách biệt:
- content_type (content_presets.py) → giọng văn/kịch bản (tự detect từ text).
- visual_style (file này) → nhóm template + CÓ gen ảnh hay không + dải số cảnh + phụ đề.

`image`  = template ảnh AI cinematic (gen ảnh, 1–3 cảnh, không phụ đề) — như event_game cũ.
`solid`  = template nền màu đơn sắc theo brand + pattern (KHÔNG gen ảnh, 3–5 cảnh, có phụ đề).
Người dùng chọn visual_style bằng chip; brand chỉ hỏi khi `solid`.
"""
from __future__ import annotations

VISUAL_STYLES = {
    "image": {
        "label": "🖼️ Ảnh AI",
        "hint": "ảnh nền AI cinematic (1–3 cảnh)",
        "templates": ["epic", "esports", "poster", "editorial"],
        "default_template": "poster",
        "gen_images": True,
        "theme": "llm",            # màu do storyboard LLM tự chọn
        "scenes": [1, 2, 3],
        "scene_default": 2,
        "captions": False,
    },
    "solid": {
        "label": "🎨 Đơn sắc",
        "hint": "nền màu brand, không gen ảnh (3–5 cảnh)",
        "templates": ["listicle", "news", "corporate", "slide"],
        "default_template": "slide",
        "gen_images": False,
        "theme": "brand",          # màu lấy từ brand theme
        "scenes": [3, 4, 5],
        "scene_default": 4,
        "captions": True,
    },
}

DEFAULT_VISUAL_STYLE = "image"

# Brand theme cho template Đơn sắc: nền đơn sắc + accent + chữ + pattern chéo mờ.
BRAND_THEMES = {
    "vng": {
        "label": "VNG (cam/trắng)",
        # Nền CAM, chữ TRẮNG (accent trắng → highlight bật bằng đậm; muted = trắng ngả nhẹ).
        "bg": "#ff6a00", "accent": "#ffffff", "text": "#ffffff", "muted": "#ffe0cc",
        "pattern": "rgba(255,255,255,0.10)",
    },
    "anthropic": {
        "label": "Anthropic (đen/đỏ coral)",
        "bg": "#0c0c0d", "accent": "#e8553d", "text": "#f5f4f0", "muted": "#8b8987",
        "pattern": "rgba(255,255,255,0.05)",
    },
    "neutral_dark": {
        "label": "Neutral dark",
        "bg": "#0e1116", "accent": "#5b9cff", "text": "#f2f4f8", "muted": "#8a93a3",
        "pattern": "rgba(255,255,255,0.045)",
    },
    "neutral_light": {
        "label": "Neutral light",
        "bg": "#f6f7f9", "accent": "#2563eb", "text": "#11151c", "muted": "#6b7280",
        "pattern": "rgba(0,0,0,0.045)",
    },
}

DEFAULT_BRAND = "vng"


def get_visual_style(key: str | None) -> dict:
    """Lấy visual style; key lạ/None → image (mặc định an toàn = hành vi event_game cũ)."""
    return VISUAL_STYLES.get(key or "") or VISUAL_STYLES[DEFAULT_VISUAL_STYLE]


def get_brand_theme(brand: str | None) -> dict:
    """Lấy brand theme (cho template Đơn sắc); brand lạ/None → vng."""
    return BRAND_THEMES.get(brand or "") or BRAND_THEMES[DEFAULT_BRAND]


def scene_options(visual_style: str | None) -> list:
    """Dải số cảnh hợp lệ theo visual_style (image: [1,2,3] · solid: [3,4,5])."""
    return list(get_visual_style(visual_style)["scenes"])


def clamp_scenes(visual_style: str | None, n) -> int:
    """Ép n về dải hợp lệ của visual_style; lỗi parse → scene_default."""
    opts = scene_options(visual_style)
    try:
        n = int(n)
    except (TypeError, ValueError):
        return get_visual_style(visual_style)["scene_default"]
    if n in opts:
        return n
    return min(opts, key=lambda v: abs(v - n))


def brand_theme_to_scene_theme(brand: str | None) -> dict:
    """Brand theme → dict 'theme' tương thích render (primary/secondary/accent + bộ màu solid)."""
    b = get_brand_theme(brand)
    return {
        "primary": b["bg"], "secondary": b["bg"], "accent": b["accent"],
        "mood": "solid",
        # màu riêng cho template Đơn sắc:
        "bg": b["bg"], "text": b["text"], "muted": b["muted"], "pattern": b["pattern"],
    }
