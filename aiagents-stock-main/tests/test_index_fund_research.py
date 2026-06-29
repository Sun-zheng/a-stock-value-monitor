from __future__ import annotations

import pandas as pd

from backend.strategies.index_fund_research.index_fund_analyzer import (
    FundResearchConfig,
    IndexFundResearchAnalyzer,
    classify_fund,
    is_equity_index_fund,
)


def _history(high: float, current: float, low: float, periods: int = 260) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=periods, freq="B")
    closes = []
    for index in range(periods):
        if index < 40:
            value = high * (0.9 + index / 400)
        elif index < 150:
            value = high - (high - low) * ((index - 40) / 110)
        else:
            value = low + (current - low) * ((index - 150) / max(1, periods - 151))
        closes.append(value)
    closes[-1] = current
    frame = pd.DataFrame(
        {
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": closes,
            "收盘": closes,
            "最高": [price * 1.01 for price in closes],
            "最低": [price * 0.99 for price in closes],
            "成交额": [80_000_000] * periods,
            "涨跌幅": [0] * periods,
        }
    )
    frame.loc[35, "最高"] = high
    frame.loc[150, "最低"] = low
    return frame


def test_classify_and_filter_equity_index_fund_names() -> None:
    assert classify_fund("半导体ETF") == "半导体/芯片"
    assert classify_fund("人工智能ETF") == "人工智能/数字经济"
    assert is_equity_index_fund("半导体ETF")
    assert not is_equity_index_fund("国债ETF")
    assert not is_equity_index_fund("现金货币ETF")


def test_fetch_universe_filters_non_equity_and_low_turnover() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "512760", "名称": "半导体ETF", "最新价": 0.82, "成交额": 50_000_000},
            {"代码": "511010", "名称": "国债ETF", "最新价": 115.0, "成交额": 200_000_000},
            {"代码": "159915", "名称": "创业板ETF", "最新价": 1.5, "成交额": 5_000_000},
        ]
    )
    analyzer = IndexFundResearchAnalyzer(spot_fetcher=lambda: spot)
    universe = analyzer.fetch_universe(FundResearchConfig(min_turnover=20_000_000))
    assert universe["代码"].tolist() == ["512760"]
    assert universe["分类"].tolist() == ["半导体/芯片"]


def test_analyze_selects_drawdown_candidates_and_builds_report() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "512760", "名称": "半导体ETF", "最新价": 0.8, "成交额": 180_000_000},
            {"代码": "159995", "名称": "芯片ETF", "最新价": 0.9, "成交额": 160_000_000},
            {"代码": "516160", "名称": "人工智能ETF", "最新价": 0.7, "成交额": 150_000_000},
        ]
    )
    histories = {
        "512760": _history(1.7, 0.86, 0.68),
        "159995": _history(1.6, 0.82, 0.63),
        "516160": _history(1.4, 1.15, 0.95),
    }
    analyzer = IndexFundResearchAnalyzer(
        spot_fetcher=lambda: spot,
        history_fetcher=lambda code, start_date: histories[code],
    )

    result = analyzer.analyze(FundResearchConfig(top_n=2, history_candidates=3))

    assert result["success"] is True
    assert result["universe_count"] == 3
    assert result["analyzed_count"] == 3
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["高点回撤"] < -40
    assert "预测最低点" in result["report"]
    assert "回涨确认点" in result["report"]
    assert "预计修复周期" in result["report"]
    assert "多分析师规则复核" in result["report"]
