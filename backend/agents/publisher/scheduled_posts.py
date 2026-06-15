"""DAO bảng `scheduled_posts` — queue lịch đăng (calendar + audit + dedup + limit).

Mỗi hàm mở `with pg() as conn` riêng (commit-on-exit). Atomic claim dùng
`FOR UPDATE SKIP LOCKED` chống đăng đôi khi >1 tick/replica chạy song song.

`snapshot` = dict tự chứa: {run_id?, library, video_object, caption, script, text_hook?}.
status: pending|publishing|published|failed|skipped_dup|skipped_limit|blocked_guardrail|cancelled
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from agents.producer.db import pg

from .guardrails import content_hash

# Cột trả về cho UI/caller (đủ render calendar, không lộ gì nhạy cảm).
_COLS = (
    "id, run_id, library, video_object, caption, script, text_hook, content_hash, "
    "trigger, actor, status, scheduled_for, published_at, tiktok_publish_id, "
    "tiktok_video_id, error, created_at, updated_at"
)


def insert(snapshot: dict, trigger: str, actor: str,
           scheduled_for: Optional[datetime] = None,
           status: str = "pending") -> dict:
    """Chèn 1 row queue. content_hash tự tính từ script. RETURNING full row."""
    with pg() as conn:
        cur = conn.execute(
            f"""
            INSERT INTO scheduled_posts
              (run_id, library, video_object, caption, script, text_hook,
               content_hash, trigger, actor, status, scheduled_for)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING {_COLS}
            """,
            (snapshot.get("run_id"), snapshot["library"], snapshot["video_object"],
             snapshot["caption"], snapshot["script"], snapshot.get("text_hook"),
             content_hash(snapshot["script"]), trigger, actor, status, scheduled_for),
        )
        return cur.fetchone()


def is_duplicate(hash_: str, exclude_id: Optional[int] = None) -> bool:
    """True nếu đã/đang có bài cùng content_hash (status published HOẶC publishing đang bay).

    Tính cả `publishing` (in-flight) → chặn on-demand + scheduled đăng đôi cùng script
    trong lúc cả 2 đang upload (chưa kịp mark published). `exclude_id` bỏ qua chính row
    đang xét (đường scheduled đã ở publishing trước khi check).
    """
    with pg() as conn:
        cur = conn.execute(
            "SELECT 1 FROM scheduled_posts "
            "WHERE content_hash=%s AND status IN ('published','publishing') "
            "AND (%s::bigint IS NULL OR id <> %s) LIMIT 1",
            (hash_, exclude_id, exclude_id),
        )
        return cur.fetchone() is not None


def count_published_today(tz: str) -> int:
    """Đếm bài published kể từ đầu ngày hôm nay theo timezone `tz` (so sánh ở UTC)."""
    local_now = datetime.now(ZoneInfo(tz))
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=ZoneInfo(tz))
    start_utc = start_local.astimezone(timezone.utc)
    with pg() as conn:
        cur = conn.execute(
            "SELECT count(*) AS n FROM scheduled_posts "
            "WHERE status='published' AND published_at >= %s",
            (start_utc,),
        )
        return int(cur.fetchone()["n"])


def claim_due(now_utc: datetime, limit: int) -> list[dict]:
    """Atomic claim: flip status pending→publishing cho bài tới hạn rồi RETURNING.

    `FOR UPDATE SKIP LOCKED` → 2 tick song song không claim cùng row. Flip-then-release
    (không giữ lock suốt lúc upload nhiều phút) — publish chạy NGOÀI lock.
    """
    with pg() as conn:
        cur = conn.execute(
            f"""
            UPDATE scheduled_posts SET status='publishing', updated_at=now()
            WHERE id IN (
                SELECT id FROM scheduled_posts
                WHERE status='pending' AND scheduled_for IS NOT NULL AND scheduled_for <= %s
                ORDER BY scheduled_for ASC
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            RETURNING {_COLS}
            """,
            (now_utc, limit),
        )
        return cur.fetchall()


def mark_published(id_: int, publish_id: Optional[str], video_id: Optional[str]) -> None:
    with pg() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET status='published', published_at=now(), "
            "tiktok_publish_id=%s, tiktok_video_id=%s, error=NULL, updated_at=now() WHERE id=%s",
            (publish_id, video_id, id_),
        )


def mark_failed(id_: int, error: str) -> None:
    with pg() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET status='failed', error=%s, updated_at=now() WHERE id=%s",
            ((error or "")[:1000], id_),
        )


def mark_skipped(id_: int, status: str, reason: str) -> None:
    """status ∈ {skipped_dup, skipped_limit, blocked_guardrail}."""
    with pg() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET status=%s, error=%s, updated_at=now() WHERE id=%s",
            (status, (reason or "")[:1000], id_),
        )


def defer_to_next_day(id_: int) -> None:
    """Vượt limit ngày → dời bài (giữ nội dung) sang +1 ngày, status về pending."""
    with pg() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET status='pending', "
            "scheduled_for = COALESCE(scheduled_for, now()) + interval '1 day', "
            "updated_at=now() WHERE id=%s",
            (id_,),
        )


def list_posts(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    """List calendar (mới nhất trước). Lọc theo status nếu truyền."""
    with pg() as conn:
        if status:
            cur = conn.execute(
                f"SELECT {_COLS} FROM scheduled_posts WHERE status=%s "
                "ORDER BY COALESCE(scheduled_for, created_at) DESC LIMIT %s",
                (status, limit),
            )
        else:
            cur = conn.execute(
                f"SELECT {_COLS} FROM scheduled_posts "
                "ORDER BY COALESCE(scheduled_for, created_at) DESC LIMIT %s",
                (limit,),
            )
        return cur.fetchall()


def get(id_: int) -> Optional[dict]:
    with pg() as conn:
        cur = conn.execute(f"SELECT {_COLS} FROM scheduled_posts WHERE id=%s", (id_,))
        return cur.fetchone()


def cancel(id_: int) -> Optional[dict]:
    """Huỷ — CHỈ khi đang pending. Trả row đã huỷ, hoặc None nếu không hợp lệ."""
    with pg() as conn:
        cur = conn.execute(
            f"UPDATE scheduled_posts SET status='cancelled', updated_at=now() "
            f"WHERE id=%s AND status='pending' RETURNING {_COLS}",
            (id_,),
        )
        return cur.fetchone()
