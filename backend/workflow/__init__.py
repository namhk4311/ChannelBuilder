"""[★] Orchestrator — workflow API cho UI visualize pipeline A→B→C→D.

Public surface:
    from workflow import workflow_router    # FastAPI mount
"""
from .router import router as workflow_router

__all__ = ["workflow_router"]
