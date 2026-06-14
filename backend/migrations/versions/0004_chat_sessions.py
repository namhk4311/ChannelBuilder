"""chat_sessions: lịch sử chat tab Chat (DB-backed)

Revision ID: 0004_chat
Revises: 0003_music
Create Date: 2026-06-14

Mỗi cuộc chat = 1 row. messages + spec lưu JSONB ngay trong row (hội thoại ngắn,
luôn load nguyên cuộc → đơn giản hơn bảng messages riêng). Survive reload + restart
server. Sidebar lấy từ index updated_at DESC.
"""
from __future__ import annotations

from alembic import op

revision = "0004_chat"
down_revision = "0003_music"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            spec        JSONB NOT NULL DEFAULT '{}'::jsonb,
            messages    JSONB NOT NULL DEFAULT '[]'::jsonb,
            run_id      TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS chat_sessions_updated_idx "
        "ON chat_sessions (updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_sessions")
