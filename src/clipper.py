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
    from src.sources import ytdlp_bin
    ytdlp = ytdlp_bin()
    if ytdlp is None:
        raise RuntimeError("yt-dlp not found (pip install yt-dlp in the venv).")
    temp_file = f"temp_full_video_{abs(hash(url)) % 10_000_000}.mp4"
    dl_cmd = [
        ytdlp,
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


def _ytdlp():
    from src.sources import ytdlp_bin
    b = ytdlp_bin()
    if b is None:
        raise RuntimeError("yt-dlp not found (pip install yt-dlp in the venv).")
    return b


def _download_section(url: str, start, end, browser_for_cookies: str | None) -> str:
    """Download ONLY the [start, end] section (fast, low bandwidth)."""
    ytdlp = _ytdlp()
    temp_file = f"temp_section_{abs(hash((url, start, end))) % 10_000_000}.mp4"
    cmd = [
        ytdlp, "-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4",
        "--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts",
        "-o", temp_file, url,
    ]
    if "kick.com" in url.lower():
        cmd += ["--impersonate", "chrome"]
        if browser_for_cookies:
            cmd += ["--cookies-from-browser", browser_for_cookies]
    log.info("Downloading section %s-%s of %s ...", start, end, url)
    subprocess.run(cmd, check=True)
    return temp_file


def _download_audio(url: str, browser_for_cookies: str | None) -> str:
    """Download audio only (small) — used to scan for the loudest window."""
    import glob
    ytdlp = _ytdlp()
    stem = f"temp_audio_{abs(hash(url)) % 10_000_000}"
    cmd = [ytdlp, "-f", "bestaudio/best", "-o", f"{stem}.%(ext)s", url]
    if "kick.com" in url.lower():
        cmd += ["--impersonate", "chrome"]
        if browser_for_cookies:
            cmd += ["--cookies-from-browser", browser_for_cookies]
    log.info("Downloading audio of %s for highlight scan ...", url)
    subprocess.run(cmd, check=True)
    hits = glob.glob(f"{stem}.*")
    if not hits:
        raise RuntimeError("audio download produced no file")
    return hits[0]


def _scale(src: str, output_path: str) -> str:
    """Scale/pad an already-trimmed file to vertical 1080x1920."""
    _require("ffmpeg")
    output_path = str(Path(output_path).with_suffix(".mp4"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", src, "-c:v", "libx264", "-c:a", "aac",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        output_path,
    ], check=True)
    log.info("Clip saved: %s", output_path)
    return output_path


def create_clip_from_url(
    url: str, start_time: str, end_time: str, output_path: str,
    *, browser_for_cookies: str | None = None, keep_temp: bool = False,
) -> str:
    """Fixed [start,end] window — downloads only that section, then scales 9:16.
    Falls back to full download + trim if section download fails."""
    try:
        sec = _download_section(url, start_time, end_time, browser_for_cookies)
        try:
            return _scale(sec, output_path)
        finally:
            if not keep_temp and os.path.exists(sec):
                os.remove(sec)
    except subprocess.CalledProcessError:
        log.warning("section download failed; falling back to full download")
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
    """Scan a small audio-only download for the loudest window, then download
    just that section as video. Falls back to a full download if needed."""
    target_len = float(target_len)
    try:
        audio = _download_audio(url, browser_for_cookies)
        try:
            start, length = pick_loud_window(audio, target_len)
        finally:
            if not keep_temp and os.path.exists(audio):
                os.remove(audio)
        return create_clip_from_url(
            url, str(round(start, 2)), str(round(start + length, 2)),
            output_path, browser_for_cookies=browser_for_cookies, keep_temp=keep_temp)
    except subprocess.CalledProcessError:
        log.warning("audio/section path failed; falling back to full download")
        temp_file = _download(url, browser_for_cookies)
        try:
            try:
                start, length = pick_loud_window(temp_file, target_len)
            except Exception:
                start, length = 0.0, target_len
            return _trim(temp_file, str(start), str(start + length), output_path)
        finally:
            if not keep_temp and os.path.exists(temp_file):
                os.remove(temp_file)
