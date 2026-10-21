"""Stage 2: condense market.json + news.jsonl into digest.md, the only news Claude reads.

Kept to a few thousand tokens: one line per article, grouped by AI-bottleneck
segment, with price moves alongside so headlines can be read against the tape.
"""

import json
import re
from collections import defaultdict

from common import day_dir, today, universe, read_json, MACRO_NAMES

MAX_ITEMS = 110
SUMMARY_CHARS = 140
# Untagged articles are kept only if they touch the market, macro or the AI build-out.
RELEVANT = re.compile(r"\b(stock|market|nasdaq|s&p|dow|fed|federal reserve|rate|yield|treasur|inflation|cpi|jobs|tariff|"
                      r"recession|dollar|oil|crude|bitcoin|crypto|ai|chip|semiconductor|data ?cent|gpu|nuclear|power|grid|"
                      r"energy|electric|cloud|hyperscal|capex|export|china|taiwan)", re.I)


def pct(x):
    return f"{x * 100:+.1f}%" if x is not None else "n/a"


def main():
    d = day_dir()
    market = read_json(d / "market.json", {})
    sources = read_json(d / "sources.json", {})
    news = [json.loads(line) for line in open(d / "news.jsonl")]
    news = [it for it in news if it["tickers"] or RELEVANT.search(f"{it['title']} {it['summary']}")][:MAX_ITEMS]
    segs = universe()["segments"]
    seg_of = {t: s for s, ts in segs.items() for t in ts}

    lines = [f"# Market digest {today()}", ""]
    failed = [k for k, v in sources.items() if v.startswith("failed")]
    lines.append(f"Sources: {len(sources) - len(failed)} ok, {len(failed)} failed" + (f" ({', '.join(failed)})" if failed else ""))

    lines += ["", "## Tape", "", "| Symbol | Close | 1d | 5d | 1m |", "|---|---:|---:|---:|---:|"]
    for sym, name in MACRO_NAMES.items():
        m = market.get(sym)
        if m:
            lines.append(f"| {name} | {m['close']:,} | {pct(m['chg_1d'])} | {pct(m['chg_5d'])} | {pct(m['chg_1m'])} |")

    lines += ["", "## Segments (equal-weight average)", "", "| Segment | 1d | 5d | 1m | Best 5d | Worst 5d |", "|---|---:|---:|---:|---|---|"]
    for seg, ts in segs.items():
        rows = [(t, market[t]) for t in ts if t in market]
        if not rows:
            continue
        avg = lambda k: sum(m[k] for _, m in rows) / len(rows)
        best = max(rows, key=lambda r: r[1]["chg_5d"])
        worst = min(rows, key=lambda r: r[1]["chg_5d"])
        lines.append(f"| {seg} | {pct(avg('chg_1d'))} | {pct(avg('chg_5d'))} | {pct(avg('chg_1m'))} | {best[0]} {pct(best[1]['chg_5d'])} | {worst[0]} {pct(worst[1]['chg_5d'])} |")

    groups = defaultdict(list)
    for it in news:
        key = seg_of.get(it["tickers"][0], "other") if it["tickers"] else "market_macro"
        groups[key].append(it)
    lines += ["", f"## News, last 36h ({len(news)} items)"]
    for seg in ["market_macro", *segs, "other"]:
        if not groups.get(seg):
            continue
        lines += ["", f"### {seg}"]
        for it in groups[seg]:
            t = f" [{','.join(it['tickers'])}]" if it["tickers"] else ""
            s = it["summary"][:SUMMARY_CHARS].rsplit(" ", 1)[0] + "…" if len(it["summary"]) > SUMMARY_CHARS else it["summary"]
            lines.append(f"- ({it['id']}) {it['title']}{t}" + (f" — {s}" if s and s != it["title"] else ""))

    (d / "digest.md").write_text("\n".join(lines) + "\n")
    print(f"digest.md: {len(news)} items, ~{len(' '.join(lines).split()) * 4 // 3} tokens")


if __name__ == "__main__":
    main()
