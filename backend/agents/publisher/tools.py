"""
Publisher tools — what the Orchestrator imports to talk to the Publisher agent.

Two ways to use:

1. Direct function call (Orchestrator code calls Python directly):

    from publisher_tools import publish_video, get_video_metrics

    result = publish_video(video_path="/shared/video_123.mp4",
                           caption="Caption from Creative #ai")
    # {"status": "published", "publish_id": "...", "video_id": "...", "error": null}

2. LLM function calling (Orchestrator is an LLM agent with tools):

    from publisher_tools import TOOL_DEFINITIONS, execute_tool

    # Pass TOOL_DEFINITIONS into the LLM `tools` parameter (Anthropic format;
    # for OpenAI wrap each as {"type": "function", "function": {...}}).
    # When the model returns a tool_use block:
    result = execute_tool(tool_name, tool_input)  # always returns a dict

All tool results are plain JSON-serializable dicts and never raise — errors
come back as {"status": "failed", "error": "..."} so the Orchestrator/LLM
can decide what to do next.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .client import TikTokClient, TikTokError

log = logging.getLogger(__name__)

_client: Optional[TikTokClient] = None


def _get_client() -> TikTokClient:
    global _client
    if _client is None:
        log.info("client · khởi tạo TikTokClient lần đầu")
        _client = TikTokClient()
    return _client


def reset_client() -> None:
    """Bỏ client cache — gọi sau khi tokens.json thay đổi (OAuth lại từ UI)."""
    global _client
    _client = None


# ---------------------------------------------------------------- tools

def publish_video(video_path: str, caption: str) -> dict:
    """Publish a video file to TikTok. Blocks until processing completes."""
    t0 = time.monotonic()
    log.info("publish · BẮT ĐẦU · path=%r caption=%r…", video_path, (caption or "")[:60])
    try:
        result = _get_client().post_video(video_path, caption)
        log.info("publish · XONG · %s video_id=%s publish_id=%s (%.1fs)",
                 result.get("status"), result.get("video_id"),
                 result.get("publish_id"), time.monotonic() - t0)
        return {**result, "error": None}
    except TikTokError as e:
        log.warning("publish · TikTokError sau %.1fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "publish_id": None, "video_id": None,
                "error": str(e)}
    except Exception as e:  # noqa: BLE001 — never crash the orchestrator
        log.exception("publish · LỖI bất ngờ sau %.1fs", time.monotonic() - t0)
        return {"status": "failed", "publish_id": None, "video_id": None,
                "error": f"unexpected: {e}"}


def get_video_metrics(video_ids: list[str]) -> dict:
    """Fetch view/like/comment/share counts for previously published videos."""
    t0 = time.monotonic()
    log.info("metrics · query %d video_id", len(video_ids or []))
    try:
        videos = _get_client().get_video_metrics(video_ids)
        log.info("metrics · XONG · %d video trả về (%.1fs)",
                 len(videos), time.monotonic() - t0)
        return {"status": "ok", "videos": videos, "error": None}
    except TikTokError as e:
        log.warning("metrics · TikTokError sau %.1fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "videos": [], "error": str(e)}
    except Exception as e:  # noqa: BLE001
        log.exception("metrics · LỖI bất ngờ sau %.1fs", time.monotonic() - t0)
        return {"status": "failed", "videos": [], "error": f"unexpected: {e}"}


# ------------------------------------------------- LLM tool definitions

TOOL_DEFINITIONS = [
    {
        "name": "publish_video",
        "description": (
            "Publish a video file to the connected TikTok account. "
            "Input: local path to an mp4 file and the caption text (may include "
            "hashtags). Blocks until TikTok finishes processing. Returns "
            "publish_id and video_id on success. Note: with an unaudited API "
            "client the video is posted as private (SELF_ONLY)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Absolute path to the video file (mp4) produced by the Producer agent.",
                },
                "caption": {
                    "type": "string",
                    "description": "Caption text including hashtags, e.g. from the Creative agent. Max ~2200 chars.",
                },
            },
            "required": ["video_path", "caption"],
        },
    },
    {
        "name": "get_video_metrics",
        "description": (
            "Get performance metrics (view_count, like_count, comment_count, "
            "share_count) for videos previously published on the connected "
            "TikTok account. Max 20 video ids per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "TikTok video ids returned by publish_video.",
                },
            },
            "required": ["video_ids"],
        },
    },
]

_TOOL_DISPATCH = {
    "publish_video": lambda inp: publish_video(**inp),
    "get_video_metrics": lambda inp: get_video_metrics(**inp),
}


def execute_tool(name: str, tool_input: dict) -> dict:
    """Dispatch a tool call coming from the LLM. Always returns a dict."""
    fn = _TOOL_DISPATCH.get(name)
    if fn is None:
        return {"status": "failed", "error": f"unknown tool: {name}"}
    return fn(tool_input)
