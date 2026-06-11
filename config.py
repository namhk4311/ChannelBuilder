"""
Local config — chỉ chứa giá trị có thể đổi giữa các máy / môi trường.

Mọi giá trị đều có default cho local dev; override bằng env var.

Vd:  POSTGRES_URL=postgresql://... python3 -m uvicorn server:app
"""
from __future__ import annotations

import os
from pathlib import Path

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

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_RAW_PATH = Path(os.getenv("DATA_RAW_PATH", "data_raw"))
STATIC_DIR    = Path(os.getenv("STATIC_DIR", "static"))
