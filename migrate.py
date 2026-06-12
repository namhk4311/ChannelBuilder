"""
Migrate data_raw → MinIO + Postgres (CLI).

Chạy:
  python3 migrate.py                          # import vào DB + MinIO
  python3 migrate.py --data-raw ./data_raw    # custom path
  python3 migrate.py --dry-run                # liệt kê, không ghi

Idempotent: chạy lại không trùng.
Yêu cầu: `docker compose up -d` đã chạy (Postgres + MinIO healthy).
"""
import argparse
import logging
import sys
from pathlib import Path

from config import DATA_RAW_PATH
from logger import setup_logging
from agents.producer import import_from_data_raw, init_buckets, run_migrations


def main() -> None:
    setup_logging()
    log = logging.getLogger("migrate")

    ap = argparse.ArgumentParser(description="Import data_raw → MinIO + Postgres")
    ap.add_argument("--data-raw", default=str(DATA_RAW_PATH),
                    help=f"Path tới folder data_raw (default: {DATA_RAW_PATH})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Liệt kê việc sẽ làm, không ghi DB / MinIO")
    args = ap.parse_args()

    data_raw = Path(args.data_raw)
    if not data_raw.exists():
        log.error("data_raw folder không tồn tại: %s", data_raw)
        sys.exit(2)

    init_buckets()
    run_migrations()

    result = import_from_data_raw(data_raw, dry_run=args.dry_run)

    # Summary CLI-style cuối cùng (không qua logger để dễ đọc)
    print()
    print(f"  Categories upserted : {result['categories_upserted']}")
    print(f"  Videos imported     : {result['videos_imported']}")
    print(f"  Videos skipped      : {result['videos_skipped']}")
    if result["missing_files"]:
        print(f"  Missing files       : {len(result['missing_files'])}")
        for m in result["missing_files"]:
            print(f"    - {m}")
    else:
        print(f"  Missing files       : 0")

    sys.exit(1 if result["missing_files"] else 0)


if __name__ == "__main__":
    main()
