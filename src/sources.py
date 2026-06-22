"""List recent videos for a YouTube or Kick channel via yt-dlp (flat playlist)."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    u = url.lower()
    if "kick.com" in u:
        return "kick"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "unknown"


def list_recent_videos(channel_url: str, limit: int = 5) -> list[dict]:
    """Return [{id, url, title}] for the newest `limit` videos on a channel.

    Uses `yt-dlp --flat-playlist` so it does not download anything — just lists.
    Works for YouTube channels and (where supported) Kick channel video pages.
    """
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp not found on PATH (pip install yt-dlp).")

    cmd = [
        "yt-dlp",
        "-J",                       # dump single JSON
        "--flat-playlist",
        "--playlist-end", str(limit),
        channel_url,
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    data = json.loads(out)

    entries = data.get("entries") or []
    videos: list[dict] = []
    for e in entries:
        if not e:
            continue
        vid = e.get("id")
        vurl = e.get("url") or e.get("webpage_url")
        # flat-playlist often returns bare ids; rebuild a watchable URL when needed
        if vurl and not vurl.startswith("http"):
            vurl = None
        if not vurl and vid:
            vurl = f"https://www.youtube.com/watch?v={vid}" if "youtube" in channel_url.lower() else None
        if vid and vurl:
            videos.append({"id": str(vid), "url": vurl, "title": e.get("title") or ""})
    log.info("Found %d recent videos for %s", len(videos), channel_url)
    return videos
