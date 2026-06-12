"""[D] Publisher — endpoints OAuth TikTok cho UI (kết nối 1 lần, token tự refresh).

GET  /api/publisher/status          — đã kết nối chưa (đọc tokens.json, không gọi API)
GET  /api/publisher/oauth/url       — authorize URL để UI mở tab đăng nhập TikTok
POST /api/publisher/oauth/exchange  — đổi code (user dán từ trang callback) → tokens.json

Lưu ý: TIKTOK_REDIRECT_URI là trang tĩnh đã đăng ký với TikTok (GitHub Pages) —
TikTok không cho đăng ký localhost nên backend không tự nhận callback được;
user copy code/URL từ trang callback dán vào UI (hoặc callback.html redirect
về UI kèm ?code=... để UI tự đổi).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import oauth
from .tools import reset_client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/publisher", tags=["publisher"])


class ExchangeRequest(BaseModel):
    code: str = Field(..., min_length=4,
                      description="Authorization code từ trang callback TikTok")


@router.get("/status")
def publisher_status() -> dict:
    return oauth.get_status()


@router.get("/oauth/url")
def oauth_url() -> dict:
    try:
        return {"status": "ok", "url": oauth.build_authorize_url(), "error": None}
    except oauth.OAuthError as e:
        return {"status": "failed", "url": None, "error": str(e)}


@router.post("/oauth/exchange")
def oauth_exchange(req: ExchangeRequest) -> dict:
    try:
        data = oauth.exchange_code(req.code.strip())
    except oauth.OAuthError as e:
        log.warning("oauth exchange failed: %s", e)
        return {"status": "failed", "error": str(e), **oauth.get_status()}
    except Exception as e:  # noqa: BLE001 — network/JSON lỗi không được 500
        log.exception("oauth exchange crashed")
        return {"status": "failed", "error": f"unexpected: {e}", **oauth.get_status()}
    reset_client()  # client cache đang giữ token cũ/lỗi — ép init lại từ tokens.json mới
    log.info("oauth exchange OK · open_id=%s", data.get("open_id"))
    return {"status": "ok", "error": None, **oauth.get_status()}
