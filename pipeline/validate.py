"""Check the two files Claude writes each day before anything downstream reads them.

  data/worldview/<date>.json   the updated worldview
  data/<date>/picks.json       1-2 tickers chosen from the shortlist

Prints every problem and exits 1 if there are any, so the daily session can fix
and rerun instead of publishing a malformed page.
"""

import sys

from utils.common import DATA, day_dir, today, universe, read_json

STANCES = {"bullish", "bearish", "neutral"}
SEG_STANCES = {"overweight", "neutral", "underweight"}
CHANGES = {"new", "stronger", "weaker", "unchanged", "retired"}


def check_worldview(w, errs):
    if not isinstance(w, dict):
        return errs.append("worldview: missing or not JSON")
    for k in ("date", "headline", "regime", "theses", "segments", "risks", "watch"):
        if k not in w:
            errs.append(f"worldview: missing '{k}'")
    if w.get("date") != today():
        errs.append(f"worldview: date is {w.get('date')}, expected {today()}")
    segs = set(universe()["segments"])
    for n, t in enumerate(w.get("theses", [])):
        where = f"worldview.theses[{n}] ({t.get('id', '?')})"
        for k in ("id", "title", "stance", "confidence", "segments", "evidence", "change", "change_note"):
            if k not in t:
                errs.append(f"{where}: missing '{k}'")
        if t.get("stance") not in STANCES:
            errs.append(f"{where}: stance must be one of {sorted(STANCES)}")
        if t.get("change") not in CHANGES:
            errs.append(f"{where}: change must be one of {sorted(CHANGES)}")
        if not isinstance(t.get("confidence"), int) or not 0 <= t["confidence"] <= 100:
            errs.append(f"{where}: confidence must be an integer 0-100")
        if bad := set(t.get("segments", [])) - segs:
            errs.append(f"{where}: unknown segments {sorted(bad)}")
    if missing := segs - set(w.get("segments", {})):
        errs.append(f"worldview.segments: missing {sorted(missing)}")
    for s, v in w.get("segments", {}).items():
        if (v or {}).get("stance") not in SEG_STANCES:
            errs.append(f"worldview.segments.{s}: stance must be one of {sorted(SEG_STANCES)}")


def check_picks(p, shortlist, errs):
    if not isinstance(p, dict) or not p.get("picks"):
        return errs.append("picks: missing or empty")
    allowed = {r["ticker"] for r in shortlist}
    for n, pick in enumerate(p["picks"]):
        for k in ("ticker", "segment", "why", "risk", "thesis_ids"):
            if k not in pick:
                errs.append(f"picks[{n}]: missing '{k}'")
        if pick.get("ticker") not in allowed:
            errs.append(f"picks[{n}]: {pick.get('ticker')} is not on today's shortlist {sorted(allowed)}")
    if len(p["picks"]) > 2:
        errs.append("picks: at most 2")


def main():
    errs = []
    d = day_dir()
    check_worldview(read_json(DATA / "worldview" / f"{today()}.json"), errs)
    check_picks(read_json(d / "picks.json"), read_json(d / "shortlist.json", {}).get("shortlist", []), errs)
    for e in errs:
        print("ERROR", e)
    if errs:
        sys.exit(1)
    print("worldview and picks OK")


if __name__ == "__main__":
    main()
