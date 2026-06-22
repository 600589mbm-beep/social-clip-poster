"""Batch pipeline: read config.json -> clip each entry -> post to platforms.

Usage:
    python -m src.main --config config.json
    python -m src.main --config config.json --dry-run        # clip only, no posting
    python -m src.main --config config.json --schedule 09:00 # run daily at 09:00
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .clipper import create_clip_from_url
from .platforms.instagram import post_to_instagram
from .platforms.tiktok import post_to_tiktok

POST_DELAY_SECONDS = 30  # be polite between posts to reduce rate-limit/ban risk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("run.log")],
)
log = logging.getLogger("clip-poster")


def process_entry(entry: dict, env: dict, *, dry_run: bool, out_dir: Path) -> None:
    url = entry["url"]
    slug = "".join(c for c in url if c.isalnum())[-12:] or "clip"
    out_path = out_dir / f"{slug}_{entry['start'].replace(':', '')}.mp4"

    clip = create_clip_from_url(
        url, entry["start"], entry["end"], str(out_path),
        browser_for_cookies=env.get("BROWSER_FOR_COOKIES") or None,
    )

    platforms = entry.get("platforms", ["instagram", "tiktok"])

    if dry_run:
        log.info("[dry-run] clip ready (%s); skipping posts to %s", clip, platforms)
        return

    if "instagram" in platforms:
        if env.get("IG_USERNAME") and env.get("IG_PASSWORD"):
            try:
                post_to_instagram(clip, entry.get("caption_ig", ""), env["IG_USERNAME"], env["IG_PASSWORD"])
            except Exception:
                log.exception("Instagram post failed for %s", url)
            time.sleep(POST_DELAY_SECONDS)
        else:
            log.warning("Skipping Instagram: IG_USERNAME/IG_PASSWORD not set in .env")

    if "tiktok" in platforms:
        cookies = env.get("TIKTOK_COOKIES", "tiktok_cookies.txt")
        if os.path.exists(cookies):
            try:
                post_to_tiktok(clip, entry.get("caption_tt", ""), cookies)
            except Exception:
                log.exception("TikTok post failed for %s", url)
            time.sleep(POST_DELAY_SECONDS)
        else:
            log.warning("Skipping TikTok: cookies file %r not found", cookies)


def run_once(config_path: str, *, dry_run: bool) -> None:
    load_dotenv()
    env = dict(os.environ)
    entries = json.loads(Path(config_path).read_text())
    out_dir = Path("clips")
    out_dir.mkdir(exist_ok=True)

    log.info("Loaded %d entries from %s", len(entries), config_path)
    for i, entry in enumerate(entries, 1):
        log.info("[%d/%d] %s", i, len(entries), entry["url"])
        try:
            process_entry(entry, env, dry_run=dry_run, out_dir=out_dir)
        except Exception:
            log.exception("Entry failed: %s", entry.get("url"))
    log.info("Done.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Clip long videos and auto-post to IG/TikTok.")
    ap.add_argument("--config", default="config.json", help="Path to config JSON")
    ap.add_argument("--dry-run", action="store_true", help="Create clips but do not post")
    ap.add_argument("--schedule", metavar="HH:MM", help="Run daily at this time instead of once")
    args = ap.parse_args()

    if args.schedule:
        import schedule  # lazy import

        schedule.every().day.at(args.schedule).do(run_once, args.config, dry_run=args.dry_run)
        log.info("Scheduled daily run at %s. Ctrl-C to stop.", args.schedule)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run_once(args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
