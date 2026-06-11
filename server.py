"""
VNG Insider — Clip Warehouse · FastAPI entry point.

Run:
  docker compose up -d                          # MinIO + Postgres + Adminer
  pip install -r requirements.txt
  python3 migrate.py                            # bulk import data_raw → MinIO + PG
  python3 -m uvicorn server:app --reload --port 8000

UIs:
  http://localhost:8000   App
  http://localhost:9101   MinIO Console  (minioadmin / minioadmin)
  http://localhost:8081   Adminer (PG)   (postgres / vng / vng / vng_insider)

Layout: tất cả logic nằm trong package `video/` (chia theo chức năng).
File này chỉ là entry point: lifespan + mount routers + serve static + log requests.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from config import STATIC_DIR
from logger import setup_logging
from video.categories import router as categories_router
from video.clips import router as clips_router
from video.db import init_db
from video.editor import router as editor_router
from video.importer import router as importer_router
from video.storage import init_buckets

# Setup logging ngay khi module load — uvicorn import server sẽ trigger
setup_logging()
log = logging.getLogger("server")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("──────── startup ────────")
    init_buckets()
    init_db()
    log.info("ready · listening on http://localhost:8000")
    yield
    log.info("──────── shutdown ────────")


app = FastAPI(title="VNG Insider · Clip Warehouse", lifespan=lifespan)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    """Log mỗi request: METHOD path → status (Xms)."""
    # Bỏ qua static files để log gọn
    path = request.url.path
    if path.startswith("/static") or path in ("/favicon.ico",):
        return await call_next(request)

    t0 = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - t0) * 1000

    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    log.log(level, "%s %s → %d (%.0fms)",
            request.method, path, response.status_code, elapsed_ms)
    return response


# Mount feature routers (mỗi feature 1 module trong video/)
app.include_router(categories_router)
app.include_router(clips_router)
app.include_router(importer_router)
app.include_router(editor_router)

# Static frontend — mount LAST để /api routes ưu tiên
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
