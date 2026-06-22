# social-clip-poster

Download long videos from **YouTube or Kick**, trim them into vertical **9:16 clips**,
and **auto-post to Instagram and TikTok** — driven by a simple `config.json` batch file,
with logging, inter-post delays, a dry-run mode, and optional daily scheduling.

> ⚠️ **Use responsibly.** Only clip/repost content you own or are licensed to use.
> Instagram (`instagrapi`) and TikTok (`tiktok-uploader`) automation uses **unofficial**
> APIs — they can break without notice and may violate each platform's Terms of Service;
> automated accounts risk rate-limits or bans. You are responsible for compliance.

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
# System dependency: ffmpeg (brew install ffmpeg | apt install ffmpeg | choco install ffmpeg)
```

## Configure

```bash
cp .env.example .env                # fill in IG creds / cookie paths (gitignored)
cp config.example.json config.json  # define your clips (gitignored)
```

- **Instagram:** set `IG_USERNAME` / `IG_PASSWORD` in `.env`. A `<user>_session.json`
  is cached after first login (also gitignored).
- **TikTok:** export cookies with a *"Get cookies.txt LOCALLY"* browser extension while
  logged in, save as `tiktok_cookies.txt`, and point `TIKTOK_COOKIES` at it.
- **Kick:** downloads use yt-dlp browser impersonation; set `BROWSER_FOR_COOKIES` so
  yt-dlp can read your logged-in cookies.

Each `config.json` entry:

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "start": "00:05:30",
  "end": "00:06:45",
  "caption_ig": "caption + #hashtags",
  "caption_tt": "caption + #fyp",
  "platforms": ["instagram", "tiktok"]
}
```

`start`/`end` accept `HH:MM:SS` or seconds.

## Run

```bash
python -m src.main --config config.json            # clip + post everything
python -m src.main --config config.json --dry-run  # clip only, no posting (safe test)
python -m src.main --config config.json --schedule 09:00   # run daily at 09:00
```

Clips land in `clips/`; activity is logged to `run.log`. Both are gitignored.

## Layout

```
src/
  clipper.py            # yt-dlp download + ffmpeg trim/scale to 1080x1920
  main.py               # config loop, delays, logging, dry-run, scheduling
  platforms/
    instagram.py        # instagrapi upload (+ session caching)
    tiktok.py           # tiktok-uploader (cookie-based)
config.example.json     # sample batch
.env.example            # sample credentials/cookie paths
```

## Web dashboard + auto-watch (the "add a channel, it posts forever" mode)

Instead of editing `config.json`, run the dashboard and the watcher. You add a
**channel** once and connect **accounts**; the watcher checks each channel and
auto-clips + posts every *new* video going forward.

```bash
python -m web.db          # create the SQLite database (data/app.db)
python -m web.app         # dashboard at http://localhost:8090
python -m src.poller --interval 600   # watch channels every 10 min (separate process)
```

In the dashboard you can:
- **Add source channels** — paste a YouTube or Kick channel URL; set the auto-clip length.
- **Connect accounts** — TikTok / Instagram / Facebook. Add as many as you want (100+ each).
- **Route** — a grid of checkboxes maps which accounts each channel posts to.
- Watch a **recent-activity** log of every post attempt (ok/error).

### What YOU add to make it run
Secrets are **never** stored in the app DB — only the *names/paths* are. You provide:

| Platform  | What to add | Where |
|-----------|-------------|-------|
| Instagram | username + an env var holding the password (e.g. `IG_PW_1`) | account form → `.env` |
| TikTok    | a cookies file per account (e.g. `cookies/acct1.txt`) | account form → server file |
| Facebook  | Page ID + an env var holding a Page access token (e.g. `FB_TOKEN_1`) | account form → `.env` |

Put the real secrets in `.env` (gitignored) / cookie files on the server; reference
them by name in the dashboard.

### First-poll safety
The first time a channel is polled, all its current videos are recorded as "seen"
**without posting**, so you don't blast the entire backlog — only videos uploaded
*after* you add the channel get posted.

### Deploying (VPS)
Run `web.app` behind a reverse proxy (Caddy/Nginx) with auth, and run `src.poller`
as a long-running service (systemd / pm2). It is a backend app (DB + workers +
your account secrets) — it cannot run as a static page.

### Scale & honesty (read this for 100+ accounts)
- `instagrapi` and `tiktok-uploader` are **unofficial** and the biggest ban/breakage
  risk at scale. For real volume, migrate the posters in `src/platforms/` to the
  **official** APIs: Instagram Graph **Content Publishing**, TikTok **Content Posting
  API**, Facebook **Graph API** (the included `facebook.py` already uses Graph). Each
  needs an approved Meta/TikTok developer app.
- Posting hundreds of videos rapidly *will* trip rate limits. Keep delays generous,
  stagger channels, and treat the unofficial posters as best-effort.

## Hermes — performance watcher & growth coach

Hermes learns what actually grows your channels. It collects each posted clip's
stats over time + follower snapshots, then ranks **clip mode (auto vs fixed),
source channel, posting hour, and platform** by views, and writes a brief with
concrete next actions.

```bash
python -m hermes.watch --once            # collect metrics + write a brief now
python -m hermes.watch --interval 21600  # loop every 6h (or: systemctl start clipper-hermes)
```

- Dashboard tab **📈 Hermes** (`/hermes`) shows leaderboards, follower growth, and the latest brief.
- **Optional LLM coach:** set `OPENROUTER_API_KEY` (+ `HERMES_MODEL`) and Hermes adds a
  plain-English "coach's read" + next actions; without it, it emits a clean template.

### What returns real numbers (honest status)
| Platform | Metrics read | Needs |
|----------|--------------|-------|
| Facebook | views via Graph `video_insights`; Page followers | Page access token |
| Instagram | views/likes/comments via instagrapi; follower count | IG login |
| TikTok | **stub** — no reliable read without the official API | TikTok Display/Content API access |

Hermes runs `clipper-hermes.service` (installed, **stopped** until you start it).

## Notes & alternatives

- The `tiktok-uploader` package exposes `upload_video(filename, description, cookies, ...)`.
  Some forks expose a `TikTokUploader` class instead — adjust `src/platforms/tiktok.py`
  to match your installed version's README if the call signature differs.
- For AI highlight detection, auto-captions, and face-tracked cropping, consider mature
  projects like `jipraks/yt-short-clipper`, `mutonby/openshorts`, or
  `lukesorvik/brainrotinator` and extend them with yt-dlp for Kick.

## License

MIT — see `LICENSE`.
