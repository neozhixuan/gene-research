from __future__ import annotations

from collections import defaultdict

from pipeline_common import (
    dump_json,
    ensure_day_dir,
    load_json,
    load_jsonl,
    parse_date_arg,
    previous_day_dir,
)


def main() -> None:
    args = parse_date_arg()
    day_dir = ensure_day_dir(args.date, args.data_dir)
    news = load_jsonl(day_dir / "news.jsonl")
    prices = load_json(day_dir / "prices.json", default={"close": {}})

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in news:
        grouped[row.get("ticker", "UNKNOWN")].append(row)

    lines = [
        f"# Daily Market Digest ({args.date})",
        "",
        "This is a generalized template digest (~3-5k token target once real fetchers are plugged in).",
        "",
        "## Price snapshot",
        "",
        "| Ticker | Close |",
        "| --- | ---: |",
    ]
    for ticker, close in sorted(prices.get("close", {}).items()):
        lines.append(f"| {ticker} | {close} |")

    lines.extend(["", "## News grouped by ticker", ""])
    for ticker, rows in sorted(grouped.items()):
        lines.append(f"### {ticker}")
        for row in rows:
            lines.append(f"- **{row.get('headline', 'N/A')}** — {row.get('summary', '')}")
        lines.append("")

    lines.extend(
        [
            "## Claude worldview update handoff",
            "",
            "Use this digest with yesterday's `worldview.json`.",
            "Output updated `worldview.json` with:",
            "- theses",
            "- confidence per thesis",
            "- what changed and why",
            "- invalidation triggers",
        ]
    )

    (day_dir / "digest.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    previous = previous_day_dir(args.date, args.data_dir)
    previous_worldview = load_json(previous / "worldview.json", default=None) if previous else None
    if previous_worldview is not None:
        dump_json(day_dir / "worldview.previous.json", previous_worldview)

    worldview_template = {
        "date": args.date,
        "theses": [],
        "confidence": {},
        "changes": [],
        "invalidation_triggers": [],
        "notes": "Claude should overwrite this template with actual worldview output.",
    }
    if not (day_dir / "worldview.json").exists():
        dump_json(day_dir / "worldview.json", worldview_template)

    print(f"Wrote {day_dir / 'digest.md'}")
    if previous_worldview is not None:
        print(f"Wrote {day_dir / 'worldview.previous.json'}")
    print(f"Ensured {day_dir / 'worldview.json'}")


if __name__ == "__main__":
    main()
