"""
Video agent package.

Layout theo CHỨC NĂNG (không theo layer):
  • clips.py       — feature: upload / list / patch / delete clip
  • categories.py  — feature: CRUD category
  • importer.py    — feature: bulk import data_raw → MinIO + PG
  • editor.py      — feature: cắt ghép (concat); sau: overlay, voice mux, shot-list compose

Shared internals (chỉ dùng bên trong package này):
  • db.py          — Postgres connection + schema init
  • storage.py     — MinIO client + bucket bootstrap
  • ffprobe.py     — đọc duration + resolution từ file video

Mỗi feature export `router: APIRouter`. server.py mount tất cả.
"""
