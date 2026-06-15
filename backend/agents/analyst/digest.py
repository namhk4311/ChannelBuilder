"""[E] Analyst — rút insight_digest từ batch đã graded (deterministic, stdlib).

insight_digest = công thức "thắng/thua" + đề xuất vòng sau, đẩy về [B] Creative qua
generate_ideas(insight_digest=...). Shape linh hoạt (Creative chỉ json.dumps vào
prompt) nhưng phải JSON-serializable — không nhét object lạ.

Heuristic độ dài: lấy max do_dai trong nhóm video ĐẠT ngưỡng (passB) làm mốc "thắng",
min do_dai nhóm KILL làm mốc "tụt" — suy từ data, không hard-code.
"""
from __future__ import annotations

from typing import Any, Iterable


def build_insight_digest(videos: list[dict[str, Any]], batch: str) -> dict[str, Any]:
    scale = [v for v in videos if v["label"] == "SCALE"]
    monitor = [v for v in videos if v["label"] == "MONITOR"]
    kill = [v for v in videos if v["label"] == "KILL"]
    good = [v for v in videos if v.get("passB")]        # đạt ngưỡng tuyệt đối
    win_src = scale or monitor or good                  # nguồn tín hiệu "thắng"

    thang = {
        "hook_type": _uniq(v.get("hook_type") for v in win_src),
        "chu_de": [v.get("chu_de") for v in win_src if v.get("chu_de")],
        "do_dai": _len_note(good, kill),
    }
    thua = {
        "hook_type": _uniq(v.get("hook_type") for v in kill),
        "chu_de": [v.get("chu_de") for v in kill if v.get("chu_de")],
    }
    return {
        "batch": batch,
        "thang": thang,
        "thua": thua,
        "de_xuat_vong_sau": _recommend(scale, good, kill, thang, thua),
    }


def _uniq(values: Iterable[Any]) -> list[Any]:
    """Bỏ trùng + giữ thứ tự xuất hiện, loại None/rỗng."""
    out: list[Any] = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return out


def _len_note(good: list[dict], kill: list[dict]) -> str:
    if not good:
        return "Cả lô dưới ngưỡng — chưa kết luận được độ dài tối ưu."
    win_max = max(v.get("do_dai", 0) for v in good)
    if kill:
        kill_min = min(v.get("do_dai", 0) for v in kill)
        if kill_min > win_max:
            return f"Video ≤{win_max}s giữ chân tốt; video >{kill_min - 1}s dễ tụt."
    return f"Video ≤{win_max}s giữ chân tốt."


def _recommend(scale: list[dict], good: list[dict], kill: list[dict],
               thang: dict, thua: dict) -> str:
    lose_hooks = ", ".join(thua["hook_type"]) or "không rõ"
    if not scale:
        # Cả lô không có video nào vừa top vừa vượt ngưỡng → không có công thức thắng
        # để nhân (điểm wow: best of a bad batch vẫn KHÔNG được scale).
        return (f"Cả lô không đạt — không có công thức thắng để nhân. Hạn chế hook "
                f"«{lose_hooks}» (tả cảnh chay); vòng sau thử hook phủ định / liệt kê và "
                f"rút video ≤50s.")
    win_hooks = ", ".join(_uniq(v.get("hook_type") for v in scale)) or "không rõ"
    win_max = max(v.get("do_dai", 0) for v in good) if good else 50
    return (f"Ưu tiên hook «{win_hooks}»; giữ video ≤{win_max}s; "
            f"hạn chế hook «{lose_hooks}» (tả cảnh chay, video dài).")
