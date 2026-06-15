"""[E] Analyst — absolute gate (2 phanh) thuần Python, deterministic.

Đây là "logic chấm thật": không LLM, không network, không DB — chỉ số học.
Mỗi video được gắn 2 cờ:
  • passA = top 20% retention TRONG LÔ (giỏi tương đối) — chặn "best of a bad batch"
    bằng cách kết hợp với passB.
  • passB = retention ≥ ngưỡng tuyệt đối (giỏi thật).
Nhãn (passB = ngưỡng tuyệt đối là điều kiện sống còn — chốt theo success criteria
của plan, KHÔNG theo pseudocode "passA or passB" vì pseudocode đó cho b03 = MONITOR,
mâu thuẫn yêu cầu "badbatch → KILL hết"):
  • SCALE   = passA AND passB → vừa top lô vừa vượt ngưỡng → đáng nhân nội dung.
  • MONITOR = passB AND NOT passA → vượt ngưỡng nhưng chưa vào top lô → giữ, theo dõi.
  • KILL    = NOT passB → dưới ngưỡng tuyệt đối → ngừng làm kiểu này.
              (kể cả khi passA = top lô — chính là "best of a bad batch" cần chặn.)

Quy ước Nghi (KHÔNG đổi): ngưỡng retention_3s = 65 · top 20% = ceil(0.2×n) · metric = retention_3s_pct.
"""
from __future__ import annotations

import math
from typing import Any


def grade_batch(videos: list[dict[str, Any]], threshold: int = 65) -> dict[str, Any]:
    """Chấm cả batch theo absolute gate. Trả dict gọn (không raise).

    top_k = ceil(0.2 × n) (8→2, 4→1). Tie ở ranh top_k: sort desc ổn định + lấy N đầu.
    """
    n = len(videos)
    top_k = math.ceil(0.2 * n) if n else 0
    ranked = sorted(videos, key=lambda v: v.get("retention_3s_pct", 0), reverse=True)
    top_ids = {v["id"] for v in ranked[:top_k]}

    out: list[dict[str, Any]] = []
    for v in videos:
        retention = v.get("retention_3s_pct", 0)
        passA = v["id"] in top_ids                 # top 20% — giỏi tương đối
        passB = retention >= threshold             # ngưỡng tuyệt đối — giỏi thật
        if passA and passB:
            label = "SCALE"
        elif passB:                                # passB & not passA (passA&passB đã là SCALE)
            label = "MONITOR"
        else:
            label = "KILL"                         # not passB — kể cả top lô (best of a bad batch)
        out.append({**v, "passA": passA, "passB": passB, "label": label,
                    "reason": _reason(v, label, passA, threshold)})
    return {"status": "ok", "threshold": threshold, "top_k": top_k, "n": n, "videos": out}


def _reason(v: dict[str, Any], label: str, passA: bool, threshold: int) -> str:
    """Lý do người-đọc theo hook_type + chủ đề + độ dài."""
    hook = v.get("hook_type", "?")
    chu_de = v.get("chu_de", "?")
    do_dai = v.get("do_dai", 0)
    retention = v.get("retention_3s_pct", 0)
    if label == "SCALE":
        return f"Nhân thêm: hook «{hook}» / chủ đề «{chu_de}» giữ chân tốt."
    if label == "MONITOR":
        return f"Đạt ngưỡng giữ chân nhưng chưa vào top lô — giữ, theo dõi thêm hook «{hook}»."
    long_note = ", video >53s dễ tụt" if do_dai > 53 else ""
    if passA:  # top lô nhưng dưới ngưỡng — đúng bẫy "best of a bad batch"
        return (f"Top lô nhưng retention {retention} < ngưỡng {threshold} — KHÔNG nhân "
                f"(tránh scale best-of-a-bad-batch){long_note}.")
    return f"Ngừng kiểu này: hook «{hook}» dưới ngưỡng{long_note}."
