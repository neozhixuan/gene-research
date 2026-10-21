from __future__ import annotations

import random

from pipeline_common import dump_json, dump_jsonl, ensure_day_dir, parse_date_arg, utc_timestamp

DEFAULT_TICKERS = ["NVDA", "MSFT", "TSLA", "AMD", "AVGO", "TSM", "ASML", "INTC", "QQQ", "SMH"]


def _price_for(ticker: str, run_date: str) -> float:
    rng = random.Random(f"{run_date}:{ticker}")
    return round(rng.uniform(60, 420), 2)


def main() -> None:
    args = parse_date_arg()
    day_dir = ensure_day_dir(args.date, args.data_dir)

    news_rows = []
    for idx, ticker in enumerate(DEFAULT_TICKERS[:6], start=1):
        news_rows.append(
            {
                "id": f"{args.date}-{idx}",
                "ticker": ticker,
                "headline": f"Template market headline for {ticker}",
                "summary": "Replace this with your real upstream fetcher output.",
                "source": "template",
                "published_at": utc_timestamp(),
                "tags": ["ai", "semis" if ticker in {"NVDA", "AMD", "TSM", "ASML"} else "macro"],
            }
        )

    prices = {
        "as_of": args.date,
        "source": "template",
        "close": {ticker: _price_for(ticker, args.date) for ticker in DEFAULT_TICKERS},
    }

    dump_jsonl(day_dir / "news.jsonl", news_rows)
    dump_json(day_dir / "prices.json", prices)

    print(f"Wrote {day_dir / 'news.jsonl'}")
    print(f"Wrote {day_dir / 'prices.json'}")


if __name__ == "__main__":
    main()
