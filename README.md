# VNG Insider · AI Agent tự xây kênh TikTok

End-to-end pipeline tự sinh video TikTok 40-55s cho kênh **VNG Insider**, từ ý
tưởng văn bản → kịch bản → giọng đọc → ghép video → đăng bài. Build cho
GreenNode Claw-a-thon (7 ngày).

> Trạng thái: **Card 1-4 + Creative agent + Producer agent đã chạy E2E**.
> Publisher agent tool đã sẵn (chưa wire UI). Scout + Analyst chưa khởi tạo.

---

## Kiến trúc 5-agent

```
              ┌───── [A] Scout ─────┐       ┌──── [E] Analyst ────┐
              │ trend research      │       │ metric gate         │
              │ (chưa khởi tạo)     │       │ (chưa khởi tạo)     │
              └──────────┬──────────┘       └──────────┬──────────┘
                         │ trend_digest                │ insight_digest
                         ▼                             ▼
                   ┌──────────────────────────────────────┐
                   │  [B] Creative Brain                  │
                   │  • generate_ideas(topic)             │
                   │  • generate_script(idea)             │
                   │  → MaaS minimax/minimax-m2.5         │
                   └────────────────┬─────────────────────┘
                                    │ script (string)
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  [C] Producer                        │
                   │  1. TTS giọng đọc (ElevenLabs eleven_v3)│
                   │  2. LLM pick clip (deepseek-flash)   │
                   │     ↳ scope: WHERE library = ?       │
                   │  3. ffmpeg concat normalize          │
                   │  4. align (trim hoặc setpts)         │
                   │  5. mux voice + phụ đề (overlay PNG) │
                   │  6. upload MinIO outputs             │
                   └────────────────┬─────────────────────┘
                                    │ 3 link MinIO (silent / voice / final)
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  [D] Publisher                       │
                   │  • publish_video (TikTok Content API)│
                   │  • get_video_metrics                 │
                   │  (tools sẵn, chưa wire UI)           │
                   └──────────────────────────────────────┘
```

---

## Tech stack

| Layer | Tool |
|---|---|
| Web framework | FastAPI + uvicorn |
| Runtime | Python 3.9.6 |
| Database | PostgreSQL 16 (Docker) + Alembic migrations |
| Object storage | MinIO (S3-compatible, Docker) |
| Video | ffmpeg (homebrew) — concat filter + setpts + overlay |
| TTS | ElevenLabs `eleven_v3` (character-level timestamps) |
| LLM | VNGCloud MaaS — `minimax/minimax-m2.5` (Creative) + `deepseek/deepseek-v4-flash` (Producer) |
| Frontend | Single-page vanilla HTML + JS (`static/index.html`) |
| Migration | Alembic — auto-applied lúc app start |

---

## Cấu trúc project

```
elevenlabs/
├── .env                       # secrets + config (KHÔNG commit)
├── .env.example               # template không secret
├── config.py                  # ★ DUY NHẤT đọc env (single source of truth)
├── server.py                  # FastAPI entry — mount routers + lifespan
├── migrate.py                 # CLI bulk import data_raw → MinIO + PG
├── orchestrator.py            # 5-agent skeleton (chưa wire)
├── logger.py                  # structured logging setup
├── main.py                    # ElevenLabs demo standalone
├── docker-compose.yml         # MinIO + Postgres + Adminer
├── alembic.ini                # Alembic config
├── migrations/                # versioned DB schema
│   ├── env.py                 # đọc POSTGRES_URL từ config
│   └── versions/
│       ├── 0001_initial_schema.py        # categories + videos + tts_cache
│       └── 0002_libraries.py             # libraries + composite PK
│
├── agents/
│   ├── creative/              # [B] Creative Brain
│   │   ├── tools.py           #   generate_ideas, generate_script (streaming MaaS + pregen cache)
│   │   ├── prompts.py         #   SYSTEM_IDEAS, SYSTEM_SCRIPT, CLIP_TAGS (9 nhóm VNG)
│   │   ├── router.py          #   POST /api/creative/{ideas,script}
│   │   └── SCHEMAS.md
│   ├── publisher/             # [D] Publisher (tools sẵn, chưa router)
│   │   ├── tools.py           #   publish_video, get_video_metrics
│   │   ├── client.py          #   TikTokClient (chunked upload + poll)
│   │   └── oauth.py           #   CLI OAuth flow
│   └── producer/              # [C] Producer (vốn là video_editor/)
│       ├── pipeline.py        #   POST /api/produce — 6-step orchestrator
│       ├── editor.py          #   POST /api/concat (ffmpeg helper)
│       ├── clips.py           #   POST/GET/PATCH/DELETE /api/videos
│       ├── categories.py      #   /api/categories (scope theo library)
│       ├── libraries.py       #   /api/libraries
│       ├── importer.py        #   POST /api/import-data-raw + bulk function
│       ├── tts_cache.py       #   hash(script) → MinIO mp3 + alignment JSONB
│       ├── migrations_runner.py  # alembic upgrade head wrapper
│       ├── db.py              #   pg() context manager
│       ├── storage.py         #   minio_client + init_buckets
│       └── ffprobe.py         #   metadata extract
│
├── static/
│   └── index.html             # SPA — library selector + 4 card + creative
├── data_raw/                  # 32 video gốc + 00_INDEX.json (gitignored)
└── requirements.txt
```

