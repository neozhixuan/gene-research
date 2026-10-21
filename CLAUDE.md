# Gene Research daily run

You are the daily research run. Code does the data work; you do only the thinking steps below. **The owner has a small weekly token budget, so keep this run lean:**

- Do not read the pipeline scripts, `news.jsonl`, `fundamentals.json` or agent outputs. Read only the files named in the steps.
- Do not explore the repo, run extra checks or summarise your work at length. If a step fails, fix the cause and rerun only that step.
- Write each output file once, with Write. No drafts.

All commands run from the repo root. Dates are Singapore time (`RUN_DATE=YYYY-MM-DD` overrides).

## 1. Set up and pull data

```bash
bash scripts/setup.sh && .venv/bin/python pipeline/run.py pre
```

This prints which files to read. If `GOOGLE_API_KEY` is unset, stop and report it.

## 2. Update the worldview

Read `data/<date>/digest.md` and the previous worldview it names (skip that on the first run). Write `data/worldview/<date>.json`:

```json
{
  "date": "YYYY-MM-DD",
  "previous": "YYYY-MM-DD or null",
  "headline": "One sentence: the single most important thing about the market today",
  "regime": "2-4 sentences on the current market regime for AI-bottleneck stocks, citing the tape",
  "theses": [
    {
      "id": "kebab-case, stable across days",
      "title": "Short claim, e.g. 'Power, not chips, is the binding constraint'",
      "stance": "bullish | bearish | neutral",
      "confidence": 0-100,
      "segments": ["segment keys from universe.json"],
      "evidence": ["one line each, cite digest item ids like (287b1ab1f9c1)"],
      "change": "new | stronger | weaker | unchanged | retired",
      "change_note": "What today's news changed, or why nothing did"
    }
  ],
  "segments": { "<every segment key in universe.json>": { "stance": "overweight | neutral | underweight", "note": "one line" } },
  "risks": ["3-5 lines"],
  "watch": ["3-5 concrete things to watch next session"]
}
```

Rules:
- Carry every previous thesis forward by `id`. Change confidence only when today's evidence justifies it, and say why in `change_note`. Mark `retired` instead of deleting.
- Keep 4-8 live theses. Add a new one only with real evidence.
- House style: Situational Awareness for direction (AI's bottlenecks: compute, power, grid, cooling, data centres and their suppliers), Buffett for selection (real cash flow, low debt, a price that limits the downside). Say plainly when the evidence argues against the AI trade.
- On Mondays, before reading the previous worldview, sketch the theses from the digest alone, then reconcile. Note any thesis that only survives because it was carried forward.

## 3. Pick 1-2 stocks to watch

Read `data/<date>/shortlist.md`. Choose from it only. Prefer names in segments the worldview rates overweight and segments with few past picks; avoid two picks from one segment. Write `data/<date>/picks.json`:

```json
{
  "date": "YYYY-MM-DD",
  "picks": [
    { "ticker": "XXX", "segment": "segment key", "why": "2 sentences tying the numbers to a thesis",
      "risk": "1 sentence: what would make this wrong", "thesis_ids": ["..."] }
  ],
  "passed_on": [ { "ticker": "YYY", "reason": "one line" } ]
}
```

Order matters: TradingAgents runs the first pick first, and the second only if Gemini quota remains.

## 4. Verify, track, publish

```bash
.venv/bin/python pipeline/run.py post --max 2
```

Run it in the background: TradingAgents takes 5-8 minutes per stock on the Gemini free tier. Wait for the completion notice instead of polling. `validate.py` runs first; if it prints errors, fix the two files and rerun.

Then commit and push:

```bash
git add -A data site && git commit -m "Daily run <date>: <tickers> (<final ratings>)" && git push origin main
```

Vercel deploys the `site/` folder on push.

## 5. Monthly review (first run of each month only)

Read `data/tracking.json` (the `summary` and `scorecard` keys only) and write `data/reviews/<YYYY-MM>.md`, at most 200 words: what the ratings got right and wrong, any pattern by segment, and one change to try (to `universe.json`, the screen weights in `pipeline/screen.py`, or these instructions). Do not make the change yourself; the owner decides.

## Finish

Reply with 3 lines: the headline, the picks with their final ratings, and anything that failed.
