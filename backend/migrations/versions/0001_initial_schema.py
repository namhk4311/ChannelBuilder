"""initial schema: categories + videos + tts_cache

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-12

Port y nguyên DDL từ agents/producer/db.py::init_db() trước khi xóa hàm đó.
Dùng `CREATE TABLE IF NOT EXISTS` → lần đầu chạy trên DB đã có data sẽ no-op
(adopt existing schema pattern), Alembic chỉ insert revision vào
alembic_version rồi xong, không drop, không re-create.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            name         TEXT PRIMARY KEY,
            label        TEXT,
            default_tag  TEXT,
            description  TEXT DEFAULT '',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id              TEXT PRIMARY KEY,
            file            TEXT NOT NULL,
            category        TEXT NOT NULL
                REFERENCES categories(name)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            clip_tag        TEXT NOT NULL,
            description     TEXT DEFAULT '',
            mood            TEXT DEFAULT '',
            duration_sec    REAL,
            has_people      BOOLEAN DEFAULT FALSE,
            people_note_raw TEXT DEFAULT '',
            resolution      TEXT,
            notes           TEXT DEFAULT '',
            object_name     TEXT NOT NULL,
            size_bytes      BIGINT,
            uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS videos_category_idx ON videos(category)")
    op.execute("CREATE INDEX IF NOT EXISTS videos_clip_tag_idx ON videos(clip_tag)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS tts_cache (
            hash         TEXT PRIMARY KEY,
            voice_id     TEXT NOT NULL,
            model_id     TEXT NOT NULL,
            script       TEXT NOT NULL,
            object_name  TEXT NOT NULL,
            voice_url    TEXT NOT NULL,
            alignment    JSONB,
            duration_sec REAL,
            size_bytes   BIGINT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hit_count    INTEGER NOT NULL DEFAULT 0
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tts_cache")
    op.execute("DROP INDEX IF EXISTS videos_clip_tag_idx")
    op.execute("DROP INDEX IF EXISTS videos_category_idx")
    op.execute("DROP TABLE IF EXISTS videos")
    op.execute("DROP TABLE IF EXISTS categories")
