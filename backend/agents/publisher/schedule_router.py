"""[D] Publisher — REST cho queue lịch đăng (calendar + run-now).

POST   /api/publisher/schedule            {snapshot, scheduled_for?}  → insert pending
GET    /api/publisher/schedule?status=    → list calendar
DELETE /api/publisher/schedule/{id}       → cancel (chỉ pending)
POST   /api/publisher/schedule/run-now    → tick ngay (demo)  → {published, skipped, failed}

Mọi handler bọc try → trả {status:"failed", error} (không 500) để UI render gọn.
Lệnh "đăng ngay" tại gate đi qua workflow (POST /api/workflow/runs/.../approval),
không phải ở đây — router này chỉ quản lý hàng đợi lịch.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import scheduled_posts
from .guardrails import check_publishable
from .scheduler import default_schedule_slot, run_now

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/publisher", tags=["publisher-schedule"])


class ScheduleRequest(BaseModel):
    library: str
    video_object: str = Field(..., description="URL MinIO video final (snapshot tự chứa)")
    caption: str
    script: str
    text_hook: Optional[str] = None
    run_id: Optional[str] = None
    scheduled_for: Optional[datetime] = Field(
        None, description="Giờ hẹn ISO (UTC). None → slot mặc định 9h ngày kế (Asia/Saigon).")


@router.post("/schedule")
def create_schedule(req: ScheduleRequest) -> dict:
    try:
        # Phanh nội dung sớm: BANNED → từ chối enqueue luôn (không vào queue).
        g = check_publishable(req.caption, req.script, req.text_hook)
        if not g["ok"]:
            return {"status": "failed", "reason": "blocked_guardrail",
                    "error": g["blocked_reason"], "post": None}
        scheduled_for = req.scheduled_for or default_schedule_slot()
        snapshot = {"run_id": req.run_id, "library": req.library,
                    "video_object": req.video_object, "caption": req.caption,
                    "script": req.script, "text_hook": req.text_hook}
        row = scheduled_posts.insert(snapshot, trigger="scheduled",
                                     actor="human:ui", scheduled_for=scheduled_for)
        return {"status": "ok", "error": None, "warnings": g["warnings"], "post": row}
    except Exception as e:  # noqa: BLE001
        log.exception("create_schedule lỗi")
        return {"status": "failed", "error": f"unexpected: {e}", "post": None}


@router.get("/schedule")
def list_schedule(status: Optional[str] = None) -> dict:
    try:
        return {"status": "ok", "error": None, "posts": scheduled_posts.list_posts(status)}
    except Exception as e:  # noqa: BLE001
        log.exception("list_schedule lỗi")
        return {"status": "failed", "error": f"unexpected: {e}", "posts": []}


@router.delete("/schedule/{post_id}")
def cancel_schedule(post_id: int) -> dict:
    try:
        row = scheduled_posts.cancel(post_id)
        if row is None:
            return {"status": "failed", "error": "Chỉ huỷ được bài đang chờ (pending)", "post": None}
        return {"status": "ok", "error": None, "post": row}
    except Exception as e:  # noqa: BLE001
        log.exception("cancel_schedule lỗi")
        return {"status": "failed", "error": f"unexpected: {e}", "post": None}


@router.post("/schedule/run-now")
def trigger_run_now() -> dict:
    try:
        return {"status": "ok", "error": None, **run_now()}
    except Exception as e:  # noqa: BLE001
        log.exception("run-now lỗi")
        return {"status": "failed", "error": f"unexpected: {e}"}
