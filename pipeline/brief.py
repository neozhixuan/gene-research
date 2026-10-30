"""Tonight's brief: do the site's buy-side ratings still hold at the next US open?

The daily run finishes about 1.5 hours before the US open, but the ratings it
shows can be days old. Code gathers the facts; Claude adds a short read of what
changed since (see .claude/skills/tonight-brief/SKILL.md).

  python pipeline/brief.py prep    write data/<date>/brief_inputs.md for Claude to read
  python pipeline/brief.py check   validate data/<date>/brief.json and stamp when it was done

prep and check also stamp data/<date>/brief_meta.json with start and finish
times, so usage.py can report what the brief cost in tokens.
"""

import sys
from datetime import date as Date, datetime, time, timedelta, timezone

import watchlist
from constants.market import ACTIONS, MACRO_NAMES
from utils.common import DATA, SGT, day_dir, read_json, today, write_json

BUY_SIDE = {"Buy", "Overweight"}
LEANS = {"wait": "Wait a session", "small": "Small positions only", "stands": "Ratings still stand"}
NAME_KEYS = ("ticker", "rating", "rated_on", "rated_price", "last_price", "since_rated", "catalyst", "take")


# ---------- time ----------

def _us_eastern_offset(d: Date) -> int:
    """UTC offset in hours for US Eastern on a date (DST: 2nd Sunday of March to 1st Sunday of November)."""
    def nth_sunday(month, n):
        first = Date(d.year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))
    return -4 if nth_sunday(3, 2) <= d < nth_sunday(11, 1) else -5


def next_us_open(now: datetime) -> datetime:
    """The next 09:30 New York weekday open after `now`. Ignores US market holidays."""
    d = now.astimezone(timezone(timedelta(hours=_us_eastern_offset(now.date())))).date()
    for _ in range(8):
        if d.weekday() < 5:
            opens = datetime.combine(d, time(9, 30), timezone(timedelta(hours=_us_eastern_offset(d))))
            if opens > now:
                return opens
        d += timedelta(days=1)
    raise RuntimeError("no open found")


def session_label(now: datetime) -> str:
    o = next_us_open(now).astimezone(SGT)
    return f"US open {o.strftime('%a %-d %b')}, {o.strftime('%H:%M')} SGT"


# ---------- facts ----------

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def candidates(watch: dict, track: dict) -> list[dict]:
    """Active watchlist names whose latest rating is Buy or Overweight, with the price the agents saw."""
    rows = (track or {}).get("picks", [])
    out = []
    for t, w in sorted(watch.items()):
        if w.get("status") != "active":
            continue
        rated = [c for c in w["checks"] if c.get("rating")]
        if not rated or rated[-1]["rating"] not in BUY_SIDE:
            continue
        last = rated[-1]
        row = next((r for r in rows if r["ticker"] == t and r["date"] == last["date"]), {})
        out.append({"ticker": t, "segment": w["segment"], "rating": last["rating"], "rated_on": last["date"],
                    "history": [c.get("rating") or "not run" for c in w["checks"]],
                    "rated_price": num(row.get("price")), "last_price": num(row.get("now")),
                    "since_rated": row.get("return"), "vs_qqq": row.get("vs_qqq")})
    return out


def earnings_dates(tickers: list[str]) -> dict[str, str]:
    """Next earnings date per ticker from Yahoo, best effort (empty when Yahoo can't be reached)."""
    out = {}
    try:
        import yfinance as yf
    except ImportError:
        return out
    for t in tickers:
        try:
            cal = yf.Ticker(t).calendar or {}
            dates = cal.get("Earnings Date") or []
            upcoming = sorted(str(x) for x in dates if str(x) >= today())
            if upcoming:
                out[t] = upcoming[0]
        except Exception:  # network, parsing, rate limits: the brief just says "unknown"
            continue
    return out


def pctf(x):
    if x is None:
        return "–"
    return "0.0%" if round(x * 1000) == 0 else f"{x * 100:+.1f}%"


