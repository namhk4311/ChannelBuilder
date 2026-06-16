# -*- coding: utf-8 -*-
"""Auto gen ảnh nền (no-text) cho mỗi scene qua LiteLLM (gpt-image-2).

OpenAI-compatible images endpoint qua LiteLLM proxy. Ảnh dọc (portrait) → render
dùng background-size:cover crop về đúng 9:16. quality=low cho nhanh/rẻ.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import requests

from config import LITE_LLM_API_KEY, LITE_LLM_BASE_URL, LITE_LLM_IMAGE_MODEL

log = logging.getLogger("banner_proto.imagegen")

# gpt-image portrait chuẩn = 1024x1536 (~2:3); CSS cover crop về 9:16 ở banner.
# Nếu LiteLLM/model hỗ trợ 9:16 thật thì đổi sang "1080x1920".
IMAGE_SIZE = "1024x1536"
IMAGE_QUALITY = "low"
TIMEOUT = 180


def generate_bg(prompt: str, out_path: Path) -> Path:
    """Sinh 1 ảnh nền từ prompt → lưu ra out_path (png). Raise nếu lỗi."""
    if not LITE_LLM_API_KEY:
        raise RuntimeError("Thiếu LITE_LLM_API_KEY trong .env")

    url = f"{LITE_LLM_BASE_URL.rstrip('/')}/v1/images/generations"
    payload = {
        "model": LITE_LLM_IMAGE_MODEL,
        "prompt": prompt,
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
        "n": 1,
    }
    log.info("imagegen · model=%s size=%s quality=%s prompt=%dc",
             LITE_LLM_IMAGE_MODEL, IMAGE_SIZE, IMAGE_QUALITY, len(prompt))
    r = requests.post(url, headers={"Authorization": f"Bearer {LITE_LLM_API_KEY}"},
                      json=payload, timeout=TIMEOUT)
    if r.status_code == 404:
        # 1 số deploy LiteLLM không có prefix /v1
        r = requests.post(f"{LITE_LLM_BASE_URL.rstrip('/')}/images/generations",
                          headers={"Authorization": f"Bearer {LITE_LLM_API_KEY}"},
                          json=payload, timeout=TIMEOUT)
    r.raise_for_status()

    data = (r.json().get("data") or [{}])[0]
    if data.get("b64_json"):
        out_path.write_bytes(base64.b64decode(data["b64_json"]))
    elif data.get("url"):
        img = requests.get(data["url"], timeout=60)
        img.raise_for_status()
        out_path.write_bytes(img.content)
    else:
        raise RuntimeError(f"image response thiếu b64_json/url: {str(r.json())[:200]}")
    log.info("imagegen · wrote %s (%d bytes)", out_path.name, out_path.stat().st_size)
    return out_path
