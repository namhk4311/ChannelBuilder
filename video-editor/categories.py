"""Category CRUD + helpers tạo default_tag."""
from __future__ import annotations

import logging
import re
from typing import Optional

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .db import pg

log = logging.getLogger(__name__)
router = APIRouter(tags=["categories"])

CATEGORY_NAME_RE = re.compile(r"^[a-z0-9_]+$")


# ─── Helpers (cũng dùng bởi importer.py) ────────────────────────────────────

def default_tag_from_clip_id(clip_id: str) -> str:
    """campusngoaicanh_bancongcang_01 → campusngoaicanh"""
    return clip_id.split("_", 1)[0] if "_" in clip_id else clip_id


def default_tag_from_category(name: str) -> str:
    """01_campus_ngoaicanh → campusngoaicanh"""
    parts = name.split("_")
    if parts and parts[0].isdigit():
        parts = parts[1:]
    return "".join(parts)


# ─── List ────────────────────────────────────────────────────────────────────

@router.get("/api/categories")
def list_categories():
    with pg() as conn:
        rows = conn.execute("""
            SELECT c.name, c.label, c.default_tag, c.description, c.created_at,
                   COUNT(v.id) AS video_count
            FROM categories c
            LEFT JOIN videos v ON v.category = c.name
            GROUP BY c.name, c.label, c.default_tag, c.description, c.created_at
            ORDER BY c.name
        """).fetchall()
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


# ─── Create ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    label: Optional[str] = None
    default_tag: Optional[str] = None
    description: Optional[str] = ""


@router.post("/api/categories")
def create_category(body: CategoryCreate):
    if not CATEGORY_NAME_RE.match(body.name):
        raise HTTPException(
            400,
            "name chỉ gồm a-z 0-9 underscore (lowercase). Vd: 01_campus_ngoaicanh",
        )
    default_tag = body.default_tag or default_tag_from_category(body.name)
    try:
        with pg() as conn:
            conn.execute("""
                INSERT INTO categories (name, label, default_tag, description)
                VALUES (%s, %s, %s, %s)
            """, (body.name, body.label, default_tag, body.description or ""))
    except psycopg.errors.UniqueViolation:
        log.warning("create category rejected: '%s' already exists", body.name)
        raise HTTPException(409, f"Category '{body.name}' đã tồn tại")
    log.info("category created: name=%s default_tag=%s", body.name, default_tag)
    return {"ok": True, "name": body.name, "default_tag": default_tag}


# ─── Patch ───────────────────────────────────────────────────────────────────

class CategoryUpdate(BaseModel):
    label: Optional[str] = None
    default_tag: Optional[str] = None
    description: Optional[str] = None


@router.patch("/api/categories/{name}")
def update_category(name: str, body: CategoryUpdate):
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "Không có field nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in payload.keys())
    values = list(payload.values()) + [name]
    with pg() as conn:
        cur = conn.execute(
            f"UPDATE categories SET {set_clause} WHERE name = %s",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Category không tồn tại")
    log.info("category updated: name=%s fields=%s", name, list(payload.keys()))
    return {"ok": True, "updated": list(payload.keys())}


# ─── Delete ──────────────────────────────────────────────────────────────────

@router.delete("/api/categories/{name}")
def delete_category(name: str):
    with pg() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM videos WHERE category = %s", (name,)
        ).fetchone()
        if count_row and count_row["n"] > 0:
            log.warning("delete category '%s' blocked: %d video remaining",
                        name, count_row["n"])
            raise HTTPException(
                409,
                f"Còn {count_row['n']} video trong category '{name}', xoá hết trước.",
            )
        cur = conn.execute("DELETE FROM categories WHERE name = %s", (name,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Category không tồn tại")
    log.info("category deleted: name=%s", name)
    return {"ok": True}
