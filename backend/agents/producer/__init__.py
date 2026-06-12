"""
[C] Producer agent — TTS + LLM clip pick + concat + align + mux + upload.

Public surface re-exported để bên ngoài import gọn:
    from agents.producer import init_buckets, run_migrations, producer_router, ...

Layout bên trong:
  • pipeline.py            — orchestrator script → video (TTS, LLM, align, mux)
  • clips.py               — upload / list / patch / delete clip
  • categories.py          — CRUD category
  • importer.py            — bulk import data_raw → MinIO + PG
  • editor.py              — cắt ghép (concat endpoint)
  • tts_cache.py           — cache TTS hash → MinIO mp3 + alignment JSONB
  • migrations_runner.py   — alembic upgrade head wrapper (gọi lúc app start)
  • db / storage / ffprobe — internal helpers
"""
from .categories import router as categories_router
from .clips import router as clips_router
from .editor import router as editor_router
from .importer import import_from_data_raw, router as importer_router
from .libraries import router as libraries_router
from .migrations_runner import run_migrations
from .pipeline import router as producer_router
from .storage import init_buckets

__all__ = [
    "run_migrations",
    "init_buckets",
    "import_from_data_raw",
    "libraries_router",
    "categories_router",
    "clips_router",
    "editor_router",
    "importer_router",
    "producer_router",
]
