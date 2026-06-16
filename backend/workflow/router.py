"""[★] Orchestrator — FastAPI endpoints cho UI workflow.

GET  /api/workflow/agents              — catalog 4 agent + tools (live TOOL_DEFINITIONS)
POST /api/workflow/runs                — start run nền, trả run state ngay
GET  /api/workflow/runs                — danh sách run (mới nhất trước)
GET  /api/workflow/runs/{run_id}       — chi tiết run (UI poll 1.5s khi đang chạy)
POST /api/workflow/runs/{run_id}/approval — human gate: duyệt / từ chối đăng
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

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
    music_volume: float = Field(0.3, ge=0.3, le=0.5,
                         description="Base gain music — clamped 0.3-0.5 (~-10 tới -6dB)")
    review_script: bool = Field(False,
                         description="Dừng ở gate cho human duyệt/sửa kịch bản trước khi dựng video")
    publish_mode: str = Field("review_publish",
                         pattern="^(review_publish|schedule)$",
                         description="Chế độ đăng: 'review_publish' (duyệt → đăng ngay) | 'schedule' (duyệt → lên lịch)")
    qc_mode: str = Field("auto",
                         pattern="^(auto|confirm)$",
                         description="QC kịch bản: 'auto' (AI tự sửa lỗi nặng rồi dựng) | 'confirm' (dừng gate cho human duyệt/viết lại)")
    # Video thông tin (mode="info") — mirror các field chat conductor đã đẩy xuống runner.
    # mode="vlog" (mặc định, ghép clip) | "info" (gen ảnh AI / nền brand + banner động).
    mode: str = Field("vlog", pattern="^(vlog|info)$",
                         description="Loại video: 'vlog' (clip có sẵn) | 'info' (video thông tin)")
    event_text: Optional[str] = Field(None,
                         description="Nội dung thông tin (chỉ dùng khi mode='info', tối thiểu ~20 ký tự)")
    visual_style: str = Field("image", pattern="^(image|solid)$",
                         description="Phong cách hình ảnh info: 'image' (gen ảnh AI 1-3 cảnh) | 'solid' (nền brand 3-5 cảnh)")
    brand: str = Field("vng",
                         description="Brand theme cho visual_style='solid' (vng/anthropic/neutral_dark/neutral_light)")
    n_scenes: Optional[int] = Field(None, ge=1, le=8,
                         description="Số cảnh info — None → mặc định theo visual_style. Server clamp về dải hợp lệ của style.")

    @field_validator("brand")
    @classmethod
    def _brand_known(cls, v: str) -> str:
        # Brand lạ → 422 thay vì âm thầm fallback (chỉ check khi field được gửi; default 'vng' luôn hợp lệ).
        from agents.event_game.visual_styles import BRAND_THEMES
        if v not in BRAND_THEMES:
            raise ValueError(f"brand không hợp lệ: {v!r} (hợp lệ: {', '.join(BRAND_THEMES)})")
        return v


class ApprovalRequest(BaseModel):
    # decision = lựa chọn mới (3 nhánh). approve = field cũ (backward-compat).
    decision: Optional[str] = Field(
        None, description="'now' (đăng ngay) | 'schedule' (lên lịch) | 'reject'")
    scheduled_for: Optional[datetime] = Field(
        None, description="Giờ hẹn ISO UTC — chỉ dùng khi decision='schedule'")
    approve: Optional[bool] = Field(None, description="[deprecated] True→now, False→reject")


class IdeaDecisionRequest(BaseModel):
    approve: bool
    idea_index: Optional[int] = Field(None, description="Chỉ số ý tưởng được chọn (0-based)")


class ScriptDecisionRequest(BaseModel):
    approve: bool = True
    decision: Optional[str] = Field(
        None, pattern="^(approve|regenerate|reject)$",
        description="'approve' | 'regenerate' (cho [B] viết lại theo QC) | 'reject'. None → dùng `approve` bool")
    script: Optional[str] = Field(None, description="Bản kịch bản đã sửa (optional). None = dùng bản gốc")
    caption: Optional[str] = Field(None, description="Caption đã sửa (optional). None = dùng bản gốc")
    hashtags: Optional[list[str]] = Field(None, description="Hashtag đã sửa (optional). None = dùng bản gốc")


@router.get("/agents")
def workflow_agents() -> dict:
    return {"agents": get_agents()}


@router.get("/info-options")
def info_options() -> dict:
    """Option cho form 'Video thông tin' — single source of truth = visual_styles.py.
    Frontend render dropdown visual_style / brand / n_scenes từ đây (không hardcode → không lệch)."""
    from agents.event_game.visual_styles import (
        VISUAL_STYLES, BRAND_THEMES, DEFAULT_VISUAL_STYLE, DEFAULT_BRAND,
    )
    return {
        "visual_styles": [
            {"value": k, "label": v["label"], "hint": v["hint"],
             "scenes": list(v["scenes"]), "scene_default": v["scene_default"],
             "needs_brand": v["theme"] == "brand"}
            for k, v in VISUAL_STYLES.items()
        ],
        "brands": [{"value": k, "label": v["label"]} for k, v in BRAND_THEMES.items()],
        "default_visual_style": DEFAULT_VISUAL_STYLE,
        "default_brand": DEFAULT_BRAND,
    }


@router.post("/runs")
def start_run(req: StartRunRequest) -> dict:
    topic = (req.topic or "").strip() or None
    event_text = (req.event_text or "").strip() or None
    kwargs = dict(topic=topic, library=req.library,
                  subtitles=req.subtitles, n_ideas=req.n_ideas,
                  music_track_id=req.music_track_id,
                  beat_sync=req.beat_sync,
                  music_volume=req.music_volume,
                  review_script=req.review_script,
                  publish_mode=req.publish_mode,
                  qc_mode=req.qc_mode,
                  mode=req.mode, event_text=event_text,
                  visual_style=req.visual_style, brand=req.brand)
    # Info: clamp n_scenes về dải hợp lệ của visual_style (None → scene_default) — REST không
    # qua conductor nên phải tự chốt giống chat. Vlog bỏ qua (pipeline vlog không dùng n_scenes).
    if req.mode == "info":
        from agents.event_game.visual_styles import clamp_scenes
        kwargs["n_scenes"] = clamp_scenes(req.visual_style, req.n_scenes)
    return runner.start_run(**kwargs)


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
    run = runner.decide_gate(run_id, decision=req.decision,
                             scheduled_for=req.scheduled_for, approve=req.approve)
    if run is None:
        raise HTTPException(404, "Run không tồn tại (server restart?)")
    log.info("workflow %s · gate decision=%s", run_id, run["gate"]["decision"])
    return run


@router.post("/runs/{run_id}/idea")
def decide_idea(run_id: str, req: IdeaDecisionRequest) -> dict:
    run = runner.decide_idea(run_id, req.approve, req.idea_index)
    if run is None:
        raise HTTPException(404, "Run không tồn tại (server restart?)")
    log.info("workflow %s · idea gate %s (idx=%s)", run_id,
             "APPROVED" if req.approve else "REJECTED", req.idea_index)
    return run


@router.post("/runs/{run_id}/script")
def decide_script(run_id: str, req: ScriptDecisionRequest) -> dict:
    run = runner.decide_script(run_id, approve=req.approve, decision=req.decision,
                               script=req.script, caption=req.caption, hashtags=req.hashtags)
    if run is None:
        raise HTTPException(404, "Run không tồn tại (server restart?)")
    log.info("workflow %s · script gate decision=%s%s", run_id,
             run["script_gate"]["decision"],
             " (edited)" if req.script or req.caption or req.hashtags else "")
    return run
