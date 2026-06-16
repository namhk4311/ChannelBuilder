# -*- coding: utf-8 -*-
"""
[★] QC kịch bản (plan-level) — review script_package TRƯỚC khi produce.

Chèn giữa generate_script → script_approval ở orchestrator. Bắt lỗi sớm để
tiết kiệm quota ElevenLabs/render: clip thiếu/không phủ câu, kịch bản cụt, hook
yếu, clip_tag lệch ý. KHÔNG hard-block — verdict là cảnh báo, human quyết retry.

2 lớp:
  • deterministic (_deterministic_checks + _check_cut_off + base_warnings) —
    LUÔN chạy, 0 quota: clip existence + coverage (mirror bucket logic của
    Producer shotlist.py) + cụt-detection tiếng Việt + gộp warnings[] của [B].
  • LLM judge (_llm_judge) — sau cờ CREATIVE_QC_USE_LLM: hook/mạch/khớp-ý,
    grounded bằng metadata clip thật + deterministic issues. Tái dùng _chat.

Verdict schema (chốt ở plan.md):
  {"verdict": "pass|warn",
   "checks": {"deterministic": "pass|warn|skipped", "llm": "pass|warn|skipped"},
   "issues": [{"type", "severity", "where", "detail", "suggested_fix"}]}

KHÔNG raise (contract mục 4 CLAUDE.md). Mọi import agent là LAZY (package
agents.producer/__init__ kéo theo ffmpeg/PIL/minio/openai) → module này chỉ
phụ thuộc stdlib lúc import → unit-test được trên python trần.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

log = logging.getLogger(__name__)

# Lazy-bound — None ở production (import thật trong helper), test monkeypatch
# trực tiếp `qc_script.list_all_clips_for_llm` / `qc_script._chat`.
list_all_clips_for_llm = None  # type: ignore[assignment]
_chat = None  # type: ignore[assignment]

# 6 type issue hợp lệ (khớp UI + plan). LLM trả type lạ → ép về "flow".
_VALID_TYPES = {"clip_missing", "clip_coverage", "script_cut", "hook_weak", "flow", "clip_mismatch"}

# Heuristic cụt-detection tiếng Việt.
_SENTENCE_END = (".", "!", "?", "…")
_DANGLING_CONJ = {  # liên từ / giới từ treo cuối câu → câu cụt
    "và", "nhưng", "hoặc", "mà", "vì", "nên", "rồi", "thì",
    "để", "với", "của", "là", "cho", "khi", "nếu", "còn",
}
_MIN_HOOK_WORDS = 3            # text_hook phải là mệnh đề
_MIN_LAST_SENTENCE_WORDS = 3  # câu cuối script không cụt lủn


# ─── lazy binders (giữ module top stdlib-only) ──────────────────────────────

def _load_catalog(library: str) -> Optional[list[dict]]:
    """Catalog clip thật của `library`. None nếu DB/import lỗi → bỏ clip-check."""
    fn = list_all_clips_for_llm
    if fn is None:
        try:
            from agents.producer.pipeline import list_all_clips_for_llm as fn  # type: ignore
        except Exception as e:  # noqa: BLE001 — thiếu dep/DB không được giết QC
            log.warning("QC: không import được catalog clip (%s) → bỏ qua clip-check", e)
            return None
    try:
        return list(fn(library) or [])
    except Exception as e:  # noqa: BLE001
        log.warning("QC: list_all_clips_for_llm lỗi (%s) → bỏ qua clip-check", e)
        return None


def _load_chat():
    """`_chat` của Creative (dùng CREATIVE_MODEL). None nếu thiếu dep/config."""
    fn = _chat
    if fn is None:
        try:
            from agents.creative.tools import _chat as fn  # type: ignore
        except Exception as e:  # noqa: BLE001
            log.warning("QC: không import được _chat (%s) → llm=skipped", e)
            return None
    return fn


# ─── deterministic layer ─────────────────────────────────────────────────────

def _bucket_for_line(line: dict, catalog: list[dict]) -> list[dict]:
    """Clip cùng `clip_tag` (rỗng → thử `alt_tag`). Mirror shotlist._bucket_for_line."""
    tag = line.get("clip_tag")
    bucket = [c for c in catalog if c.get("clip_tag") == tag] if tag else []
    if not bucket:
        alt = line.get("alt_tag")
        bucket = [c for c in catalog if c.get("clip_tag") == alt] if alt else []
    return bucket


def _deterministic_checks(package: dict, library: str) -> tuple[list[dict], list[dict]]:
    """Clip existence + coverage cho mỗi câu trong shot_list.

    Trả (issues, clip_meta) — clip_meta = dữ kiện clip thật theo từng câu để
    LLM judge grounding (không bịa clip không có trong kho).
    """
    issues: list[dict] = []
    clip_meta: list[dict] = []
    shot_list = package.get("shot_list") or []

    catalog = _load_catalog(library)
    if catalog is None:
        issues.append({
            "type": "clip_missing", "severity": "warning", "where": "kho clip",
            "detail": f"Không truy cập được kho clip (library={library!r}) để đối chiếu",
            "suggested_fix": "Kiểm tra DB/library; QC bỏ qua bước đối chiếu clip",
        })
        catalog = []

    for line in shot_list:
        if not isinstance(line, dict):
            continue
        i = line.get("line")
        where = f"câu {i}" if i is not None else "câu"
        tag = line.get("clip_tag")
        alt = line.get("alt_tag")
        dur = float(line.get("duration_sec") or 0)
        bucket = _bucket_for_line(line, catalog)

        if not bucket:
            issues.append({
                "type": "clip_missing", "severity": "error", "where": where,
                "detail": (f"Tag '{tag}'" + (f" và alt '{alt}'" if alt else "")
                           + " không có clip nào trong kho — produce sẽ lỗi/thiếu hình"),
                "suggested_fix": (f"Đổi clip_tag ở {where} sang tag có clip, thêm alt_tag, "
                                  f"hoặc bổ sung footage tag '{tag}'"),
            })
            continue

        # Coverage: tổng thời lượng clip trong bucket < thời lượng câu → Producer
        # phải loop-fill (lặp hình). Khớp hành vi shotlist.build_fill_plan.
        bucket_total = sum(float(c.get("duration_sec") or 0) for c in bucket)
        if dur > 0 and bucket_total < dur:
            used_tag = bucket[0].get("clip_tag") or tag   # bucket có thể đến từ alt_tag
            issues.append({
                "type": "clip_coverage", "severity": "warning", "where": where,
                "detail": (f"Câu cần ~{dur:.0f}s nhưng tag '{used_tag}' chỉ có {bucket_total:.0f}s "
                           f"clip ({len(bucket)} clip) → video sẽ lặp hình"),
                "suggested_fix": f"Rút ngắn {where}, thêm alt_tag, hoặc bổ sung clip tag '{used_tag}'",
            })

        clip_meta.append({
            "line": i, "voiceover": line.get("voiceover"),
            "clip_tag": tag, "scene_hint": line.get("scene_hint"),
            "clips": [{"description": c.get("description"), "duration_sec": c.get("duration_sec")}
                      for c in bucket[:5]],
        })

    return issues, clip_meta


def _last_sentence(script: str) -> str:
    # Tách câu ở . ! ? … NHƯNG không tách dấu chấm giữa 2 chữ số (3.5, 12.000)
    # → tránh "câu cuối quá ngắn" giả khi câu kết có số thập phân.
    parts = [p.strip() for p in re.split(r"[!?…]+|(?<!\d)\.+(?!\d)", script) if p.strip()]
    return parts[-1] if parts else script.strip()


def _check_cut_off(script: Optional[str], text_hook: Optional[str]) -> list[dict]:
    """Heuristic phát hiện kịch bản/hook cụt (kết treo liên từ, thiếu dấu câu)."""
    issues: list[dict] = []
    s = (script or "").strip()
    if not s:
        return [{
            "type": "script_cut", "severity": "error", "where": "kịch bản",
            "detail": "Kịch bản rỗng", "suggested_fix": "Sinh lại kịch bản",
        }]

    if not s.endswith(_SENTENCE_END):
        issues.append({
            "type": "script_cut", "severity": "warning", "where": "câu cuối",
            "detail": f"Kịch bản không kết thúc bằng dấu câu (…{s[-30:]!r})",
            "suggested_fix": "Viết trọn câu kết + thêm dấu chấm",
        })

    last_words = _last_sentence(s).split()
    if last_words:
        if len(last_words) < _MIN_LAST_SENTENCE_WORDS:
            issues.append({
                "type": "script_cut", "severity": "warning", "where": "câu cuối",
                "detail": f"Câu cuối quá ngắn ({len(last_words)} từ) — có thể cụt",
                "suggested_fix": "Viết câu kết trọn ý",
            })
        if last_words[-1].strip(".,!?…").lower() in _DANGLING_CONJ:
            issues.append({
                "type": "script_cut", "severity": "warning", "where": "câu cuối",
                "detail": f"Câu cuối kết bằng liên từ treo '{last_words[-1]}' → câu cụt",
                "suggested_fix": "Hoàn thành ý sau liên từ hoặc bỏ từ treo",
            })

    h = (text_hook or "").strip()
    if h:
        hw = h.split()
        if len(hw) < _MIN_HOOK_WORDS:
            issues.append({
                "type": "hook_weak", "severity": "warning", "where": "hook",
                "detail": f"Text hook quá ngắn ({len(hw)} từ) — chưa đủ kéo người xem",
                "suggested_fix": "Viết hook ≥3 từ, gợi tò mò",
            })
        elif hw[-1].strip(".,!?…").lower() in _DANGLING_CONJ:
            issues.append({
                "type": "hook_weak", "severity": "warning", "where": "hook",
                "detail": f"Hook kết bằng liên từ treo '{hw[-1]}'",
                "suggested_fix": "Viết hook thành mệnh đề trọn ý",
            })
    return issues


def _merge_base_warnings(base_warnings: Optional[list]) -> list[dict]:
    """Gộp warnings[] của validator [B] thành issues (CẤM → error, còn lại warning)."""
    out: list[dict] = []
    for w in base_warnings or []:
        text = str(w)
        sev = "error" if "CẤM" in text else "warning"
        out.append({
            "type": "flow", "severity": sev, "where": "validator [B]",
            "detail": text, "suggested_fix": "Xem lại kịch bản theo cảnh báo validator",
        })
    return out


# ─── LLM judge layer ─────────────────────────────────────────────────────────

_QC_SYSTEM_PROMPT = (
    "Bạn là biên tập viên QC khó tính của kênh TikTok 'VNG Insider — Đời sống ở VNG'. "
    "Tone kênh: hài duyên, gần gũi, câu nào cũng có giá trị, KHÔNG quảng cáo lên gân. "
    "Soi kịch bản 40-55s TRƯỚC khi dựng video, chỉ dựa trên DỮ KIỆN được cung cấp "
    "(lời thoại + clip thật theo từng câu + lỗi máy đã phát hiện). KHÔNG bịa clip "
    "không có trong danh sách. Chấm 3 trục: (1) hook 2-3s đầu có giữ chân không, "
    "(2) mạch các câu có trôi/liền lạc không, (3) clip_tag/scene_hint có KHỚP ý câu "
    "không (vd câu nói cà phê mà clip là phòng gym = lệch). "
    "CHỈ trả JSON đúng dạng, KHÔNG văn xuôi:\n"
    '{"issues":[{"type":"hook_weak|flow|clip_mismatch","severity":"warning|error",'
    '"where":"câu i / hook","detail":"...","suggested_fix":"..."}]}\n'
    "Không có vấn đề → {\"issues\":[]}. Trích dẫn câu/tag cụ thể trong 'where'/'detail'."
)


def _build_judge_prompt(package: dict, clip_meta: list[dict], det_issues: list[dict]) -> str:
    lines = [
        "TEXT HOOK (overlay 2-3s đầu): " + (package.get("text_hook") or "—"),
        "",
        "KỊCH BẢN (lời thoại liền mạch):",
        (package.get("script") or "—"),
        "",
        "TỪNG CÂU + CLIP THẬT GẮN ĐƯỢC (chỉ các clip này tồn tại trong kho):",
        json.dumps(clip_meta, ensure_ascii=False, indent=2),
    ]
    if det_issues:
        lines += ["", "LỖI MÁY ĐÃ PHÁT HIỆN (đừng lặp lại, hãy bổ sung góc nhìn biên tập):",
                  json.dumps(det_issues, ensure_ascii=False, indent=2)]
    return "\n".join(lines)


def _parse_judge_json(raw: Optional[str]) -> Optional[list[dict]]:
    """Parse {"issues":[...]} từ output LLM (chịu code-fence). None nếu vỡ."""
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except Exception:  # noqa: BLE001 — JSON vỡ → coi như judge skip
        return None
    raw_issues = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(raw_issues, list):
        return []
    out: list[dict] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        out.append({
            "type": t if t in _VALID_TYPES else "flow",
            "severity": "error" if str(it.get("severity")).lower() == "error" else "warning",
            "where": str(it.get("where") or "—"),
            "detail": str(it.get("detail") or ""),
            "suggested_fix": str(it.get("suggested_fix") or ""),
        })
    return out


def _llm_judge(package: dict, clip_meta: list[dict], det_issues: list[dict]) -> Optional[list[dict]]:
    """Chấm hook/mạch/khớp-ý. None = skipped (thiếu dep / 429 / JSON vỡ)."""
    chat = _load_chat()
    if chat is None:
        return None
    try:
        raw = chat(_QC_SYSTEM_PROMPT, _build_judge_prompt(package, clip_meta, det_issues),
                   temperature=0.3)
    except Exception as e:  # noqa: BLE001 — 429/network/timeout → llm=skipped
        log.warning("QC LLM judge lỗi (%s) → llm=skipped", e)
        return None
    return _parse_judge_json(raw)


# ─── public entry ─────────────────────────────────────────────────────────────

def run_script_qc(package: dict, library: str,
                  base_warnings: Optional[list] = None,
                  use_llm: Optional[bool] = None) -> dict[str, Any]:
    """QC 1 script_package. KHÔNG raise — lỗi → check tương ứng = skipped."""
    if use_llm is None:
        try:
            from config import CREATIVE_QC_USE_LLM
            use_llm = CREATIVE_QC_USE_LLM
        except Exception:  # noqa: BLE001
            use_llm = False

    pkg = package or {}
    issues: list[dict] = []

    # ── lớp deterministic (luôn chạy) ──
    try:
        det_issues, clip_meta = _deterministic_checks(pkg, library)
        det_issues += _check_cut_off(pkg.get("script"), pkg.get("text_hook"))
        det_issues += _merge_base_warnings(base_warnings)
        det_status = "warn" if det_issues else "pass"
    except Exception as e:  # noqa: BLE001 — deterministic không được giết pipeline
        log.warning("QC deterministic lỗi (%s) → skipped", e)
        det_issues, clip_meta, det_status = [], [], "skipped"
    issues += det_issues

    # ── lớp LLM judge (sau cờ) ──
    if use_llm:
        llm_issues = _llm_judge(pkg, clip_meta, det_issues)
        if llm_issues is None:
            llm_status = "skipped"
        else:
            llm_status = "warn" if llm_issues else "pass"
            issues += llm_issues
    else:
        llm_status = "skipped"

    return {
        "verdict": "warn" if issues else "pass",
        "checks": {"deterministic": det_status, "llm": llm_status},
        "issues": issues,
    }
