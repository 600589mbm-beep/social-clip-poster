"""Hermes decides the clip length/window — explore, then exploit.

Channels set to "Hermes" mode (clip_seconds = -1) call recommend_clip(): until
each candidate mode has enough samples, Hermes picks the least-sampled one to
gather data; after that, it picks whichever has the most average views.

Returns seconds where 0 means the loudness "auto" window. Deterministic
(no randomness) so behaviour is reproducible.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hermes.analyze import analyze  # noqa: E402

# 0 = loudness auto-window (60s); the rest are first-N-seconds
CANDIDATES = [0, 30, 60, 90]


def _label(seconds: int) -> str:
    return "auto" if seconds == 0 else f"{seconds}s"


def recommend_clip(min_n: int = 3, a: dict | None = None) -> tuple[int, str]:
    """Return (seconds, reason). reason is 'explore' or 'exploit'."""
    a = a or analyze()
    counts = {m: n for m, _avg, n in a["by_mode"]}
    avgs = {m: avg for m, avg, _n in a["by_mode"]}

    under = [c for c in CANDIDATES if counts.get(_label(c), 0) < min_n]
    if under:
        under.sort(key=lambda c: (counts.get(_label(c), 0), CANDIDATES.index(c)))
        return under[0], "explore"

    best = max(CANDIDATES, key=lambda c: avgs.get(_label(c), -1.0))
    return best, "exploit"


def describe(a: dict | None = None) -> str:
    secs, reason = recommend_clip(a=a)
    mode = "auto (loudness window)" if secs == 0 else f"first {secs}s"
    return f"{mode} — {reason}"


if __name__ == "__main__":
    print(describe())
