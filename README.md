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

## Notes & alternatives

- The `tiktok-uploader` package exposes `upload_video(filename, description, cookies, ...)`.
  Some forks expose a `TikTokUploader` class instead — adjust `src/platforms/tiktok.py`
  to match your installed version's README if the call signature differs.
- For AI highlight detection, auto-captions, and face-tracked cropping, consider mature
  projects like `jipraks/yt-short-clipper`, `mutonby/openshorts`, or
  `lukesorvik/brainrotinator` and extend them with yt-dlp for Kick.

## License

MIT — see `LICENSE`.
