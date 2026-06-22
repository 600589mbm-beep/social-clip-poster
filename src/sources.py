"""List recent videos for a YouTube or Kick channel via yt-dlp (flat playlist)."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def ytdlp_bin() -> str | None:
    """Resolve the yt-dlp executable: PATH first, else next to the running python
    (so it works under a venv/systemd without venv/bin on PATH)."""
    cand = shutil.which("yt-dlp")
    if cand:
        return cand
    local = Path(sys.executable).parent / "yt-dlp"
    return str(local) if local.exists() else None


def detect_platform(url: str) -> str:
    u = url.lower()
    if "kick.com" in u:
        return "kick"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "unknown"


def _youtube_channel_id(url: str) -> str | None:
    """Resolve a YouTube channel's UC… id from any channel URL (handle, /channel/, etc.)."""
    import re
    m = re.search(r"/channel/(UC[\w-]{20,})", url)
    if m:
        return m.group(1)
    try:
        import requests
        # SOCS cookie bypasses YouTube's consent gate so the full page loads
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
                         cookies={"SOCS": "CAI"}, timeout=20)
        m = re.search(r'"channelId":"(UC[\w-]{22})"', r.text) \
            or re.search(r'"externalId":"(UC[\w-]{22})"', r.text) \
            or re.search(r"/channel/(UC[\w-]{22})", r.text)
        return m.group(1) if m else None
    except Exception:
        log.exception("could not resolve channel id for %s", url)
        return None


def _youtube_rss_videos(channel_url: str, limit: int) -> list[dict]:
    """Newest videos via the channel RSS feed — no rate-limit, no JS runtime needed."""
    import re
    import requests
    cid = _youtube_channel_id(channel_url)
    if not cid:
        return []
    feed = requests.get(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
        headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
    vids: list[dict] = []
    for entry in re.findall(r"<entry>(.*?)</entry>", feed, re.S)[:limit]:
        vm = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", entry)
        tm = re.search(r"<title>([^<]+)</title>", entry)
        if vm:
            vid = vm.group(1)
            vids.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                         "title": tm.group(1) if tm else ""})
    log.info("RSS found %d videos for channel %s", len(vids), cid)
    return vids


def list_recent_videos(channel_url: str, limit: int = 5) -> list[dict]:
    """Return [{id, url, title}] for the newest `limit` videos on a channel.

    YouTube uses the RSS feed (reliable, no rate-limit). Kick/others fall back to
    `yt-dlp --flat-playlist`. Never downloads media — just lists.
    """
    if detect_platform(channel_url) == "youtube":
        rss = _youtube_rss_videos(channel_url, limit)
        if rss:
            return rss
        log.warning("RSS empty for %s; falling back to yt-dlp", channel_url)

    ytdlp = ytdlp_bin()
    if ytdlp is None:
        raise RuntimeError("yt-dlp not found (pip install yt-dlp in the venv).")

    cmd = [
        ytdlp,
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
