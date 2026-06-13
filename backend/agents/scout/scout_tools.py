# -*- coding: utf-8 -*-
"""
[A] Scout — tools cho Orchestrator (VNG Insider / Claw-a-thon).

Pattern giống agents.creative.tools / agents.publisher.tools:
    from agents.scout import TOOL_DEFINITIONS, execute_tool
Tools KHÔNG BAO GIỜ raise — lỗi trả {"status": "failed", "error": "..."}.

2 chế độ nguồn vào, CÙNG 1 logic xử lý:
  - Demo:  scout_dummy_input.json (metric = retention_3s_pct, đủ field)
  - Thật:  videos từ scout_fetcher.py (LLM extract trang search TikTok;
           metric = likes vì retention không public, format/độ dài có thể thiếu)

Không cần LLM / env var cho phần phân tích — thống kê thuần, deterministic.
"""

import json
import logging
import os
import re
import time
from statistics import mean, median

log = logging.getLogger(__name__)

# Bộ keyword ngách (Nghi chốt) — scout_fetcher dùng để quét.
KEYWORDS = {
    "career": ["tips phỏng vấn", "cv xin việc", "fresher it", "sinh viên ra trường",
               "xin việc công ty công nghệ"],
    "life_at_company": ["một ngày đi làm", "pov đi làm", "office tour",
                        "văn phòng công ty công nghệ", "day in the life"],
    "brand_nganh": ["vng", "vnggames", "zalo", "làm game", "dân it"],
    "format_viral": ['"3 điều"', '"đừng bao giờ"', '"sự thật về"', "pov"],
}

# Catalog hook pattern cần dò (tên hiển thị, regex match trên hook lowercase)
HOOK_PATTERNS = [
    ("Đừng bao giờ... (phủ định)", r"^đừng|đừng bao giờ|đừng trả lời"),
    ("3 điều... / N sai lầm... (liệt kê số)", r"\b\d+\s*(điều|sai lầm|cách|lý do|bí mật|tips?|câu hỏi)"),
    ("Sự thật về... (bóc trần)", r"sự thật|không ai nói|đột nhập"),
    ("POV: ... (nhập vai)", r"^pov|một ngày (đi làm|của|làm việc)"),
    ("Câu hỏi trực diện (bao nhiêu/thì sao/thế nào)", r"(bao nhiêu|thì sao|thế nào|như thế nào|\?)"),
    ("Bí quyết / mẹo", r"bí quyết|mẹo|tip giúp|cứu mạng"),
]

LENGTH_BUCKETS = [("30-40s", 30, 40), ("41-50s", 41, 50), ("51-60s", 51, 60)]
MIN_VIDEOS_PER_GROUP = 2  # nhóm <2 video không đủ tin cậy để xếp hạng
DUMMY_INPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "scout_dummy_input.json")


# ---------------------------------------------------------------- helpers

def _load_videos(input_path=None, videos=None):
    if videos:
        return {"videos": videos, "nganh": "(truyền trực tiếp)", "thu_thap_ngay": None}
    path = input_path or DUMMY_INPUT
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(mean(vals), 1) if vals else None


def _group_stats(videos, key, metric):
    """Nhóm theo 1 field (bỏ video thiếu field) → stats từng nhóm, sort theo metric."""
    groups = {}
    for v in videos:
        if v.get(key):
            groups.setdefault(v[key], []).append(v)
    out = []
    for name, vs in groups.items():
        out.append({
            "nhom": name,
            "so_video": len(vs),
            "metric_tb": _avg([v.get(metric) for v in vs]),
            "shares_tb": _avg([v.get("shares") for v in vs]),
            "views_tb": _avg([v.get("views") for v in vs]),
        })
    return sorted(out, key=lambda g: g["metric_tb"] or 0, reverse=True)


def _length_bucket_stats(videos, metric):
    out = []
    for label, lo, hi in LENGTH_BUCKETS:
        vs = [v for v in videos if v.get("do_dai_giay") and lo <= v["do_dai_giay"] <= hi]
        if vs:
            out.append({"nhom": label, "so_video": len(vs),
                        "metric_tb": _avg([v.get(metric) for v in vs])})
    return sorted(out, key=lambda g: g["metric_tb"] or 0, reverse=True)


