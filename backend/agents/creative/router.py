"""[B] Creative Brain — FastAPI endpoints cho UI gọi.

POST /api/creative/ideas   — sinh n ý tưởng từ chủ đề
POST /api/creative/script  — từ 1 idea → script package
                             (script string + hook + caption + hashtags + warnings)

Cả 2 đều blocking ~30-60s (gọi MaaS streaming). Không dùng job/polling
vì agent tools đã trả dict tổng thẳng, không cần state machine — UI chỉ
cần spinner + status text.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .tools import generate_ideas, generate_script, pregen_scripts

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/creative", tags=["creative"])


class IdeasRequest(BaseModel):
    topic: str = Field(..., min_length=2, description="Chủ đề video (Vietnamese)")
    n_ideas: int = Field(5, ge=1, le=10)
    target_duration_sec: int = Field(48, ge=30, le=60,
                                     description="Truyền vào để pre-gen script đúng độ dài user sẽ pick")


class ScriptRequest(BaseModel):
    idea: dict = Field(..., description="1 object từ /api/creative/ideas .ideas[*]")
    target_duration_sec: int = Field(48, ge=30, le=60)


@router.post("/ideas")
def post_ideas(req: IdeasRequest) -> dict:
    """Trả {status, error, ideas[]}. Blocking ~30-60s (streaming MaaS).

    Sau khi ideas xong, KICK OFF song song generate_script cho TỪNG idea (cache
    nền). User pick + bấm "Viết kịch bản" → /script tra cache → thường instant.
    """
    log.info("creative.ideas · topic=%r n=%d dur=%ds",
             req.topic, req.n_ideas, req.target_duration_sec)
    result = generate_ideas(topic=req.topic, n_ideas=req.n_ideas)
    log.info("creative.ideas · %s (ideas=%d)",
             result.get("status"), len(result.get("ideas") or []))
    if result.get("status") == "ok" and result.get("ideas"):
        # Fire-and-forget — pregen_scripts non-blocking, return ngay.
        n = pregen_scripts(result["ideas"], target_duration_sec=req.target_duration_sec)
        log.info("creative.ideas · spawned %d pre-gen script (song song)", n)
    return result


@router.post("/script")
def post_script(req: ScriptRequest) -> dict:
    """Trả {status, error, package:{script,text_hook,shot_list,caption,hashtags}, warnings[]}.

    Blocking ~30-60s.
    """
    log.info("creative.script · idea=%r dur=%ds",
             (req.idea or {}).get("title", "?"), req.target_duration_sec)
    result = generate_script(idea=req.idea, target_duration_sec=req.target_duration_sec)
    log.info("creative.script · %s (warnings=%d)",
             result.get("status"), len(result.get("warnings") or []))
    return result
