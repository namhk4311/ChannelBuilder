"""Alembic env — kéo POSTGRES_URL từ config.py (single source of truth).

KHÔNG đọc .env trực tiếp ở đây. KHÔNG gọi fileConfig() — app đã setup logging
qua logger.py rồi, gọi lại sẽ ghi đè handler/format.
"""
from __future__ import annotations

import re

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import POSTGRES_URL

config = context.config

# Ép dùng psycopg v3 (đã cài via psycopg[binary]).
# postgresql://...  →  postgresql+psycopg://...
url = POSTGRES_URL
if url.startswith("postgresql://") and not url.startswith("postgresql+"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
config.set_main_option("sqlalchemy.url", url)


def _mask(u: str) -> str:
    """postgresql+psycopg://vng:vng@host/db → postgresql+psycopg://vng:***@host/db"""
    return re.sub(r"://([^:/]+):([^@]+)@", r"://\1:***@", u)


# Trực quan cho dev — chứng minh đang trỏ vào container đúng (host:port + db).
print(f"[alembic] connecting to {_mask(url)}", flush=True)


target_metadata = None  # raw-SQL migrations, không dùng SQLAlchemy ORM


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
