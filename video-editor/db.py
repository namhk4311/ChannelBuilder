"""Postgres connection helper + schema init. Dùng bên trong package video."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from config import POSTGRES_URL

log = logging.getLogger(__name__)


@contextmanager
def pg() -> Iterator[psycopg.Connection]:
    """
    Postgres connection với dict_row factory.
    Commit khi exit không có exception, rollback nếu có.
    """
    conn = psycopg.connect(POSTGRES_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Tạo 2 bảng idempotent. categories TRƯỚC vì videos có FK sang nó.
    """
    log.info("init_db: connect %s", POSTGRES_URL.split("@")[-1])
    with pg() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                name         TEXT PRIMARY KEY,
                label        TEXT,
                default_tag  TEXT,
                description  TEXT DEFAULT '',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
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
        conn.execute("CREATE INDEX IF NOT EXISTS videos_category_idx ON videos(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS videos_clip_tag_idx ON videos(clip_tag)")
    log.info("init_db: schema ready (categories + videos)")
