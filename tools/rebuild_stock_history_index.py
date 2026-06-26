from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stock_history_store import DATASETS  # noqa: E402
from src.stock_index_store import update_stock_history_index  # noqa: E402


def _discover_dates(history_dir: Path) -> list[str]:
    dates: set[str] = set()
    for dataset in DATASETS:
        dataset_dir = history_dir / dataset
        if not dataset_dir.exists():
            continue
        dates.update(path.stem for path in dataset_dir.glob("*.csv"))
    return sorted(dates)


def rebuild(data_dir: Path, dates: list[str] | None = None) -> dict:
    history_dir = data_dir / "daily_stock_history"
    selected_dates = dates or _discover_dates(history_dir)
    outputs: dict[str, object] = {"dates": [], "sqlite": str(history_dir / "stock_history_index.sqlite3")}

    for run_date in selected_dates:
        frames: dict[str, pd.DataFrame] = {}
        for dataset in DATASETS:
            path = history_dir / dataset / f"{run_date}.csv"
            if path.exists():
                frames[dataset] = pd.read_csv(path, dtype={"代码": str})
        if frames:
            update_stock_history_index(data_dir, run_date, frames)
            outputs["dates"].append({"date": run_date, "datasets": sorted(frames)})
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild SQLite/Parquet indexes from daily stock CSV files.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--date", action="append", help="Run date to rebuild. Can be passed multiple times.")
    args = parser.parse_args()

    result = rebuild(Path(args.data_dir), args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
