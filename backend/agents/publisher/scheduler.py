"""Scheduler — APScheduler BackgroundScheduler chạy 1 tick job poller mỗi phút
quét bài tới hạn (`scheduled_for <= now`) → publish_service.publish_now từng bài.

Poller (không cron 9h cố định) để đăng đúng GIỜ RIÊNG từng bài user chọn trên UI.
Persist nằm ở bảng `scheduled_posts` → tick chỉ cần tái tạo lúc app startup
(idempotent), KHÔNG cần Postgres jobstore.

Single instance / process. Nếu >1 replica → claim_due atomic SKIP LOCKED chống
đăng đôi; muốn tuyệt đối 1 scheduler thì chỉ bật SCHEDULE_TICK_ENABLED ở 1 instance.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import (
    MAX_POSTS_PER_DAY,
    SCHEDULE_DEFAULT_HOUR,
    SCHEDULE_TICK_ENABLED,
    SCHEDULE_TICK_SECONDS,
    SCHEDULE_TZ,
)

from . import publish_service, scheduled_posts

log = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def default_schedule_slot() -> datetime:
    """Slot pre-fill: SCHEDULE_DEFAULT_HOUR giờ ngày KẾ (Asia/Saigon) → trả UTC aware.

    Dùng chung cho schedule_router (POST /schedule) lẫn workflow gate (decision=schedule)
    khi user không truyền giờ hẹn cụ thể.
    """
    tz = ZoneInfo(SCHEDULE_TZ)
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
    local = datetime.combine(tomorrow, time(hour=SCHEDULE_DEFAULT_HOUR), tzinfo=tz)
    return local.astimezone(timezone.utc)


def _snapshot_from(row: dict) -> dict:
    """Row queue → snapshot tự chứa cho publish_now."""
    return {
        "run_id": row.get("run_id"),
        "library": row["library"],
        "video_object": row["video_object"],
        "caption": row["caption"],
        "script": row["script"],
        "text_hook": row.get("text_hook"),
    }


def tick() -> dict:
    """Quét bài tới hạn → publish từng bài (bọc try mỗi bài để 1 bài lỗi không chặn bài khác)."""
    now_utc = datetime.now(timezone.utc)
    published = skipped = failed = 0
    try:
        due = scheduled_posts.claim_due(now_utc, limit=MAX_POSTS_PER_DAY)
    except Exception as e:  # noqa: BLE001 — DB lỗi không được giết thread scheduler
        log.warning("scheduler.tick · claim_due lỗi: %s", e)
        return {"published": 0, "skipped": 0, "failed": 0, "error": str(e)}

    if due:
        log.info("scheduler.tick · %d bài tới hạn", len(due))
    for row in due:
        try:
            res = publish_service.publish_now(
                _snapshot_from(row), actor="agent:scheduler",
                trigger="scheduled", post_id=row["id"])
            status = res.get("status")
            if status == "published":
                published += 1
            elif status == "failed":
                failed += 1
            else:  # skipped | deferred
                skipped += 1
        except Exception as e:  # noqa: BLE001 — phòng thủ (publish_now vốn không raise)
            failed += 1
            log.exception("scheduler.tick · bài %s lỗi bất ngờ", row["id"])
            try:
                scheduled_posts.mark_failed(row["id"], f"tick unexpected: {e}")
            except Exception:  # noqa: BLE001
                pass

    if due:
        log.info("scheduler.tick · xong: %d đăng / %d skip / %d fail",
                 published, skipped, failed)
    return {"published": published, "skipped": skipped, "failed": failed}


def run_now() -> dict:
    """Chạy tick ngay (cho nút demo / endpoint run-now) — không đợi poller."""
    log.info("scheduler.run_now · trigger thủ công")
    return tick()


def start_scheduler() -> None:
    """Khởi động poller lúc app startup (idempotent)."""
    global _scheduler
    if not SCHEDULE_TICK_ENABLED:
        log.info("scheduler · skip: SCHEDULE_TICK_ENABLED=false")
        return
    if _scheduler is not None and _scheduler.running:
        log.info("scheduler · đã chạy, bỏ qua start lặp")
        return
    _scheduler = BackgroundScheduler(timezone=ZoneInfo(SCHEDULE_TZ))
    _scheduler.add_job(tick, IntervalTrigger(seconds=SCHEDULE_TICK_SECONDS),
                       id="publish-tick", replace_existing=True,
                       max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("scheduler · started · poller mỗi %ds · tz %s",
             SCHEDULE_TICK_SECONDS, SCHEDULE_TZ)


def shutdown_scheduler() -> None:
    """Tắt poller lúc app shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler · shutdown")
    _scheduler = None
