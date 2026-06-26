from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.stock_index_store import update_stock_history_index


DATASETS = {
    "all_stocks": "全市场轻量快照",
    "light_candidates": "估值轻筛候选",
    "reviewed_candidates": "深度检查候选",
    "passed_candidates": "通过一票否决候选",
}


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        frame.to_csv(temporary_path, index=False, encoding="utf-8-sig")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _with_run_columns(
    frame: pd.DataFrame,
    run_date: str,
    analysis_trade_date: str,
    dataset: str,
) -> pd.DataFrame:
    data = frame.copy()
    data.insert(0, "数据集", dataset)
    data.insert(0, "估值交易日", analysis_trade_date)
    data.insert(0, "运行日期", run_date)
    return data


def _read_index(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"datasets": {}}


def write_daily_stock_history(
    data_dir: Path,
    run_date: str,
    analysis_trade_date: str,
    frames: dict[str, pd.DataFrame],
    metadata: dict | None = None,
) -> dict:
    history_dir = data_dir / "daily_stock_history"
    outputs: dict[str, str] = {}
    indexed_frames: dict[str, pd.DataFrame] = {}
    index = _read_index(history_dir / "index.json")
    index.setdefault("datasets", {})
    for dataset, frame in frames.items():
        if dataset not in DATASETS:
            continue
        normalized = _with_run_columns(
            frame,
            run_date=run_date,
            analysis_trade_date=analysis_trade_date,
            dataset=DATASETS[dataset],
        )
        path = history_dir / dataset / f"{run_date}.csv"
        _write_csv(path, normalized)
        outputs[dataset] = str(path)
        index["datasets"].setdefault(dataset, {})[run_date] = {
            "path": str(path),
            "rows": int(len(normalized)),
            "analysis_trade_date": analysis_trade_date,
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        indexed_frames[dataset] = normalized
    if metadata is not None:
        meta_path = history_dir / "metadata" / f"{run_date}.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        outputs["metadata"] = str(meta_path)
    index_path = history_dir / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    outputs["index"] = str(index_path)
    outputs.update(update_stock_history_index(data_dir, run_date, indexed_frames))
    return outputs
