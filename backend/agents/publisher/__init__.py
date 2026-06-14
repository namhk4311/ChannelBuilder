"""[D] Publisher — đăng TikTok (on-demand + scheduled) + kéo metric.

Public surface:
    from agents.publisher import publisher_oauth_router          # FastAPI mount (OAuth)
    from agents.publisher import publisher_schedule_router       # FastAPI mount (queue lịch)
    from agents.publisher import start_scheduler, shutdown_scheduler, run_now
    from agents.publisher.tools import publish_video, get_video_metrics, TOOL_DEFINITIONS
"""
from .router import router as publisher_oauth_router
from .scheduler import run_now, shutdown_scheduler, start_scheduler
from .schedule_router import router as publisher_schedule_router

__all__ = [
    "publisher_oauth_router",
    "publisher_schedule_router",
    "start_scheduler",
    "shutdown_scheduler",
    "run_now",
]
