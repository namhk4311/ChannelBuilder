"""
Central logging setup.

Gọi `setup_logging()` 1 lần ở entry point (server.py + migrate.py).
Idempotent — gọi nhiều lần không tạo handler trùng.

Env vars:
  LOG_LEVEL = DEBUG | INFO | WARNING | ERROR    (default INFO)
  LOG_FILE  = ./logs/app.log                    (optional — bật ghi file)

Cách dùng trong module:
  import logging
  log = logging.getLogger(__name__)
  log.info("upload start: file=%s", filename)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from config import LOG_FILE, LOG_LEVEL

_CONFIGURED = False

# Thư viện noisy → chỉ show từ WARNING trở lên
_QUIET_LIBS = ("urllib3", "psycopg.pool", "minio", "asyncio",
               "multipart", "python_multipart")


def setup_logging() -> None:
    """Configure root logger. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = LOG_LEVEL.upper()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Stdout handler — luôn có
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # File handler — chỉ khi LOG_FILE được set trong config/.env
    if LOG_FILE:
        log_path = Path(LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Tone down noisy libraries
    for lib in _QUIET_LIBS:
        logging.getLogger(lib).setLevel(logging.WARNING)

    _CONFIGURED = True
