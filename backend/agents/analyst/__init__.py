"""[E] Analyst — absolute gate + insight digest → đẩy về [B] Creative cho vòng sau.

Public surface (đúng tool pattern mục 4 — Orchestrator import trực tiếp):
    from agents.analyst import TOOL_DEFINITIONS, execute_tool   # LLM tool calling
    from agents.analyst import run_analyst                      # direct call
    from agents.analyst import get_active_insight, set_active_insight  # đóng vòng học
    from agents.analyst import analyst_router                   # FastAPI mount (Phase 4)

Lõi "logic chấm thật" (gate.py) thuần stdlib, deterministic — testable độc lập,
không phụ thuộc LLM / network / DB. Data demo là dummy batch (metric thật TikTok
chưa có retention_3s — xem R1 trong brainstorm); input contract giữ nguyên để
metric thật drop-in về sau.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .digest import build_insight_digest
from .gate import grade_batch
from .report import build_report

log = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
_STATE_PATH = os.path.join(_DIR, "analyst_state.json")

# Batch dummy khả dụng: tên → file. Tên (file stem) dùng làm khóa ở API/UI.
_BATCHES: dict[str, str] = {
    "analyst_dummy_batch": "analyst_dummy_batch.json",
    "analyst_dummy_badbatch": "analyst_dummy_badbatch.json",
}


# ------------------------------------------------------------------ batch load

def _load_batch(batch_name: str) -> dict[str, Any] | None:
    fname = _BATCHES.get(batch_name)
    if fname is None:
        return None
    try:
        with open(os.path.join(_DIR, fname), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001 — thiếu/hỏng file không được raise
        log.warning("analyst · load batch %s lỗi: %s", batch_name, e)
        return None


def list_batches() -> dict[str, Any]:
    """Danh sách batch dummy khả dụng cho UI picker."""
    items = []
    for name in _BATCHES:
        data = _load_batch(name) or {}
        items.append({
            "name": name,
            "label": data.get("nhan", name),
            "n_videos": len(data.get("videos") or []),
        })
    return {"status": "ok", "batches": items}


def run_analyst(batch_name: str = "analyst_dummy_batch") -> dict[str, Any]:
    """Chấm 1 batch → graded + insight_digest + report + scale_ids. Không raise.

    Pipeline thuần Python: load dummy → grade_batch (absolute gate) →
    build_insight_digest (rút thắng/thua → [B]) → build_report (người đọc).
    scale_ids = id các video SCALE, theo retention giảm dần.
    """
    data = _load_batch(batch_name)
    if data is None:
        return {"status": "failed",
                "error": f"Batch không tồn tại: {batch_name} (có: {', '.join(_BATCHES)})"}
    threshold = int(data.get("nguong_tuyet_doi_retention", 65))
    label = data.get("batch", batch_name)
    graded = grade_batch(data.get("videos") or [], threshold=threshold)
    videos = graded["videos"]
    scale_ids = [v["id"] for v in sorted(
        (v for v in videos if v["label"] == "SCALE"),
        key=lambda v: v.get("retention_3s_pct", 0), reverse=True)]
    insight_digest = build_insight_digest(videos, label)
    report = build_report(videos, insight_digest, label,
                          threshold=threshold, top_k=graded["top_k"])
    return {
        "status": "ok",
        "batch": label,
        "batch_name": batch_name,
        "threshold": threshold,
        "top_k": graded["top_k"],
        "videos": videos,
        "insight_digest": insight_digest,
        "report": report,
        "scale_ids": scale_ids,
    }


# ------------------------------------------------------------- insight store
# Persist insight_digest đang active ra file (giống tokens.json publisher) — sống
# qua restart để quay demo nhiều take. Runner đọc get_active_insight() đóng vòng [E]→[B].

def set_active_insight(digest: dict[str, Any] | None) -> None:
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"insight_digest": digest, "updated_at": _now()},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        log.warning("analyst · ghi insight state lỗi: %s", e)


def get_active_insight() -> dict[str, Any] | None:
    """insight_digest đang active, hoặc None (thiếu file / parse lỗi → None, không raise)."""
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            return (json.load(f) or {}).get("insight_digest")
    except Exception:  # noqa: BLE001 — chưa confirm batch nào / file hỏng
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------- tool surface

TOOL_DEFINITIONS = [
    {
        "name": "analyze_batch",
        "description": (
            "Chạy absolute gate (2 phanh: top 20% lô + ngưỡng tuyệt đối retention_3s) "
            "trên 1 batch video → nhãn SCALE/MONITOR/KILL từng video + insight digest "
            "(thắng/thua/đề xuất vòng sau) + báo cáo người đọc. Chỉ ĐỀ XUẤT, human confirm scale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "batch": {"type": "string",
                          "description": "Tên batch dummy (analyst_dummy_batch | analyst_dummy_badbatch)"},
            },
        },
    },
    {
        "name": "list_batches",
        "description": "Liệt kê các batch khả dụng để phân tích (tên + nhãn + số video).",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_DISPATCH = {
    "analyze_batch": lambda batch="analyst_dummy_batch", **_: run_analyst(batch),
    "list_batches": lambda **_: list_batches(),
}


def execute_tool(name: str, tool_input: dict | None = None) -> dict:
    """Entry point hợp nhất cho Orchestrator. Không bao giờ raise."""
    fn = _DISPATCH.get(name)
    if fn is None:
        log.warning("execute_tool · tool không tồn tại: %s (có: %s)",
                    name, ", ".join(_DISPATCH))
        return {"status": "failed", "error": f"Tool không tồn tại: {name}"}
    try:
        return fn(**(tool_input or {}))
    except TypeError as e:
        log.warning("execute_tool · sai input cho %s: %s", name, e)
        return {"status": "failed", "error": f"Sai input: {e}"}


# analyst_router re-export ở Phase 4 (router.py). Import mềm để Phase 1-3 chưa có
# router vẫn import được package.
try:
    from .router import router as analyst_router  # noqa: F401
except Exception as e:  # noqa: BLE001 — router (Phase 4) chưa tồn tại / FastAPI thiếu
    analyst_router = None  # type: ignore[assignment]
    log.debug("analyst · router chưa khả dụng: %s", e)


__all__ = [
    "TOOL_DEFINITIONS",
    "execute_tool",
    "run_analyst",
    "list_batches",
    "grade_batch",
    "get_active_insight",
    "set_active_insight",
    "analyst_router",
]
