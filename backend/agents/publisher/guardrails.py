"""Publisher guardrails — phanh #1 (nội dung) + helper dedup hash.

DRY: tái dùng đúng list BANNED_WORDS/REVIEW_WORDS của Creative (KHÔNG copy) để
1 nguồn sự thật cho từ cấm. BANNED → chặn cứng (không đăng); REVIEW → cảnh báo
(vẫn đăng được, cần human để ý). Không bao giờ raise — trả dict.
"""
from __future__ import annotations

import hashlib

from agents.creative.tools import BANNED_WORDS, REVIEW_WORDS


def content_hash(script: str) -> str:
    """sha256 của script đã strip — canonical content cho dedup. Cùng script → cùng hash."""
    return hashlib.sha256((script or "").strip().encode("utf-8")).hexdigest()


def check_publishable(caption: str, script: str, text_hook: str | None = None) -> dict:
    """Phanh nội dung. Ghép caption+script+text_hook, soi từ cấm/review (case-insensitive).

    text_hook = chữ overlay viewer thấy trên video → cũng phải qua phanh.

    Returns:
      {ok: True,  blocked_reason: None,        warnings: [...]}  — đăng được (có thể có cảnh báo)
      {ok: False, blocked_reason: "BANNED:<w>", warnings: []}    — chặn cứng, KHÔNG đăng
    """
    text = f"{caption or ''} {script or ''} {text_hook or ''}".lower()

    for w in BANNED_WORDS:
        if w in text:
            return {"ok": False, "blocked_reason": f"BANNED:{w.strip()}", "warnings": []}

    warnings = [f"REVIEW:{w}" for w in REVIEW_WORDS if w in text]
    return {"ok": True, "blocked_reason": None, "warnings": warnings}
