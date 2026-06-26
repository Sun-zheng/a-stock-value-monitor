from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


class CacheManager:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / name

    def read(self, name: str) -> pd.DataFrame:
        path = self.path(name)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(
            path,
            dtype={
                "代码": str, "ts_code": str, "trade_date": str,
                "估值数据交易日": str, "财报数据报告期": str,
            },
        )

    def write(self, name: str, frame: pd.DataFrame, metadata: dict | None = None) -> Path:
        path = self.path(name)
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
        if metadata is not None:
            metadata_path = path.with_suffix(".meta.json")
            metadata_tmp = metadata_path.with_suffix(".meta.json.tmp")
            metadata_tmp.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            os.replace(metadata_tmp, metadata_path)
        return path

    def is_fresh(self, name: str, max_age: timedelta) -> bool:
        path = self.path(name)
        if not path.exists():
            return False
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - modified <= max_age
