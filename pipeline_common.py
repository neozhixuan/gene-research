from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def parse_date_arg() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date in YYYY-MM-DD")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Base data directory")
    return parser.parse_args()


def ensure_day_dir(run_date: str, data_dir: str | Path) -> Path:
    target = Path(data_dir) / run_date
    target.mkdir(parents=True, exist_ok=True)
    return target


def day_dirs(data_dir: str | Path) -> list[Path]:
    base = Path(data_dir)
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir() and _is_date_dir(p.name)])


def previous_day_dir(run_date: str, data_dir: str | Path) -> Path | None:
    dirs = [p for p in day_dirs(data_dir) if p.name < run_date]
    return dirs[-1] if dirs else None


def latest_day_dir(data_dir: str | Path) -> Path | None:
    dirs = day_dirs(data_dir)
    return dirs[-1] if dirs else None


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def dump_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _is_date_dir(name: str) -> bool:
    try:
        datetime.strptime(name, "%Y-%m-%d")
        return True
    except ValueError:
        return False
