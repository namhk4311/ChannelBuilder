"""[D] Publisher — đăng TikTok + kéo metric.

Public surface:
    from agents.publisher import publisher_oauth_router        # FastAPI mount
    from agents.publisher.tools import publish_video, get_video_metrics, TOOL_DEFINITIONS
"""
from .router import router as publisher_oauth_router

__all__ = ["publisher_oauth_router"]
