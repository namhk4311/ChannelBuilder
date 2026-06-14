"""music_tracks: thư viện nhạc nền + beat times cached

Revision ID: 0003_music
Revises: 0002_libraries
Create Date: 2026-06-13

Wow feature #1: beat-sync cuts. Bảng lưu mỗi mp3 nhạc nền với BPM và list
timestamps các beat (detect bằng librosa lúc upload, cache vào JSONB để
không phải detect lại mỗi lần dùng).
"""
from __future__ import annotations

from alembic import op

revision = "0003_music"
down_revision = "0002_libraries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS music_tracks (
            id           TEXT PRIMARY KEY,
            label        TEXT,
            file         TEXT NOT NULL,
            object_name  TEXT NOT NULL,
            duration_sec REAL,
            bpm          REAL,
            beat_times   JSONB NOT NULL,
            mood         TEXT,
            size_bytes   BIGINT,
            uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS music_tracks")
