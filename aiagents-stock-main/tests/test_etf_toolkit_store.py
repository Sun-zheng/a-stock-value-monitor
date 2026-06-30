from __future__ import annotations

from backend.strategies.index_fund_research.etf_toolkit_settings import load_etf_toolkit_settings
from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore


def test_etf_toolkit_store_caches_and_indexes_history(tmp_path) -> None:
    settings = load_etf_toolkit_settings(tmp_path)
    store = ETFToolkitStore(tmp_path)
    result = {
        "success": True,
        "market_snapshot_count": 10,
        "analyzed_count": 5,
        "error_count": 0,
        "alerts": [{"类型": "ETF定投触发"}],
        "report": "ETF策略工具箱报告",
    }

    paths = store.save_result(result, settings)
    cached = store.load_cached_result(settings)
    history = store.list_history()
    loaded = store.load_history_result(paths["history_path"])

    assert cached is not None
    assert cached["cache_hit"] is True
    assert cached["analyzed_count"] == 5
    assert history[0]["alert_count"] == 1
    assert loaded is not None
    assert loaded["report"] == "ETF策略工具箱报告"
