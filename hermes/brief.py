"""Turn the analysis into a markdown brief — with an optional LLM narrative.

If OPENROUTER_API_KEY is set, Hermes asks a model to write a short growth-coach
narrative + next actions (your existing Hermes pattern). Otherwise it emits a
clean deterministic template. Briefs are saved to the `briefs` table.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.db import get_conn  # noqa: E402
from hermes.analyze import analyze  # noqa: E402

log = logging.getLogger(__name__)


def _template(a: dict) -> str:
    lines = ["# Hermes growth brief", "", f"_Based on {a['n_posts']} clips with collected metrics._", ""]
    lines.append("## Recommendations")
    for r in a["recommendations"]:
        lines.append(f"- {r}")
    lines.append("")

    def table(title, rows, unit="avg views"):
        lines.append(f"## {title}")
        if not rows:
            lines.append("_no data yet_\n"); return
        lines.append(f"| item | {unit} | n |\n|---|--:|--:|")
        for name, avg, n in rows[:8]:
            lines.append(f"| {name} | {avg:,.0f} | {n} |")
        lines.append("")

    table("Clip mode", a["by_mode"])
    table("Source channel", a["by_channel"])
    table("Posting hour", a["by_hour"])
    table("Platform", a["by_platform"])

    lines.append("## Follower growth")
    if a["growth"]:
        lines.append("| account | platform | Δ followers | now |\n|---|---|--:|--:|")
        for g in a["growth"][:12]:
            lines.append(f"| {g['label']} | {g['platform']} | {g['delta']:+,} | {g['followers']:,} |")
    else:
        lines.append("_no follower snapshots yet_")
    lines.append("")
    return "\n".join(lines)


def _llm_narrative(a: dict, base_brief: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        import requests
        model = os.environ.get("HERMES_MODEL", "google/gemini-flash-1.5")
        prompt = (
            "You are Hermes, a short-form social growth coach. Given this data brief, "
            "write 4-6 sentences of plain-English analysis of what is and isn't working, "
            "then 3 specific next actions to grow views/followers. Be concrete, no fluff.\n\n"
            + base_brief
        )
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        log.exception("LLM narrative failed; using template only")
        return None


def build_brief() -> str:
    a = analyze()
    md = _template(a)
    narrative = _llm_narrative(a, md)
    if narrative:
        md = f"# Hermes growth brief\n\n## Coach's read\n{narrative}\n\n---\n\n" + md.split("\n", 1)[1]
    with get_conn() as conn:
        conn.execute("INSERT INTO briefs(markdown) VALUES (?)", (md,))
    return md


if __name__ == "__main__":
    print(build_brief())
