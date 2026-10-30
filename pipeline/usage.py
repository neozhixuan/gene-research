"""Record what a daily run cost in tokens, for tracking against plan limits and for optimising.

Claude's numbers come from the session's own transcript: Claude Code logs token
usage for every model call in ~/.claude/projects/*/<session>.jsonl, and the newest
transcript is the running session. Gemini's come from the TradingAgents runs saved
today.

  python pipeline/usage.py                     # read the current session's transcript
  echo '<usage json>' | python pipeline/usage.py -   # or pass a usage object explicitly

Writes data/<date>/usage.json and upserts one row per day in data/usage.csv.
The brief_* columns are the part of the Claude total spent on tonight's brief
(pipeline/brief.py stamps when it started and finished); they are included in,
not added to, the claude_* totals.
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from utils.common import DATA, day_dir, today, read_json, write_json

LEDGER = DATA / "usage.csv"
FIELDS = ["date", "claude_calls", "claude_input", "claude_output", "claude_cache_read", "claude_cache_write", "claude_cost_usd",
          "gemini_calls", "gemini_input", "gemini_output", "ta_runs",
          "brief_calls", "brief_input", "brief_output", "brief_cache_read", "brief_cache_write"]


def _totals(u):
    add = lambda k: sum(x.get(k) or 0 for x in u)  # some entries carry null counts
    return {"input_tokens": add("input_tokens"), "output_tokens": add("output_tokens"),
            "cache_read_tokens": add("cache_read_input_tokens"), "cache_write_tokens": add("cache_creation_input_tokens"),
            "model_calls": len(u)}


def claude_from_transcript(window=None):
    """Sum token usage over the newest Claude Code transcript, once per model message.

    With window=(start_iso, end_iso), also return the subset whose timestamps fall
    inside it, as "brief"."""
    files = [f for f in Path.home().glob(".claude/projects/*/*.jsonl") if f.is_file()]
    if not files:
        return {}
    per_message, stamps = {}, {}
    with open(max(files, key=lambda f: f.stat().st_mtime)) as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = entry.get("message") or {}
            if isinstance(msg, dict) and msg.get("usage") and msg.get("id"):
                per_message[msg["id"]] = msg["usage"]  # a message's blocks repeat its usage; keep one
                stamps.setdefault(msg["id"], entry.get("timestamp", ""))
    u = list(per_message.values())
    out = {**_totals(u), "source": "transcript"}
    if window and window[0]:
        start, end = _utc(window[0]), _utc(window[1]) if window[1] else None
        inside = [v for k, v in per_message.items() if stamps.get(k) and _utc(stamps[k]) >= start and (end is None or _utc(stamps[k]) <= end)]
        out["brief"] = _totals(inside)
    return out


def _utc(stamp):
    t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


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
        meta = read_json(day_dir() / "brief_meta.json", {})
        claude = claude_from_transcript((meta.get("started_at"), meta.get("finished_at")))
    d = day_dir()
    gemini, runs = gemini_today(d)
    write_json(d / "usage.json", {"date": today(), "claude": claude, "gemini": gemini, "tradingagents_runs": runs})

    row = {"date": today(), "claude_calls": claude.get("model_calls", ""), "claude_input": claude.get("input_tokens", ""), "claude_output": claude.get("output_tokens", ""),
           "claude_cache_read": claude.get("cache_read_tokens", ""), "claude_cache_write": claude.get("cache_write_tokens", ""),
           "claude_cost_usd": round(claude["cost_usd"], 4) if "cost_usd" in claude else "",
           "gemini_calls": gemini["calls"], "gemini_input": gemini["input_tokens"], "gemini_output": gemini["output_tokens"],
           "ta_runs": runs}
    brief = claude.get("brief") or {}
    row.update({"brief_calls": brief.get("model_calls", ""), "brief_input": brief.get("input_tokens", ""),
                "brief_output": brief.get("output_tokens", ""), "brief_cache_read": brief.get("cache_read_tokens", ""),
                "brief_cache_write": brief.get("cache_write_tokens", "")})
    existing = []
    if LEDGER.exists():
        with open(LEDGER) as f:
            existing = list(csv.DictReader(f))
    rows = [r for r in existing if r["date"] != today()] + [row]
    with open(LEDGER, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in sorted(rows, key=lambda r: r["date"]))
    print(f"usage {today()}: Claude out {row['claude_output']}, cache read {row['claude_cache_read']}, "
          f"${row['claude_cost_usd']}; Gemini {gemini['calls']} calls, {gemini['input_tokens']} in / {gemini['output_tokens']} out")


if __name__ == "__main__":
    main()
