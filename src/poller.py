"""Channel watcher: poll each active channel, clip & post any NEW videos.

Run continuously:  python -m src.poller --interval 600
Run once:          python -m src.poller --once

Behaviour:
- The FIRST time a channel is polled, all current videos are recorded as "seen"
  WITHOUT posting (so you don't blast the entire backlog). Only videos that
  appear AFTER you add the channel get clipped and posted.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

from dotenv import load_dotenv

from .clipper import create_clip_from_url
from .sources import list_recent_videos
from .platforms.instagram import post_to_instagram
from .platforms.tiktok import post_to_tiktok
from .platforms.facebook import post_to_facebook

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.db import get_conn, init_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("poller.log")],
)
log = logging.getLogger("poller")

POST_DELAY_SECONDS = 30


def _secret(account: dict) -> str | None:
    """Resolve an account's password/token from the env var it references."""
    name = account["secret_env"]
    return os.environ.get(name) if name else None


def _post_one(conn, channel: dict, account: dict, video: dict) -> None:
    plat = account["platform"]
    caption = f"{video['title']}".strip() or ""
    clip_path = None
    try:
        clip_path = create_clip_from_url(
            video["url"], "0", str(channel["clip_seconds"]),
            f"clips/{channel['id']}_{video['id']}.mp4",
            browser_for_cookies=os.environ.get("BROWSER_FOR_COOKIES") or None,
        )

        if plat == "instagram":
            pw = _secret(account)
            if not (account["username"] and pw):
                raise RuntimeError("instagram account missing username/secret_env")
            post_to_instagram(clip_path, caption, account["username"], pw)
        elif plat == "tiktok":
            if not account["cookies_path"] or not os.path.exists(account["cookies_path"]):
                raise RuntimeError("tiktok account missing cookies_path")
            post_to_tiktok(clip_path, caption, account["cookies_path"])
        elif plat == "facebook":
            extra = json.loads(account["extra"] or "{}")
            token = _secret(account)
            if not (extra.get("page_id") and token):
                raise RuntimeError("facebook account missing page_id/secret_env token")
            post_to_facebook(clip_path, caption, extra["page_id"], token)
        else:
            raise RuntimeError(f"unknown platform {plat}")

        conn.execute(
            "INSERT INTO posts(channel_id,account_id,video_id,video_url,status,detail) "
            "VALUES (?,?,?,?, 'ok', ?)",
            (channel["id"], account["id"], video["id"], video["url"], f"posted to {plat}"),
        )
    except Exception as exc:  # one account failing must not stop the others
        log.exception("post failed: channel=%s account=%s video=%s", channel["id"], account["id"], video["id"])
        conn.execute(
            "INSERT INTO posts(channel_id,account_id,video_id,video_url,status,detail) "
            "VALUES (?,?,?,?, 'error', ?)",
            (channel["id"], account["id"], video["id"], video["url"], str(exc)),
        )
    finally:
        conn.commit()
        time.sleep(POST_DELAY_SECONDS)


def poll_channel(conn, channel: dict) -> None:
    try:
        videos = list_recent_videos(channel["url"], limit=5)
    except Exception:
        log.exception("listing failed for channel %s", channel["url"])
        return

    seen = {r["video_id"] for r in conn.execute(
        "SELECT video_id FROM seen_videos WHERE channel_id=?", (channel["id"],))}

    first_poll = len(seen) == 0
    accounts = conn.execute(
        "SELECT a.* FROM accounts a JOIN links l ON l.account_id=a.id "
        "WHERE l.channel_id=? AND a.active=1", (channel["id"],)).fetchall()

    # oldest -> newest so chronological posting order
    for video in reversed(videos):
        if video["id"] in seen:
            continue
        conn.execute("INSERT OR IGNORE INTO seen_videos(channel_id,video_id) VALUES (?,?)",
                     (channel["id"], video["id"]))
        conn.commit()
        if first_poll:
            log.info("baseline (no post): channel=%s video=%s", channel["id"], video["id"])
            continue
        log.info("NEW video channel=%s video=%s -> %d account(s)",
                 channel["id"], video["id"], len(accounts))
        for account in accounts:
            _post_one(conn, channel, dict(account), video)


def run_once() -> None:
    load_dotenv()
    init_db()
    with get_conn() as conn:
        channels = conn.execute("SELECT * FROM channels WHERE active=1").fetchall()
        log.info("polling %d active channel(s)", len(channels))
        for ch in channels:
            poll_channel(conn, dict(ch))


def main() -> None:
    ap = argparse.ArgumentParser(description="Poll channels and auto-post new videos.")
    ap.add_argument("--once", action="store_true", help="poll a single time and exit")
    ap.add_argument("--interval", type=int, default=600, help="seconds between polls (loop mode)")
    args = ap.parse_args()

    if args.once:
        run_once()
        return
    log.info("poller loop started; interval=%ss", args.interval)
    while True:
        run_once()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
