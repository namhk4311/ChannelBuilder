"""Run Alembic 'upgrade head' programmatically khi app start.

Idempotent: nếu DB đã ở head thì no-op (~30ms cost: connect + select version).
Gọi từ server.py lifespan VÀ migrate.py CLI (cùng nguồn DDL duy nhất).
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)

# Repo root = parent của agents/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI  = PROJECT_ROOT / "alembic.ini"


def run_migrations() -> None:
    """Apply tất cả migration pending. No-op khi đã ở head."""
    log.info("alembic: upgrade head (cfg=%s)", ALEMBIC_INI.name)
    cfg = Config(str(ALEMBIC_INI))
    # Absolute path — script_location ở alembic.ini là relative; khi server
    # start từ cwd khác (vd /tmp khi cron) cần ép absolute.
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    try:
        command.upgrade(cfg, "head")
    except OperationalError as e:
        raise RuntimeError(
            "Alembic không kết nối được Postgres. "
            "Kiểm tra `docker compose ps postgres` (phải Up + healthy) "
            "và POSTGRES_URL trong .env trỏ đúng host:port "
            "(default localhost:5433).\n"
            f"  → root cause: {e.orig}"
        ) from e
    log.info("alembic: schema at head")
