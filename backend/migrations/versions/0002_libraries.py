"""libraries: parent của categories + videos

Revision ID: 0002_libraries
Revises: 0001_initial
Create Date: 2026-06-12

Thêm 1 tầng grouping trên categories. categories.name không còn unique
toàn cục, mà unique trong phạm vi 1 library — PRIMARY KEY trở thành
composite (library, name). FK videos→categories cũng đổi sang composite
(library, name).

Idempotent: seed library `vng_insider`; toàn bộ 11 categories + 32 videos
cũ tự backfill vào library này.

Thứ tự bắt buộc:
  1) Tạo libraries + seed
  2) Add categories.library + backfill + FK → libraries
  3) Add videos.library + backfill
  4) DROP FK cũ videos→categories(name)         ← phải trước (5) vì FK ref tới PK cũ
  5) DROP PK cũ categories(name) → ADD PK mới (library, name)
  6) ADD FK mới videos → categories(library, name)
  7) Index trên videos.library
"""
from __future__ import annotations

from alembic import op

revision = "0002_libraries"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


DEFAULT_LIBRARY = "vng_insider"
DEFAULT_LABEL = "VNG Insider"
DEFAULT_DESC = "Library mặc định — toàn bộ clip của kênh VNG Insider."


def upgrade() -> None:
    # ─── 1. Bảng libraries + seed ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS libraries (
            name        TEXT PRIMARY KEY,
            label       TEXT,
            description TEXT DEFAULT '',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(f"""
        INSERT INTO libraries (name, label, description)
        VALUES ('{DEFAULT_LIBRARY}', '{DEFAULT_LABEL}', '{DEFAULT_DESC}')
        ON CONFLICT (name) DO NOTHING
    """)

    # ─── 2. categories.library + backfill + FK → libraries ─────────────────
    op.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS library TEXT")
    op.execute(f"UPDATE categories SET library = '{DEFAULT_LIBRARY}' WHERE library IS NULL")
    op.execute("ALTER TABLE categories ALTER COLUMN library SET NOT NULL")
    op.execute(f"ALTER TABLE categories ALTER COLUMN library SET DEFAULT '{DEFAULT_LIBRARY}'")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'categories_library_fkey') THEN
                ALTER TABLE categories ADD CONSTRAINT categories_library_fkey
                    FOREIGN KEY (library) REFERENCES libraries(name)
                    ON UPDATE CASCADE ON DELETE RESTRICT;
            END IF;
        END $$
    """)

    # ─── 3. videos.library + backfill (chưa add FK vì categories PK chưa đổi) ─
    op.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS library TEXT")
    op.execute(f"UPDATE videos SET library = '{DEFAULT_LIBRARY}' WHERE library IS NULL")
    op.execute("ALTER TABLE videos ALTER COLUMN library SET NOT NULL")
    op.execute(f"ALTER TABLE videos ALTER COLUMN library SET DEFAULT '{DEFAULT_LIBRARY}'")

    # ─── 4. Drop FK cũ videos.category → categories(name) ──────────────────
    # Phải trước (5) vì FK này ref tới PK cũ categories_pkey
    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_category_fkey")

    # ─── 5. Đổi PK categories: (name) → (library, name) ────────────────────
    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_pkey")
    op.execute("ALTER TABLE categories ADD PRIMARY KEY (library, name)")

    # ─── 6. Add FK mới videos → categories(library, name) ──────────────────
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'videos_library_category_fkey') THEN
                ALTER TABLE videos ADD CONSTRAINT videos_library_category_fkey
                    FOREIGN KEY (library, category) REFERENCES categories(library, name)
                    ON UPDATE CASCADE ON DELETE RESTRICT;
            END IF;
        END $$
    """)

    # ─── 7. Index trên videos.library cho Producer filter ──────────────────
    op.execute("CREATE INDEX IF NOT EXISTS videos_library_idx ON videos(library)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS videos_library_idx")
    op.execute("ALTER TABLE videos DROP CONSTRAINT IF EXISTS videos_library_category_fkey")

    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_pkey")
    op.execute("ALTER TABLE categories ADD PRIMARY KEY (name)")

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'videos_category_fkey') THEN
                ALTER TABLE videos ADD CONSTRAINT videos_category_fkey
                    FOREIGN KEY (category) REFERENCES categories(name)
                    ON UPDATE CASCADE ON DELETE RESTRICT;
            END IF;
        END $$
    """)
    op.execute("ALTER TABLE videos DROP COLUMN IF EXISTS library")
    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_library_fkey")
    op.execute("ALTER TABLE categories DROP COLUMN IF EXISTS library")
    op.execute("DROP TABLE IF EXISTS libraries")
