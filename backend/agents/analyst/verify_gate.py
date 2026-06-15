"""Verify "logic chấm là thật" — assert absolute gate ra ĐÚNG bảng spec, deterministic.

Chạy bằng system python3 (gate/digest/report thuần stdlib, KHÔNG cần venv backend):
    cd backend && python3 agents/analyst/verify_gate.py
Exit 0 khi PASS, in bảng so sánh + exit 1 khi lệch.

Hai bộ kỳ vọng:
  • MAIN  → 2 SCALE (p03,p01) · 2 MONITOR (p02,p06) · 4 KILL — bảng spec mục 4.
  • BAD   → toàn KILL (b03 là top lô / passA=True nhưng passB=False → KILL):
            điểm wow "chặn scale best of a bad batch".
"""
from __future__ import annotations

import sys

# Cho phép chạy trực tiếp `python3 agents/analyst/verify_gate.py` từ backend/.
if __package__ in (None, ""):
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agents.analyst import run_analyst  # noqa: E402

EXPECTED_MAIN = {
    "p03": "SCALE", "p01": "SCALE",
    "p02": "MONITOR", "p06": "MONITOR",
    "p04": "KILL", "p05": "KILL", "p07": "KILL", "p08": "KILL",
}
EXPECTED_BAD = {"b01": "KILL", "b02": "KILL", "b03": "KILL", "b04": "KILL"}


def _check_labels(batch_name: str, expected: dict[str, str], fails: list[str]) -> dict:
    result = run_analyst(batch_name)
    assert result["status"] == "ok", f"{batch_name}: run_analyst status != ok ({result.get('error')})"
    got = {v["id"]: v["label"] for v in result["videos"]}
    print(f"\n[{batch_name}] threshold={result['threshold']} top_k={result['top_k']}")
    for vid, exp in expected.items():
        actual = got.get(vid)
        ok = actual == exp
        print(f"  {'✓' if ok else '✗'} {vid}: expected {exp:<8} got {actual}")
        if not ok:
            fails.append(f"{batch_name}/{vid}: expected {exp}, got {actual}")
    return result


def main() -> int:
    fails: list[str] = []

    main_res = _check_labels("analyst_dummy_batch", EXPECTED_MAIN, fails)
    bad_res = _check_labels("analyst_dummy_badbatch", EXPECTED_BAD, fails)

    # Ca passA/passB minh hoạ — lõi của "best of a bad batch".
    by_id_main = {v["id"]: v for v in main_res["videos"]}
    by_id_bad = {v["id"]: v for v in bad_res["videos"]}

    def _assert(cond: bool, msg: str) -> None:
        print(f"  {'✓' if cond else '✗'} {msg}")
        if not cond:
            fails.append(msg)

    print("\n[flags] ca minh hoạ passA/passB:")
    _assert(by_id_main["p02"]["passA"] is False and by_id_main["p02"]["passB"] is True,
            "p02: passB only (đạt ngưỡng, ngoài top lô) → MONITOR")
    _assert(by_id_bad["b03"]["passA"] is True and by_id_bad["b03"]["passB"] is False
            and by_id_bad["b03"]["label"] == "KILL",
            "b03: passA only (top lô, dưới ngưỡng) → KILL (best of a bad batch)")

    # scale_ids + digest sanity.
    print("\n[derived]")
    _assert(main_res["scale_ids"] == ["p03", "p01"],
            f"MAIN scale_ids == ['p03','p01'] (got {main_res['scale_ids']})")
    _assert(bad_res["scale_ids"] == [],
            f"BAD scale_ids rỗng (got {bad_res['scale_ids']})")
    dg = main_res["insight_digest"]
    _assert("phủ định" in dg["thang"]["hook_type"] and "liệt kê" in dg["thang"]["hook_type"],
            "MAIN digest thang.hook_type chứa phủ định + liệt kê")
    _assert("tả cảnh" in dg["thua"]["hook_type"],
            "MAIN digest thua.hook_type chứa tả cảnh")
    _assert("≤50s" in dg["de_xuat_vong_sau"],
            "MAIN digest de_xuat nhắc ≤50s")
    _assert("SCALE (0)" in bad_res["report"],
            "BAD report: SCALE rỗng")

    print()
    if fails:
        print(f"❌ FAIL ({len(fails)} lệch):")
        for f in fails:
            print("   -", f)
        return 1
    print("✅ PASS — absolute gate khớp bảng spec (MAIN + BAD) + flags + digest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
