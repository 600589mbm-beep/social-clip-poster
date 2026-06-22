"""Download a video (YouTube / Kick) and trim it to a vertical 9:16 clip.

Two modes:
  - create_clip_from_url(...)  -> fixed start/end (or first-N-seconds)
  - create_auto_clip(...)      -> the bot picks the best ~N-second window
    by scanning audio loudness (a proxy for the "exciting" part) and cutting
    there. Falls back to the start if analysis fails.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _require(tool: str) -> None:
    if shutil.which(tool) is None:
        raise RuntimeError(
            f"`{tool}` not found on PATH. Install it first "
            f"(yt-dlp via pip; ffmpeg via brew/apt/choco)."
        )


def _download(url: str, browser_for_cookies: str | None) -> str:
    _require("yt-dlp")
    temp_file = f"temp_full_video_{abs(hash(url)) % 10_000_000}.mp4"
    dl_cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", temp_file,
        url,
    ]
    if "kick.com" in url.lower():
        dl_cmd += ["--impersonate", "chrome"]
        if browser_for_cookies:
            dl_cmd += ["--cookies-from-browser", browser_for_cookies]
    log.info("Downloading from %s ...", url)
    subprocess.run(dl_cmd, check=True)
    return temp_file


def _trim(src: str, start: str, end: str, output_path: str) -> str:
    """Re-encode [start, end] and pad/scale to vertical 1080x1920."""
    _require("ffmpeg")
    output_path = str(Path(output_path).with_suffix(".mp4"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    clip_cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", src,
        "-c:v", "libx264", "-c:a", "aac",
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        output_path,
    ]
    log.info("Creating clip %s -> %s ...", start, end)
    subprocess.run(clip_cmd, check=True)
    log.info("Clip saved: %s", output_path)
    return output_path


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _mean_volume(path: str, start: float, length: float) -> float:
    """Mean volume (dB) of a window; higher = louder. -999 on failure/silence."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(length),
         "-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", r.stderr)
    return float(m.group(1)) if m else -999.0


def pick_loud_window(path: str, target_len: float, max_candidates: int = 12) -> tuple[float, float]:
    """Return (start_seconds, length) of the loudest target_len window.

    If the video is shorter than the target, returns the whole thing.
    """
    _require("ffprobe")
    dur = _duration(path)
    if dur <= 0:
        return 0.0, target_len
    if dur <= target_len + 1:
        return 0.0, dur

    last_start = dur - target_len
    n = min(max_candidates, max(2, int(last_start // 15) + 1))
    step = last_start / (n - 1)
    best_start, best_vol = 0.0, -1e9
    for i in range(n):
        s = round(i * step, 2)
        v = _mean_volume(path, s, target_len)
        log.info("auto-scan window @%.0fs mean_volume=%.1fdB", s, v)
        if v > best_vol:
            best_vol, best_start = v, s
    log.info("auto-pick: start=%.0fs len=%.0fs (loudest %.1fdB)", best_start, target_len, best_vol)
    return best_start, target_len


def create_clip_from_url(
    url: str, start_time: str, end_time: str, output_path: str,
    *, browser_for_cookies: str | None = None, keep_temp: bool = False,
) -> str:
    """Download and trim to a fixed [start_time, end_time] window (HH:MM:SS or seconds)."""
    temp_file = _download(url, browser_for_cookies)
    try:
        return _trim(temp_file, start_time, end_time, output_path)
    finally:
        if not keep_temp and os.path.exists(temp_file):
            os.remove(temp_file)


def create_auto_clip(
    url: str, target_len: float, output_path: str,
    *, browser_for_cookies: str | None = None, keep_temp: bool = False,
) -> str:
    """Download, auto-detect the loudest target_len window, and clip it 9:16."""
    temp_file = _download(url, browser_for_cookies)
    try:
        try:
            start, length = pick_loud_window(temp_file, float(target_len))
        except Exception:
            log.exception("auto window detection failed; falling back to start")
            start, length = 0.0, float(target_len)
        return _trim(temp_file, str(start), str(start + length), output_path)
    finally:
        if not keep_temp and os.path.exists(temp_file):
            os.remove(temp_file)
