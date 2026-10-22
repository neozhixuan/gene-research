"""Stage 6: mark every past pick to market and grade the ratings that are old enough.

Returns are always shown against QQQ and SMH over the same window, since in an
AI bull market every AI pick goes up. A rating is graded once it is
GRADE_AFTER_DAYS old, against QQQ:
  Buy / Overweight   right if the stock beat QQQ
  Sell / Underweight right if it trailed QQQ
  Hold               right if it stayed within HOLD_BAND of QQQ
"""

import csv
from collections import defaultdict
from datetime import date

import yfinance as yf

from common import DATA, today, write_json

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


def main():
    path = DATA / "picks.csv"
    if path.exists():
        with open(path) as f:
            rows = list(csv.DictReader(f))
    else:
        rows = []
    if not rows:
        write_json(DATA / "tracking.json", {"date": today(), "picks": [], "scorecard": {}})
        print("no picks yet")
        return
    symbols = sorted({r["ticker"] for r in rows} | {"QQQ", "SMH"})
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
                                        "rules": {"grade_after_days": GRADE_AFTER_DAYS, "hold_band": HOLD_BAND},
                                        "picks": sorted(out, key=lambda i: i["date"], reverse=True)})
    print(f"tracking: {summary}")


if __name__ == "__main__":
    main()
