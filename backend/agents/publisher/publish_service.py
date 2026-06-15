"""publish_service — 1 hàm `publish_now` đi qua đủ 4 phanh, dùng chung cho CẢ
on-demand (gate "Đăng ngay") lẫn scheduled (tick job). Đây là chỗ duy nhất tập
trung logic an toàn → phase khác chỉ gọi vào (DRY).

4 phanh: guardrail (BANNED chặn cứng) · dedup (content_hash) · limit (MAX/ngày)
· audit (mọi lần đăng/skip/block đều ghi 1 row scheduled_posts).

Không bao giờ raise — trả dict {status, reason?, detail?, post}.
  status ∈ published | skipped | deferred | failed
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from config import MAX_POSTS_PER_DAY, SCHEDULE_TZ

from . import scheduled_posts
from .guardrails import check_publishable, content_hash
from .tools import publish_video

log = logging.getLogger(__name__)


def publish_now(snapshot: dict, actor: str, trigger: str,
                post_id: Optional[int] = None) -> dict:
    """Đăng 1 bài qua đủ 4 phanh. snapshot tự chứa nội dung; không phụ thuộc state in-memory.

    on-demand (post_id=None) reserve 1 row status='publishing' SỚM (trước dedup) → bài
    đang bay hiển thị cho dedup của tiến trình khác (chống đăng đôi cùng script). scheduled
    đã có post_id sẵn ('publishing' do claim_due flip atomic).
    """
    try:
        caption = snapshot.get("caption") or ""
        script = snapshot.get("script") or ""
        text_hook = snapshot.get("text_hook")

        # ── phanh 1: guardrail nội dung (gồm text_hook overlay) — BANNED chặn cứng ──
        g = check_publishable(caption, script, text_hook)
        if not g["ok"]:
            reason = g["blocked_reason"]
            log.warning("publish_service · BLOCKED guardrail (%s) actor=%s", reason, actor)
            if post_id is None:
                row = scheduled_posts.insert(snapshot, trigger, actor,
                                             scheduled_for=None, status="blocked_guardrail")
                scheduled_posts.mark_skipped(row["id"], "blocked_guardrail", reason)
            else:
                scheduled_posts.mark_skipped(post_id, "blocked_guardrail", reason)
                row = scheduled_posts.get(post_id)
            return {"status": "failed", "reason": "blocked_guardrail", "detail": reason, "post": row}

        # Reserve slot 'publishing' sớm cho on-demand → concurrent dedup thấy bài đang bay.
        if post_id is None:
            post_id = scheduled_posts.insert(snapshot, trigger, actor,
                                             scheduled_for=None, status="publishing")["id"]

        # ── phanh 2: dedup (published + publishing in-flight), bỏ qua chính row đang xét ──
        if scheduled_posts.is_duplicate(content_hash(script), exclude_id=post_id):
            log.info("publish_service · SKIP dup (script đã/đang đăng) actor=%s", actor)
            scheduled_posts.mark_skipped(post_id, "skipped_dup", "trùng script đã/đang đăng")
            return {"status": "skipped", "reason": "skipped_dup", "post": scheduled_posts.get(post_id)}

        # ── phanh 3: limit bài/ngày ──
        if scheduled_posts.count_published_today(SCHEDULE_TZ) >= MAX_POSTS_PER_DAY:
            if trigger == "scheduled":  # dời sang ngày kế (giữ nội dung)
                scheduled_posts.defer_to_next_day(post_id)
                log.info("publish_service · DEFER (vượt %d/ngày) post=%s", MAX_POSTS_PER_DAY, post_id)
                return {"status": "deferred", "reason": "skipped_limit",
                        "post": scheduled_posts.get(post_id)}
            scheduled_posts.mark_skipped(post_id, "skipped_limit",
                                         f"vượt {MAX_POSTS_PER_DAY} bài/ngày")
            return {"status": "skipped", "reason": "skipped_limit",
                    "post": scheduled_posts.get(post_id)}

        # ── đăng thật: tải video MinIO → publish → dọn tmp ──
        try:
            from agents.producer.storage import download_to_tmp
            local_path = download_to_tmp(snapshot["video_object"])
        except Exception as e:  # noqa: BLE001
            log.warning("publish_service · download lỗi: %s", e)
            scheduled_posts.mark_failed(post_id, f"download lỗi: {e}")
            return {"status": "failed", "reason": "download_error", "detail": str(e),
                    "post": scheduled_posts.get(post_id)}

        try:
            result = publish_video(video_path=local_path, caption=caption)
        finally:
            Path(local_path).unlink(missing_ok=True)

        # ── phanh 4: audit row theo kết quả ──
        if result.get("status") == "failed":
            scheduled_posts.mark_failed(post_id, result.get("error") or "publish failed")
            return {"status": "failed", "reason": "publish_failed",
                    "detail": result.get("error"), "post": scheduled_posts.get(post_id)}

        scheduled_posts.mark_published(post_id, result.get("publish_id"), result.get("video_id"))
        log.info("publish_service · PUBLISHED actor=%s video_id=%s", actor, result.get("video_id"))
        return {"status": "published", "publish_id": result.get("publish_id"),
                "video_id": result.get("video_id"), "post": scheduled_posts.get(post_id)}

    except Exception as e:  # noqa: BLE001 — không bao giờ raise ra orchestrator/scheduler
        log.exception("publish_service · LỖI bất ngờ")
        if post_id is not None:
            try:
                scheduled_posts.mark_failed(post_id, f"unexpected: {e}")
            except Exception:  # noqa: BLE001
                pass
        return {"status": "failed", "reason": "unexpected", "detail": str(e), "post": None}
