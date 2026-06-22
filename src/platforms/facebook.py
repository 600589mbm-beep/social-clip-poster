"""Post a video to a Facebook Page via the official Graph API.

Facebook does NOT allow reliable username/password automation — you need a Page
access token. Create a Meta app, get a Page access token with `pages_manage_posts`
(and Reels permissions for Reels), then store the Page ID + token.

This is the production-correct path; it requires Meta app review for live use.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

GRAPH = "https://graph-video.facebook.com/v20.0"


def post_to_facebook(video_path: str, description: str, page_id: str, access_token: str):
    """Upload a video to a Facebook Page feed via Graph API."""
    import requests  # lazy import

    url = f"{GRAPH}/{page_id}/videos"
    with open(video_path, "rb") as f:
        resp = requests.post(
            url,
            data={"description": description, "access_token": access_token},
            files={"source": f},
            timeout=600,
        )
    resp.raise_for_status()
    out = resp.json()
    log.info("Posted to Facebook page %s: %s", page_id, out.get("id"))
    return out
