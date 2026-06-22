"""Download a video (YouTube / Kick) and trim it to a vertical 9:16 clip."""
from __future__ import annotations

import logging
import os
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


def create_clip_from_url(
    url: str,
    start_time: str,
    end_time: str,
    output_path: str,
    *,
    browser_for_cookies: str | None = None,
    keep_temp: bool = False,
) -> str:
    """Download from a Kick or YouTube URL and trim to a clip.

    start_time / end_time accept HH:MM:SS or seconds.
    Returns the path to the rendered 9:16 mp4.
    """
    _require("yt-dlp")
    _require("ffmpeg")

    output_path = str(Path(output_path).with_suffix(".mp4"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name so concurrent/successive runs don't clobber each other.
    temp_file = f"temp_full_video_{abs(hash(url)) % 10_000_000}.mp4"

    dl_cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", temp_file,
        url,
    ]
    # Kick is more reliable with browser impersonation + cookies.
    if "kick.com" in url.lower():
        dl_cmd += ["--impersonate", "chrome"]
        if browser_for_cookies:
            dl_cmd += ["--cookies-from-browser", browser_for_cookies]

    log.info("Downloading from %s ...", url)
    subprocess.run(dl_cmd, check=True)

    try:
        # Re-encode for frame-accurate cuts and pad/scale to vertical 1080x1920.
        clip_cmd = [
            "ffmpeg", "-y",
            "-ss", start_time,
            "-to", end_time,
            "-i", temp_file,
            "-c:v", "libx264", "-c:a", "aac",
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            output_path,
        ]
        log.info("Creating clip %s -> %s ...", start_time, end_time)
        subprocess.run(clip_cmd, check=True)
    finally:
        if not keep_temp and os.path.exists(temp_file):
            os.remove(temp_file)

    log.info("Clip saved: %s", output_path)
    return output_path
