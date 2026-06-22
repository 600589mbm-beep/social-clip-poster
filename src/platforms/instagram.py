"""Post a clip to Instagram via instagrapi (unofficial API)."""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def post_to_instagram(video_path: str, caption: str, username: str, password: str):
    """Upload a video/reel to Instagram. Caches a session file to avoid re-login.

    Note: instagrapi is an unofficial client; Instagram may challenge logins
    (2FA / checkpoints). Handle those interactively the first time.
    """
    from instagrapi import Client  # imported lazily so the module loads without the dep

    cl = Client()
    session_file = f"{username}_session.json"
    if os.path.exists(session_file):
        cl.load_settings(session_file)
        cl.login(username, password)  # refreshes the cached session
    else:
        cl.login(username, password)
        cl.dump_settings(session_file)

    media = cl.video_upload(video_path, caption=caption)
    log.info("Posted to Instagram: pk=%s", media.pk)
    return media
