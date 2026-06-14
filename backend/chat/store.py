# -*- coding: utf-8 -*-
"""Persistence cho chat sessions — Postgres (bảng chat_sessions, migration 0004).

Mỗi cuộc chat = 1 row; messages + spec là JSONB. Dùng helper pg() chung
(agents/producer/db.py). Conductor gọi các hàm này thay cho dict in-memory cũ.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from psycopg.types.json import Jsonb

from agents.producer.db import pg

log = logging.getLogger(__name__)


def create(conv: dict) -> None:
    with pg() as conn:
        conn.execute(
            """
            INSERT INTO chat_sessions (id, title, spec, messages, run_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conv["id"], conv.get("title"), Jsonb(conv["spec"]),
             Jsonb(conv["messages"]), conv.get("run_id")),
        )


def get(conv_id: str) -> Optional[dict]:
    with pg() as conn:
        row = conn.execute(
            """
            SELECT id, title, spec, messages, run_id, created_at, updated_at
            FROM chat_sessions WHERE id = %s
            """,
            (conv_id,),
        ).fetchone()
    if row is None:
        return None
    # JSONB → list/dict tự decode bởi psycopg; timestamptz → isoformat string.
    row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else None
    row["updated_at"] = row["updated_at"].isoformat() if row.get("updated_at") else None
    return row


def save(conv: dict) -> None:
    with pg() as conn:
        conn.execute(
            """
            UPDATE chat_sessions
               SET title = %s, spec = %s, messages = %s, run_id = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (conv.get("title"), Jsonb(conv["spec"]), Jsonb(conv["messages"]),
             conv.get("run_id"), conv["id"]),
        )


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    with pg() as conn:
        rows = conn.execute(
            """
            SELECT id, title, run_id, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    for r in rows:
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
    return rows


def delete(conv_id: str) -> bool:
    with pg() as conn:
        cur = conn.execute("DELETE FROM chat_sessions WHERE id = %s", (conv_id,))
        return cur.rowcount > 0
