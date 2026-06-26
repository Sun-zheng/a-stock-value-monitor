import json

import pandas as pd

from src.stock_history_store import write_daily_stock_history


def test_write_daily_stock_history_creates_partitioned_files_and_index(tmp_path):
    outputs = write_daily_stock_history(
        tmp_path,
        run_date="2026-06-25",
        analysis_trade_date="20260624",
        frames={
            "all_stocks": pd.DataFrame(
                [{"代码": "600000", "名称": "浦发银行", "PE TTM": 5.2}]
            ),
            "light_candidates": pd.DataFrame(
                [{"代码": "600000", "候选来源": "低估"}]
            ),
            "reviewed_candidates": pd.DataFrame(
                [{"代码": "600000", "综合评分": 72, "一票否决原因": ""}]
            ),
            "passed_candidates": pd.DataFrame(
                [{"代码": "600000", "综合评分": 72}]
            ),
        },
        metadata={"scope": "境内全市场A股"},
    )

    all_stocks_path = tmp_path / "daily_stock_history" / "all_stocks" / "2026-06-25.csv"
    index_path = tmp_path / "daily_stock_history" / "index.json"
    metadata_path = tmp_path / "daily_stock_history" / "metadata" / "2026-06-25.json"

    assert all_stocks_path.exists()
    assert metadata_path.exists()
    assert outputs["all_stocks"] == str(all_stocks_path)

    frame = pd.read_csv(all_stocks_path, dtype={"代码": str, "估值交易日": str})
    assert frame.loc[0, "运行日期"] == "2026-06-25"
    assert frame.loc[0, "估值交易日"] == "20260624"
    assert frame.loc[0, "数据集"] == "全市场轻量快照"
    assert frame.loc[0, "代码"] == "600000"

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["datasets"]["all_stocks"]["2026-06-25"]["rows"] == 1
    assert index["datasets"]["reviewed_candidates"]["2026-06-25"]["analysis_trade_date"] == "20260624"
