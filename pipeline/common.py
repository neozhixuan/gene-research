"""Shared paths and helpers. Every stage reads and writes plain files under data/."""

import json
import re
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SGT = timezone(timedelta(hours=8))
MACRO_NAMES = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq", "SMH": "Semis ETF", "^VIX": "VIX", "^TNX": "US 10y yield",
               "DX-Y.NYB": "Dollar index", "CL=F": "Crude oil", "BTC-USD": "Bitcoin"}


def today() -> str:
    """Run date in Singapore time, overridable with RUN_DATE=YYYY-MM-DD."""
    return os.environ.get("RUN_DATE") or datetime.now(SGT).strftime("%Y-%m-%d")


def day_dir(date: str | None = None) -> Path:
    d = DATA / (date or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


def universe() -> dict:
    return json.loads((ROOT / "universe.json").read_text())


def segment_of() -> dict[str, str]:
    return {t: seg for seg, ts in universe()["segments"].items() for t in ts}


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# What each final rating means for you, depending on whether you already own the stock.
ACTIONS = {
    "Buy": ("Buy a full position (your normal size)", "Add to it"),
    "Overweight": ("Start a small position; add if the thesis holds", "Add a little"),
    "Hold": ("Don't buy yet; keep watching", "Keep it; no change"),
    "Underweight": ("Don't buy", "Trim: sell part of it"),
    "Sell": ("Don't buy", "Sell it all"),
}

_HEADING = re.compile(r"(?<=[.!?)])\s+((?:\d+\.\s+)?[A-Z][\w&/\-’' ]{2,40}?):\s")


def clean_report(text: str | None) -> str:
    """Repair agent output for display.

    Gemini sometimes leaks a fragment of its hidden reasoning as the first line
    (e.g. "শিল্পীthought"), and when TradingAgents falls back to free text the
    model can squash headings and a whole table onto one line. Both are fixed
    here; the stored output stays untouched.
    """
    text = re.sub(r"\A\s*\S*thought\s*\n", "", text or "")
    lines = []
    for line in text.split("\n"):
        if len(line) > 500:
            line = _HEADING.sub(r"\n\n**\1:** ", line)
        if line.count("|") > 8 and re.search(r"\|\s*-{3,}\s*\|", line):
            head, _, table = line.partition("|")
            line = f"{head.rstrip()}\n\n|{re.sub(r'\|\s+\|', '|\n|', table)}"
        lines.append(line)
    return "\n".join(lines)


def previous_worldview(before: str) -> tuple[str | None, dict | None]:
    """Latest worldview strictly before the given date."""
    files = sorted(p for p in (DATA / "worldview").glob("*.json") if p.stem < before)
    if not files:
        return None, None
    return files[-1].stem, read_json(files[-1])
