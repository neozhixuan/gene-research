from __future__ import annotations

from pathlib import Path

from pipeline_common import dump_json, day_dirs, load_json


def _pick_list(path: Path) -> list[str]:
    payload = load_json(path, default={})
    if isinstance(payload, dict) and isinstance(payload.get("picks"), list):
        return [row.get("ticker") for row in payload["picks"] if isinstance(row, dict) and row.get("ticker")]
    if isinstance(payload, list):
        return [row.get("ticker") for row in payload if isinstance(row, dict) and row.get("ticker")]
    return []


def main() -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    all_days = day_dirs(data_dir)

    first_seen: dict[str, dict] = {}
    latest_prices: dict[str, float] = {}
    benchmark_first: dict[str, float] = {}
    benchmark_latest: dict[str, float] = {}

    for day in all_days:
        prices = load_json(day / "prices.json", default={}).get("close", {})
        for ticker, price in prices.items():
            latest_prices[ticker] = float(price)
            if ticker in {"QQQ", "SMH"} and ticker not in benchmark_first:
                benchmark_first[ticker] = float(price)
            if ticker in {"QQQ", "SMH"}:
                benchmark_latest[ticker] = float(price)

        for ticker in _pick_list(day / "picks.json"):
            if ticker not in first_seen and ticker in prices:
                first_seen[ticker] = {
                    "first_seen": day.name,
                    "first_price": float(prices[ticker]),
                }

    results = []
    qqq_ret = (
        (benchmark_latest["QQQ"] - benchmark_first["QQQ"]) / benchmark_first["QQQ"]
        if benchmark_first.get("QQQ") and benchmark_latest.get("QQQ")
        else None
    )
    smh_ret = (
        (benchmark_latest["SMH"] - benchmark_first["SMH"]) / benchmark_first["SMH"]
        if benchmark_first.get("SMH") and benchmark_latest.get("SMH")
        else None
    )

    for ticker, meta in sorted(first_seen.items()):
        latest_price = latest_prices.get(ticker)
        if latest_price is None:
            continue
        raw_ret = (latest_price - meta["first_price"]) / meta["first_price"]
        results.append(
            {
                "ticker": ticker,
                "first_seen": meta["first_seen"],
                "first_price": meta["first_price"],
                "latest_price": latest_price,
                "return": round(raw_ret, 4),
                "alpha_vs_qqq": round(raw_ret - qqq_ret, 4) if qqq_ret is not None else None,
                "alpha_vs_smh": round(raw_ret - smh_ret, 4) if smh_ret is not None else None,
            }
        )

    payload = {
        "benchmark": {
            "QQQ": {"first": benchmark_first.get("QQQ"), "latest": benchmark_latest.get("QQQ"), "return": qqq_ret},
            "SMH": {"first": benchmark_first.get("SMH"), "latest": benchmark_latest.get("SMH"), "return": smh_ret},
        },
        "picks": results,
    }

    dump_json(data_dir / "tracking.json", payload)
    print(f"Wrote {data_dir / 'tracking.json'}")


if __name__ == "__main__":
    main()
