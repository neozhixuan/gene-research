# gene-research

Generalized Python template for a daily market-analysis pipeline.

## Daily flow (20:00 SGT / 12:00 UTC)

1. `python fetch.py` → `data/YYYY-MM-DD/news.jsonl`, `prices.json`
2. `python digest.py` → `digest.md`, worldview handoff files
3. Claude updates `data/YYYY-MM-DD/worldview.json`
4. `python screen.py` → `shortlist.json` (~8 names)
5. Claude picks 2 names and writes `data/YYYY-MM-DD/picks.json`
6. `python agents.py` → Gemini-agent job payload (`agents_jobs.json`)
7. `python track.py` → performance tracking vs `QQQ`/`SMH`
8. `python site.py` → static site output in `docs/`

Monthly:

- `python score.py` → monthly score summary (`data/score/YYYY-MM.json`)

## GitHub Actions

- `.github/workflows/daily-market-analysis.yml` runs the non-Claude steps daily at 20:00 SGT.
- `.github/workflows/deploy-pages.yml` deploys `docs/` to GitHub Pages on push to `main`.

## Notes

This repository intentionally uses template/mock data and explicit handoff points so the heavy-lifting models and data providers can be plugged in later with minimal prompt tokens.
