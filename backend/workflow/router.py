"""[★] Orchestrator — FastAPI endpoints cho UI workflow.

GET  /api/workflow/agents              — catalog 4 agent + tools (live TOOL_DEFINITIONS)
POST /api/workflow/runs                — start run nền, trả run state ngay
GET  /api/workflow/runs                — danh sách run (mới nhất trước)
GET  /api/workflow/runs/{run_id}       — chi tiết run (UI poll 1.5s khi đang chạy)
POST /api/workflow/runs/{run_id}/approval — human gate: duyệt / từ chối đăng
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import runner
from .catalog import get_agents

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class StartRunRequest(BaseModel):
    topic: Optional[str] = Field(None, description="Chủ đề cho Creative")
    library: str = Field("vng_insider", description="Thư viện clip cho Producer")
    subtitles: bool = True
    n_ideas: int = Field(5, ge=1, le=10)
    # Music params — mirror ProduceRequest, default cùng giá trị
    music_track_id: Optional[str] = Field(None,
                         description="ID track nhạc nền từ /api/music. None → không nhạc")
    beat_sync: bool = Field(True,
                         description="Snap cut vào beat. Chỉ effective khi có music_track_id")
    music_volume: float = Field(0.3, ge=0.05, le=1.0,
                         description="Base gain music (0.3 ≈ -10dB)")


class ApprovalRequest(BaseModel):
    approve: bool


@router.get("/agents")
def workflow_agents() -> dict:
    return {"agents": get_agents()}


@router.post("/runs")
def start_run(req: StartRunRequest) -> dict:
    topic = (req.topic or "").strip() or None
    return runner.start_run(topic=topic, library=req.library,
                            subtitles=req.subtitles, n_ideas=req.n_ideas,
                            music_track_id=req.music_track_id,
                            beat_sync=req.beat_sync,
                            music_volume=req.music_volume)


@router.get("/runs")
def list_runs() -> dict:
    return {"runs": runner.list_runs()}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = runner.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run không tồn tại (server restart?)")
    return run


@router.post("/runs/{run_id}/approval")
def decide_gate(run_id: str, req: ApprovalRequest) -> dict:
    run = runner.decide_gate(run_id, req.approve)
    if run is None:
        raise HTTPException(404, "Run không tồn tại (server restart?)")
    log.info("workflow %s · gate %s", run_id, "APPROVED" if req.approve else "REJECTED")
    return run
