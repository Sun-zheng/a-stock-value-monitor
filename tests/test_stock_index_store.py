from pathlib import Path

import pandas as pd

from src.stock_history_store import write_daily_stock_history
from src.stock_index_store import query_stock_history


def test_daily_history_updates_sqlite_index(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {"代码": "000001", "名称": "平安银行", "行业": "银行", "综合评分": 72.5},
            {"代码": "600000", "名称": "浦发银行", "行业": "银行", "综合评分": 70.0},
        ]
    )

    outputs = write_daily_stock_history(
        tmp_path,
        run_date="2026-06-26",
        analysis_trade_date="2026-06-26",
        frames={"all_stocks": frame},
    )

    assert "sqlite" in outputs
    assert Path(outputs["sqlite"]).exists()

    result = query_stock_history(
        tmp_path,
        dataset="all_stocks",
        run_date="2026-06-26",
        code="000001",
    )

    assert len(result) == 1
    assert result.iloc[0]["名称"] == "平安银行"
    assert result.iloc[0]["运行日期"] == "2026-06-26"
