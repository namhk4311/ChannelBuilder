"""Library CRUD — parent của categories + videos.

Endpoints:
  GET    /api/libraries                 — list + count categories/videos per lib
  POST   /api/libraries                 — create
  PATCH  /api/libraries/{name}          — update label / description
  DELETE /api/libraries/{name}          — delete (chỉ khi rỗng)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import pg

log = logging.getLogger(__name__)
router = APIRouter(tags=["libraries"])

LIBRARY_NAME_RE = re.compile(r"^[a-z0-9_]+$")


@router.get("/api/libraries")
def list_libraries():
    with pg() as conn:
        rows = conn.execute("""
            SELECT l.name, l.label, l.description, l.created_at,
                   (SELECT COUNT(*) FROM categories WHERE library = l.name) AS category_count,
                   (SELECT COUNT(*) FROM videos     WHERE library = l.name) AS video_count
            FROM libraries l
            ORDER BY l.created_at
        """).fetchall()
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


class LibraryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80,
                      description="Slug: a-z 0-9 underscore. Vd: nhatrang_travel")
    label: Optional[str] = None
    description: Optional[str] = ""


@router.post("/api/libraries")
def create_library(body: LibraryCreate):
    if not LIBRARY_NAME_RE.match(body.name):
        raise HTTPException(400,
            "name chỉ gồm a-z 0-9 underscore (lowercase). Vd: nhatrang_travel")
    try:
        with pg() as conn:
            conn.execute("""
                INSERT INTO libraries (name, label, description)
                VALUES (%s, %s, %s)
            """, (body.name, body.label or body.name, body.description or ""))
    except psycopg.errors.UniqueViolation:
        log.warning("create library rejected: '%s' already exists", body.name)
        raise HTTPException(409, f"Library '{body.name}' đã tồn tại")
    log.info("library created: name=%s label=%s", body.name, body.label)
    return {"ok": True, "name": body.name}


class LibraryUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None


@router.patch("/api/libraries/{name}")
def update_library(name: str, body: LibraryUpdate):
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "Không có field nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in payload.keys())
    values = list(payload.values()) + [name]
    with pg() as conn:
        cur = conn.execute(
            f"UPDATE libraries SET {set_clause} WHERE name = %s",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Library không tồn tại")
    log.info("library updated: name=%s fields=%s", name, list(payload.keys()))
    return {"ok": True, "updated": list(payload.keys())}


@router.delete("/api/libraries/{name}")
def delete_library(name: str):
    with pg() as conn:
        # Block xóa nếu còn category hoặc video tham chiếu
        check = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM categories WHERE library = %s) AS n_cat,
                (SELECT COUNT(*) FROM videos     WHERE library = %s) AS n_vid
        """, (name, name)).fetchone()
        if check and (check["n_cat"] > 0 or check["n_vid"] > 0):
            log.warning("delete library '%s' blocked: %d categories + %d videos",
                        name, check["n_cat"], check["n_vid"])
            raise HTTPException(409,
                f"Library '{name}' còn {check['n_cat']} category + {check['n_vid']} video — "
                f"xóa hết trước.")
        cur = conn.execute("DELETE FROM libraries WHERE name = %s", (name,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Library không tồn tại")
    log.info("library deleted: name=%s", name)
    return {"ok": True}
