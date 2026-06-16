"""Run Alembic 'upgrade head' programmatically khi app start.

Idempotent: nếu DB đã ở head thì no-op (~30ms cost: connect + select version).
Gọi từ server.py lifespan VÀ migrate.py CLI (cùng nguồn DDL duy nhất).
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import OperationalError

from .db import pg

log = logging.getLogger(__name__)

# Repo root = parent của agents/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI  = PROJECT_ROOT / "alembic.ini"

# Revision id ĐÃ BỊ XOÁ/ĐỔI TÊN trong lịch sử → ánh xạ về ancestor an toàn để
# re-stamp. DB nào lỡ apply revision cũ (vd deploy scheduler TRƯỚC khi linearize)
# sẽ kẹt "Can't locate revision '<id>'" lúc upgrade. Vì các migration nối sau
# ancestor này đều idempotent (CREATE ... IF NOT EXISTS), stamp về ancestor rồi
# upgrade head là an toàn — bảng đã có thì bỏ qua, bảng thiếu thì tạo lại.
_ORPHAN_REMAP = {
    # scheduler từng là 0004_scheduled (nhánh từ 0003_music) trước khi đổi tên
    # thành 0005_scheduled (nối sau 0004_chat). Stamp về 0003_music → upgrade
    # head chạy lại 0004_chat (tạo chat_sessions nếu thiếu) + 0005_scheduled.
    "0004_scheduled": "0003_music",
}


def _heal_orphaned_revisions(cfg: Config) -> None:
    """Re-stamp khi alembic_version trỏ tới revision không còn trong script tree.

    Tránh crash startup trên DB đã apply migration cũ rồi bị đổi tên revision.
    Chỉ heal id có trong `_ORPHAN_REMAP`; id lạ khác để alembic tự báo lỗi.
    """
    try:
        known = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
        with pg() as conn:
            reg = conn.execute("SELECT to_regclass('public.alembic_version') AS t").fetchone()
            if not reg or not reg["t"]:
                return  # DB chưa từng migrate → upgrade head lo từ base
            for r in conn.execute("SELECT version_num FROM alembic_version").fetchall():
                cur = r["version_num"]
                if cur in known:
                    continue
                target = _ORPHAN_REMAP.get(cur)
                if not target:
                    log.warning("alembic: revision %r không có trong script tree "
                                "và không có remap — để alembic tự xử lý", cur)
                    continue
                conn.execute(
                    "UPDATE alembic_version SET version_num = %s WHERE version_num = %s",
                    (target, cur),
                )
                log.warning("alembic: HEAL orphaned revision %s → %s (re-stamp trước upgrade)",
                            cur, target)
    except Exception as e:  # noqa: BLE001 — heal lỗi KHÔNG được chặn upgrade thật
        log.warning("alembic: heal check bỏ qua (%s)", e)


def run_migrations() -> None:
    """Apply tất cả migration pending. No-op khi đã ở head."""
    log.info("alembic: upgrade head (cfg=%s)", ALEMBIC_INI.name)
    cfg = Config(str(ALEMBIC_INI))
    # Absolute path — script_location ở alembic.ini là relative; khi server
    # start từ cwd khác (vd /tmp khi cron) cần ép absolute.
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    _heal_orphaned_revisions(cfg)
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
