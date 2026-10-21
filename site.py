from __future__ import annotations

from pathlib import Path

from pipeline_common import latest_day_dir, load_json


def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    latest = latest_day_dir(data_dir)
    digest = ""
    shortlist = {"shortlist": []}
    if latest:
        digest_path = latest / "digest.md"
        if digest_path.exists():
            digest = digest_path.read_text(encoding="utf-8")
            (docs_dir / "digest.md").write_text(digest, encoding="utf-8")
        shortlist = load_json(latest / "shortlist.json", default=shortlist)

    tracking = load_json(data_dir / "tracking.json", default={"picks": []})

    rows = "\n".join(
        f"<li><strong>{row.get('ticker')}</strong> — score {row.get('score')} ({row.get('rationale')})</li>"
        for row in shortlist.get("shortlist", [])
    )
    track_rows = "\n".join(
        f"<li>{row.get('ticker')}: return {row.get('return')} | alpha vs QQQ {row.get('alpha_vs_qqq')}</li>"
        for row in tracking.get("picks", [])
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>gene-research</title>
</head>
<body>
  <h1>gene-research</h1>
  <p>Latest run: {latest.name if latest else 'N/A'}</p>
  <h2>Shortlist</h2>
  <ul>{rows}</ul>
  <h2>Tracking</h2>
  <ul>{track_rows}</ul>
  <h2>Digest preview</h2>
  <pre>{digest[:3000]}</pre>
</body>
</html>
"""

    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {docs_dir / 'index.html'}")


if __name__ == "__main__":
    main()
