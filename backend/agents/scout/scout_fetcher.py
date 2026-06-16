# -*- coding: utf-8 -*-
"""
[A] Scout fetcher — bước "browsing" lấy data THẬT, dùng LLM extract.

Pipeline LLM-browsing (2 bước, tách rõ vai):
  1. BROWSE  — lấy raw text trang search TikTok theo keyword ngách.
     Demo hiện tại: browser có session login (agent/Claude in Chrome/AgentBase
     browser tool) mở https://www.tiktok.com/search/video?q=<keyword>,
     lấy page text → lưu samples/raw_search_*.txt
  2. EXTRACT — LLM đọc raw text → list video JSON đúng schema scan_trends.
     (extract_videos / fetch_from_samples dưới đây)

Nguyên tắc: LLM CHỈ làm phần hiểu ngôn ngữ (extract, phân loại chủ đề,
đoán format từ caption). KHÔNG để LLM tính số — phân tích/benchmark là
việc của scout_tools.scan_trends (Python thuần).

Lưu ý data thật từ trang search:
  - likes có (dạng "213.7K" → LLM đổi ra số), views/shares/retention KHÔNG có
  - độ dài video KHÔNG có → scan_trends(metric_field="likes") đã chịu được
  - format chỉ đoán được từ caption (POV/vlog/listicle...) → có thể null

Env đọc qua root config.py (single source of truth — giống agents.creative):
    AI_PLATFORM_BASE_URL  — share endpoint với Creative + Producer
    AI_PLATFORM_API_KEY   — share API key
    SCOUT_MODEL           — model RIÊNG cho Scout (tách khỏi CREATIVE_MODEL,
                            sau này có thể đổi độc lập)
"""

import glob
import json
import logging
import os
import re
import time

import requests

from config import AI_PLATFORM_API_KEY, AI_PLATFORM_BASE_URL, SCOUT_MODEL

log = logging.getLogger(__name__)

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 300

SYSTEM_EXTRACT = """Bạn là bộ extract dữ liệu của Scout Agent (trinh sát trend TikTok ngách career/office-life VN).
Input: raw text của trang kết quả search TikTok (mỗi video gồm: số like, caption, author, ngày đăng — thứ tự có thể lẫn nhãn "Top liked").
Nhiệm vụ: trả về JSON array, mỗi video 1 object:
{
  "hook": "<câu mở/ý chính của caption, BỎ hashtag, giữ tiếng Việt nguyên bản>",
  "likes": <số nguyên, đổi 22.4K -> 22400, 1.2M -> 1200000>,
  "author": "<username>",
  "ngay_dang": "<YYYY-MM-DD nếu đủ; '3-12' nghĩa là tháng 3 ngày 12 năm hiện tại (2026); '4d ago' -> null>",
  "chu_de": "<một trong: tips phỏng vấn | career tips | office life | office tour | làm game | làm tech | khác>",
  "format": "<chỉ khi caption cho thấy rõ: 'POV b-roll' | 'vlog' | 'listicle' | 'talking-head' | 'office tour'; không rõ -> null>",
  "top_liked": <true nếu video có nhãn Top liked, ngược lại false>
}
Quy tắc:
- KHÔNG bịa số. Không suy ra views/shares/độ dài (trang không có).
- Caption không liên quan ngách career/office-life (vd quảng cáo phim) vẫn extract, để chu_de="khác".
- Chỉ trả JSON array, không giải thích."""


def _chat(system: str, user: str, temperature: float = 0.1, max_tokens: int = 16000) -> str:
    # max_tokens 16000: trang search ~24 video, model trả JSON pretty-print
    # nên 4000 bị cụt trước khi đóng ']' (extract fail toàn trang)
    """Gọi VNGCloud MaaS (OpenAI-compatible, streaming — cùng lý do với creative.tools:
    response non-stream dễ dính idle timeout ở gateway). KHÔNG tự retry."""
    if not AI_PLATFORM_BASE_URL or not AI_PLATFORM_API_KEY:
        raise RuntimeError("Thiếu AI_PLATFORM_BASE_URL / AI_PLATFORM_API_KEY trong env")
    if not SCOUT_MODEL:
        raise RuntimeError("Thiếu SCOUT_MODEL trong env")
    t0 = time.monotonic()
    log.info("chat · POST %s/chat/completions · model=%s temp=%.2f sys=%dc user=%dc max=%d",
             AI_PLATFORM_BASE_URL, SCOUT_MODEL, temperature, len(system), len(user), max_tokens)
    resp = requests.post(
        f"{AI_PLATFORM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {AI_PLATFORM_API_KEY}"},
        json={"model": SCOUT_MODEL, "stream": True, "temperature": temperature,
              "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True,
    )
    if resp.status_code == 429:
        log.warning("chat · 429 rate limit từ MaaS — KHÔNG retry")
        raise RuntimeError("429 rate limit từ gateway — chờ window reset, không retry")
    resp.raise_for_status()
    # Ép utf-8: route Gemini của MaaS trả 'text/event-stream' không kèm charset →
    # requests đoán Latin-1 → mojibake khi decode_unicode. Vô hại với model đã utf-8.
    resp.encoding = "utf-8"
    chunks = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            delta = json.loads(payload)["choices"][0]["delta"]
            chunks.append(delta.get("content") or "")
        except (KeyError, IndexError, json.JSONDecodeError):
            continue
    out = "".join(chunks)
    log.info("chat · done · %d chars trong %.1fs (model=%s)", len(out), time.monotonic() - t0, SCOUT_MODEL)
    return out


