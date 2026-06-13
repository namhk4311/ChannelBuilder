"""[A] Scout — quét trend thị trường + seed benchmark tuyệt đối cho vòng đánh giá.

Public surface (đúng tool pattern mục 4 — Orchestrator import trực tiếp):
    from agents.scout import TOOL_DEFINITIONS, execute_tool   # LLM tool calling
    from agents.scout import scan_trends, run_scout           # direct call

2 lớp:
  • scout_tools.scan_trends — phân tích deterministic (Python thuần), không LLM.
  • scout_fetcher.{fetch_from_samples,extract_videos} — browse + LLM extract data
    thật (dùng SCOUT_MODEL). Import bọc try/except: thiếu config/dep không được
    làm hỏng scan_trends (đường pipeline sống còn).
"""
from __future__ import annotations

import logging

from .scout_tools import (
    TOOL_DEFINITIONS as _SCAN_DEFS,
    scan_trends,
)
from .scout_tools import _DISPATCH as _SCAN_DISPATCH

log = logging.getLogger(__name__)

# Fetcher (LLM extract) — import mềm để scan_trends luôn dùng được.
_FETCH_DEFS: list[dict] = []
_FETCH_DISPATCH: dict = {}
fetch_from_samples = None  # type: ignore[assignment]
extract_videos = None  # type: ignore[assignment]
try:
    from .scout_fetcher import (
        TOOL_DEFINITIONS as _FETCH_DEFS,  # noqa: F811
        extract_videos,  # noqa: F811
        fetch_from_samples,  # noqa: F811
    )
    from .scout_fetcher import _DISPATCH as _FETCH_DISPATCH  # noqa: F811
except Exception as e:  # noqa: BLE001 — thiếu config/requests không được sập Scout
    log.warning("Scout fetcher không load được (LLM extract sẽ không khả dụng): %s", e)

TOOL_DEFINITIONS = [*_SCAN_DEFS, *_FETCH_DEFS]
_DISPATCH = {**_SCAN_DISPATCH, **_FETCH_DISPATCH}


def execute_tool(name: str, tool_input: dict) -> dict:
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


def run_scout(top_n: int = 3, prefer_live: bool = True) -> dict:
    """Trend digest cho pipeline orchestrator.

    prefer_live (mặc định True): chạy Scout Agent LLM — browse + extract các trang
    search TikTok đã lưu (`fetch_from_samples`, dùng SCOUT_MODEL) → phân tích
    `scan_trends(metric_field='likes')` = DATA THẬT từ TikTok. LLM chỉ làm phần
    hiểu ngôn ngữ (extract video từ trang search); phân tích/benchmark vẫn
    deterministic (không để LLM tự bịa số).

    Fallback (LLM lỗi — thiếu SCOUT_MODEL/key, 429, không có samples, extract rỗng):
    `scan_trends` trên dataset seed bundled (deterministic, retention_3s_pct) để
    pipeline không chết ở step đầu.

    Gắn top-level `source`: "llm" (data thật từ LLM) | "seed" (fallback dataset seed)
    để orchestrator quyết data_source hiển thị trên UI.
    """
    if prefer_live and fetch_from_samples is not None:
        fetched = fetch_from_samples()
        if fetched.get("status") == "ok" and fetched.get("videos"):
            result = scan_trends(videos=fetched["videos"], metric_field="likes", top_n=top_n)
            if result.get("status") == "ok":
                result["source"] = "llm"
                result["fetch_note"] = fetched.get("error")  # phần tử bị bỏ khi extract (nếu có)
                log.info("Scout: LLM extract %d video từ samples → digest (metric=likes)",
                         len(fetched["videos"]))
                return result
            log.warning("Scout: scan_trends trên data LLM lỗi (%s) → fallback dataset seed",
                        result.get("error"))
        else:
            log.warning("Scout: fetch_from_samples lỗi (%s) → fallback dataset seed",
                        fetched.get("error"))
    result = scan_trends(top_n=top_n)
    result["source"] = "seed"
    return result


__all__ = [
    "TOOL_DEFINITIONS",
    "execute_tool",
    "scan_trends",
    "run_scout",
    "fetch_from_samples",
    "extract_videos",
]