---

## Setup local (lần đầu)

### 1. Prereqs
```bash
brew install ffmpeg docker          # macOS
python3 --version                    # cần 3.9+
```

### 2. Clone + copy env
```bash
cp .env.example .env
# Mở .env, điền giá trị thật cho:
#   ELEVENLABS_API_KEY
#   AI_PLATFORM_API_KEY              # VNGCloud MaaS key
#   TIKTOK_CLIENT_KEY/SECRET         # nếu dùng Publisher
```

### 3. Khởi động infra Docker
```bash
docker compose up -d
# → MinIO  : http://localhost:9101 (minioadmin/minioadmin)
# → PG     : localhost:5433 (vng/vng/vng_insider)
# → Adminer: http://localhost:8081
```

### 4. Cài Python deps
```bash
python3 -m pip install -r requirements.txt
```

### 5. (Optional) Bulk import 32 clip mẫu
Nếu có `data_raw/00_INDEX.json`:
```bash
python3 migrate.py
# → tự alembic upgrade head + init_buckets + import_from_data_raw
```

### 6. Start server
```bash
python3 -m uvicorn server:app --reload --port 8000
# → http://localhost:8000  (UI)
```

Lifespan tự chạy:
1. `init_buckets()` — tạo bucket MinIO nếu chưa có
2. `run_migrations()` — `alembic upgrade head` (idempotent)
3. Ready

---

## User flow

### Khái niệm

- **Library** (`vng_insider`, `nhatrang_travel`…) — kho top-level. Mỗi
  library có taxonomy riêng (set categories khác nhau).
- **Category** (vd `canteen_cafe`, `khong_gian_mo`) — nhóm trong 1 library.
  PK composite `(library, name)` → 2 lib khác nhau có thể cùng tên cat.
- **Video** — clip cụ thể, thuộc 1 (library, category).

### Flow tạo video TikTok mới

```
1. Trên cùng: chọn LIBRARY ở dropdown sticky-header
   ↓
2. Card 1 "Categories" — kiểm/tạo category trong lib đang chọn
   ↓
3. Card 2 "Upload" — upload video, gán category
   ↓
4. Card 3a "Sinh kịch bản" (Creative agent):
   • Nhập chủ đề + click "💡 Sinh ý tưởng"
   • Pick 1 trong N idea
   • Click "✍️ Viết kịch bản" → script tự fill xuống card 3
   • (Backend đã pregen script song song cho 5 idea trong nền)
   ↓
5. Card 3 "Tạo video" (Producer agent):
   • Kịch bản hiện sẵn, button "🎬 Tạo video" enable
   • Click → backend 6-step → 3 link MinIO (silent / voice / final)
   ↓
6. Card 4 "Kho clip" — list video đã upload (scope theo library)
```

---

