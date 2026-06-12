"""Postgres connection helper. DDL nằm ở migrations/versions/ (Alembic)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from config import POSTGRES_URL


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
