"""Chat conductor — FastAPI endpoints cho tab Chat (điều khiển pipeline bằng NLU).

POST /api/chat/sessions               — tạo conversation mới, trả greeting + ui
GET  /api/chat/sessions/{id}          — state hiện tại (refresh / khôi phục)
POST /api/chat/sessions/{id}/messages — gửi 1 message → 1 lượt conductor

Tiến trình run + duyệt gate dùng lại /api/workflow/runs/{run_id} (+ /approval) —
không định nghĩa endpoint mới ở đây.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import conductor

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Tin nhắn của user")


@router.post("/sessions")
def create_session() -> dict:
    return conductor.create_session()


@router.get("/sessions")
def list_sessions() -> dict:
    return {"sessions": conductor.list_sessions()}


@router.get("/sessions/{conv_id}")
def get_session(conv_id: str) -> dict:
    state = conductor.get_session(conv_id)
    if state is None:
        raise HTTPException(404, "Session không tồn tại")
    return state


@router.delete("/sessions/{conv_id}")
def delete_session(conv_id: str) -> dict:
    ok = conductor.delete_session(conv_id)
    if not ok:
        raise HTTPException(404, "Session không tồn tại")
    return {"ok": True}


@router.post("/sessions/{conv_id}/messages")
def send_message(conv_id: str, req: MessageRequest) -> dict:
    state = conductor.send_message(conv_id, req.text)
    if state is None:
        raise HTTPException(404, "Session không tồn tại (server restart?)")
    return state


@router.post("/sessions/{conv_id}/record-run")
def record_run(conv_id: str) -> dict:
    """Ghi mốc pipeline (video / đăng xong / huỷ / lỗi) vào hội thoại. FE gọi khi run đổi mốc."""
    state = conductor.record_run_events(conv_id)
    if state is None:
        raise HTTPException(404, "Session không tồn tại")
    return state
