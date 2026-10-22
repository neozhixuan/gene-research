"""The watchlist: every picked stock stays under watch and gets re-checked until it earns its way off.

data/watchlist.json holds one entry per ticker with its rating history. Each day
one active name that is due gets a fresh TradingAgents run alongside the new
pick, confident names first, so a Buy that turns Underweight is caught.

A name is dropped when the agents lose conviction:
  - two negative ratings (Underweight / Sell) in a row, or
  - three Holds in a row, or
  - the list is over MAX_ACTIVE, in which case the stalest Hold goes first.
Dropped names stay out of the screen for COOLDOWN_DAYS.
"""

from datetime import date, timedelta

from utils.common import DATA, read_json, write_json

PATH = DATA / "watchlist.json"
RECHECK_AFTER_DAYS = 3
MAX_ACTIVE = 8
COOLDOWN_DAYS = 14
POSITIVE = {"Buy", "Overweight"}
NEGATIVE = {"Underweight", "Sell"}


def load() -> dict:
    return read_json(PATH, {})


def save(watch: dict) -> None:
    write_json(PATH, dict(sorted(watch.items())))


def active(watch: dict) -> dict:
    return {t: w for t, w in watch.items() if w["status"] == "active"}


def last_rating(w: dict) -> str | None:
    rated = [c["rating"] for c in w["checks"] if c.get("rating")]
    return rated[-1] if rated else None


def due_recheck(watch: dict, today: str) -> str | None:
    """The one active name to re-check today: confident names first, then the longest unchecked."""
    cutoff = (date.fromisoformat(today) - timedelta(days=RECHECK_AFTER_DAYS)).isoformat()
    due = [(t, w) for t, w in active(watch).items() if w["checks"] and w["checks"][-1]["date"] <= cutoff]
    if not due:
        return None
    due.sort(key=lambda tw: (last_rating(tw[1]) not in POSITIVE, tw[1]["checks"][-1]["date"]))
    return due[0][0]


def excluded(watch: dict, today: str) -> set[str]:
    """Tickers the screen should skip: everything active, plus names dropped in the last COOLDOWN_DAYS."""
    cutoff = (date.fromisoformat(today) - timedelta(days=COOLDOWN_DAYS)).isoformat()
    return {t for t, w in watch.items() if w["status"] == "active" or (w.get("dropped") or "") >= cutoff}


def record(watch: dict, ticker: str, segment: str, today: str, rating: str | None, kind: str) -> None:
    w = watch.get(ticker)
    if w is None or (w["status"] == "dropped" and kind == "new"):
        w = watch[ticker] = {"segment": segment, "added": today, "status": "active", "checks": []}
    w["checks"] = [c for c in w["checks"] if c["date"] != today] + [{"date": today, "rating": rating, "kind": kind}]
    rated = [c["rating"] for c in w["checks"] if c.get("rating")]
    reason = None
    if len(rated) >= 2 and set(rated[-2:]) <= NEGATIVE:
        reason = "rated negative twice in a row"
    elif len(rated) >= 3 and set(rated[-3:]) == {"Hold"}:
        reason = "three Holds in a row: no conviction either way"
    if reason:
        w.update(status="dropped", dropped=today, dropped_reason=reason)


def trim(watch: dict, today: str) -> None:
    """Keep at most MAX_ACTIVE names, dropping the stalest Holds first."""
    act = active(watch)
    if len(act) <= MAX_ACTIVE:
        return
    holds = sorted((t for t, w in act.items() if last_rating(w) not in POSITIVE), key=lambda t: act[t]["checks"][-1]["date"])
    for t in holds[: len(act) - MAX_ACTIVE]:
        watch[t].update(status="dropped", dropped=today, dropped_reason=f"watchlist over {MAX_ACTIVE}; stalest non-positive name")
