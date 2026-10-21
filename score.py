from __future__ import annotations

from datetime import date
from pathlib import Path

from pipeline_common import dump_json, load_json


def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    month_key = date.today().strftime("%Y-%m")

    tracking = load_json(data_dir / "tracking.json", default={"picks": []})
    picks = tracking.get("picks", [])

    if picks:
        avg_return = sum(float(row.get("return", 0.0)) for row in picks) / len(picks)
        avg_alpha_qqq = sum(float(row.get("alpha_vs_qqq", 0.0)) for row in picks if row.get("alpha_vs_qqq") is not None) / max(
            1, len([row for row in picks if row.get("alpha_vs_qqq") is not None])
        )
    else:
        avg_return = 0.0
        avg_alpha_qqq = 0.0

    payload = {
        "month": month_key,
        "num_tracked_picks": len(picks),
        "avg_return": round(avg_return, 4),
        "avg_alpha_vs_qqq": round(avg_alpha_qqq, 4),
        "claude_review_prompt": "Summarize what worked, what failed, and what to adjust next month.",
    }

    out = data_dir / "score" / f"{month_key}.json"
    dump_json(out, payload)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
