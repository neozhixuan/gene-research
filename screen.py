from __future__ import annotations

from pipeline_common import dump_json, ensure_day_dir, load_json, parse_date_arg


SECTORS = {
    "NVDA": "ai chips",
    "MSFT": "cloud ai",
    "TSLA": "ev autonomy",
    "AMD": "ai chips",
    "AVGO": "semiconductors",
    "TSM": "foundry",
    "ASML": "lithography",
    "INTC": "semiconductors",
}


def _worldview_boost(worldview_text: str, sector: str) -> float:
    sector_terms = set(sector.lower().split())
    worldview_terms = set(worldview_text.lower().split())
    overlap = sector_terms.intersection(worldview_terms)
    return 0.15 * len(overlap)


def main() -> None:
    args = parse_date_arg()
    day_dir = ensure_day_dir(args.date, args.data_dir)
    prices = load_json(day_dir / "prices.json", default={"close": {}})
    worldview = load_json(day_dir / "worldview.json", default={})

    worldview_text = " ".join(
        [" ".join(worldview.get("theses", []))]
        + [" ".join(worldview.get("changes", []))]
        + [" ".join(worldview.get("invalidation_triggers", []))]
    )

    scored = []
    for ticker, close in prices.get("close", {}).items():
        if ticker in {"QQQ", "SMH"}:
            continue
        momentum = (float(close) - 100.0) / 100.0
        value_factor = 1.0 / (1.0 + abs(float(close) - 150.0) / 150.0)
        sector = SECTORS.get(ticker, "other")
        score = 0.5 * momentum + 0.35 * value_factor + _worldview_boost(worldview_text, sector)
        scored.append(
            {
                "ticker": ticker,
                "score": round(score, 4),
                "sector": sector,
                "filters": {
                    "ai_bottleneck_relevance": round(max(0.0, 0.6 + _worldview_boost(worldview_text, sector)), 3),
                    "value_factor": round(value_factor, 3),
                    "momentum": round(momentum, 3),
                },
                "rationale": f"Template ranking based on momentum/value + worldview overlap for {sector}.",
            }
        )

    shortlist = sorted(scored, key=lambda row: row["score"], reverse=True)[:8]
    payload = {
        "date": args.date,
        "target_count": 8,
        "source": "template",
        "shortlist": shortlist,
        "next_step": "Claude picks 2 names with reasons and writes data/YYYY-MM-DD/picks.json",
    }

    dump_json(day_dir / "shortlist.json", payload)
    print(f"Wrote {day_dir / 'shortlist.json'}")


if __name__ == "__main__":
    main()
