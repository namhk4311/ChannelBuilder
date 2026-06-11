"""
VNG Insider — Orchestrator demo (mock agents, full flow).

Chạy:   python3 orchestrator.py
Output: ./runs/<run_id>/*.json  (state mỗi bước)

Mental model: orchestrator CHỈ là 1 hàm gọi 5 agent theo thứ tự,
truyền JSON, lưu state, đóng vòng feedback E → B.
Mọi LLM/ffmpeg/TikTok API nằm BÊN TRONG từng agent — không phải việc của orchestrator.
"""
from __future__ import annotations
from typing import TypedDict, Literal, Optional
from pathlib import Path
import json, time, uuid

# ─────────────────────────────────────────────────────────────────────────────
# 1) SHARED SCHEMA — đây là "hợp đồng" giữa các agent.
#    Trong prod nên dùng pydantic để validate runtime; TypedDict đủ cho demo.
# ─────────────────────────────────────────────────────────────────────────────

class RunContext(TypedDict):
    run_id: str
    trigger: Literal["scheduled", "on_demand"]
    topic: Optional[str]
    brand_guide: dict

class TrendDigest(TypedDict):              # [A] Scout output
    formats: list[dict]
    hooks: list[str]
    absolute_thresholds: dict              # {retention_3s: 0.65, ctr: 0.05}

class CreativeBrief(TypedDict):            # [B] Creative Brain output
    idea: str
    script: str                            # 40–55s lời thoại
    text_hook: str                         # 2–3s chữ trên màn hình
    shot_list: list[dict]                  # [{ts, clip_id, duration, narration}]
    hashtags: list[str]

class VideoArtifact(TypedDict):            # [C] Producer output
    video_path: str
    duration_sec: float
    voice_track: str
    caption: str

class PublishResult(TypedDict):            # [D] Publisher output
    tiktok_post_id: str
    posted_at: str
    metrics: dict                          # điền dần khi polling

class GateDecision(TypedDict):             # [E] Analyst output
    pass_a: bool                           # top 20% lô
    pass_b: bool                           # vượt ngưỡng tuyệt đối
    decision: Literal["SCALE", "MONITOR", "KILL"]
    reason: str
    insight_for_next_round: str            # ← đẩy ngược về B

# ─────────────────────────────────────────────────────────────────────────────
# 2) AGENTS — mock. Trong prod mỗi hàm gọi LLM hoặc tool thật.
# ─────────────────────────────────────────────────────────────────────────────

def agent_scout(ctx: RunContext) -> TrendDigest:
    """[A] Quét trend từ Apify, seed ngưỡng tuyệt đối. Chạy hàng tuần."""
    # Prod: call LLM (Claude) với data trend scrape từ Apify
    return {
        "formats": [
            {"name": "POV office tour", "retention_estimate": 0.70},
            {"name": "Tip vào công ty tech", "retention_estimate": 0.66},
        ],
        "hooks": ["Đây là lý do tôi nghỉ FAANG về VNG...",
                  "3 thứ ở VNG Campus mà công ty khác không có"],
        "absolute_thresholds": {"retention_3s": 0.65, "ctr": 0.05},
    }

def agent_creative(ctx: RunContext, trend: TrendDigest,
                   prev_insight: Optional[str]) -> CreativeBrief:
    """[B] Sinh idea + script 40–55s + hook 2–3s + shot list từ kho clip. Hàng ngày."""
    # Prod: gọi Claude Opus 4.8 với input:
    #   - trend digest từ A
    #   - prev_insight (insight digest từ E vòng trước)  ← đóng vòng học
    #   - brand_guide (tone hài, xưng "Starter", hashtag #VNG #VNGCampus)
    #   - clip warehouse tags (chọn clip phù hợp shot list)
    learning_note = f" (vận dụng insight: {prev_insight})" if prev_insight else ""
    return {
        "idea": f"POV: ngày đầu làm Starter ở VNG Campus{learning_note}",
        "script": "Ngày đầu vào VNG, tôi không ngờ canteen lại... [40-55s]",
        "text_hook": "Ngày đầu vào VNG, tôi không ngờ...",
        "shot_list": [
            {"ts": 0.0, "clip_id": "campus_entrance_02", "duration": 3.0,
             "narration": "Mở đầu cảnh cổng Campus"},
            {"ts": 3.0, "clip_id": "canteen_lunch_01", "duration": 4.0,
             "narration": "Cảnh canteen giờ trưa"},
            {"ts": 7.0, "clip_id": "office_collab_03", "duration": 5.0,
             "narration": "Góc làm việc team"},
        ],
        "hashtags": ["#VNG", "#VNGCampus", "#Starter"],
    }

