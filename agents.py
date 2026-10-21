from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

from pipeline_common import DATA_DIR, dump_json, ensure_day_dir, load_json, utc_timestamp


def _pick_rows(day_dir: Path) -> list[dict]:
    picks = load_json(day_dir / "picks.json", default=None)
    if isinstance(picks, dict) and isinstance(picks.get("picks"), list):
        return picks["picks"]

    shortlist = load_json(day_dir / "shortlist.json", default={}).get("shortlist", [])
    return [{"ticker": row.get("ticker"), "reason": "Fallback to shortlist top names."} for row in shortlist[:2]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument(
        "--command-template",
        default="",
        help="Optional shell command template, e.g. 'python run_agent.py --ticker {ticker}'",
    )
    parser.add_argument("--background", action="store_true", help="Launch command-template in background if provided")
    args = parser.parse_args()
    if args.date is None:
        from datetime import date

        args.date = date.today().isoformat()

    day_dir = ensure_day_dir(args.date, args.data_dir)
    rows = _pick_rows(day_dir)

    jobs = []
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue

        job = {
            "ticker": ticker,
            "model": "gemini",
            "created_at": utc_timestamp(),
            "status": "queued_template",
            "reason": row.get("reason", ""),
            "command": None,
            "pid": None,
        }

        if args.command_template:
            command = args.command_template.format(ticker=ticker)
            job["command"] = command
            if args.background:
                proc = subprocess.Popen(shlex.split(command), start_new_session=True)
                job["status"] = "launched"
                job["pid"] = proc.pid
            else:
                job["status"] = "prepared"

        jobs.append(job)

    dump_json(day_dir / "agents_jobs.json", {"date": args.date, "jobs": jobs})
    print(f"Wrote {day_dir / 'agents_jobs.json'}")


if __name__ == "__main__":
    main()
