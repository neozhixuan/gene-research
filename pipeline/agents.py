"""Stage 5: verify the day's picks with TradingAgents (runs on Gemini, not Claude).

Runs, in order and up to --max: Claude's first new pick, the watchlist name due
for a re-check, then Claude's second new pick. Each run writes
data/<date>/agents/<TICKER>.json with every agent's output and the models used;
data/<date>/runs.json lists what ran today. A Gemini quota error stops the run
cleanly: later tickers are recorded as skipped. Every run is added to
data/picks.csv (the ledger tracking reads) and to the watchlist.
"""

import argparse
import csv
import importlib.metadata
import os
import re
import time

import watchlist
from common import DATA, ROOT, day_dir, today, read_json, write_json

os.environ.setdefault("TRADINGAGENTS_LLM_PROVIDER", "google")
os.environ.setdefault("TRADINGAGENTS_DEEP_THINK_LLM", "gemini-3.5-flash-lite")
os.environ.setdefault("TRADINGAGENTS_QUICK_THINK_LLM", "gemini-3.1-flash-lite")
os.environ.setdefault("TRADINGAGENTS_LLM_MAX_RETRIES", "10")
os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", str(DATA / "ta_memory" / "trading_memory.md"))
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", str(ROOT / ".ta_results"))
os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", str(ROOT / ".ta_cache"))

LEDGER = DATA / "picks.csv"
LEDGER_FIELDS = ["date", "ticker", "kind", "segment", "price", "qqq", "smh", "rating", "trader", "research_manager"]
PAPER_CASH = 10_000
QUOTA = re.compile(r"RESOURCE_EXHAUSTED|quota|429", re.I)
OVERLOADED = re.compile(r"503|UNAVAILABLE|high demand|overloaded", re.I)
# When Gemini is overloaded, retry after these waits, alternating the quick model with a fallback
# that has its own capacity. Each entry is (seconds to wait, quick model or None for the default).
FALLBACK_QUICK = os.environ.get("GENE_FALLBACK_QUICK_LLM", "gemini-3.5-flash-lite")
ATTEMPTS = [(0, None), (30, FALLBACK_QUICK), (180, None), (300, FALLBACK_QUICK)]


def verdict(text, label):
    m = re.search(rf"\*\*{label}\*\*:\s*\**\s*(\w+)", text or "")
    return m.group(1).capitalize() if m else None


def run_one(ticker, quick_model=None):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext

    config = DEFAULT_CONFIG.copy()
    if quick_model:
        config["quick_think_llm"] = quick_model
    ta = TradingAgentsGraph(debug=False, config=config)
    book = PortfolioContext(cash=PAPER_CASH, currency="USD", positions=[])
    state, rating = ta.propagate(ticker, today(), portfolio=book)
    inv, risk = state.get("investment_debate_state", {}), state.get("risk_debate_state", {})
    return {
        "rating": rating,
        "models": {"provider": config["llm_provider"], "deep": config["deep_think_llm"], "quick": config["quick_think_llm"],
                   "quick_is_fallback": bool(quick_model), "tradingagents": importlib.metadata.version("tradingagents")},
        "research_manager": verdict(state.get("investment_plan"), "Recommendation"),
        "trader": verdict(state.get("trader_investment_plan"), "Action"),
        "outputs": {
            "Market analyst": state.get("market_report"),
            "Sentiment analyst": state.get("sentiment_report"),
            "News analyst": state.get("news_report"),
            "Fundamentals analyst": state.get("fundamentals_report"),
            "Bull researcher": inv.get("bull_history"),
            "Bear researcher": inv.get("bear_history"),
            "Research manager": state.get("investment_plan"),
            "Trader": state.get("trader_investment_plan"),
            "Aggressive analyst": risk.get("aggressive_history"),
            "Conservative analyst": risk.get("conservative_history"),
            "Neutral analyst": risk.get("neutral_history"),
            "Portfolio manager": state.get("final_trade_decision"),
        },
    }


def upsert_ledger(rows):
    """Add today's picks, or fill in ratings for picks whose earlier run failed. Prices at pick never change."""
    old = list(csv.DictReader(open(LEDGER))) if LEDGER.exists() else []
    index = {(r["date"], r["ticker"]): r for r in old}
    for r in rows:
        if (prev := index.get((r["date"], r["ticker"]))):
            if r["rating"]:
                prev.update(rating=r["rating"], trader=r["trader"], research_manager=r["research_manager"])
        else:
            old.append(r)
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k) or ("new" if k == "kind" else "") for k in LEDGER_FIELDS} for r in old)


def run_list(picks, watch):
    """New pick 1, then today's due re-check, then new pick 2."""
    new = [{"ticker": p["ticker"].upper(), "segment": p.get("segment", ""), "kind": "new"} for p in picks]
    recheck = watchlist.due_recheck(watch, today())
    if recheck and recheck not in {r["ticker"] for r in new}:
        new.insert(1, {"ticker": recheck, "segment": watch[recheck]["segment"], "kind": "recheck"})
    return new


def analyse(t):
    """One TradingAgents run with overload retries. Returns (result, quota_hit)."""
    start = time.time()
    for wait, quick in ATTEMPTS:
        time.sleep(wait)
        try:
            result = run_one(t, quick)
            break
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:300]}"
            result = {"rating": None, "error": msg}
            if QUOTA.search(msg) or not OVERLOADED.search(msg):
                break
            print(f"{t}: Gemini overloaded, retrying", flush=True)
    result["seconds"] = round(time.time() - start)
    return result, bool(QUOTA.search(result.get("error") or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=2, help="most tickers to run through TradingAgents")
    args = ap.parse_args()
    d = day_dir()
    picks = read_json(d / "picks.json", {}).get("picks", [])
    market = read_json(d / "market.json", {})
    if not picks:
        raise SystemExit("no picks.json for today; Claude writes it before this stage")
    watch = watchlist.load()
    runs = read_json(d / "runs.json") or run_list(picks, watch)  # a rerun keeps today's original plan
    write_json(d / "runs.json", runs)

    rows, stop = [], None
    for n, r in enumerate(runs):
        t = r["ticker"]
        out = d / "agents" / f"{t}.json"
        if (prev := read_json(out)) and prev.get("rating"):
            result = prev  # already ran today; a rerun of this stage costs no Gemini quota
        elif n >= args.max or stop:
            result = {"rating": None, "skipped": stop or f"over --max {args.max}"}
        else:
            result, quota_hit = analyse(t)
            if quota_hit:
                stop = "Gemini quota exhausted earlier in this run"
        result.update(ticker=t, date=today(), kind=r["kind"])
        write_json(out, result)
        print(f"{t} ({r['kind']}): {result.get('rating') or result.get('error') or result.get('skipped')}", flush=True)
        if result.get("rating") or r["kind"] == "new":
            watchlist.record(watch, t, r["segment"], today(), result.get("rating"), r["kind"])
        rows.append({"date": today(), "ticker": t, "kind": r["kind"], "segment": r["segment"],
                     "price": (market.get(t) or {}).get("close", ""), "qqq": (market.get("QQQ") or {}).get("close", ""),
                     "smh": (market.get("SMH") or {}).get("close", ""), "rating": result.get("rating") or "",
                     "trader": result.get("trader") or "", "research_manager": result.get("research_manager") or ""})

    watchlist.trim(watch, today())
    watchlist.save(watch)
    upsert_ledger([row for row in rows if row["kind"] == "new" or row["rating"]])


if __name__ == "__main__":
    main()
