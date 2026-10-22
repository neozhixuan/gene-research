"""Stage 6: mark every past pick to market and grade the ratings that are old enough.

Returns are always shown against QQQ and SMH over the same window, since in an
AI bull market every AI pick goes up. A rating is graded once it is
GRADE_AFTER_DAYS old, against QQQ:
  Buy / Overweight   right if the stock beat QQQ
  Sell / Underweight right if it trailed QQQ
  Hold               right if it stayed within HOLD_BAND of QQQ

It also scores simple alternatives over the same days, so the picks have to beat
more than the index to show the AI steps add anything:
  universe       every stock in universe.json, equal weight
  shortlist_avg  the average shortlist name (what a random pick would expect)
  screen_top     the screen's top-ranked name, no AI involved
  picks          Claude's new picks
  ta_positive    the picks TradingAgents rated Buy or Overweight
"""

import csv
from collections import defaultdict
from datetime import date

import yfinance as yf

from common import DATA, read_json, segment_of, today, write_json

GRADE_AFTER_DAYS = 28
HOLD_BAND = 0.05


def correct(rating, excess):
    if rating in ("Buy", "Overweight"):
        return excess > 0
    if rating in ("Sell", "Underweight"):
        return excess < 0
    if rating == "Hold":
        return abs(excess) <= HOLD_BAND
    return None


STRATEGIES = {
    "picks": "Claude's picks",
    "ta_positive": "Picks rated Buy / Overweight",
    "screen_top": "Screen's #1 (no AI)",
    "shortlist_avg": "Random shortlist pick (average)",
    "universe": "Whole universe, equal weight",
    "QQQ": "QQQ (Nasdaq-100)",
    "SMH": "SMH (chip stocks)",
}


def baselines(rows, px):
    """Average return since each pick day, per strategy, entered at that day's recorded close."""
    days = sorted({r["date"] for r in rows if r.get("kind", "new") == "new"})
    per = defaultdict(list)
    for d in days:
        market = read_json(DATA / d / "market.json", {})
        short = [x["ticker"] for x in read_json(DATA / d / "shortlist.json", {}).get("shortlist", [])]

        def ret(t):
            try:
                return float(px[t]) / market[t]["close"] - 1
            except (KeyError, TypeError, ZeroDivisionError, ValueError):
                return None

        def avg(ts):
            rs = [x for x in map(ret, ts) if x is not None]
            return sum(rs) / len(rs) if rs else None

        new = [r for r in rows if r["date"] == d and r.get("kind", "new") == "new"]
        got = {"picks": avg(r["ticker"] for r in new),
               "ta_positive": avg(r["ticker"] for r in new if r["rating"] in ("Buy", "Overweight")),
               "screen_top": avg(short[:1]), "shortlist_avg": avg(short),
               "universe": avg(segment_of()), "QQQ": ret("QQQ"), "SMH": ret("SMH")}
        for k, v in got.items():
            if v is not None and v == v:  # skip NaN from missing prices
                per[k].append(v)
    q = per.get("QQQ") or []
    out = {}
    for k, label in STRATEGIES.items():
        vals = per.get(k, [])
        out[k] = {"label": label, "days": len(vals), "avg_return": round(sum(vals) / len(vals), 4) if vals else None}
    if q:
        for v in out.values():
            if v["avg_return"] is not None:
                v["avg_vs_qqq"] = round(v["avg_return"] - sum(q) / len(q), 4)
    return {"pick_days": len(days), "strategies": out}


def repair_ledger():
    """Re-add ledger rows for any saved run that is missing from picks.csv (e.g. lost in a git sync)."""
    from agents import upsert_ledger  # local import: agents pulls in langchain

    rows = []
    for runs_file in sorted(DATA.glob("*/runs.json")):
        d = runs_file.parent
        market = read_json(d / "market.json", {})
        for r in read_json(runs_file, []):
            a = read_json(d / "agents" / f"{r['ticker']}.json", {})
            if r["kind"] != "new" and not a.get("rating"):
                continue
            close = lambda t: (market.get(t) or {}).get("close", "")
            rows.append({"date": d.name, "ticker": r["ticker"], "kind": r["kind"], "segment": r["segment"],
                         "price": close(r["ticker"]), "qqq": close("QQQ"), "smh": close("SMH"),
                         "rating": a.get("rating") or "", "trader": a.get("trader") or "",
                         "research_manager": a.get("research_manager") or ""})
    upsert_ledger(rows)


def main():
    repair_ledger()
    path = DATA / "picks.csv"
    rows = list(csv.DictReader(open(path))) if path.exists() else []
    if not rows:
        write_json(DATA / "tracking.json", {"date": today(), "picks": [], "scorecard": {}})
        print("no picks yet")
        return
    symbols = sorted({r["ticker"] for r in rows} | {"QQQ", "SMH"} | set(segment_of()))
    px = yf.download(symbols, period="5d", interval="1d", auto_adjust=True, progress=False)["Close"].ffill().iloc[-1]
    now = date.fromisoformat(today())
    out, by_rating = [], defaultdict(lambda: {"graded": 0, "right": 0, "excess": []})
    for r in rows:
        try:
            p0, q0, s0 = float(r["price"]), float(r["qqq"]), float(r["smh"])
        except ValueError:
            continue
        ret = float(px[r["ticker"]]) / p0 - 1
        ex_q = ret - (float(px["QQQ"]) / q0 - 1)
        ex_s = ret - (float(px["SMH"]) / s0 - 1)
        age = (now - date.fromisoformat(r["date"])).days
        item = {**r, "now": round(float(px[r["ticker"]]), 2), "return": round(ret, 4), "vs_qqq": round(ex_q, 4),
                "vs_smh": round(ex_s, 4), "age_days": age, "correct": None}
        if age >= GRADE_AFTER_DAYS and r["rating"]:
            item["correct"] = correct(r["rating"], ex_q)
            b = by_rating[r["rating"]]
            b["graded"] += 1
            b["right"] += bool(item["correct"])
            b["excess"].append(ex_q)
        out.append(item)

    scorecard = {k: {"graded": v["graded"], "hit_rate": round(v["right"] / v["graded"], 2),
                     "avg_vs_qqq": round(sum(v["excess"]) / len(v["excess"]), 4)} for k, v in by_rating.items()}
    all_ex = [i["vs_qqq"] for i in out if i.get("kind", "new") == "new"]
    summary = {"picks": len(out), "avg_vs_qqq": round(sum(all_ex) / len(all_ex), 4) if all_ex else None,
               "beating_qqq": sum(x > 0 for x in all_ex)}
    write_json(DATA / "tracking.json", {"date": today(), "summary": summary, "scorecard": scorecard,
                                        "baselines": baselines(rows, px),
                                        "rules": {"grade_after_days": GRADE_AFTER_DAYS, "hold_band": HOLD_BAND},
                                        "picks": sorted(out, key=lambda i: i["date"], reverse=True)})
    print(f"tracking: {summary}")


if __name__ == "__main__":
    main()
