"""[B] Creative Brain — script & ideas generation cho VNG Insider channel.

Public surface:
    from agents.creative import creative_router       # FastAPI mount
    from agents.creative import generate_ideas, generate_script   # direct call
    from agents.creative import TOOL_DEFINITIONS, execute_tool    # LLM tool calling
"""
from .router import router as creative_router
from .tools import TOOL_DEFINITIONS, execute_tool, generate_ideas, generate_script

__all__ = [
    "creative_router",
    "TOOL_DEFINITIONS",
    "execute_tool",
    "generate_ideas",
    "generate_script",
]
