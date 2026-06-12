"""Category CRUD — scoped theo library.

PK composite (library, name) → mọi endpoint cần `library` để định danh.
List filter qua `?library=X`. Create/Patch/Delete dùng `?library=X` query param
hoặc field trong body.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import psycopg
from fastapi import APIRouter, HTTPException, Query
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
def list_categories(library: Optional[str] = Query(None, description="Filter theo library")):
    """List categories. Nếu library=None, trả toàn bộ (mọi library)."""
    with pg() as conn:
        if library:
            rows = conn.execute("""
                SELECT c.name, c.label, c.library, c.default_tag, c.description, c.created_at,
                       COUNT(v.id) AS video_count
                FROM categories c
                LEFT JOIN videos v ON v.library = c.library AND v.category = c.name
                WHERE c.library = %s
                GROUP BY c.library, c.name, c.label, c.default_tag, c.description, c.created_at
                ORDER BY c.name
            """, (library,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT c.name, c.label, c.library, c.default_tag, c.description, c.created_at,
                       COUNT(v.id) AS video_count
                FROM categories c
                LEFT JOIN videos v ON v.library = c.library AND v.category = c.name
                GROUP BY c.library, c.name, c.label, c.default_tag, c.description, c.created_at
                ORDER BY c.library, c.name
            """).fetchall()
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return rows


# ─── Create ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    library: str = Field(..., min_length=1, max_length=80,
                         description="Library slug — phải tồn tại")
    label: Optional[str] = None
    default_tag: Optional[str] = None
    description: Optional[str] = ""


@router.post("/api/categories")
def create_category(body: CategoryCreate):
    if not CATEGORY_NAME_RE.match(body.name):
        raise HTTPException(400,
            "name chỉ gồm a-z 0-9 underscore (lowercase). Vd: 01_campus_ngoaicanh")
    default_tag = body.default_tag or default_tag_from_category(body.name)
    try:
        with pg() as conn:
            conn.execute("""
                INSERT INTO categories (library, name, label, default_tag, description)
                VALUES (%s, %s, %s, %s, %s)
            """, (body.library, body.name, body.label, default_tag, body.description or ""))
    except psycopg.errors.UniqueViolation:
        log.warning("create category rejected: '%s/%s' already exists", body.library, body.name)
        raise HTTPException(409, f"Category '{body.name}' đã tồn tại trong library '{body.library}'")
    except psycopg.errors.ForeignKeyViolation:
        log.warning("create category rejected: library '%s' không tồn tại", body.library)
        raise HTTPException(400, f"Library '{body.library}' chưa tồn tại")
    log.info("category created: library=%s name=%s default_tag=%s",
             body.library, body.name, default_tag)
    return {"ok": True, "library": body.library, "name": body.name, "default_tag": default_tag}


# ─── Patch ───────────────────────────────────────────────────────────────────

class CategoryUpdate(BaseModel):
    label: Optional[str] = None
    default_tag: Optional[str] = None
    description: Optional[str] = None


@router.patch("/api/categories/{name}")
def update_category(name: str, body: CategoryUpdate,
                    library: str = Query(..., description="Library chứa category")):
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "Không có field nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in payload.keys())
    values = list(payload.values()) + [library, name]
    with pg() as conn:
        cur = conn.execute(
            f"UPDATE categories SET {set_clause} WHERE library = %s AND name = %s",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, f"Category '{name}' không tồn tại trong library '{library}'")
    log.info("category updated: library=%s name=%s fields=%s",
             library, name, list(payload.keys()))
    return {"ok": True, "updated": list(payload.keys())}


# ─── Delete ──────────────────────────────────────────────────────────────────

@router.delete("/api/categories/{name}")
def delete_category(name: str,
                    library: str = Query(..., description="Library chứa category")):
    with pg() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS n FROM videos WHERE library = %s AND category = %s",
            (library, name),
        ).fetchone()
        if count_row and count_row["n"] > 0:
            log.warning("delete category '%s/%s' blocked: %d video remaining",
                        library, name, count_row["n"])
            raise HTTPException(409,
                f"Còn {count_row['n']} video trong '{library}/{name}', xoá hết trước.")
        cur = conn.execute(
            "DELETE FROM categories WHERE library = %s AND name = %s",
            (library, name),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Category không tồn tại")
    log.info("category deleted: library=%s name=%s", library, name)
    return {"ok": True}