def agent_producer(ctx: RunContext, brief: CreativeBrief) -> VideoArtifact:
    """[C] Ghép clip theo shot list + chèn text hook 2–3s + TTS Việt tone hài. Hàng ngày."""
    # Prod:
    #   1. Lookup clip_id từ Clip Warehouse → file paths
    #   2. ffmpeg concat theo shot_list timeline
    #   3. TTS (ElevenLabs / VietTTS) với tone hài → audio track
    #   4. Overlay text_hook 2-3s đầu (PIL/ffmpeg drawtext)
    #   5. Mix audio (chỉ giọng lồng tiếng, mute clip gốc)
    return {
        "video_path": f"renders/{ctx['run_id']}.mp4",
        "duration_sec": 47.3,
        "voice_track": f"audio/{ctx['run_id']}.mp3",
        "caption": brief["script"][:100] + " " + " ".join(brief["hashtags"]),
    }

def agent_publisher(ctx: RunContext, video: VideoArtifact) -> PublishResult:
    """[D] Đăng TikTok (lịch + on-demand) + kéo metric. Hàng ngày + realtime."""
    # Prod:
    #   - TikTok Content Posting API: upload video + caption
    #   - Schedule metric polling sau N giờ → ghi Metrics DB
    #   - Fallback nếu API chưa duyệt: xuất file + caption cho human bấm tay
    return {
        "tiktok_post_id": f"tt_{uuid.uuid4().hex[:8]}",
        "posted_at": "2026-06-11T10:00:00+07:00",
        "metrics": {},                     # ban đầu rỗng, polling fill sau
    }