def _hook_pattern_stats(videos, metric):
    out = []
    for name, pattern in HOOK_PATTERNS:
        vs = [v for v in videos if re.search(pattern, (v.get("hook") or "").lower())]
        if vs:
            out.append({"pattern": name, "so_video": len(vs),
                        "metric_tb": _avg([v.get(metric) for v in vs])})
    return sorted(out, key=lambda g: g["metric_tb"] or 0, reverse=True)


def _do_dai_toi_uu(videos, nguong, metric):
    """Khoảng IQR độ dài của video vượt ngưỡng. None nếu thiếu data độ dài."""
    co_do_dai = [v for v in videos if v.get("do_dai_giay")]
    if len(co_do_dai) < 3:
        return None
    durs = sorted(v["do_dai_giay"] for v in co_do_dai if (v.get(metric) or 0) >= nguong)
    if len(durs) < 2:
        durs = sorted(v["do_dai_giay"] for v in co_do_dai)
    lo = durs[max(0, len(durs) // 4)]
    hi = durs[min(len(durs) - 1, (3 * len(durs)) // 4)]
    return f"{lo}-{hi} giây ({metric} cao nhất)"


def _fmt_nguong(nguong, metric):
    return f"{nguong}{'%' if 'pct' in metric else ''} {metric}"


def _insights_nguoi_doc(digest, metric):
    """Mẫu câu digest cho người đọc (spec mục 6). Python thuần — deterministic.
    Muốn câu chữ tự nhiên hơn: thay hàm này bằng 1 LLM call, input là digest."""
    s = []
    if digest["top_format"]:
        top = digest["top_format"][0]
        s.append(f"Format thắng là {top['format']}, {metric} trung bình {top['metric_tb']}.")
    if digest["do_dai_toi_uu"]:
        s.append(f"Video {digest['do_dai_toi_uu']} giữ chân tốt nhất.")
        buckets = digest["chi_tiet"]["nhom_do_dai"]
        if len(buckets) > 1:
            s[-1] += f" Nhóm {buckets[-1]['nhom']} tụt rõ (~{buckets[-1]['metric_tb']})."
    if digest["hook_pattern_thang"]:
        hooks = " và ".join(f"'{h}'" for h in digest["hook_pattern_thang"][:2])
        s.append(f"Hook dạng {hooks} đang ăn.")
    if digest["format_yeu"]:
        s.append(digest["format_yeu"])
    s.append(f"Đề xuất ngưỡng đạt: {_fmt_nguong(digest['benchmark_khoi_tao']['nguong'], metric)} trở lên.")
    return s


# ---------------------------------------------------------------- tool chính

def scan_trends(input_path=None, videos=None, top_n=3, metric_field="retention_3s_pct"):
    """Đọc dữ liệu video viral → digest xu hướng.

    metric_field: cột dùng để xếp hạng + seed benchmark.
      - dummy/demo: "retention_3s_pct"
      - data thật từ fetcher: "likes" (retention không public — proxy)
    Video thiếu metric_field bị loại khỏi phân tích (đếm trong so_video_loai).
    """
    t0 = time.monotonic()
    nguon = "videos truyền thẳng" if videos else (input_path or "dummy seed")
    log.info("scan_trends · BẮT ĐẦU · metric=%s top_n=%d nguon=%s", metric_field, top_n, nguon)
    try:
        data = _load_videos(input_path, videos)
        raw = data.get("videos") or []
        vids = [v for v in raw if v.get(metric_field) is not None]
        if len(vids) < 3:
            log.warning("scan_trends · quá ít video có '%s' (%d/%d) — không đủ rút insight",
                        metric_field, len(vids), len(raw))
            return {"status": "failed",
                    "error": f"Quá ít video có '{metric_field}' để rút insight ({len(vids)}/{len(raw)})",
                    "digest": None}

        nguong = round(median(v[metric_field] for v in vids))

        fmt = _group_stats(vids, "format", metric_field)
        fmt_ranked = [g for g in fmt if g["so_video"] >= MIN_VIDEOS_PER_GROUP] or fmt
        top_format = [{"format": g["nhom"], "metric_tb": g["metric_tb"],
                       "so_video": g["so_video"],
                       **({"ghi_chu": "thắng nhất"} if i == 0 else {})}
                      for i, g in enumerate(fmt_ranked[:top_n])]
        format_yeu = None
        if fmt_ranked and (fmt_ranked[-1]["metric_tb"] or 0) < nguong:
            yeu = fmt_ranked[-1]
            format_yeu = (f"{yeu['nhom']} ({metric_field} thấp ~{yeu['metric_tb']}) "
                          f"→ cần thêm hook mạnh 3s đầu video")

        buckets = _length_bucket_stats(vids, metric_field)
        hooks = _hook_pattern_stats(vids, metric_field)
        hook_thang = [h["pattern"] for h in hooks if (h["metric_tb"] or 0) >= nguong]
        chude = _group_stats(vids, "chu_de", metric_field)
        chu_de_hot = [g["nhom"] for g in chude if g["so_video"] >= MIN_VIDEOS_PER_GROUP][:2]

        digest = {
            "digest_tuan": data.get("thu_thap_ngay"),
            "nganh": data.get("nganh"),
            "metric": metric_field,
            "so_video_quet": len(vids),
            "so_video_loai": len(raw) - len(vids),
            "top_format": top_format,
            "do_dai_toi_uu": _do_dai_toi_uu(vids, nguong, metric_field),
            "hook_pattern_thang": hook_thang,
            "chu_de_hot": chu_de_hot,
            "format_yeu": format_yeu,
            "benchmark_khoi_tao": {
                "metric": metric_field,
                "nguong": nguong,
                # alias giữ tương thích spec gốc khi chạy demo retention
                **({"retention_3s_pct_nguong": nguong} if metric_field == "retention_3s_pct" else {}),
                "ghi_chu": f"video dưới {_fmt_nguong(nguong, metric_field)} coi như chưa đạt ngưỡng tuyệt đối",
            },
            "chi_tiet": {"format": fmt, "nhom_do_dai": buckets,
                         "hook_pattern": hooks, "chu_de": chude},
        }
        digest["insight"] = _insights_nguoi_doc(digest, metric_field)
        log.info("scan_trends · XONG · %d video (loại %d) · ngưỡng %d %s · %d hook thắng · "
                 "%d chủ đề hot · %.2fs",
                 len(vids), len(raw) - len(vids), nguong, metric_field,
                 len(hook_thang), len(chu_de_hot), time.monotonic() - t0)
        return {
            "status": "ok", "error": None,
            "digest": digest,
            "day_cho_creative": {  # → [B] bám trend
                "top_format": top_format,
                "hook_pattern_thang": hook_thang,
                "do_dai_toi_uu": digest["do_dai_toi_uu"],
                "chu_de_hot": chu_de_hot,
            },
            "day_cho_analyst": digest["benchmark_khoi_tao"],  # → [E] làm passB
        }
    except Exception as e:
        log.exception("scan_trends · LỖI sau %.2fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "error": str(e), "digest": None}


# ------------------------------------------------- contract với Orchestrator

TOOL_DEFINITIONS = [
    {
        "name": "scan_trends",
        "description": (
            "Trinh sát thị trường: đọc dữ liệu video viral cùng ngách (dummy input hoặc "
            "data thật từ scout_fetcher) → digest xu hướng: top format, hook pattern thắng, "
            "độ dài tối ưu, chủ đề hot + benchmark khởi tạo. Chạy ngay khi human yêu cầu "
            "'quét trend'. Output: day_cho_creative → [B], day_cho_analyst → [E]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string",
                               "description": "File input JSON (default: scout_dummy_input.json)"},
                "videos": {"type": "array",
                           "description": "List video truyền thẳng (vd: output scout_fetcher)"},
                "top_n": {"type": "integer", "default": 3},
                "metric_field": {"type": "string", "default": "retention_3s_pct",
                                 "description": "Cột xếp hạng: retention_3s_pct (demo) | likes (data thật)"},
            },
        },
    },
]

_DISPATCH = {"scan_trends": scan_trends}


def execute_tool(name: str, tool_input: dict) -> dict:
    """Entry point cho Orchestrator. Không bao giờ raise."""
    fn = _DISPATCH.get(name)
    if fn is None:
        log.warning("execute_tool · tool không tồn tại: %s", name)
        return {"status": "failed", "error": f"Tool không tồn tại: {name}"}
    try:
        return fn(**(tool_input or {}))
    except TypeError as e:
        log.warning("execute_tool · sai input cho %s: %s", name, e)
        return {"status": "failed", "error": f"Sai input: {e}"}


# ---------------------------------------------------------------- smoke test
if __name__ == "__main__":
    r = execute_tool("scan_trends", {})
    print(json.dumps(r, ensure_ascii=False, indent=2))
