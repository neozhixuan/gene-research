---
name: tonight-brief
description: Write tonight's pre-open brief for the gene-research site — whether the watchlist's Buy/Overweight ratings still hold at the next US open, given news since they were made. Use in the daily run after `run.py post`, or when asked "should I still buy the recommended stocks tonight?".
---

# Tonight's brief

The reader is the site's owner, deciding at about 21:30 Singapore time whether to act on the site's buy-side ratings. Ratings can be days old; your job is to say what has changed since, plainly, and how much the ratings can be trusted. It is a read on the site's own ratings, not personal financial advice: give facts and a lean, never an order to trade.

Budget: about 6 tool calls. Read one file, at most 3 web searches, at most 1 page fetch, one Write, one check. Don't read pipeline code, agent outputs or news files.

## 1. Gather

```bash
.venv/bin/python pipeline/brief.py prep
```

Read `data/<date>/brief_inputs.md`. It has every buy-side name with the price the agents saw, the last close, next earnings date (if Yahoo answered), today's worldview risks and the track record.

## 2. Check what moved since the last close (web search, extended mode)

Prices in the inputs stop at the last US close. Search for what came after it, in one turn, with `mode: "extended"` (standard mode has returned stale results here).

Your training data is older than today, so never guess the year: take today's date from the inputs' "Prepared" line and write it out in every query, e.g. `stock futures November 2 2026`. Ignore any result dated before the last close.

1. `stock market futures <Month D YYYY>`: index futures direction and size, and why.
2. `after hours earnings <Month D YYYY> AI chips data center`: results and news since the last close that move AI suppliers.
3. Only if needed: `<TICKER> stock <Month D YYYY>` for the candidate with the biggest open question (an earnings date shown as "unknown" or today, or a large move).

If search isn't available or still returns nothing dated after the last close, write the brief from the inputs alone and say in `bottom_line` that overnight news wasn't checked.

## 3. Write `data/<date>/brief.json` once

```json
{
  "date": "YYYY-MM-DD (today's run date)",
  "session": "copy the 'Next session' line, e.g. US open Fri 30 Oct, 21:30 SGT",
  "written_at": "ISO time with +08:00",
  "lean": "wait | small | stands",
  "bottom_line": "2-3 sentences: do the ratings still hold tonight, and the one reason that matters most",
  "what_changed": ["2-5 lines: news since the ratings, with numbers; say which worldview risk or thesis it touches"],
  "names": [
    { "ticker": "XXX", "segment": "segment key from the inputs", "rating": "Overweight", "rated_on": "YYYY-MM-DD",
      "rated_price": 123.45, "last_price": 130.1, "since_rated": 0.054,
      "catalyst": "Earnings tonight before the open | Earnings 9 Nov | empty string",
      "take": "One line: what this means for buying it tonight" }
  ],
  "trust": "1-2 sentences from the track record: how many ratings are graded, and whether the picks beat the no-AI baselines",
  "if_buying": ["2-4 practical lines: sizing per the rating, names to wait on, limit orders on a volatile open"],
  "sources": [{ "title": "...", "url": "https://..." }]
}
```

Rules:
- One entry in `names` per buy-side name in the inputs, in the same order. Copy the numbers from the inputs (`since_rated` as a fraction, `null` where the inputs show –); put moves after the last close in `take` or `what_changed`, from your searches.
- `lean`: **wait** when news since the ratings hits the worldview's own named risks or bearish theses, index futures are down about 1% or more, or most names have run up or face a catalyst before or at the open. **stands** only when nothing material happened. Otherwise **small**.
- Flag a name whose segment the worldview now rates underweight or neutral while the stock is rated Overweight/Buy: the two disagree, so say which you'd trust tonight.
- Flag a name that has already risen a lot since it was rated (the agents saw a lower price), and one reporting earnings at or before the open (wait for the reaction).
- No candidates: `names: []`, `lean: "wait"`, and say in `bottom_line` that nothing is rated Buy or Overweight.
- Plain words, short lines, no hype. Every claim from a search needs its source in `sources`.

## 4. Check

```bash
.venv/bin/python pipeline/brief.py check
```

Fix and rerun if it prints errors. `site.py` shows the brief on the landing page under the watchlist and archives it on the day page; `usage.py` records its token share.
