"""
Shot-list-driven assembly helpers (Producer [C]).

Pure, deterministic, KHÔNG LLM / KHÔNG network / KHÔNG DB / KHÔNG ffmpeg —
tách riêng khỏi pipeline.py để unit-test được trên python trần (chỉ stdlib).

2 hàm chính, gọi từ `pipeline.produce_from_script` khi có `shot_list` từ Creative:
  • compute_sentence_cuts(...)  — Fix 1: timeline cắt theo từng câu thoại.
  • build_fill_plan(...)        — Fix 3 + diệt lặp: chọn clip theo scene_hint
                                  (diệt Starbucks-vs-Phúc Long) VÀ lấp mỗi câu
                                  bằng nhiều clip phân biệt thay vì loop 1 clip.

Cả 2 trả `None` khi không đủ điều kiện → caller fallback path cũ (LLM-pick +
align_to_voice). Xem plan: plans/260615-1130-producer-shotlist-sync-fps-fix/.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

log = logging.getLogger(__name__)

# Khoảng cách tối thiểu giữa 2 mốc cut (giây) — tránh segment 0s khi câu cực ngắn.
_MIN_SEGMENT_SEC = 0.05


# ─── Fix 1: sentence-timed cuts ──────────────────────────────────────────────

def _voiceovers(shot_list: list[dict]) -> list[str]:
    """Lấy voiceover đã strip mỗi line (khớp creative.tools._script_to_text)."""
    return [(l.get("voiceover") or "").strip() for l in shot_list]


def _sanitize_cuts(cuts: list[float], voice_duration: float) -> list[float]:
    """Ép cuts đơn điệu tăng, clamp [0, voice_duration], mốc cuối = voice_duration."""
    out = [0.0]
    for c in cuts[1:]:
        c = min(max(float(c), out[-1]), voice_duration)
        if c <= out[-1]:
            c = min(out[-1] + _MIN_SEGMENT_SEC, voice_duration)
        out.append(c)
    out[-1] = voice_duration
    # Sau khi ép mốc cuối, có thể phá đơn điệu ở mốc kế cuối → kéo lùi nếu cần.
    for i in range(len(out) - 2, 0, -1):
        if out[i] > out[i + 1]:
            out[i] = out[i + 1]
    return out


def _proportional_cuts(shot_list: list[dict], voice_duration: float) -> list[float]:
    """Fallback: chia voice_duration theo tỉ lệ duration_sec của shot_list.

    Dùng khi char-offset mapping không khớp alignment (TTS normalize/merge token).
    Nếu thiếu duration_sec → chia đều theo số câu.
    """
    durs = [float(l.get("duration_sec") or 0) for l in shot_list]
    total = sum(durs)
    if total <= 0:
        durs = [1.0] * len(shot_list)
        total = float(len(shot_list))
    cuts = [0.0]
    acc = 0.0
    for d in durs:
        acc += d
        cuts.append(voice_duration * acc / total)
    return cuts


def compute_sentence_cuts(
    shot_list: Optional[list[dict]],
    alignment: Any,
    voice_duration: float,
    script: str,
) -> Optional[list[float]]:
    """Tính timeline cắt theo biên thời gian thực mỗi câu thoại (Fix 1).

    Map char-offset cộng dồn của từng câu → `alignment.character_end_times_seconds`
    → cuts `[0.0, t_end(câu0), ..., voice_duration]` (n+1 mốc cho n câu).
    Output length = voice_duration chính xác → caller SKIP STEP 4 align (hết slow-mo).

    Gating — trả `None` (→ fallback path cũ) khi BẤT KỲ điều kiện nào sai:
      1. shot_list rỗng / có câu thiếu voiceover.
      2. alignment is None (TTS không trả timestamps).
      3. script != " ".join(voiceovers) → script đã bị sửa ở gate, shot_list lệch.

    Khớp được gating nhưng char-offset lệch mảng alignment → fallback proportional
    (KHÔNG trả None — vẫn dùng path mới với cut chia tỉ lệ).
    """
    # ── Gating ───────────────────────────────────────────────────────────────
    if not shot_list:
        return None
    if not all(isinstance(l, dict) for l in shot_list):
        # shot_list dị dạng (không phải list[dict]) → fallback legacy thay vì raise.
        log.info("sentence-cuts: shot_list có phần tử không phải dict → fallback legacy")
        return None
    voiceovers = _voiceovers(shot_list)
    if not all(voiceovers):  # có câu rỗng/whitespace → không tin shot_list
        log.info("sentence-cuts: shot_list có câu thiếu voiceover → fallback legacy")
        return None
    if alignment is None:
        log.info("sentence-cuts: không có alignment (TTS thiếu timestamps) → fallback legacy")
        return None
    joined = " ".join(voiceovers)
    if (script or "").strip() != joined.strip():
        # script bị override ở human gate → shot_list không còn map đúng câu.
        log.info("sentence-cuts: script != join(voiceovers) (script_override?) → fallback legacy")
        return None

    n = len(shot_list)
    chars = getattr(alignment, "characters", None)
    ends = getattr(alignment, "character_end_times_seconds", None)

    # ── Char-offset mapping (chính) ──────────────────────────────────────────
    # Chỉ tin char-offset khi alignment khớp đúng từng ký tự của script. ElevenLabs
    # đôi khi normalize text (số → chữ) → char count lệch → dùng proportional.
    use_char = (
        chars is not None and ends is not None
        and len(chars) == len(ends) == len(joined)
    )
    cuts: Optional[list[float]] = None
    if use_char:
        cuts = [0.0]
        offset = 0
        for i, v in enumerate(voiceovers):
            offset += len(v)                       # offset cuối câu i (exclusive)
            idx = min(offset - 1, len(ends) - 1)    # index ký tự cuối câu i
            if idx < 0:
                cuts = None
                break
            cuts.append(float(ends[idx]))
            offset += 1                             # nhảy qua space phân cách
        if cuts is not None and len(cuts) != n + 1:
            cuts = None

    if cuts is None:
        log.warning("sentence-cuts: char-offset không khớp alignment (chars=%s ends=%s script=%s) "
                    "→ fallback proportional theo duration_sec",
                    len(chars) if chars else None,
                    len(ends) if ends else None, len(joined))
        cuts = _proportional_cuts(shot_list, voice_duration)

    cuts = _sanitize_cuts(cuts, voice_duration)
    if len(cuts) != n + 1:
        log.warning("sentence-cuts: cuts có %d mốc, cần %d → fallback legacy", len(cuts), n + 1)
        return None
    # Guard collapse: voice_duration quá ngắn cho số câu → có segment ~0s. KHÔNG
    # đẩy `trim=0:0.000` vào ffmpeg (glitch/concat fail) → fallback legacy an toàn.
    if any(cuts[i + 1] - cuts[i] < _MIN_SEGMENT_SEC for i in range(n)):
        log.warning("sentence-cuts: segment < %.2fs (voice %.2fs quá ngắn cho %d câu) "
                    "→ fallback legacy", _MIN_SEGMENT_SEC, voice_duration, n)
        return None
    log.info("sentence-cuts: %d câu → %d cuts %s (voice=%.2fs, mode=%s)",
             n, len(cuts), [round(c, 2) for c in cuts], voice_duration,
             "char" if use_char else "proportional")
    return cuts


# ─── Fix 3: scene-hint clip picker ───────────────────────────────────────────

# Token Việt có dấu: \w trong Python 3 là Unicode → khớp chữ có dấu. Bỏ token 1
# ký tự (nhiễu). Giữ nguyên dấu để "phúc"/"long" match đúng description.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# scene_hint nhắc tới người → KHÔNG phạt has_people=true (brand ưu tiên no-people
# trừ khi cảnh cần người: sự kiện, team, ca sĩ...).
_PEOPLE_HINTS = (
    "người", "nhân viên", "starter", "đồng nghiệp", "team", "nhóm",
    "bạn", "ca sĩ", "hát", "event", "sự kiện", "mọi người",
)

_HAS_PEOPLE_PENALTY = 0.5   # trừ điểm clip có người khi hint không cần người
_DEDUP_PENALTY = 2.0        # trừ mạnh clip đã dùng (×số lần đã dùng) tránh lặp


def _tokens(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2]


def _scene_hint_score(scene_hint: Optional[str], description: Optional[str]) -> float:
    """Overlap token scene_hint ↔ description (case-insensitive, giữ dấu Việt).

    Đếm số token của scene_hint xuất hiện trong description. Đủ để phân biệt
    brand literal (Phúc Long vs Starbucks) mà không cần embedding (YAGNI).
    """
    h = _tokens(scene_hint)
    if not h:
        return 0.0
    dset = set(_tokens(description))
    if not dset:
        return 0.0
    return float(sum(1 for t in h if t in dset))


def _hint_mentions_people(scene_hint: Optional[str]) -> bool:
    if not scene_hint:
        return False
    low = scene_hint.lower()
    return any(kw in low for kw in _PEOPLE_HINTS)


# Fill-plan tuning (mỗi câu lấp bằng NHIỀU clip phân biệt thay vì loop 1 clip):
_FILL_EPS = 0.05             # bỏ qua phần dư < 50ms
_MIN_SUB_SEGMENT_SEC = 1.5  # mỗi clip hiện ≥1.5s (đủ xem, tránh cắt lia lịa)
_MAX_CLIPS_PER_SENTENCE = 6  # trần clip/câu (6×1.5s≈9s window vẫn không machine-gun-cut)

# clip_tag → pillar (brand 3 pillar). Khi bucket của 1 tag cạn distinct clip mà câu còn
# dài, mượn thêm clip PHÂN BIỆT từ tag KHÁC CÙNG PILLAR (thay vì loop 1 clip). `buzones`
# (logo/Zalo/VNGGames) = pillar `bu` → cô lập; còn lại đều campus B-roll, kênh tour campus
# nên mượn chéo trong campus là brand-safe. Tag lạ → coi như campus (pool lớn nhất, an toàn).
_TAG_PILLAR = {
    "campusngoaicanh": "campus", "khonggianmo": "campus", "gym": "campus",
    "canteencafe": "campus", "goclamviec": "campus", "cayxanhthugian": "campus",
    "hopteam": "campus", "sukienclb": "campus",
    "buzones": "bu",
}
_DEFAULT_PILLAR = "campus"


def _bucket_for_line(line: dict, clips_catalog: list[dict]) -> list[dict]:
    """Clip cùng `clip_tag` (rỗng → thử `alt_tag`)."""
    tag = line.get("clip_tag")
    bucket = [c for c in clips_catalog if c.get("clip_tag") == tag] if tag else []
    if not bucket:
        alt = line.get("alt_tag")
        bucket = [c for c in clips_catalog if c.get("clip_tag") == alt] if alt else []
    return bucket


def _pillar_of(tag: Optional[str]) -> str:
    return _TAG_PILLAR.get(tag or "", _DEFAULT_PILLAR)


def _pillar_pool(primary: list[dict], clips_catalog: list[dict], exclude_ids: set) -> list[dict]:
    """Clip CÙNG PILLAR với footage primary đang chiếu — để mượn chéo khi bucket cạn.

    Pillar suy từ `clip_tag` THỰC của `primary[0]` (= tag mà `_bucket_for_line` đã match, đã
    xử fallback clip_tag→alt_tag). KHÔNG dùng `line.clip_tag` thô: nếu clip_tag là tag
    rỗng-bucket và bucket thực rơi xuống alt_tag KHÁC pillar, pillar suy theo line.clip_tag sẽ
    lệch với footage thật → pool rỗng → loop thay vì mượn (bug M1). Bỏ `exclude_ids` (primary) +
    clip thiếu id. `buzones` cô lập (pillar bu); còn lại pool chung campus.
    """
    if not primary:
        return []
    pillar = _pillar_of(primary[0].get("clip_tag"))
    pool = []
    for c in clips_catalog:
        cid = c.get("id")
        if cid is None or cid in exclude_ids:
            continue
        if _pillar_of(c.get("clip_tag")) == pillar:
            pool.append(c)
    return pool


def _rank_bucket(line: dict, bucket: list[dict], used: dict[str, int]) -> list[dict]:
    """Bucket → xếp giảm dần theo score (scene_hint overlap − phạt has_people −
    phạt dedup). Tie-break: giữ thứ tự bucket (sort ổn định → deterministic)."""
    hint = line.get("scene_hint") or ""
    hint_people = _hint_mentions_people(hint)

    def score(c: dict) -> float:
        s = _scene_hint_score(hint, c.get("description"))
        if c.get("has_people") and not hint_people:
            s -= _HAS_PEOPLE_PENALTY
        n_used = used.get(c.get("id"), 0)
        if n_used:
            s -= _DEDUP_PENALTY * n_used
        return s

    return sorted(bucket, key=score, reverse=True)


def build_fill_plan(
    shot_list: Optional[list[dict]],
    cuts: Optional[list[float]],
    clips_catalog: list[dict],
) -> Optional[tuple[list[str], list[float]]]:
    """Mở rộng mỗi câu thành 1+ clip KHÁC NHAU lấp đủ thời lượng câu (Fix 3 + diệt
    lặp 1-clip-loop). Trả `(expanded_ids, expanded_cuts)` cho
    `concat_with_cut_timeline`, hoặc `None` nếu thiếu điều kiện → caller fallback.

    Mỗi câu i lấp window `[cuts[i], cuts[i+1]]` bằng clip cùng bucket xếp theo
    `scene_hint`: mỗi clip hiện ~độ dài thật (≥`_MIN_SUB_SEGMENT_SEC`), tối đa
    `_MAX_CLIPS_PER_SENTENCE` clip/câu, KHÔNG lặp 1 clip nếu còn clip phân biệt.
    Hết clip phân biệt mà vẫn dư → clip cuối loop-fill phần còn lại (editor xử).
    Biên câu giữ NGUYÊN = cuts gốc → visual vẫn bám narration từng câu.
    Dedup toàn cục (`used`) → giảm lặp clip giữa các câu.
    """
    if not shot_list or not clips_catalog or not cuts:
        return None
    if not all(isinstance(l, dict) for l in shot_list):
        log.info("fill-plan: shot_list có phần tử không phải dict → fallback legacy")
        return None
    n = len(shot_list)
    if len(cuts) != n + 1:
        log.warning("fill-plan: cuts %d mốc ≠ %d câu +1 → fallback legacy", len(cuts), n)
        return None

    used: dict[str, int] = {}
    ids: list[str] = []
    ecuts: list[float] = [float(cuts[0])]

    for i, line in enumerate(shot_list):
        ws, we = float(cuts[i]), float(cuts[i + 1])
        window = we - ws
        if window <= 0:
            # compute_sentence_cuts đã đảm bảo segment ≥ _MIN_SEGMENT_SEC; guard này
            # chỉ phòng caller truyền cuts thủ công không hợp lệ → fallback an toàn.
            return None
        primary = _bucket_for_line(line, clips_catalog)
        if not primary:
            log.warning("fill-plan: câu %d tag=%r alt=%r không có clip → fallback legacy",
                        i, line.get("clip_tag"), line.get("alt_tag"))
            return None
        # Ứng viên = clip đúng tag (rank scene_hint) TRƯỚC, rồi clip cùng pillar (mượn chéo)
        # khi window dài hơn footage phân biệt của tag. Primary luôn đứng đầu → chỉ mượn khi
        # primary đã cạn (greedy break theo window). Loop 1-clip chỉ còn là last resort.
        primary_ids = {c.get("id") for c in primary}
        ranked_primary = _rank_bucket(line, primary, used)
        ranked_pillar = _rank_bucket(line, _pillar_pool(primary, clips_catalog, primary_ids), used)
        candidates = ranked_primary + ranked_pillar

        # Greedy lấp window bằng clip phân biệt (theo thứ tự rank).
        segs: list[tuple[dict, float]] = []  # (clip, length sec)
        consumed = 0.0
        for clip in candidates:
            if consumed >= window - _FILL_EPS or len(segs) >= _MAX_CLIPS_PER_SENTENCE:
                break
            if clip.get("id") is None:
                continue
            remaining = window - consumed
            src = clip.get("duration_sec") or 0
            length = min(src, remaining) if src > 0 else remaining
            # mỗi clip hiện ≥ MIN_SUB (nhưng không quá phần còn lại)
            length = max(length, min(_MIN_SUB_SEGMENT_SEC, remaining))
            # phần dư sau clip này quá nhỏ để host clip khác → gộp vào clip này
            if remaining - length < _MIN_SUB_SEGMENT_SEC:
                length = remaining
            segs.append((clip, length))
            consumed += length

        if not segs:  # mọi clip thiếu id
            log.warning("fill-plan: câu %d không clip hợp lệ → fallback legacy", i)
            return None
        # Hết clip phân biệt mà còn dư → clip cuối loop-fill phần còn lại.
        if consumed < window - _FILL_EPS:
            clip, length = segs[-1]
            segs[-1] = (clip, length + (window - consumed))

        # Emit sub-cuts; sub cuối của câu ép = we (giữ sync + nuốt rounding).
        acc = ws
        for j, (clip, length) in enumerate(segs):
            acc = we if j == len(segs) - 1 else min(acc + length, we)
            ids.append(clip["id"])
            used[clip["id"]] = used.get(clip["id"], 0) + 1
            ecuts.append(acc)
        n_distinct = len({c["id"] for c, _ in segs})
        n_borrowed = sum(1 for c, _ in segs if c.get("id") not in primary_ids)
        log.info("fill-plan: câu %d window=%.2fs tag=%r scene_hint=%r → %d clip (%d phân biệt, "
                 "%d mượn chéo cùng pillar)%s",
                 i, window, line.get("clip_tag"), line.get("scene_hint"), len(segs), n_distinct,
                 n_borrowed, " [tail loop — pillar cạn]" if consumed < window - _FILL_EPS else "")

    ecuts = _sanitize_cuts(ecuts, float(cuts[-1]))
    if len(ecuts) != len(ids) + 1:
        return None
    if any(ecuts[k + 1] - ecuts[k] < _MIN_SEGMENT_SEC for k in range(len(ids))):
        log.warning("fill-plan: sub-segment ~0s → fallback legacy")
        return None
    log.info("fill-plan: %d câu → %d clip-segment (multi-clip fill, no slow-mo), tổng=%.2fs",
             n, len(ids), ecuts[-1])
    return ids, ecuts
