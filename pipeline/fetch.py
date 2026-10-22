"""Stage 1: pull market data and financial news into data/<date>/.

Writes market.json (index and universe price moves) and news.jsonl (one article
per line, deduplicated). Every source is optional: a source that fails is
logged in sources.json and skipped, so a blocked host never stops the run.
"""

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import yfinance as yf

from constants.market import MACRO_NAMES as MACRO
from utils.common import day_dir, today, universe, segment_of, write_json

UA = {"User-Agent": "Mozilla/5.0 (gene-research)"}
LOOKBACK = timedelta(hours=36)
EXTRA_FEEDS = {
    "CNBC Markets": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Tech": "https://www.cnbc.com/id/19854910/device/rss/rss.html",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "Investing.com": "https://www.investing.com/rss/news_25.rss",
}


def get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def parse_rss(raw, source):
    items = []
    for it in ET.fromstring(raw).iter("item"):
        when = it.findtext("pubDate")
        try:
            ts = parsedate_to_datetime(when).astimezone(timezone.utc) if when else None
        except (TypeError, ValueError):
            ts = None
        desc = re.sub(r"<[^>]+>", "", it.findtext("description") or "").strip()
        items.append({"title": (it.findtext("title") or "").strip(), "link": it.findtext("link") or "",
                      "published": ts.isoformat() if ts else None, "source": source, "summary": desc[:400]})
    return items


def fetch_news(status):
    uni = universe()
    tickers = list(segment_of())
    items = []

    def attempt(name, fn):
        try:
            got = fn()
            status[name] = f"ok ({len(got)})"
            items.extend(got)
        except Exception as e:  # any source may be blocked or down
            status[name] = f"failed: {type(e).__name__}: {str(e)[:120]}"

    batches = [uni["market_news_symbols"]] + [tickers[i:i + 10] for i in range(0, len(tickers), 10)]
    for batch in batches:
        syms = ",".join(batch)
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(syms, safe=',')}&region=US&lang=en-US"
        attempt(f"yahoo-rss {syms}", lambda u=url: parse_rss(get(u), "Yahoo Finance"))
    for name, url in EXTRA_FEEDS.items():
        attempt(name, lambda u=url, n=name: parse_rss(get(u), n))
    return items


def tag_tickers(item, known):
    text = f"{item['title']} {item['summary']}"
    found = {t for t in item.get("related", []) if t in known}
    found |= {t for t in known if re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", text)}
    return sorted(found)


def dedupe(items, cutoff):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["published"] or "", reverse=True):
        if it["published"] and datetime.fromisoformat(it["published"]) < cutoff:
            continue
        key = hashlib.sha1(re.sub(r"\W+", "", it["title"].lower()).encode()).hexdigest()
        if not it["title"] or key in seen:
            continue
        seen.add(key)
        it["id"] = key[:12]
        out.append(it)
    return out


def fetch_market():
    uni = universe()
    symbols = list(MACRO) + uni["benchmarks"] + list(segment_of())
    px = yf.download(symbols, period="1mo", interval="1d", auto_adjust=True, progress=False, threads=True)["Close"]
    out = {}
    for s in dict.fromkeys(symbols):
        col = px[s].dropna() if s in px else None
        if col is None or len(col) < 6:
            continue
        last = float(col.iloc[-1])
        out[s] = {"name": MACRO.get(s, s), "close": round(last, 2), "date": col.index[-1].strftime("%Y-%m-%d"),
                  "chg_1d": round(last / float(col.iloc[-2]) - 1, 4), "chg_5d": round(last / float(col.iloc[-6]) - 1, 4),
                  "chg_1m": round(last / float(col.iloc[0]) - 1, 4)}
    return out


def main():
    d = day_dir()
    status = {}
    market = fetch_market()
    write_json(d / "market.json", market)
    known = set(segment_of())
    news = dedupe(fetch_news(status), datetime.now(timezone.utc) - LOOKBACK)
    for it in news:
        it["tickers"] = tag_tickers(it, known)
        it.pop("related", None)
    with open(d / "news.jsonl", "w") as f:
        for it in news:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    write_json(d / "sources.json", status)
    failed = [k for k, v in status.items() if v.startswith("failed")]
    print(f"{today()}: {len(market)} prices, {len(news)} articles, {len(failed)}/{len(status)} sources failed")


if __name__ == "__main__":
    main()