def inputs_md(d: str, now: datetime) -> str:
    watch = watchlist.load()
    track = read_json(DATA / "tracking.json", {})
    w = read_json(DATA / "worldview" / f"{d}.json", {})
    market = read_json(DATA / d / "market.json", {})
    names = candidates(watch, track)
    earn = earnings_dates([c["ticker"] for c in names])
    lines = [f"# Brief inputs {d}", "",
             f"Next session: **{session_label(now)}** (holidays not checked). Prepared {now.astimezone(SGT):%Y-%m-%d %H:%M} SGT.",
             "Prices below are the last US close the pipeline saw; anything after that close needs a search.", "",
             "## Buy-side names on the watchlist", ""]
    if names:
        lines += ["| Ticker | Segment (today's stance) | Rating | Rated on | Price then | Last close | Since rated | vs QQQ | Next earnings | Ratings so far |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for c in names:
            stance = (w.get("segments", {}).get(c["segment"]) or {}).get("stance", "?")
            lines.append(f"| {c['ticker']} | {c['segment']} ({stance}) | {c['rating']} | {c['rated_on']} | {c['rated_price'] or '–'} | "
                         f"{c['last_price'] or '–'} | {pctf(c['since_rated'])} | {pctf(c['vs_qqq'])} | {earn.get(c['ticker'], 'unknown')} | "
                         f"{', '.join(c['history'])} |")
        lines += ["", "What each rating means for someone who doesn't own it: " +
                  "; ".join(f"{k}: {ACTIONS[k][0]}" for k in BUY_SIDE & set(ACTIONS)) + "."]
    else:
        lines.append("None: no active watchlist name is rated Buy or Overweight.")
    lines += ["", "## Today's worldview", "", f"Headline: {w.get('headline', '–')}", "",
              "Theses: " + "; ".join(f"{t['title']} ({t['stance']} {t['confidence']}, {t['change']})" for t in w.get("theses", [])
                                     if t.get("change") != "retired"), "",
              "Risks it named:", *[f"- {x}" for x in w.get("risks", [])], "",
              "Watching next:", *[f"- {x}" for x in w.get("watch", [])], "",
              "## Last close", "",
              "; ".join(f"{name} {pctf(market[k].get('chg_1d'))}" for k, name in MACRO_NAMES.items() if k in market), "",
              "## Track record so far", ""]
    s = track.get("summary") or {}
    graded = sum(v.get("graded", 0) for v in (track.get("scorecard") or {}).values())
    rule = (track.get("rules") or {}).get("grade_after_days", 28)
    lines.append(f"{s.get('picks', 0)} new picks, average {pctf(s.get('avg_vs_qqq'))} vs QQQ; {graded} ratings graded (grading starts after {rule} days).")
    base = ((track.get("baselines") or {}).get("strategies")) or {}
    if base:
        lines.append("Against no-AI alternatives (average vs QQQ): " +
                     "; ".join(f"{v['label']} {pctf(v.get('avg_vs_qqq'))}" for v in base.values() if v.get("avg_vs_qqq") is not None) + ".")
    return "\n".join(lines) + "\n"


# ---------- validation ----------

def check_brief(b, d, errs):
    if not isinstance(b, dict):
        return errs.append("brief: missing or not JSON")
    for k in ("date", "session", "written_at", "lean", "bottom_line", "what_changed", "names", "trust", "if_buying", "sources"):
        if k not in b:
            errs.append(f"brief: missing '{k}'")
    if b.get("date") != d:
        errs.append(f"brief: date is {b.get('date')}, expected {d}")
    if b.get("lean") not in LEANS:
        errs.append(f"brief: lean must be one of {sorted(LEANS)}")
    for k in ("what_changed", "if_buying", "names", "sources"):
        if k in b and not isinstance(b[k], list):
            errs.append(f"brief: '{k}' must be a list")
    if not 1 <= len(b.get("what_changed") or []) <= 6:
        errs.append("brief: what_changed needs 1-6 lines")
    for n, x in enumerate(b.get("names") or []):
        if not isinstance(x, dict):
            errs.append(f"brief.names[{n}]: must be an object")
            continue
        for k in NAME_KEYS:
            if k not in x:
                errs.append(f"brief.names[{n}] ({x.get('ticker', '?')}): missing '{k}'")
        for k in ("rated_price", "last_price", "since_rated"):
            if x.get(k) is not None and not isinstance(x.get(k), (int, float)):
                errs.append(f"brief.names[{n}]: '{k}' must be a number or null")
    for n, s in enumerate(b.get("sources") or []):
        if not (isinstance(s, dict) and s.get("title") and str(s.get("url", "")).startswith("http")):
            errs.append(f"brief.sources[{n}]: needs a title and an http(s) url")
    return errs


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    d = today()
    folder = day_dir(d)
    meta_path = folder / "brief_meta.json"
    now = datetime.now(timezone.utc)
    if which == "prep":
        (folder / "brief_inputs.md").write_text(inputs_md(d, now))
        write_json(meta_path, {"started_at": now.isoformat(), "source": "daily run"})
        print(f"Read: data/{d}/brief_inputs.md\nWrite: data/{d}/brief.json, then run: python pipeline/brief.py check")
    elif which == "check":
        errs = check_brief(read_json(folder / "brief.json"), d, [])
        if errs:
            print("\n".join(errs))
            raise SystemExit(1)
        meta = read_json(meta_path, {})
        meta["finished_at"] = now.isoformat()
        write_json(meta_path, meta)
        print("brief ok")
    else:
        raise SystemExit("usage: brief.py prep|check")


if __name__ == "__main__":
    main()
