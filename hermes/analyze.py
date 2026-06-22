"""Learn what drives views/follows from collected metrics.

Pure-Python stats over the SQLite tables — no external deps. Produces
leaderboards (best clip mode / source channel / post hour / platform) plus
follower growth, and a list of plain-language recommendations.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.db import get_conn  # noqa: E402


def _latest_metric_per_post(conn) -> list[dict]:
    """Most recent metric row for each post (so we count each clip once)."""
    rows = conn.execute(
        """
        SELECT m.*, p.channel_id, p.posted_at, p.account_id AS p_account_id, p.clip_mode,
               c.url AS channel_url, c.clip_seconds,
               a.platform AS acct_platform, a.label AS acct_label
        FROM metrics m
        JOIN (SELECT post_id, MAX(collected_at) AS mx FROM metrics GROUP BY post_id) last
          ON last.post_id = m.post_id AND last.mx = m.collected_at
        JOIN posts p ON p.id = m.post_id
        LEFT JOIN channels c ON c.id = p.channel_id
        LEFT JOIN accounts a ON a.id = m.account_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _avg(d: dict[str, list[int]]) -> list[tuple[str, float, int]]:
    out = [(k, sum(v) / len(v), len(v)) for k, v in d.items() if v]
    return sorted(out, key=lambda x: x[1], reverse=True)


def _clip_mode(clip_seconds) -> str:
    # falls back from channel setting when a post has no recorded mode
    if not clip_seconds or clip_seconds < 0:
        return "auto"
    return f"{clip_seconds}s"


def _effective_mode(row: dict) -> str:
    return row.get("clip_mode") or _clip_mode(row.get("clip_seconds"))


def analyze() -> dict:
    with get_conn() as conn:
        rows = _latest_metric_per_post(conn)
        # follower growth: earliest vs latest snapshot per account
        fol = conn.execute(
            """
            SELECT a.label, a.platform,
                   (SELECT followers FROM account_stats s2 WHERE s2.account_id=a.id
                      ORDER BY collected_at ASC, id ASC LIMIT 1)  AS first_f,
                   (SELECT followers FROM account_stats s3 WHERE s3.account_id=a.id
                      ORDER BY collected_at DESC, id DESC LIMIT 1) AS last_f
            FROM accounts a
            """
        ).fetchall()

    by_mode: dict[str, list[int]] = defaultdict(list)
    by_channel: dict[str, list[int]] = defaultdict(list)
    by_hour: dict[str, list[int]] = defaultdict(list)
    by_platform: dict[str, list[int]] = defaultdict(list)

    for r in rows:
        v = r.get("views") or 0
        by_mode[_effective_mode(r)].append(v)
        if r.get("channel_url"):
            by_channel[r["channel_url"]].append(v)
        if r.get("acct_platform"):
            by_platform[r["acct_platform"]].append(v)
        ts = r.get("posted_at") or ""
        if len(ts) >= 13:  # 'YYYY-MM-DD HH'
            by_hour[ts[11:13] + ":00"].append(v)

    growth = []
    for f in fol:
        first_f, last_f = f["first_f"], f["last_f"]
        if first_f is not None and last_f is not None:
            growth.append({"label": f["label"], "platform": f["platform"],
                           "delta": last_f - first_f, "followers": last_f})
    growth.sort(key=lambda x: x["delta"], reverse=True)

    result = {
        "n_posts": len(rows),
        "by_mode": _avg(by_mode),
        "by_channel": _avg(by_channel),
        "by_hour": _avg(by_hour),
        "by_platform": _avg(by_platform),
        "growth": growth,
        "recommendations": _recommend(_avg(by_mode), _avg(by_channel), _avg(by_hour), _avg(by_platform)),
    }
    return result


def _recommend(mode, channel, hour, platform) -> list[str]:
    recs: list[str] = []
    if mode:
        recs.append(f"Best clip mode: **{mode[0][0]}** (avg {mode[0][1]:,.0f} views over {mode[0][2]} clips).")
    if hour:
        recs.append(f"Best posting hour: **{hour[0][0]}** (avg {hour[0][1]:,.0f} views).")
    if platform:
        recs.append(f"Top platform so far: **{platform[0][0]}** (avg {platform[0][1]:,.0f} views).")
    if channel:
        recs.append(f"Top source channel: **{channel[0][0]}** (avg {channel[0][1]:,.0f} views).")
    if not recs:
        recs.append("Not enough data yet — keep posting; Hermes needs a few clips with collected metrics.")
    return recs


if __name__ == "__main__":
    import json
    print(json.dumps(analyze(), indent=2))
