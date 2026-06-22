"""Fetch performance numbers back from each platform.

Honest status:
- Facebook: official Graph API insights — works with a Page token.
- Instagram: instagrapi media_info / user_info — works (unofficial, may rate-limit).
- TikTok: NO reliable read without the official Content/Display API. Left as a
  stub returning None; wire it to the TikTok API (or manual entry) when you have
  developer access.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)


def _secret(account: dict) -> str | None:
    if account.get("secret"):
        return account["secret"]
    name = account.get("secret_env")
    return os.environ.get(name) if name else None


# ---------------- Instagram ----------------
def instagram_media_stats(account: dict, media_pk: str) -> dict | None:
    try:
        from instagrapi import Client
        cl = Client()
        sess = f"{account['username']}_session.json"
        if os.path.exists(sess):
            cl.load_settings(sess)
        cl.login(account["username"], _secret(account))
        info = cl.media_info(media_pk)
        return {
            "views": int(getattr(info, "play_count", 0) or getattr(info, "view_count", 0) or 0),
            "likes": int(getattr(info, "like_count", 0) or 0),
            "comments": int(getattr(info, "comment_count", 0) or 0),
            "shares": 0,
        }
    except Exception:
        log.exception("instagram_media_stats failed for %s", media_pk)
        return None


def instagram_followers(account: dict) -> int | None:
    try:
        from instagrapi import Client
        cl = Client()
        sess = f"{account['username']}_session.json"
        if os.path.exists(sess):
            cl.load_settings(sess)
        cl.login(account["username"], _secret(account))
        return int(cl.user_info_by_username(account["username"]).follower_count)
    except Exception:
        log.exception("instagram_followers failed for %s", account.get("label"))
        return None


# ---------------- Facebook (Graph API) ----------------
def facebook_video_stats(account: dict, video_id: str) -> dict | None:
    try:
        import requests
        token = _secret(account)
        r = requests.get(
            f"https://graph.facebook.com/v20.0/{video_id}/video_insights",
            params={"metric": "total_video_views,total_video_reactions_by_type_total",
                    "access_token": token},
            timeout=60,
        )
        r.raise_for_status()
        data = {d["name"]: d for d in r.json().get("data", [])}
        views = data.get("total_video_views", {}).get("values", [{}])[0].get("value", 0)
        return {"views": int(views or 0), "likes": 0, "comments": 0, "shares": 0}
    except Exception:
        log.exception("facebook_video_stats failed for %s", video_id)
        return None


def facebook_followers(account: dict) -> int | None:
    try:
        import requests
        extra = json.loads(account.get("extra") or "{}")
        r = requests.get(
            f"https://graph.facebook.com/v20.0/{extra.get('page_id')}",
            params={"fields": "followers_count,fan_count", "access_token": _secret(account)},
            timeout=60,
        )
        r.raise_for_status()
        j = r.json()
        return int(j.get("followers_count") or j.get("fan_count") or 0)
    except Exception:
        log.exception("facebook_followers failed for %s", account.get("label"))
        return None


# ---------------- TikTok (stub) ----------------
def tiktok_media_stats(account: dict, external_id: str) -> dict | None:
    # Requires the official TikTok API (Display/Content) — no reliable scrape.
    log.info("tiktok stats not implemented (needs official API); skipping %s", external_id)
    return None


def collect_media(account: dict, platform: str, external_id: str) -> dict | None:
    if platform == "instagram":
        return instagram_media_stats(account, external_id)
    if platform == "facebook":
        return facebook_video_stats(account, external_id)
    if platform == "tiktok":
        return tiktok_media_stats(account, external_id)
    return None


def collect_followers(account: dict, platform: str) -> int | None:
    if platform == "instagram":
        return instagram_followers(account)
    if platform == "facebook":
        return facebook_followers(account)
    return None  # tiktok stub
