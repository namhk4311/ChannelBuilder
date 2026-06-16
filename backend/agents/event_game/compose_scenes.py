# -*- coding: utf-8 -*-
"""Ghép nhiều scene thành 1 video có chuyển cảnh + (optional) lồng nhạc nền.

VIDEO: chain ffmpeg `xfade` giữa các silent clip. AUDIO: đặt voice mỗi scene đúng mốc
(adelay) rồi amix. Sau đó `mux_music_over` lồng nhạc nền + sidechain duck (nhẹ hơn vlog,
to hơn) dùng voice làm trigger.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("event_game.compose")

CURATED = ["fadeblack", "smoothleft", "circleopen", "dissolve", "zoomin", "slideup", "pixelize"]
TD = 0.6  # transition duration (giây)


def compose(silents: List[Path], voices: List[Path], vlens: List[float],
            out_path: Path, fps: int = 30, transitions: Optional[List[str]] = None) -> Path:
    """silents[i] (dài vlens[i]) + voices[i] → out_path (xfade + voice khớp mốc, CHƯA nhạc)."""
    n = len(silents)
    assert n == len(voices) == len(vlens) and n >= 1
    if n == 1:
        cmd = ["ffmpeg", "-y", "-i", str(silents[0]), "-i", str(voices[0]),
               "-map", "0:v:0", "-c:v", "copy", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(out_path)]
        _run(cmd, "compose(1)")
        return out_path

    trans = transitions or [CURATED[k % len(CURATED)] for k in range(n - 1)]
    cmd = ["ffmpeg", "-y"]
    for s in silents:
        cmd += ["-i", str(s)]
    for v in voices:
        cmd += ["-i", str(v)]

    filters = []
    prev, acc = "[0:v]", vlens[0]
    for k in range(1, n):
        out = "[vout]" if k == n - 1 else f"[vx{k}]"
        filters.append(f"{prev}[{k}:v]xfade=transition={trans[k - 1]}:duration={TD}:offset={acc - TD:.3f}{out}")
        prev = out
        acc += vlens[k] - TD

    starts, s = [0.0], 0.0
    for i in range(1, n):
        s += vlens[i - 1] - TD
        starts.append(s)
    for i in range(n):
        filters.append(f"[{n + i}:a]adelay={int(round(starts[i] * 1000))}:all=1[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0[aout]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    log.info("compose · %d scene · transitions=%s · total≈%.1fs", n, trans, acc)
    _run(cmd, f"compose({n})")
    return out_path


def mux_music_over(video_with_voice: Path, music: Path, out_path: Path, volume: float = 0.55) -> Path:
    """Lồng nhạc nền (loop) lên video đã có voice + sidechain duck NHẸ (nhạc to hơn vlog).

    Trigger duck = voice (audio sẵn của video). threshold cao + ratio thấp → duck nhẹ,
    nhạc giữ độ to/đã hơn so với vlog (vlog threshold 0.05 ratio 10).
    """
    cmd = ["ffmpeg", "-y", "-i", str(video_with_voice), "-stream_loop", "-1", "-i", str(music),
           "-filter_complex",
           f"[1:a]volume={volume},aresample=48000,aformat=channel_layouts=stereo[m];"
           f"[m][0:a]sidechaincompress=threshold=0.1:ratio=4:attack=5:release=300[ducked];"
           f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[aout]",
           "-map", "0:v:0", "-c:v", "copy", "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", str(out_path)]
    log.info("mux_music · vol=%.2f over %s", volume, video_with_voice.name)
    _run(cmd, "mux_music")
    return out_path


def _run(cmd: list, tag: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("%s FAILED: %s", tag, result.stderr[-500:])
        raise RuntimeError(f"{tag} failed: {result.stderr[-400:]}")
