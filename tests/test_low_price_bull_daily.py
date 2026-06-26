from pathlib import Path

import pandas as pd

from src.low_price_bull_daily import _fallback_from_value_index, build_low_price_bull_email
from src.stock_history_store import write_daily_stock_history


def test_build_low_price_bull_email_contains_records():
    body = build_low_price_bull_email(
        "2026-06-26",
        {
            "success": True,
            "message": "ok",
            "rows": 1,
            "records": [{"股票代码": "000001", "股票简称": "平安银行", "股价": 9.9, "净利润增长率": 120, "成交额": 1000}],
        },
    )

    assert "低价擒牛工作日筛选报告" in body
    assert "000001" in body
    assert "平安银行" in body


def test_low_price_bull_fallback_uses_value_index(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "当前价格": 9.8,
                "归母净利润同比增长率": 120,
                "营业收入同比增长率": 30,
                "上市板块": "主板",
                "行业": "银行",
            }
        ]
    )
    data_dir = tmp_path / "data"
    write_daily_stock_history(
        data_dir,
        "2026-06-26",
        "2026-06-26",
        {"reviewed_candidates": frame},
    )

    result = _fallback_from_value_index(tmp_path, 3)

    assert result["success"] is True
    assert result["records"][0]["股票代码"] == "000001"
