"""Record what a daily run cost in tokens, for tracking against plan limits and for optimising.

Claude's numbers come from the session's own transcript: Claude Code logs token
usage for every model call in ~/.claude/projects/*/<session>.jsonl, and the newest
transcript is the running session. Gemini's come from the TradingAgents runs saved
today.

  python pipeline/usage.py                     # read the current session's transcript
  echo '<usage json>' | python pipeline/usage.py -   # or pass a usage object explicitly

Writes data/<date>/usage.json and upserts one row per day in data/usage.csv.
"""

import csv
import json
import sys
from pathlib import Path

from common import DATA, day_dir, today, read_json, write_json

LEDGER = DATA / "usage.csv"
FIELDS = ["date", "claude_input", "claude_output", "claude_cache_read", "claude_cache_write", "claude_cost_usd",
          "gemini_calls", "gemini_input", "gemini_output", "ta_runs"]


def claude_from_transcript():
    """Sum token usage over the newest Claude Code transcript, once per model message."""
    files = [f for f in Path.home().glob(".claude/projects/*/*.jsonl") if f.is_file()]
    if not files:
        return {}
    per_message = {}
    for line in open(max(files, key=lambda f: f.stat().st_mtime)):
        try:
            msg = json.loads(line).get("message") or {}
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and msg.get("usage") and msg.get("id"):
            per_message[msg["id"]] = msg["usage"]  # a message's blocks repeat its usage; keep one
    u = per_message.values()
    return {"input_tokens": sum(x.get("input_tokens", 0) for x in u),
            "output_tokens": sum(x.get("output_tokens", 0) for x in u),
            "cache_read_tokens": sum(x.get("cache_read_input_tokens", 0) for x in u),
            "cache_write_tokens": sum(x.get("cache_creation_input_tokens", 0) for x in u),
            "model_calls": len(per_message), "source": "transcript"}


def gemini_today(d):
    total, runs = {"calls": 0, "input_tokens": 0, "output_tokens": 0}, 0
    for f in sorted((d / "agents").glob("*.json")):
        a = read_json(f, {})
        if a.get("date") != today() or "gemini_usage" not in a:
            continue
        runs += 1
        for m in a["gemini_usage"].values():
            for k in total:
                total[k] += m.get(k, 0)
    return total, runs


def main():
    if sys.argv[1:] == ["-"]:
        claude = json.loads(sys.stdin.read())
        claude = claude.get("usage", claude)  # accept the whole external_metadata block or just usage
    else:
        claude = claude_from_transcript()
    d = day_dir()
    gemini, runs = gemini_today(d)
    write_json(d / "usage.json", {"date": today(), "claude": claude, "gemini": gemini, "tradingagents_runs": runs})

    row = {"date": today(), "claude_input": claude.get("input_tokens", ""), "claude_output": claude.get("output_tokens", ""),
           "claude_cache_read": claude.get("cache_read_tokens", ""), "claude_cache_write": claude.get("cache_write_tokens", ""),
           "claude_cost_usd": round(claude["cost_usd"], 4) if "cost_usd" in claude else "",
           "gemini_calls": gemini["calls"], "gemini_input": gemini["input_tokens"], "gemini_output": gemini["output_tokens"],
           "ta_runs": runs}
    rows = [r for r in (csv.DictReader(open(LEDGER)) if LEDGER.exists() else []) if r["date"] != today()] + [row]
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["date"]))
    print(f"usage {today()}: Claude out {row['claude_output']}, cache read {row['claude_cache_read']}, "
          f"${row['claude_cost_usd']}; Gemini {gemini['calls']} calls, {gemini['input_tokens']} in / {gemini['output_tokens']} out")


if __name__ == "__main__":
    main()
