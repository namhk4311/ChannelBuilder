"""scheduled_posts: queue lịch đăng TikTok (calendar + audit + dedup + limit)

Revision ID: 0004_scheduled
Revises: 0003_music
Create Date: 2026-06-14

1 bảng = 4 vai trò (DRY): calendar bài hẹn, audit log mọi lần đăng, dedup theo
content_hash(script), và đếm limit/ngày. Áp cho CẢ on-demand lẫn scheduled.

scheduled_for NULL = đăng ngay (on-demand); có giá trị = giờ hẹn (lưu UTC, tick
job poller quét `scheduled_for <= now`).
"""
from __future__ import annotations

from alembic import op

revision = "0004_scheduled"
down_revision = "0003_music"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id                BIGSERIAL PRIMARY KEY,
            run_id            TEXT,
            library           TEXT NOT NULL,
            video_object      TEXT NOT NULL,
            caption           TEXT NOT NULL,
            script            TEXT NOT NULL,
            text_hook         TEXT,
            content_hash      TEXT NOT NULL,
            trigger           TEXT NOT NULL,
            actor             TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending',
            scheduled_for     TIMESTAMPTZ,
            published_at      TIMESTAMPTZ,
            tiktok_publish_id TEXT,
            tiktok_video_id   TEXT,
            error             TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Tick query: tìm bài pending tới hạn.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_scheduled_posts_status_scheduled_for
        ON scheduled_posts (status, scheduled_for)
    """)
    # Dedup theo nội dung script.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_scheduled_posts_content_hash
        ON scheduled_posts (content_hash)
    """)
    # Đếm limit/ngày theo published_at.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_scheduled_posts_status_published_at
        ON scheduled_posts (status, published_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduled_posts")
