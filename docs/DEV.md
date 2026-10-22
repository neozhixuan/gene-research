# Gene Research — Developer Reference

One page. For the daily operator, read `CLAUDE.md` instead.

## Structure

```
pipeline/
  constants/market.py   # MACRO_NAMES, ACTIONS — shared across fetch/digest/site
  utils/common.py       # paths (ROOT, DATA, SITE), read_json/write_json, today(), day_dir(), universe()
  utils/text.py         # clean_report() — repairs Gemini output for display
  utils/scoring.py      # correct(), rank() — pure functions used by track and screen
  tests/                # pytest suite for all pure-logic modules
  common.py             # re-export shim; stages import from utils.* and constants.* directly
  watchlist.py          # watchlist state machine (no direct I/O; imported by screen and agents)
  run.py                # orchestrator: chains pre/post stages via subprocess
  fetch.py … site.py    # stages 1–7 (see below)
```

## Pipeline files

Each stage is a standalone script. `run.py pre` chains stages 1–3; `run.py post` chains 4–7.

### Stage 1: `fetch.py`
Reads: `universe.json`.
Writes: `data/<date>/market.json`, `data/<date>/news.jsonl`, `data/<date>/sources.json`.
Pulls 1-month price history for the full universe via yfinance and the last 36 h of headlines from Yahoo Finance RSS + four extra feeds. Deduplicates by title hash. Tags each article with the universe tickers it mentions.

### Stage 2: `digest.py`
Reads: `data/<date>/market.json`, `data/<date>/news.jsonl`, `data/<date>/sources.json`.
Writes: `data/<date>/digest.md`.
Condenses the raw market + news data into a few-thousand-token markdown file: a tape table, segment averages, and one-line news items grouped by segment. This is the only file Claude reads for the worldview.

### Stage 3: `screen.py`
Reads: `universe.json`, `data/watchlist.json`.
Writes: `data/<date>/fundamentals.json`, `data/<date>/shortlist.json`, `data/<date>/shortlist.md`.
Fetches fundamentals for every universe ticker in parallel (8 threads), runs them through a quality gate (positive FCF, or solid margins + low debt), ranks survivors on a weighted composite of seven factors, and caps at 8 names with at most 3 per segment. Watchlist and recently-dropped names are excluded — they are re-checked via the watchlist instead.

**To change screen weights or factors:** edit `FACTORS` in `screen.py`. Each key maps to `(weight, higher_is_better)`.

### Stage 4: `validate.py`
Reads: `data/worldview/<date>.json`, `data/<date>/shortlist.json`, `data/<date>/picks.json`.
Writes: nothing (exits 1 on error).
Checks the two files Claude writes before anything downstream reads them. Enforces schema, allowed values, and that every pick is on today's shortlist.

### Stage 5: `agents.py`
Reads: `data/<date>/picks.json`, `data/<date>/market.json`, `data/watchlist.json`, `data/<date>/runs.json` (if present, so a re-run is idempotent).
Writes: `data/<date>/agents/<TICKER>.json` (one per run), `data/<date>/runs.json`, `data/watchlist.json`, `data/picks.csv`.
Runs TradingAgents on Gemini for each ticker in the day's run list (new pick 1 → watchlist re-check → new pick 2). Handles quota exhaustion and overload retries. Upserts the ledger `picks.csv` and updates the watchlist.

### Stage 6: `track.py`
Reads: `data/picks.csv`.
Writes: `data/tracking.json`.
Marks every past pick to market prices, computes return vs QQQ and SMH, and grades ratings older than 28 days. `GRADE_AFTER_DAYS` and `HOLD_BAND` are the two tunable constants.

### Stage 7: `site.py`
Reads: `data/worldview/*.json`, `data/<date>/picks.json`, `data/<date>/runs.json`, `data/<date>/agents/*.json`, `data/<date>/shortlist.json`, `data/<date>/market.json`, `data/watchlist.json`, `data/tracking.json`, `data/usage.csv`, `data/reviews/*.md`.
Writes: `site/index.html`, `site/days/<date>.html` for every worldview date, `site/assets/site.css`.
Pure renderer — no network, no side effects. Vercel serves the `site/` folder as-is.

**To add or change site sections:** edit the `landing_page()` function and the corresponding `*_html()` helper. The CSS lives in the `CSS` constant at the bottom of the file.

### `watchlist.py` — watchlist state machine (no direct I/O)
Imported by `screen.py` and `agents.py`. Owns the drop logic: two consecutive negative ratings, or three Holds in a row, or the list is over `MAX_ACTIVE`. `RECHECK_AFTER_DAYS`, `MAX_ACTIVE`, and `COOLDOWN_DAYS` are the tunable constants.

### `usage.py`
Reads: stdin (JSON usage object from `get_session`), `data/<date>/agents/*.json`.
Writes: `data/<date>/usage.json`, `data/usage.csv`.
Run manually after `run.py post`: `echo '<usage json>' | .venv/bin/python pipeline/usage.py`.

## Data files

| Path | Written by | Read by |
|---|---|---|
| `universe.json` | hand-edited | fetch, screen, digest, validate, site |
| `data/<date>/market.json` | fetch | digest, agents, site |
| `data/<date>/news.jsonl` | fetch | digest |
| `data/<date>/sources.json` | fetch | digest |
| `data/<date>/digest.md` | digest | Claude (manual) |
| `data/<date>/fundamentals.json` | screen | (archive only) |
| `data/<date>/shortlist.json` | screen | validate, site |
| `data/<date>/shortlist.md` | screen | Claude (manual) |
| `data/worldview/<date>.json` | Claude (manual) | validate, track, site |
| `data/<date>/picks.json` | Claude (manual) | validate, agents, site |
| `data/<date>/runs.json` | agents | agents (idempotency), site |
| `data/<date>/agents/<T>.json` | agents | site, usage |
| `data/watchlist.json` | agents | screen, site |
| `data/picks.csv` | agents | track |
| `data/tracking.json` | track | site |
| `data/usage.csv` | usage | site |
| `data/<date>/usage.json` | usage | (archive only) |
| `data/reviews/<YYYY-MM>.md` | Claude (manual, monthly) | site |
| `site/` | site | Vercel |

## Daily flow

```
pre:   fetch → digest → screen
       Claude reads digest.md + shortlist.md, writes worldview/<date>.json + <date>/picks.json
post:  validate → agents → track → site
       usage.py (manual) → git push
```

## Where to change common things

| What | Where |
|---|---|
| Universe tickers or segments | `universe.json` |
| Screen factors and weights | `FACTORS` dict in `screen.py` |
| Shortlist size or per-segment cap | `SHORTLIST`, `PER_SEGMENT` in `screen.py` |
| Watchlist drop rules | `RECHECK_AFTER_DAYS`, `MAX_ACTIVE`, `COOLDOWN_DAYS` in `watchlist.py` |
| Rating grading window | `GRADE_AFTER_DAYS`, `HOLD_BAND` in `track.py` |
| Site sections or layout | `landing_page()` and `*_html()` helpers in `site.py` |
| Site styles | `CSS` constant at the bottom of `site.py` |
| News lookback window | `LOOKBACK` in `fetch.py` |
| Extra RSS feeds | `EXTRA_FEEDS` in `fetch.py` |
| Gemini model overrides | `TRADINGAGENTS_*` env vars read by `agents.py` |
