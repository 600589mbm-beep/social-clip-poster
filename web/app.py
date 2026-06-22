"""Flask dashboard: manage source channels, destination accounts, and links."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.db import get_conn, init_db  # noqa: E402
from src.sources import detect_platform  # noqa: E402

app = Flask(__name__)
init_db()


@app.route("/hermes")
def hermes():
    from hermes.analyze import analyze
    from hermes.recommend import describe
    a = analyze()
    hermes_pick = describe(a)
    with get_conn() as c:
        row = c.execute("SELECT * FROM briefs ORDER BY created_at DESC LIMIT 1").fetchone()
    brief_md = row["markdown"] if row else None
    brief_at = row["created_at"] if row else None
    return render_template("hermes.html", a=a, hermes_pick=hermes_pick,
                           brief_md=brief_md, brief_at=brief_at)


@app.route("/")
def index():
    with get_conn() as c:
        channels = c.execute("SELECT * FROM channels ORDER BY created_at DESC").fetchall()
        accounts = c.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
        posts = c.execute(
            "SELECT p.*, ch.url AS channel_url, a.label AS account_label "
            "FROM posts p LEFT JOIN channels ch ON ch.id=p.channel_id "
            "LEFT JOIN accounts a ON a.id=p.account_id "
            "ORDER BY p.posted_at DESC LIMIT 50").fetchall()
        links = c.execute("SELECT channel_id, account_id FROM links").fetchall()
    linkset = {(l["channel_id"], l["account_id"]) for l in links}
    return render_template("index.html", channels=channels, accounts=accounts,
                           posts=posts, linkset=linkset)


@app.post("/channels/add")
def add_channel():
    url = request.form["url"].strip()
    platform = detect_platform(url)
    clip_seconds = int(request.form.get("clip_seconds") or 60)
    with get_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO channels(url, platform, clip_seconds) VALUES (?,?,?)",
            (url, platform, clip_seconds))
    return redirect(url_for("index"))


@app.post("/channels/<int:cid>/delete")
def delete_channel(cid: int):
    with get_conn() as c:
        c.execute("DELETE FROM channels WHERE id=?", (cid,))
    return redirect(url_for("index"))


COOKIES_DIR = Path(__file__).resolve().parent.parent / "cookies"


def _save_cookies_upload(file_storage) -> str | None:
    """Persist an uploaded TikTok cookies.txt to cookies/ and return its path."""
    if not file_storage or not file_storage.filename:
        return None
    COOKIES_DIR.mkdir(exist_ok=True)
    safe = "".join(ch for ch in file_storage.filename if ch.isalnum() or ch in "._-") or "cookies.txt"
    dest = COOKIES_DIR / f"{int(__import__('time').time())}_{safe}"
    file_storage.save(dest)
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    return str(dest)


def _resolve_facebook_page(token: str):
    """A Page access token's /me IS the Page — use it to auto-fill the real
    page_id (and name), so a mistyped Page ID can't break posting."""
    try:
        import requests
        r = requests.get("https://graph.facebook.com/v20.0/me",
                         params={"fields": "id,name", "access_token": token}, timeout=20)
        if r.status_code == 200:
            j = r.json()
            return j.get("id"), j.get("name")
    except Exception:
        pass
    return None, None


@app.post("/accounts/add")
def add_account():
    platform = request.form["platform"]
    extra = {}

    # Sign in the easy way: type the secret straight in (stored server-side), or
    # upload a TikTok cookies file. Falls back to an env-var name if provided.
    secret = (request.form.get("secret") or "").strip() or None
    label = request.form["label"].strip()

    if platform == "facebook":
        # auto-derive the real Page ID from the token (overrides any typo)
        page_id, page_name = (_resolve_facebook_page(secret) if secret else (None, None))
        if not page_id and request.form.get("page_id"):
            page_id = request.form["page_id"].strip()
        if page_id:
            extra["page_id"] = page_id
        if page_name and not label:
            label = page_name
    cookies_path = _save_cookies_upload(request.files.get("cookies_file"))
    if not cookies_path:
        cookies_path = (request.form.get("cookies_path") or "").strip() or None

    with get_conn() as c:
        c.execute(
            "INSERT INTO accounts(platform,label,username,secret,secret_env,cookies_path,extra) "
            "VALUES (?,?,?,?,?,?,?)",
            (platform,
             label,
             (request.form.get("username") or "").strip() or None,
             secret,
             (request.form.get("secret_env") or "").strip() or None,
             cookies_path,
             json.dumps(extra) if extra else None))
    return redirect(url_for("index"))


@app.post("/accounts/<int:aid>/delete")
def delete_account(aid: int):
    with get_conn() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (aid,))
    return redirect(url_for("index"))


@app.post("/link")
def toggle_link():
    cid = int(request.form["channel_id"])
    aid = int(request.form["account_id"])
    with get_conn() as c:
        existing = c.execute(
            "SELECT 1 FROM links WHERE channel_id=? AND account_id=?", (cid, aid)).fetchone()
        if existing:
            c.execute("DELETE FROM links WHERE channel_id=? AND account_id=?", (cid, aid))
        else:
            c.execute("INSERT INTO links(channel_id,account_id) VALUES (?,?)", (cid, aid))
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=True)
