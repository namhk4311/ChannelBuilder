"""[E] Analyst — FastAPI endpoints cho UI "Phân tích batch" (mount như publisher).

GET  /api/analyst/batches   — list batch dummy khả dụng (picker UI)
POST /api/analyst/analyze   — chạy absolute gate trên 1 batch → graded + report + insight (CHƯA commit vòng học)
POST /api/analyst/confirm   — human bấm "Xác nhận scale" → persist insight_digest active (đóng vòng [E]→[B])
GET  /api/analyst/insight   — insight_digest đang active (UI hiện "vòng sau đang học từ batch X")

Mọi endpoint không raise lỗi domain ra 500 — trả status trong body (mục 4 CLAUDE.md).
`confirm` re-chạy run_analyst để lấy insight_digest CHUẨN TỪ SERVER (không tin digest
client gửi lên) rồi mới set_active_insight — tránh client bơm digest bậy vào vòng học.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import get_active_insight, list_batches, run_analyst, set_active_insight

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyst", tags=["analyst"])


class AnalyzeRequest(BaseModel):
    batch: str = Field("analyst_dummy_batch",
                       description="Tên batch (analyst_dummy_batch | analyst_dummy_badbatch)")


class ConfirmRequest(BaseModel):
    batch: str = Field(..., description="Batch đang phân tích")
    scale_ids: Optional[list[str]] = Field(
        None, description="[hiển thị/log] id các video human chọn nhân — mặc định nguyên cụm SCALE")


@router.get("/batches")
def analyst_batches() -> dict:
    return list_batches()


@router.post("/analyze")
def analyst_analyze(req: AnalyzeRequest) -> dict:
    return run_analyst(req.batch)


@router.post("/confirm")
def analyst_confirm(req: ConfirmRequest) -> dict:
    result = run_analyst(req.batch)                 # digest chuẩn từ server
    if result.get("status") != "ok":
        return {"status": "failed", "error": result.get("error"),
                "active_batch": None, "insight_digest": None}
    digest = result["insight_digest"]
    # Persist kể cả batch dở (scale_ids rỗng): digest vẫn mang tín hiệu học hợp lệ
    # (thua/đề_xuất = "tránh tả cảnh, rút ngắn") → đẩy về Creative cho vòng sau.
    set_active_insight(digest)                      # persist → runner đọc đóng vòng học
    # Client scale_ids chỉ để log/hiển thị — LỌC theo tập SCALE chuẩn của server,
    # không tin giá trị lạ (digest đã persist luôn từ server, không ảnh hưởng).
    server_scale = result.get("scale_ids") or []
    chosen = [sid for sid in (req.scale_ids or server_scale) if sid in server_scale]
    log.info("analyst · confirm batch=%s scale_ids=%s → insight active", req.batch, chosen)
    return {
        "status": "ok",
        "error": None,
        "active_batch": result["batch"],
        "scale_ids": chosen,
        "insight_digest": digest,
    }


@router.get("/insight")
def analyst_insight() -> dict:
    digest = get_active_insight()
    return {"status": "ok", "insight_digest": digest,
            "active_batch": (digest or {}).get("batch") if digest else None}
