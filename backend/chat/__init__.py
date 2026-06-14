"""[Chat] Conductor — điều khiển pipeline bằng ngôn ngữ tự nhiên.

Thu thập PipelineSpec qua hội thoại (LLM) rồi gọi workflow.runner.start_run hiện
có. Public surface:
    from chat import chat_router       # FastAPI mount
"""
from .router import router as chat_router

__all__ = ["chat_router"]
