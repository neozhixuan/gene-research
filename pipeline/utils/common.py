"""Shared paths and helpers. Every stage reads and writes plain files under data/."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SGT = timezone(timedelta(hours=8))


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


def previous_worldview(before: str) -> tuple[str | None, dict | None]:
    """Latest worldview strictly before the given date."""
    files = sorted(p for p in (DATA / "worldview").glob("*.json") if p.stem < before)
    if not files:
        return None, None
    return files[-1].stem, read_json(files[-1])
