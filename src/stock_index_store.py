from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


INDEX_DB_NAME = "stock_history_index.sqlite3"
PARQUET_DIR_NAME = "parquet"


def _sqlite_table_name(dataset: str) -> str:
    return "daily_" + "".join(ch if ch.isalnum() else "_" for ch in dataset.lower())


def _normalize_for_sqlite(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in normalized.columns:
        if normalized[column].dtype == "object":
            normalized[column] = normalized[column].astype(str).where(normalized[column].notna(), None)
    return normalized


def _replace_partition(conn: sqlite3.Connection, table: str, frame: pd.DataFrame, run_date: str) -> None:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if table_exists:
        conn.execute(f'DELETE FROM "{table}" WHERE "运行日期" = ?', (run_date,))
    frame.to_sql(table, conn, if_exists="append", index=False)
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table}_date_code" ON "{table}" ("运行日期", "代码")'
    )
    if "名称" in frame.columns:
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_name" ON "{table}" ("名称")'
        )
    if "行业" in frame.columns:
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS "idx_{table}_industry" ON "{table}" ("行业")'
        )


def _write_parquet_if_available(history_dir: Path, dataset: str, run_date: str, frame: pd.DataFrame) -> Path | None:
    path = history_dir / PARQUET_DIR_NAME / dataset / f"{run_date}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_parquet(path, index=False)
    except (ImportError, ValueError, ModuleNotFoundError):
        path.unlink(missing_ok=True)
        return None
    return path


def update_stock_history_index(
    data_dir: Path,
    run_date: str,
    frames: dict[str, pd.DataFrame],
) -> dict[str, str]:
    history_dir = data_dir / "daily_stock_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    db_path = history_dir / INDEX_DB_NAME
    outputs: dict[str, str] = {"sqlite": str(db_path)}

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        for dataset, frame in frames.items():
            if frame.empty:
                continue
            table = _sqlite_table_name(dataset)
            normalized = _normalize_for_sqlite(frame)
            _replace_partition(conn, table, normalized, run_date)
            parquet_path = _write_parquet_if_available(history_dir, dataset, run_date, normalized)
            if parquet_path:
                outputs[f"{dataset}_parquet"] = str(parquet_path)
        conn.commit()

    return outputs


def query_stock_history(
    data_dir: Path,
    dataset: str,
    run_date: str | None = None,
    code: str | None = None,
    limit: int = 1000,
) -> pd.DataFrame:
    db_path = data_dir / "daily_stock_history" / INDEX_DB_NAME
    if not db_path.exists():
        return pd.DataFrame()
    table = _sqlite_table_name(dataset)
    clauses: list[str] = []
    params: list[str | int] = []
    if run_date:
        clauses.append('"运行日期" = ?')
        params.append(run_date)
    if code:
        clauses.append('"代码" = ?')
        params.append(code)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f'SELECT * FROM "{table}"{where_sql} LIMIT ?'
    params.append(limit)
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql_query(sql, conn, params=params)
        except Exception:
            return pd.DataFrame()