def agent_analyst(ctx: RunContext, publish: PublishResult,
                  thresholds: dict, batch_metrics: list[dict]) -> GateDecision:
    """[E] Absolute Gate (2 phanh) + insight digest. Chạy khi metric đủ trưởng thành."""
    m = publish["metrics"]

    # passA: top 20% của lô (batch percentile)
    batch_ret = sorted([x["retention_3s"] for x in batch_metrics], reverse=True)
    top20_cutoff = batch_ret[max(1, len(batch_ret) // 5) - 1]
    pass_a = m["retention_3s"] >= top20_cutoff

    # passB: vượt ngưỡng tuyệt đối (từ Scout seed, tinh chỉnh theo data thật)
    pass_b = m["retention_3s"] >= thresholds["retention_3s"]

    # 2 phanh — chặn lỗi "scale best of a bad batch"
    if pass_a and pass_b: decision = "SCALE"
    elif pass_a or pass_b: decision = "MONITOR"
    else: decision = "KILL"

    return {
        "pass_a": pass_a,
        "pass_b": pass_b,
        "decision": decision,
        "reason": (f"retention_3s={m['retention_3s']:.0%} | "
                   f"top20_lô={top20_cutoff:.0%} | "
                   f"absolute={thresholds['retention_3s']:.0%}"),
        "insight_for_next_round":
            "Hook đặt câu hỏi mở giữ chân +12% so với hook kể chuyện. "
            "Clip canteen perform tốt hơn clip office.",
    }

# ─────────────────────────────────────────────────────────────────────────────
# 3) STATE PERSISTENCE — file-based cho demo, prod dùng Postgres/Redis.
# ─────────────────────────────────────────────────────────────────────────────

STATE_DIR = Path("./runs")
STATE_DIR.mkdir(exist_ok=True)

def save_state(run_id: str, step: str, payload: dict) -> None:
    (STATE_DIR / run_id).mkdir(exist_ok=True)
    with open(STATE_DIR / run_id / f"{step}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def load_last_insight() -> Optional[str]:
    """Đóng vòng feedback: đọc insight digest của vòng analyst cuối cùng."""
    analyst_files = sorted(STATE_DIR.glob("*/analyst.json"))
    if not analyst_files:
        return None
    with open(analyst_files[-1], encoding="utf-8") as f:
        return json.load(f).get("insight_for_next_round")

def load_batch_metrics() -> list[dict]:
    """Pull metric các post gần đây để E tính percentile. Prod: query Metrics DB."""
    return [{"retention_3s": 0.62}, {"retention_3s": 0.55},
            {"retention_3s": 0.71}, {"retention_3s": 0.49},
            {"retention_3s": 0.58}]

# ─────────────────────────────────────────────────────────────────────────────
# 4) ORCHESTRATOR — đây là toàn bộ "orchestrator".
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(trigger: Literal["scheduled", "on_demand"],
                 topic: Optional[str] = None) -> dict:
    """A → B → C → D → (chờ metric) → E. Mỗi bước persist state."""
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ctx: RunContext = {
        "run_id": run_id,
        "trigger": trigger,
        "topic": topic,
        "brand_guide": {
            "channel": "VNG Insider",
            "tone": "hài hước, gần gũi, nhiều giá trị",
            "hashtags_fixed": ["#VNG", "#VNGCampus", "#Starter"],
        },
    }
    save_state(run_id, "00_context", dict(ctx))

    print(f"\n┌─ {run_id} ─ trigger={trigger} topic={topic!r}")

    # ── [A] Scout ──────────────────────────────────────────────────────────
    # Trong prod: cached weekly, không gọi mỗi run. Demo gọi luôn.
    print("│  → A · Scout         (quét trend, seed benchmark)")
    trend = agent_scout(ctx)
    save_state(run_id, "01_scout", dict(trend))

    # ── [B] Creative Brain ─────────────────────────────────────────────────
    # 2 nguồn học vào B: trend (A) + insight digest vòng trước (E).
    print("│  → B · Creative      (idea + script + hook + shot list)")
    prev_insight = load_last_insight()
    if prev_insight:
        print(f"│     ↺ áp dụng insight vòng trước: {prev_insight[:60]}...")
    brief = agent_creative(ctx, trend, prev_insight)
    save_state(run_id, "02_creative", dict(brief))

    # ── [C] Producer ───────────────────────────────────────────────────────
    print("│  → C · Producer      (ghép clip + TTS tone hài)")
    video = agent_producer(ctx, brief)
    save_state(run_id, "03_producer", dict(video))

    # ── [D] Publisher ──────────────────────────────────────────────────────
    print("│  → D · Publisher     (đăng TikTok + kick off metric poll)")
    publish = agent_publisher(ctx, video)
    save_state(run_id, "04_publisher", dict(publish))

    # ── Wait for metrics ───────────────────────────────────────────────────
    # Thực tế đây là JOB RIÊNG (scheduled), chạy sau N giờ. Demo simulate.
    print("│  ⏳ ... chờ metric trưởng thành (job riêng, scheduled) ...")
    publish["metrics"] = {"retention_3s": 0.68, "views": 12500, "ctr": 0.06}
    save_state(run_id, "04_publisher", dict(publish))  # update với metric

    # ── [E] Analyst ────────────────────────────────────────────────────────
    print("│  → E · Analyst       (absolute gate + insight digest)")
    decision = agent_analyst(ctx, publish, trend["absolute_thresholds"],
                             load_batch_metrics())
    save_state(run_id, "05_analyst", dict(decision))

    # ── Human-in-the-loop ──────────────────────────────────────────────────
    flag = {"SCALE": "⚡", "MONITOR": "👀", "KILL": "⛔"}[decision["decision"]]
    print(f"│  {flag} {decision['decision']} — {decision['reason']}")
    if decision["decision"] == "SCALE":
        print("│  ▲ đẩy proposal về dashboard → chờ human bấm xác nhận")
    print(f"└─ done. State ở: ./runs/{run_id}/\n")

    return {"run_id": run_id, "decision": decision}


# ─────────────────────────────────────────────────────────────────────────────
# 5) DEMO — chạy 2 vòng để thấy E → B đóng vòng học.
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 70)
    print("VÒNG 1 — chưa có insight cũ")
    print("═" * 70)
    run_pipeline(trigger="on_demand", topic="POV ngày đầu ở VNG")

    print("═" * 70)
    print("VÒNG 2 — load insight vòng 1, B sẽ điều chỉnh")
    print("═" * 70)
    run_pipeline(trigger="scheduled")