def _extract_json_array(raw: str):
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        raise ValueError(f"LLM không trả JSON array: {raw[:200]}")
    try:
        from json_repair import repair_json
        return json.loads(repair_json(m.group(0)))
    except ImportError:
        return json.loads(m.group(0))


# ---------------------------------------------------------------- tools

def extract_videos(raw_text, keyword=None):
    """LLM extract 1 trang raw text → list video dict (schema scan_trends)."""
    t0 = time.monotonic()
    log.info("extract_videos · BẮT ĐẦU · keyword=%r raw=%dc", keyword, len(raw_text or ""))
    try:
        user = (f"Keyword đã search: {keyword}\n\n" if keyword else "") + raw_text
        parsed = _extract_json_array(_chat(SYSTEM_EXTRACT, user))
        # LLM đôi khi trả lẫn string trong array — giữ object, bỏ phần còn lại
        # để vài phần tử hỏng không làm rớt cả trang
        vids = [v for v in parsed if isinstance(v, dict)]
        dropped = len(parsed) - len(vids)
        if not vids:
            log.warning("extract_videos · keyword=%r · LLM trả %d phần tử nhưng không có object",
                        keyword, len(parsed))
            return {"status": "failed",
                    "error": f"LLM trả {len(parsed)} phần tử nhưng không có object nào",
                    "videos": None}
        for i, v in enumerate(vids):
            v["id"] = f"{(keyword or 'kw').replace(' ', '_')}_{i+1:02d}"
            v["keyword"] = keyword
        err = f"bỏ {dropped}/{len(parsed)} phần tử không phải object" if dropped else None
        log.info("extract_videos · XONG · keyword=%r · %d video%s · %.1fs",
                 keyword, len(vids), f" (bỏ {dropped})" if dropped else "", time.monotonic() - t0)
        return {"status": "ok", "error": err, "videos": vids}
    except Exception as e:
        log.exception("extract_videos · LỖI keyword=%r sau %.1fs: %s", keyword, time.monotonic() - t0, e)
        return {"status": "failed", "error": str(e), "videos": None}


def fetch_from_samples(samples_dir=None):
    """Extract toàn bộ samples/raw_search_*.txt → 1 list video gộp.
    Đây là bản demo của bước browse: file raw do browser/agent lưu sẵn.
    Bản nối AgentBase browser tool: thay vòng đọc file bằng vòng gọi tool browse."""
    t0 = time.monotonic()
    try:
        d = samples_dir or SAMPLES_DIR
        files = sorted(glob.glob(os.path.join(d, "raw_search_*.txt")))
        if not files:
            log.warning("fetch_from_samples · không có raw_search_*.txt trong %s", d)
            return {"status": "failed", "error": f"Không có samples/raw_search_*.txt trong {d}", "videos": None}
        log.info("fetch_from_samples · BẮT ĐẦU · %d trang search trong %s", len(files), d)
        all_vids, errors = [], []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                raw = fh.read()
            kw = os.path.basename(f).replace("raw_search_", "").replace(".txt", "").replace("_", " ")
            r = extract_videos(raw, keyword=kw)
            if r["status"] == "ok":
                all_vids.extend(r["videos"])
                if r["error"]:  # trang ok nhưng có phần tử bị bỏ — vẫn báo lên
                    errors.append(f"{kw}: {r['error']}")
            else:
                errors.append(f"{kw}: {r['error']}")
        if not all_vids:
            log.warning("fetch_from_samples · không extract được video nào từ %d trang: %s",
                        len(files), "; ".join(errors))
            return {"status": "failed", "error": "; ".join(errors), "videos": None}
        log.info("fetch_from_samples · XONG · %d video từ %d trang%s · %.1fs",
                 len(all_vids), len(files), f" ({len(errors)} cảnh báo)" if errors else "",
                 time.monotonic() - t0)
        return {"status": "ok", "error": "; ".join(errors) or None, "videos": all_vids}
    except Exception as e:
        log.exception("fetch_from_samples · LỖI sau %.1fs: %s", time.monotonic() - t0, e)
        return {"status": "failed", "error": str(e), "videos": None}


TOOL_DEFINITIONS = [
    {
        "name": "fetch_from_samples",
        "description": ("Bước browse+extract của Scout (data thật): đọc các trang search TikTok "
                        "đã lưu trong samples/ → LLM extract ra list video JSON. "
                        "Kết quả truyền vào scan_trends(videos=..., metric_field='likes')."),
        "input_schema": {"type": "object", "properties": {
            "samples_dir": {"type": "string", "description": "Thư mục chứa raw_search_*.txt (optional)"}}},
    },
    {
        "name": "extract_videos",
        "description": "LLM extract 1 trang raw text search TikTok → list video JSON.",
        "input_schema": {"type": "object",
                         "properties": {"raw_text": {"type": "string"},
                                        "keyword": {"type": "string"}},
                         "required": ["raw_text"]},
    },
]

_DISPATCH = {"fetch_from_samples": fetch_from_samples, "extract_videos": extract_videos}


def execute_tool(name: str, tool_input: dict) -> dict:
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
    r = execute_tool("fetch_from_samples", {})
    if r["status"] == "ok":
        print(f"Extract được {len(r['videos'])} video. 3 video đầu:")
        print(json.dumps(r["videos"][:3], ensure_ascii=False, indent=2))
        from scout_tools import scan_trends
        d = scan_trends(videos=r["videos"], metric_field="likes")
        print(json.dumps(d.get("digest", d), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(r, ensure_ascii=False, indent=2))
