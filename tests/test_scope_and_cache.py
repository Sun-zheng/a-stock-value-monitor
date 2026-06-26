import json
from datetime import date, datetime, timezone

import pandas as pd

from src.data_fetcher import trusted_previous_close_cache
from src.data_source_manager import DataSourceManager
from src.strategy_config import strategy_scope_config, validate_strategy


def test_strategy_defaults_to_all_a_share_scope():
    strategy = validate_strategy({})
    scope = strategy_scope_config(strategy)
    assert strategy["recommendation_scope"] == "all_a_share"
    assert scope["label"] == "境内全市场A股"


def test_build_universe_uses_domestic_pool_for_all_market(monkeypatch, tmp_path):
    manager = DataSourceManager(tmp_path)
    expected = pd.DataFrame([{"代码": "600000"}])

    monkeypatch.setattr(
        manager,
        "build_domestic_universe",
        lambda force=False: (expected, {"source": "domestic", "cache_hit": False}),
    )

    frame, meta = manager.build_universe(
        strategy={"recommendation_scope": "all_a_share"}
    )

    assert frame.equals(expected)
    assert meta["scope"] == "境内全市场A股"


def test_trusted_previous_close_cache_rejects_legacy_intraday_source(tmp_path):
    cache = tmp_path / "market_snapshot.csv"
    cache.write_text("代码,当前价格\n600000,10\n", encoding="utf-8")
    cache.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "source": "AkShare/新浪A股行情",
                "market_data_kind": "same_day_intraday",
                "trade_date": "20260623",
                "fetched_at": datetime(2026, 6, 23, 14, 10, tzinfo=timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    trusted, status = trusted_previous_close_cache(cache, date(2026, 6, 23), "UTC")

    assert trusted is False
    assert status["valid_previous_close"] is True
