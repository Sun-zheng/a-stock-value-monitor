from pathlib import Path

import pandas as pd

from tools.rebuild_stock_history_index import rebuild
from src.stock_index_store import query_stock_history


def test_rebuild_stock_history_index_from_csv(tmp_path: Path):
    csv_path = tmp_path / "daily_stock_history" / "all_stocks" / "2026-06-26.csv"
    csv_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [{"运行日期": "2026-06-26", "估值交易日": "2026-06-26", "代码": "000001", "名称": "平安银行", "ROE": 11.2}]
    ).to_csv(csv_path, index=False, encoding="utf-8-sig")

    result = rebuild(tmp_path)
    frame = query_stock_history(tmp_path, "all_stocks", run_date="2026-06-26", code="000001")

    assert result["dates"][0]["date"] == "2026-06-26"
    assert frame.iloc[0]["ROE"] == 11.2
