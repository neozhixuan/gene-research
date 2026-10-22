"""Stage 3: screen the AI-bottleneck universe into a shortlist Claude picks from.

House style: Situational Awareness says where to look (the universe), Buffett
says what to pick. A quality gate drops cash-burners, then names are ranked on
value, quality, discount to their high and how thinly they are covered.
Names already on the watchlist (or dropped from it recently) are skipped: they are
re-checked through the watchlist instead, so the shortlist is always new names.
"""

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

import watchlist
from utils.common import day_dir, today, segment_of, write_json
from utils.scoring import rank

SHORTLIST = 8
PER_SEGMENT = 3
FIELDS = ["shortName", "industry", "currentPrice", "marketCap", "forwardPE", "trailingPE", "revenueGrowth",
          "earningsGrowth", "freeCashflow", "operatingMargins", "debtToEquity", "fiftyTwoWeekHigh",
          "twoHundredDayAverage", "numberOfAnalystOpinions", "targetMeanPrice", "recommendationKey",
          "currency", "financialCurrency"]
# Weight of each ranked factor in the composite; True means higher is better.
FACTORS = {"fcf_yield": (0.25, True), "peg": (0.20, False), "op_margin": (0.15, True), "drawdown": (0.15, False),
           "coverage": (0.10, False), "mcap": (0.05, False), "vs_200d": (0.10, True)}


def info(t):
    try:
        i = yf.Ticker(t).info
        return t, {k: i.get(k) for k in FIELDS}
    except Exception as e:
        return t, {"error": str(e)[:100]}


def fx_rate(src, dst):
    """Multiplier from src to dst currency, e.g. TWD statements against a USD market cap."""
    if not src or not dst or src == dst:
        return 1.0
    try:
        return float(yf.Ticker(f"{src}{dst}=X").fast_info["last_price"])
    except Exception:
        return None


def metrics(t, i, seg):
    px, mcap = i.get("currentPrice"), i.get("marketCap")
    if not px or not mcap:
        return None
    growth, fpe = i.get("revenueGrowth"), i.get("forwardPE")
    fx = fx_rate(i.get("financialCurrency"), i.get("currency"))
    fcf = i["freeCashflow"] * fx if i.get("freeCashflow") is not None and fx else None
    m = {
        "ticker": t, "segment": seg, "name": i.get("shortName"), "price": px, "mcap_bn": round(mcap / 1e9, 1),
        "fwd_pe": round(fpe, 1) if fpe and fpe > 0 else None,
        "rev_growth": growth, "fcf_yield": round(fcf / mcap, 4) if fcf is not None else None,
        "op_margin": i.get("operatingMargins"), "debt_to_equity": i.get("debtToEquity"),
        "drawdown": round(px / i["fiftyTwoWeekHigh"] - 1, 3) if i.get("fiftyTwoWeekHigh") else None,
        "vs_200d": round(px / i["twoHundredDayAverage"] - 1, 3) if i.get("twoHundredDayAverage") else None,
        "coverage": i.get("numberOfAnalystOpinions") or 0, "mcap": mcap,
        "analyst_upside": round(i["targetMeanPrice"] / px - 1, 3) if i.get("targetMeanPrice") else None,
    }
    m["peg"] = round(m["fwd_pe"] / (growth * 100), 2) if m["fwd_pe"] and growth and growth > 0.02 else None
    # Quality gate: real free cash flow, or solid operating margins with manageable debt.
    m["passes_gate"] = bool((fcf or 0) > 0 or ((m["op_margin"] or 0) > 0.10 and (m["debt_to_equity"] or 0) < 150))
    return m


def pct(x):
    return f"{x * 100:+.0f}%" if x is not None else "–"


def main():
    d = day_dir()
    seg = segment_of()
    with ThreadPoolExecutor(max_workers=8) as pool:
        raw = dict(pool.map(info, seg))
    write_json(d / "fundamentals.json", raw)
    rows = [m for t, i in raw.items() if (m := metrics(t, i, seg[t]))]
    watch = watchlist.load()
    cooled = watchlist.excluded(watch, today())
    on_watch = ", ".join(f"{t} ({w['segment']})" for t, w in watchlist.active(watch).items())
    eligible = rank([r for r in rows if r["passes_gate"] and r["ticker"] not in cooled], FACTORS)
    shortlist, per_seg = [], {}
    for r in eligible:
        if per_seg.get(r["segment"], 0) < PER_SEGMENT:
            shortlist.append(r)
            per_seg[r["segment"]] = per_seg.get(r["segment"], 0) + 1
        if len(shortlist) == SHORTLIST:
            break
    story = [r["ticker"] for r in rows if not r["passes_gate"]]
    write_json(d / "shortlist.json", {"date": today(), "shortlist": shortlist, "failed_quality_gate": story,
                                      "cooldown": sorted(cooled)})

    lines = [f"# Shortlist {today()}", "",
             f"Screened {len(rows)} names. Quality gate dropped {len(story)} cash-burners: {', '.join(story) or 'none'}.",
             f"On the watchlist or recently dropped, so not shown: {', '.join(sorted(cooled)) or 'none'}.",
             f"Active watchlist by segment: {on_watch or 'empty'}.", "",
             "| # | Ticker | Segment | Price | Mkt cap $bn | Fwd P/E | Rev growth | FCF yield | Op margin | Off 52w high | vs 200d | Analysts | Score |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n, r in enumerate(shortlist, 1):
        lines.append(f"| {n} | {r['ticker']} | {r['segment']} | {r['price']:,.2f} | {r['mcap_bn']} | {r['fwd_pe'] or '–'} | "
                     f"{pct(r['rev_growth'])} | {pct(r['fcf_yield'])} | {pct(r['op_margin'])} | {pct(r['drawdown'])} | "
                     f"{pct(r['vs_200d'])} | {r['coverage']} | {r['score']} |")
    (d / "shortlist.md").write_text("\n".join(lines) + "\n")
    print(f"shortlist: {[r['ticker'] for r in shortlist]}")


if __name__ == "__main__":
    main()
