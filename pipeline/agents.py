"""Stage 5: verify the day's picks with TradingAgents (runs on Gemini, not Claude).

Reads data/<date>/picks.json, runs each ticker in order up to --max, and writes
data/<date>/agents/<TICKER>.json with every agent's output. A Gemini quota error
stops the run cleanly: later tickers are recorded as skipped. Every pick is
appended to data/picks.csv, the ledger that tracking and scoring read.
"""

import argparse
import csv
import os
import re
import time

from common import DATA, ROOT, day_dir, today, read_json, write_json

os.environ.setdefault("TRADINGAGENTS_LLM_PROVIDER", "google")
os.environ.setdefault("TRADINGAGENTS_DEEP_THINK_LLM", "gemini-3.5-flash-lite")
os.environ.setdefault("TRADINGAGENTS_QUICK_THINK_LLM", "gemini-3.1-flash-lite")
os.environ.setdefault("TRADINGAGENTS_LLM_MAX_RETRIES", "10")
os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", str(DATA / "ta_memory" / "trading_memory.md"))
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", str(ROOT / ".ta_results"))
os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", str(ROOT / ".ta_cache"))

LEDGER = DATA / "picks.csv"
LEDGER_FIELDS = ["date", "ticker", "segment", "price", "qqq", "smh", "rating", "trader", "research_manager"]
PAPER_CASH = 10_000
QUOTA = re.compile(r"RESOURCE_EXHAUSTED|quota|429", re.I)
OVERLOADED = re.compile(r"503|UNAVAILABLE|high demand|overloaded", re.I)
OVERLOAD_WAITS = [60, 180, 300]  # seconds to wait before each retry when Gemini is overloaded


def verdict(text, label):
    m = re.search(rf"\*\*{label}\*\*:\s*\**\s*(\w+)", text or "")
    return m.group(1).capitalize() if m else None


def run_one(ticker):
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext

    ta = TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())
    book = PortfolioContext(cash=PAPER_CASH, currency="USD", positions=[])
    state, rating = ta.propagate(ticker, today(), portfolio=book)
    inv, risk = state.get("investment_debate_state", {}), state.get("risk_debate_state", {})
    return {
        "rating": rating,
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
        w.writerows(old)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=2, help="most tickers to run through TradingAgents")
    args = ap.parse_args()
    d = day_dir()
    picks = read_json(d / "picks.json", {}).get("picks", [])
    market = read_json(d / "market.json", {})
    if not picks:
        raise SystemExit("no picks.json for today; Claude writes it before this stage")

    rows, stop = [], None
    for n, p in enumerate(picks):
        t = p["ticker"].upper()
        out = d / "agents" / f"{t}.json"
        if n >= args.max or stop:
            result = {"rating": None, "skipped": stop or f"over --max {args.max}"}
        elif (prev := read_json(out)) and prev.get("rating"):
            result = prev  # already ran today; a rerun of this stage costs no Gemini quota
        else:
            start = time.time()
            for wait in [0, *OVERLOAD_WAITS]:
                time.sleep(wait)
                try:
                    result = run_one(t)
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {str(e)[:300]}"
                    result = {"rating": None, "error": msg}
                    if QUOTA.search(msg):
                        stop = "Gemini quota exhausted earlier in this run"
                    if not OVERLOADED.search(msg) or QUOTA.search(msg):
                        break
                    print(f"{t}: Gemini overloaded, retrying", flush=True)
            result["seconds"] = round(time.time() - start)
        result.update(ticker=t, date=today())
        write_json(out, result)
        print(f"{t}: {result.get('rating') or result.get('error') or result.get('skipped')}", flush=True)
        rows.append({"date": today(), "ticker": t, "segment": p.get("segment", ""),
                     "price": (market.get(t) or {}).get("close", ""), "qqq": (market.get("QQQ") or {}).get("close", ""),
                     "smh": (market.get("SMH") or {}).get("close", ""), "rating": result.get("rating") or "",
                     "trader": result.get("trader") or "", "research_manager": result.get("research_manager") or ""})

    upsert_ledger(rows)


if __name__ == "__main__":
    main()
