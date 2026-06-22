"""Hermes watcher: collect metrics + follower snapshots, then write a brief.

Run once:        python -m hermes.watch --once
Run on a loop:   python -m hermes.watch --interval 21600   # every 6h
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.db import get_conn, init_db  # noqa: E402
from hermes.metrics import collect_media, collect_followers  # noqa: E402
from hermes.brief import build_brief  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("hermes.log")],
)
log = logging.getLogger("hermes")


def collect_once() -> None:
    load_dotenv()
    init_db()
    with get_conn() as conn:
        # 1) per-post media metrics (only posts that returned an external id)
        posts = conn.execute(
            "SELECT p.*, a.platform, a.username, a.secret, a.secret_env, a.cookies_path, a.extra "
            "FROM posts p JOIN accounts a ON a.id=p.account_id "
            "WHERE p.status='ok' AND p.external_id IS NOT NULL"
        ).fetchall()
        for p in posts:
            acct = dict(p)
            stats = collect_media(acct, p["platform"], p["external_id"])
            if stats:
                conn.execute(
                    "INSERT INTO metrics(post_id,account_id,platform,external_id,views,likes,comments,shares) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (p["id"], p["account_id"], p["platform"], p["external_id"],
                     stats["views"], stats["likes"], stats["comments"], stats["shares"]))
                log.info("metrics post=%s views=%s", p["id"], stats["views"])

        # 2) per-account follower snapshot
        accounts = conn.execute("SELECT * FROM accounts WHERE active=1").fetchall()
        for a in accounts:
            f = collect_followers(dict(a), a["platform"])
            if f is not None:
                conn.execute("INSERT INTO account_stats(account_id,followers) VALUES (?,?)", (a["id"], f))
                log.info("followers %s = %s", a["label"], f)
        conn.commit()

    # 3) write the brief
    build_brief()
    log.info("brief written")


def main() -> None:
    ap = argparse.ArgumentParser(description="Hermes: watch performance and learn what grows the channels.")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=21600, help="seconds between cycles (loop mode)")
    args = ap.parse_args()
    if args.once:
        collect_once(); return
    log.info("hermes loop started; interval=%ss", args.interval)
    while True:
        try:
            collect_once()
        except Exception:
            log.exception("hermes cycle failed")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
