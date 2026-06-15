"""Catalog agent cho UI workflow — tool list đọc live từ TOOL_DEFINITIONS của từng package.

Import từng agent bọc try/except: 1 agent import lỗi (thiếu env, thiếu dep)
không được làm sập /api/workflow/agents — trả import_error để UI hiển thị.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Tool defs tĩnh cho agent chưa expose TOOL_DEFINITIONS.
PRODUCER_TOOLS = [{
    "name": "produce_video",
    "description": (
        "Dựng video từ script: TTS ElevenLabs (kèm timestamps phụ đề) → LLM chọn clip "
        "từ kho theo nội dung → ghép + khớp độ dài giọng đọc → mux + burn phụ đề → "
        "upload MinIO. Job nền 6 bước, có progress %."
    ),
}]


def _tool_summaries(defs: list[dict]) -> list[dict]:
    return [{"name": d["name"], "description": d["description"]} for d in defs]


def _agent(key: str, code: str, name: str, role: str, build_status: str,
           tools: list[dict], import_error: str | None = None) -> dict:
    return {"key": key, "code": code, "name": name, "role": role,
            "build_status": build_status, "import_error": import_error,
            "tools": tools}


def get_agents() -> list[dict]:
    """Build catalog mỗi lần gọi — tool defs luôn khớp code agent hiện tại."""
    scout_tools: list[dict] = []
    scout_err: str | None = None
    try:
        from agents.scout import TOOL_DEFINITIONS as scout_defs
        scout_tools = _tool_summaries(scout_defs)
    except Exception as e:  # noqa: BLE001 — catalog không được sập vì 1 agent
        scout_err = f"import agents.scout lỗi: {e}"
        log.warning(scout_err)

    creative_tools: list[dict] = []
    creative_err: str | None = None
    try:
        from agents.creative import TOOL_DEFINITIONS as creative_defs
        creative_tools = _tool_summaries(creative_defs)
    except Exception as e:  # noqa: BLE001 — catalog không được sập vì 1 agent
        creative_err = f"import agents.creative lỗi: {e}"
        log.warning(creative_err)

    publisher_tools: list[dict] = []
    publisher_err: str | None = None
    try:
        from agents.publisher.tools import TOOL_DEFINITIONS as publisher_defs
        publisher_tools = _tool_summaries(publisher_defs)
    except Exception as e:  # noqa: BLE001
        publisher_err = f"import agents.publisher lỗi: {e}"
        log.warning(publisher_err)

    return [
        _agent("scout", "A", "Scout",
               "Quét trend thị trường + seed benchmark cho vòng đánh giá",
               "built", scout_tools, scout_err),
        _agent("creative", "B", "Creative",
               "Sinh ý tưởng + kịch bản 40-55s + text hook + shot list",
               "built", creative_tools, creative_err),
        _agent("producer", "C", "Producer",
               "Dựng video: TTS tiếng Việt + LLM pick clip + ghép + phụ đề",
               "built", PRODUCER_TOOLS),
        _agent("publisher", "D", "Publisher",
               "Đăng TikTok 2 chế độ (đăng ngay / lên lịch) qua 4 phanh an toàn + kéo metric",
               "built", publisher_tools, publisher_err),
    ]
