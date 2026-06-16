# -*- coding: utf-8 -*-
"""Event/Info video agent — video thông tin (storyboard → [gen ảnh] → render → ghép → nhạc).

2 trục: content_type (giọng/kịch bản, tự detect) × visual_style (template + gen ảnh + nền brand).
Port từ prototype banner_proto, output lên MinIO để hoà vào workflow runner + human gate + publisher.
"""
from .content_presets import get_preset, list_presets
from .creative import analyze_event, detect_content_type, generate_angles
from .pipeline import produce
from .storyboard import build_storyboard
from .visual_styles import get_brand_theme, get_visual_style

__all__ = [
    "analyze_event", "generate_angles", "detect_content_type", "build_storyboard", "produce",
    "list_presets", "get_preset", "get_visual_style", "get_brand_theme",
]
