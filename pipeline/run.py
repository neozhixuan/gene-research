"""Daily orchestrator. Claude runs `pre`, writes two files, then runs `post`.

  python pipeline/run.py pre    fetch → digest → screen, then lists what Claude reads
  python pipeline/run.py post   validate → TradingAgents → track → site
"""

import subprocess
import sys

from common import DATA, day_dir, previous_worldview, today

STAGES = {"pre": ["fetch.py", "digest.py", "screen.py"], "post": ["validate.py", "agents.py", "track.py", "site.py"]}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    if which not in STAGES:
        raise SystemExit("usage: run.py pre|post [--max N]")
    for script in STAGES[which]:
        extra = sys.argv[2:] if script == "agents.py" else []
        print(f"--- {script}", flush=True)
        if subprocess.run([sys.executable, f"pipeline/{script}", *extra]).returncode:
            raise SystemExit(f"{script} failed")
    if which == "pre":
        d = day_dir().relative_to(DATA.parent)
        prev, _ = previous_worldview(today())
        print(f"\nRead: {d}/digest.md, {d}/shortlist.md, "
              f"{'data/worldview/' + prev + '.json' if prev else 'no previous worldview (first run)'}")
        print(f"Write: data/worldview/{today()}.json and {d}/picks.json, then run: python pipeline/run.py post")


if __name__ == "__main__":
    main()
