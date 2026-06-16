# -*- coding: utf-8 -*-
"""Phụ đề theo cụm (cho template Đơn sắc) — burn caption sync giọng đọc từng cảnh.

`build_caption_cues(text, voice_sec)` → list cue {t0,t1,text} chia đều theo độ dài cụm
trên [0, voice_sec]. Template render qua BT.caption(t, cues) (seek-driven, khớp determinism).
Timing là XẤP XỈ (chia theo độ dài chữ) — đủ cho phụ đề mức cụm/câu.
"""
from __future__ import annotations

import re

_TAG = re.compile(r"\[[^\]]+\]")               # emotion tag [excited]…
_SENT = re.compile(r"[^.!?…]+[.!?…]?")           # tách theo câu
_CAP_CHARS = 64                                  # cụm quá dài → chẻ mềm theo dấu phẩy


def _strip_tags(s: str) -> str:
    return _TAG.sub("", s or "").strip()


def _split_phrases(text: str) -> list:
    """Chẻ text thành các cụm hiển thị (câu; câu dài → tách thêm theo dấu phẩy)."""
    out = []
    for sent in _SENT.findall(text):
        s = sent.strip()
        if not s:
            continue
        if len(s) <= _CAP_CHARS:
            out.append(s)
            continue
        # câu dài: gộp dần các mệnh đề (phẩy) cho tới khi vượt ngưỡng
        buf = ""
        for part in re.split(r"(?<=,)\s+", s):
            if buf and len(buf) + len(part) > _CAP_CHARS:
                out.append(buf.strip())
                buf = part
            else:
                buf = (buf + " " + part).strip() if buf else part
        if buf.strip():
            out.append(buf.strip())
    return out


def build_caption_cues(text: str, voice_sec: float) -> list:
    """Voiceover (có/không tag) + độ dài voice → [{t0,t1,text}] chia đều theo độ dài cụm."""
    clean = _strip_tags(text)
    dur = float(voice_sec or 0)
    if not clean or dur <= 0.1:
        return []
    phrases = _split_phrases(clean)
    if not phrases:
        return []
    total = sum(len(p) for p in phrases) or 1
    cues, t = [], 0.0
    for i, p in enumerate(phrases):
        span = dur * (len(p) / total)
        t1 = dur if i == len(phrases) - 1 else min(dur, t + span)
        cues.append({"t0": round(t, 3), "t1": round(t1, 3), "text": p})
        t = t1
    return cues
