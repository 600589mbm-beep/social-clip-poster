"""Post a clip to TikTok via the `tiktok-uploader` package (cookie-based, Selenium)."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def post_to_tiktok(video_path: str, description: str, cookies_file: str = "tiktok_cookies.txt"):
    """Upload a video to TikTok using exported cookies.

    Export cookies with a "Get cookies.txt LOCALLY" browser extension while
    logged into TikTok, and point `cookies_file` at the saved file.

    The `tiktok-uploader` package exposes `upload_video(filename, description,
    cookies, ...)`. (Older/forked variants expose a `TikTokUploader` class — if
    your installed version differs, adjust this call to match its README.)
    """
    from tiktok_uploader.upload import upload_video  # lazy import

    failed = upload_video(video_path, description=description, cookies=cookies_file)
    if failed:
        log.error("TikTok upload reported failures: %s", failed)
    else:
        log.info("Posted to TikTok: %s", video_path)
    return failed
