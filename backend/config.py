"""
Local config — chỉ chứa giá trị có thể đổi giữa các máy / môi trường.

Mọi giá trị đều có default cho local dev; override bằng env var hoặc .env file.

Vd:  POSTGRES_URL=postgresql://... python3 -m uvicorn server:app

`.env` được auto-load (qua python-dotenv) — đặt secrets như ELEVENLABS_API_KEY,
LITELLM_API_KEY vào đó, không commit vào git.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env vào os.environ trước khi đọc bất kỳ getenv nào.
# `override=False` nghĩa là env vars set ở shell có ưu tiên cao hơn .env.
load_dotenv(override=False)

# ─── Postgres ────────────────────────────────────────────────────────────────
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://vng:vng@localhost:5433/vng_insider",
)

# ─── MinIO ───────────────────────────────────────────────────────────────────
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9100")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS",   "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET",   "minioadmin")
MINIO_SECURE   = os.getenv("MINIO_SECURE",   "false").lower() == "true"

# Buckets
BUCKET_SOURCES = os.getenv("BUCKET_SOURCES", "clips")
BUCKET_OUTPUTS = os.getenv("BUCKET_OUTPUTS", "outputs")
BUCKET_MUSIC   = os.getenv("BUCKET_MUSIC",   "music")

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_RAW_PATH = Path(os.getenv("DATA_RAW_PATH", "data_raw"))
STATIC_DIR    = Path(os.getenv("STATIC_DIR", "static"))

# ─── ElevenLabs TTS ──────────────────────────────────────────────────────────
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY")  # required for producer
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")

# ─── VNGCloud AI Platform (OpenAI-compatible) — share Producer + Creative ──
# Dùng `or` thay vì arg default vì .env có thể set key=<empty> → trả về ''
# (không trigger default của os.getenv). `or` xử lý cả None lẫn ''.
AI_PLATFORM_BASE_URL = (
    os.getenv("AI_PLATFORM_BASE_URL")
    or "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
)
AI_PLATFORM_API_KEY = os.getenv("AI_PLATFORM_API_KEY")  # required for producer + creative
AI_PLATFORM_MODEL   = os.getenv("AI_PLATFORM_MODEL")   or "deepseek/deepseek-v4-flash"  # Producer
CREATIVE_MODEL      = os.getenv("CREATIVE_MODEL")      or "minimax/minimax-m2.5"        # Creative
# Chat Conductor (tab Chat) — mặc định dùng chung model với Creative, đổi độc lập qua env.
CHAT_MODEL          = os.getenv("CHAT_MODEL")          or CREATIVE_MODEL                 # Conductor hội thoại
# Scout giữ model RIÊNG (tách khỏi CREATIVE_MODEL) — sau này có thể đổi độc lập.
SCOUT_MODEL         = os.getenv("SCOUT_MODEL")         or "minimax/minimax-m2.5"        # Scout (LLM extract)
# true (default): Scout dùng LLM extract trang TikTok thật (metric=likes); false: chỉ dataset seed (đỡ quota).
SCOUT_USE_LLM       = (os.getenv("SCOUT_USE_LLM") or "true").lower() == "true"

# ─── Creative QC (plan-level) — review script_package TRƯỚC khi produce ──────
# Lớp deterministic (clip thiếu/coverage/cụt) LUÔN chạy (0 quota). Cờ này bật
# THÊM lớp LLM judge (hook/mạch/khớp-ý) — true (default) đồng bộ SCOUT_USE_LLM;
# set false để đỡ quota MaaS lúc dev (deterministic vẫn gánh chính). QC tái dùng
# CREATIVE_MODEL qua _chat (không có model riêng để tránh dead config).
CREATIVE_QC_USE_LLM = (os.getenv("CREATIVE_QC_USE_LLM") or "true").lower() == "true"
# Số lần TỐI ĐA cho [B] viết lại kịch bản theo feedback QC (auto self-correct hoặc
# human bấm "viết lại"). Chặn vòng lặp vô tận / đốt quota. 0 = không bao giờ viết lại.
CREATIVE_QC_MAX_RETRIES = int(os.getenv("CREATIVE_QC_MAX_RETRIES", "2"))

# ─── TikTok API — Publisher agent ────────────────────────────────────────────
TIKTOK_CLIENT_KEY    = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI  = os.getenv("TIKTOK_REDIRECT_URI")
TIKTOK_SCOPES        = os.getenv("TIKTOK_SCOPES") or "user.info.basic,video.publish"

# ─── Publisher scheduler — đăng theo lịch + guardrail bài/ngày ───────────────
# MAX_POSTS_PER_DAY = guardrail tự đặt chống spam (KHÔNG phải trần TikTok — "5"
# trong doc team là đọc nhầm cap 5 *user*/24h). Chỉnh tự do qua env.
MAX_POSTS_PER_DAY     = int(os.getenv("MAX_POSTS_PER_DAY", "5"))
SCHEDULE_TZ           = os.getenv("SCHEDULE_TZ", "Asia/Saigon")
# Chu kỳ poller quét queue (mỗi phút) để đăng bài đúng giờ riêng của nó.
SCHEDULE_TICK_SECONDS = int(os.getenv("SCHEDULE_TICK_SECONDS", "60"))
# Giờ pre-fill sẵn cho datetime picker (user xoá đè được).
SCHEDULE_DEFAULT_HOUR = int(os.getenv("SCHEDULE_DEFAULT_HOUR", "9"))
# false để tắt poller (vd chỉ 1 instance bật khi scale nhiều replica).
SCHEDULE_TICK_ENABLED = (os.getenv("SCHEDULE_TICK_ENABLED", "true").lower() == "true")

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOG_FILE  = os.getenv("LOG_FILE")   # None nếu không set
