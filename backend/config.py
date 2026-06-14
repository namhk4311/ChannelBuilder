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
# Scout giữ model RIÊNG (tách khỏi CREATIVE_MODEL) — sau này có thể đổi độc lập.
SCOUT_MODEL         = os.getenv("SCOUT_MODEL")         or "minimax/minimax-m2.5"        # Scout (LLM extract)
# true (default): Scout dùng LLM extract trang TikTok thật (metric=likes); false: chỉ dataset seed (đỡ quota).
SCOUT_USE_LLM       = (os.getenv("SCOUT_USE_LLM") or "true").lower() == "true"

# ─── TikTok API — Publisher agent ────────────────────────────────────────────
TIKTOK_CLIENT_KEY    = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI  = os.getenv("TIKTOK_REDIRECT_URI")
TIKTOK_SCOPES        = os.getenv("TIKTOK_SCOPES") or "user.info.basic,video.publish"

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOG_FILE  = os.getenv("LOG_FILE")   # None nếu không set