## API endpoints

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/libraries` | List libraries + count |
| POST | `/api/libraries` | Tạo library mới |
| PATCH | `/api/libraries/{name}` | Update label/desc |
| DELETE | `/api/libraries/{name}` | Xoá (chỉ khi rỗng) |
| GET | `/api/categories?library=X` | List categories scope library |
| POST | `/api/categories` | Tạo cat trong lib (body cần `library`) |
| PATCH | `/api/categories/{name}?library=X` | Update |
| DELETE | `/api/categories/{name}?library=X` | Xoá (chỉ khi không còn video) |
| GET | `/api/videos?library=X&category=Y` | List video |
| POST | `/api/videos` | Upload video (form-data, cần `library` + `category`) |
| PATCH | `/api/videos/{id}` | Update metadata |
| DELETE | `/api/videos/{id}` | Xoá video + object MinIO |
| GET | `/api/moods` | Hardcoded list 10 mood |
| POST | `/api/creative/ideas` | Sinh N idea từ topic (~30-60s, blocking) |
| POST | `/api/creative/script` | Sinh script từ 1 idea (cache hit nếu pregen) |
| POST | `/api/produce` | Start job tạo video (body cần `library`) |
| GET | `/api/produce/status/{job_id}` | Poll progress |
| POST | `/api/concat` | Ghép video theo selection thủ công |
| POST | `/api/import-data-raw` | Bulk import từ `data_raw/` |

---

## Common tasks

### Thêm migration mới (đổi schema)
```bash
python3 -m alembic revision -m "add view_count to videos"
# → migrations/versions/<rev>_add_view_count_to_videos.py
# Edit file:
#   def upgrade(): op.execute("ALTER TABLE videos ADD COLUMN view_count INT DEFAULT 0")
#   def downgrade(): op.execute("ALTER TABLE videos DROP COLUMN view_count")
git commit
# Lần restart server kế tiếp lifespan tự alembic upgrade head
```

### Tạo library mới
Trên UI: bấm `+ Thư viện` ở header → form inline → tạo. Hoặc curl:
```bash
curl -X POST http://localhost:8000/api/libraries \
  -H "Content-Type: application/json" \
  -d '{"name":"nhatrang_travel","label":"Du lịch Nha Trang"}'
```

### Đổi model LLM
Sửa `.env`:
```env
CREATIVE_MODEL=minimax/minimax-m2.5         # thinking, ~30-60s
# hoặc nhanh hơn:
CREATIVE_MODEL=deepseek/deepseek-v4-flash   # ~10-20s
```
Restart server (`--reload` tự pickup).

### Debug LLM call (Creative chậm / rỗng)
Xem log server:
```
chat · POST … · model=… max=8000
chat · stream open (HTTP 200, TTFB 1.4s)
chat · streaming … 312 deltas · content=520c · reasoning=2100c · t+15s
chat · done · content=1820c reasoning=2400c finish=stop in 38s
```
Nếu `content=0` và `reasoning=0` với `finish=length` → tăng `max_tokens`
trong [`agents/creative/tools.py`](agents/creative/tools.py).

### Reset DB hoàn toàn (DEV only — mất data)
```bash
docker compose down -v             # ⚠ xoá volume Postgres + MinIO
docker compose up -d
python3 migrate.py                 # re-import data_raw
```

---

## Constraints (architectural)

1. **Single source of truth cho env** — `os.getenv` / `os.environ` /
   `load_dotenv` **chỉ tồn tại trong `config.py`**. Mọi module khác phải
   `from config import X`. Verify:
   ```bash
   grep -rEn '^[^#]*\b(os\.getenv|os\.environ|load_dotenv)\(' --include="*.py" . \
     | grep -vE "(\.venv|^(\./)?config\.py:)"
   # → 0 dòng
   ```

2. **DDL chỉ trong Alembic** — không có `CREATE TABLE` rải rác trong code
   Python. Schema mới = revision mới ở `migrations/versions/`.

3. **Tools agent không bao giờ raise** — pattern `execute_tool()` trả
   `{status: "ok|failed", error: str|None, ...}` để orchestrator chạy
   không bị crash.

4. **Library scope** — mọi query video phải có `WHERE library = ?` để
   Producer không pick lẫn clip giữa các lib.

---

## Test smoke E2E sau khi setup

```bash
# 1. Server health
curl -sS http://localhost:8000/api/libraries | python3 -m json.tool
# → ít nhất phải có `vng_insider` library

# 2. Categories scope đúng
curl -sS "http://localhost:8000/api/categories?library=vng_insider" \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)), 'categories')"
# → 11 (sau migrate.py)

# 3. Producer endpoint structure
curl -sS http://localhost:8000/openapi.json \
  | python3 -c "import sys,json; print([p for p in json.load(sys.stdin)['paths'] if 'produce' in p])"

# 4. UI ở http://localhost:8000:
#    • Dropdown library trên cùng — switch giữa vng_insider ↔ library khác
#    • Card 3a sinh idea + script (blocking 30-60s mỗi step)
#    • Card 3 click "🎬 Tạo video" → 3 link video trong ~2-3 phút
```

---

## Out of scope (chưa làm)

- **Scout [A]** — trend research từ Reddit/X/TikTok hashtag
- **Analyst [E]** — fetch metrics + ranking + insight digest
- **Orchestrator chạy autonomous** — hiện chỉ là skeleton
- **Multi-tenancy** — 1 user / 1 channel duy nhất
- **Audit trail** — không log ai làm gì khi nào
- **Auth** — UI public, không login

---

## License

Internal use cho VNG Insider channel — không public release.
