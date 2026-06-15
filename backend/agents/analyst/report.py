"""[E] Analyst — báo cáo người-đọc từ batch graded + insight digest (stdlib).

Kết "[Chờ human bấm xác nhận]" đúng nguyên tắc gốc: AI execute + learn, Human decide.
"""
from __future__ import annotations

from typing import Any

_ICON = {"SCALE": "✅", "MONITOR": "🟡", "KILL": "⛔"}


def build_report(videos: list[dict[str, Any]], digest: dict[str, Any], batch: str,
                 threshold: int = 65, top_k: int = 0) -> str:
    lines: list[str] = []
    lines.append(f"📊 Báo cáo Analyst — batch {batch}")
    lines.append(f"Ngưỡng tuyệt đối: retention_3s ≥ {threshold}% · Top lô: {top_k} video "
                 f"· Tổng {len(videos)} video")
    lines.append("")

    for label in ("SCALE", "MONITOR", "KILL"):
        group = [v for v in videos if v["label"] == label]
        ids = ", ".join(v["id"] for v in group) or "—"
        lines.append(f"{_ICON[label]} {label} ({len(group)}): {ids}")
        for v in group:
            lines.append(f"   • {v['id']} ({v.get('retention_3s_pct')}% · {v.get('hook_type')}): "
                         f"{v.get('reason')}")
    lines.append("")

    thang, thua = digest.get("thang", {}), digest.get("thua", {})
    lines.append("🧠 Insight vòng sau:")
    lines.append(f"   • Thắng — hook [{', '.join(thang.get('hook_type') or []) or '—'}] · "
                 f"{thang.get('do_dai', '')}")
    lines.append(f"   • Thua — hook [{', '.join(thua.get('hook_type') or []) or '—'}] (cần tránh)")
    lines.append(f"   • Đề xuất: {digest.get('de_xuat_vong_sau', '')}")
    lines.append("")
    lines.append("→ [Chờ human bấm “Xác nhận scale” trước khi nhân nội dung — "
                 "AI execute + learn, Human decide]")
    return "\n".join(lines)
