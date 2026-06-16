# VNG Insider · AI Agent tự xây kênh TikTok

End-to-end pipeline tự sinh video TikTok 40-55s cho kênh **VNG Insider**, từ ý
tưởng văn bản → kịch bản → giọng đọc → ghép video → đăng bài. Build cho
GreenNode Claw-a-thon (7 ngày).

> Trạng thái: **Card 1-4 + Creative + Producer + Publisher (with scheduling) đã chạy E2E**.
> Workflow orchestration hoàn toàn (A→E pipeline + human gate). Scout + Analyst đã khởi tạo (2026-06-13/15).

---

## Kiến trúc 5-agent

```
              ┌───── [A] Scout ─────┐       ┌──── [E] Analyst ────┐
              │ trend research      │       │ metric gate         │
              │ (built)             │       │ (built)             │
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
                   │  1. TTS giọng đọc (ElevenLabs)       │
                   │  2a. Shot-list path (Creative):      │
                   │      • Sentence-timed cuts (no LLM)  │
                   │      • Deterministic clip pick       │
                   │  2b. Legacy path (fallback):         │
                   │      • LLM pick clip (deepseek-flash)│
                   │  3. ffmpeg concat (loop-fill clips)  │
                   │  4. mux voice + phụ đề (overlay PNG)│
                   │  5. upload MinIO outputs             │
                   └────────────────┬─────────────────────┘
                                    │ 3 link MinIO (silent / voice / final)
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  [D] Publisher (scheduled + on-demand)│
                   │  • publish_video (TikTok Content API)│
                   │  • get_video_metrics                 │
                   │  → APScheduler auto-publish queue    │
                   │  → 4 safety brakes (guardrails)      │
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
│       ├── 0002_libraries.py             # libraries + composite PK
│       ├── 0003_music.py                 # tàu âm thanh + sync
│       └── 0004_scheduled_posts.py       # scheduled_posts table + 3 indexes
│
├── agents/
│   ├── creative/              # [B] Creative Brain
│   │   ├── tools.py           #   generate_ideas, generate_script (streaming MaaS + pregen cache)
│   │   ├── prompts.py         #   SYSTEM_IDEAS, SYSTEM_SCRIPT, CLIP_TAGS (9 nhóm VNG)
│   │   ├── router.py          #   POST /api/creative/{ideas,script}
│   │   └── SCHEMAS.md
│   ├── publisher/             # [D] Publisher (scheduled + on-demand)
│   │   ├── tools.py           #   publish_video, get_video_metrics
│   │   ├── client.py          #   TikTokClient (chunked upload + poll)
│   │   ├── oauth.py           #   CLI OAuth flow
│   │   ├── guardrails.py      #   BANNED_WORDS check + dedup + daily limit
│   │   ├── scheduled_posts.py #   DAO: claim_due, mark_published, etc.
│   │   ├── publish_service.py #   publish_now (atomic flip + release lock)
│   │   ├── scheduler.py       #   APScheduler tick (60s interval)
│   │   └── schedule_router.py #   POST /api/publisher/schedule + calendar
│   └── producer/              # [C] Producer (vốn là video_editor/)
│       ├── pipeline.py        #   POST /api/produce — 6-step dual-path orchestrator
│       ├── editor.py          #   POST /api/concat (ffmpeg helper + loop-fill)
│       ├── shotlist.py        #   Sentence-cut deterministic clip picker (NEW)
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

## Publisher: Scheduled + On-demand posting

**Flow:** Sau khi Producer hoàn thành video, workflow đưa user tới **human gate**. User chọn:
- **Đăng ngay** (`decision: 'now'`) — publish ngay lập tức
- **Lên lịch** (`decision: 'schedule'`, tuỳ chọn `scheduled_for`) — enqueue vào `scheduled_posts` table, scheduler APScheduler sẽ auto-publish tại thời gian
- **Từ chối** (`decision: 'reject'`) — cancel, không đăng

**4 brakes ("4 phanh") áp dụng cho cả 2 đường:**
1. **Guardrails** — kiểm BANNED_WORDS trong caption + script + text_hook
2. **Dedup** — sha256 content_hash; block nếu đã published hoặc đang publishing
3. **Daily limit** — `MAX_POSTS_PER_DAY=5` (self-imposed anti-spam, KHÔNG phải TikTok cap)
4. **Audit trail** — mỗi publish/skip/block ghi 1 row vào `scheduled_posts` (lịch sử)

**Scheduler (background):** Chạy mỗi 60s (tuỳ chỉnh `SCHEDULE_TICK_SECONDS`), scan `scheduled_posts WHERE status='pending' AND scheduled_for <= now()`. Atomic claim (`FOR UPDATE SKIP LOCKED`) → flip status `pending→publishing` → release lock → publish. Safe trên multi-replica (SKIP LOCKED).

**Công nghệ:**
- Table `scheduled_posts` (`id, video_path, caption, script, text_hook, status, content_hash, scheduled_for, published_at, error, run_id`)
- APScheduler @ `SCHEDULE_TICK_SECONDS` interval, lúc server start
- Config keys mới: `MAX_POSTS_PER_DAY`, `SCHEDULE_TZ`, `SCHEDULE_DEFAULT_HOUR`, `SCHEDULE_TICK_ENABLED`

---

## Producer: Shot-List vs Legacy Paths

**Shot-List Path** (NEW — 2026-06-15): Khi Creative [B] trả về `shot_list` (câu → `clip_tag` + `scene_hint`):
- `produce_from_script(shot_list=...)` → deterministic clip pick (no LLM), khớp `scene_hint`↔`description` (diệt Phúc Long↔Starbucks)
- Cắt timeline theo sentence từ ElevenLabs alignment (chính xác 0.1s)
- **Multi-clip fill**: câu dài lấp bằng nhiều clip phân biệt (≥1.5s/clip, ≤4 clip/câu) thay vì loop 1 clip → giảm lặp hình
- Loop-fill 1x chỉ ở phần dư (khi bucket cạn) thay vì slow-mo → fixes tụt fps / frame rate errors

**Legacy Path** (Fallback): Không có `shot_list` hoặc không hợp lệ:
- Dùng LLM (deepseek-flash) pick clip từ library
- Cách cũ unchanged
- Dùng cho Studio `/api/produce` (Studio không gửi `shot_list`)

Workflow orchestrator sẽ tự chọn path dựa vào input; không cần config.

---

## QC kịch bản (plan-level) — chặn lỗi TRƯỚC produce

Bước **`qc_script`** (orchestrator, code ★) chèn giữa `generate_script` →
`script_approval` để bắt lỗi trước khi đốt quota ElevenLabs/render. **Non-blocking,
KHÔNG hard-block** — verdict chỉ là cảnh báo, human quyết retry ở gate.

- **Deterministic (luôn chạy, 0 quota):** đối chiếu mỗi câu shot_list với kho clip
  thật (`clip_missing` nếu tag + alt_tag đều rỗng bucket; `clip_coverage` nếu tổng
  thời lượng clip < thời lượng câu → lặp hình), cụt-detection tiếng Việt
  (`script_cut` khi kết treo liên từ / thiếu dấu câu, `hook_weak` khi hook < 3 từ),
  gộp `warnings[]` của validator [B].
- **LLM judge (cờ `CREATIVE_QC_USE_LLM`, default true):** chấm hook/mạch/khớp-ý
  (`clip_mismatch`), grounded bằng metadata clip thật + lỗi deterministic. Tái dùng
  `_chat` với model riêng `CREATIVE_QC_MODEL` (default = `CREATIVE_MODEL`) — nên đặt
  model CHẤM khác model VIẾT để "second opinion" độc lập; khuyến nghị instruct
  non-thinking ổn định (`minimax/minimax-m2.5`, hoặc `qwen*-instruct` nếu MaaS có),
  tránh model reasoning/thinking. 429/JSON vỡ/thiếu dep → `llm=skipped`, deterministic gánh.
- **Verdict** `{verdict: pass|warn, checks: {deterministic, llm}, issues[]}` gắn vào
  output bước `qc_script` (timeline) + bước `script_approval` (gate) → UI card badge
  ("Kiểm tự động" / "AI đánh giá") + danh sách issue tiếng Việt + gợi ý sửa. Tắt LLM
  judge: `CREATIVE_QC_USE_LLM=false`.

**Vòng lặp tự sửa (`qc_mode`, toggle "Cần xác nhận kịch bản" ở run-controls):**
- **`auto` (default):** B → QC → nếu còn **lỗi nặng** (severity=error) thì AI tự cho
  Creative viết lại (kèm warnings làm chỉ dẫn sửa) tối đa `CREATIVE_QC_MAX_RETRIES`
  lần → rồi dựng. Không cần human. Cảnh báo nhẹ không chặn.
- **`confirm`:** B → QC → **dừng** ở gate; human bấm **Tiếp tục** / **Cho Creative
  viết lại** (regenerate với feedback QC, còn lượt thì hiện nút) / **Huỷ**.
- Feedback QC được nhồi vào prompt `generate_script(qc_feedback=...)` để bản viết lại
  khắc phục đúng các lỗi. Cap `CREATIVE_QC_MAX_RETRIES` (default 2) chặn đốt quota.

Module: `backend/workflow/qc_script.py` (pure, stdlib-importable → unit-test trên
python trần: `python3 backend/tests/test_qc_script.py`).

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
| POST | `/api/publisher/schedule` | Enqueue video (on-demand hoặc lên lịch) |
| GET | `/api/publisher/schedule` | List calendar + status (filter `?status=`) |
| DELETE | `/api/publisher/schedule/{id}` | Cancel pending post |
| POST | `/api/publisher/schedule/run-now` | Trigger scheduler tick ngay (demo) |
| GET | `/api/analyst/batches` | List batch analytics + decisions |
| POST | `/api/analyst/analyze` | Run analysis (passA/B gate) trên batch |
| POST | `/api/analyst/confirm` | Affirm decision (SCALE/MONITOR/KILL) |
| GET | `/api/analyst/insight` | Fetch last insight digest → [B] |
| POST | `/api/workflow/runs/{id}/approval` | Gate decision (`decision: 'now'|'schedule'|'reject'`) |

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

- **Retention_3s proxy** — TikTok basic API chưa return retention_3s; Analyst gate hiện mock dùng fallback. Khi TikTok audit app + open endpoint sẽ bỏ mock.
- **Multi-tenancy** — 1 user / 1 channel duy nhất
- **Auth** — UI public, không login (TikTok OAuth 1x setup)

---

## License

Internal use cho VNG Insider channel — không public release.
