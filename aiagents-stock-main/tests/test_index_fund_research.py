from __future__ import annotations

import pandas as pd

from backend.strategies.index_fund_research.index_fund_analyzer import (
    FundResearchConfig,
    IndexFundResearchAnalyzer,
    classify_fund,
    is_equity_index_fund,
)
from backend.strategies.index_fund_research.major_market_etf_analyzer import (
    MajorMarketETFAnalyzer,
    MajorMarketETFConfig,
)
from backend.strategies.index_fund_research.etf_toolkit_analyzer import (
    ETFToolkitAnalyzer,
    ETFToolkitConfig,
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


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"名称": "上证指数", "最新价": 3000, "涨跌幅": 0.3, "成交额": 300_000_000_000},
            {"名称": "沪深300", "最新价": 3500, "涨跌幅": -0.2, "成交额": 200_000_000_000},
        ]
    )


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


def test_fetch_universe_diversifies_categories_before_turnover_cutoff() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "512761", "名称": "半导体ETF一号", "最新价": 0.8, "成交额": 190_000_000},
            {"代码": "512762", "名称": "半导体ETF二号", "最新价": 0.8, "成交额": 180_000_000},
            {"代码": "512763", "名称": "半导体ETF三号", "最新价": 0.8, "成交额": 170_000_000},
            {"代码": "516160", "名称": "人工智能ETF", "最新价": 0.8, "成交额": 90_000_000},
            {"代码": "159992", "名称": "创新药ETF", "最新价": 0.8, "成交额": 80_000_000},
        ]
    )
    analyzer = IndexFundResearchAnalyzer(spot_fetcher=lambda: spot)
    universe = analyzer.fetch_universe(FundResearchConfig(history_candidates=3, min_turnover=1))

    assert set(universe["分类"]) == {"半导体/芯片", "人工智能/数字经济", "创新药/医疗"}


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
        market_fetcher=_market,
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
    assert "研究流程" in result["report"]
    assert "大盘环境" in result["report"]
    assert "长牛逻辑" in result["report"]
    assert "偏离原因" in result["report"]
    assert "半年上涨50%判断" in result["report"]
    assert "风险边界" in result["report"]
    assert result["market_snapshot_count"] == 3
    assert result["market_context"]["indices"]


def test_analyze_diversifies_categories_before_filling_by_score() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "512761", "名称": "半导体ETF一号", "最新价": 0.8, "成交额": 190_000_000},
            {"代码": "512762", "名称": "半导体ETF二号", "最新价": 0.8, "成交额": 180_000_000},
            {"代码": "512763", "名称": "半导体ETF三号", "最新价": 0.8, "成交额": 170_000_000},
            {"代码": "516160", "名称": "人工智能ETF", "最新价": 0.8, "成交额": 100_000_000},
            {"代码": "159992", "名称": "创新药ETF", "最新价": 0.8, "成交额": 90_000_000},
        ]
    )
    histories = {
        "512761": _history(1.7, 0.80, 0.62),
        "512762": _history(1.7, 0.81, 0.63),
        "512763": _history(1.7, 0.82, 0.64),
        "516160": _history(1.6, 0.80, 0.62),
        "159992": _history(1.5, 0.75, 0.58),
    }
    analyzer = IndexFundResearchAnalyzer(
        spot_fetcher=lambda: spot,
        history_fetcher=lambda code, start_date: histories[code],
        market_fetcher=_market,
    )

    result = analyzer.analyze(FundResearchConfig(top_n=3, history_candidates=5))
    categories = {item["分类"] for item in result["candidates"]}

    assert len(result["candidates"]) == 3
    assert {"半导体/芯片", "人工智能/数字经济", "创新药/医疗"}.issubset(categories)
    assert result["workflow"][0].startswith("数据抓取")
    assert "半年上涨50%概率" in result["candidates"][0]


def test_major_market_etf_analyzer_filters_broad_market_etfs() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "510300", "名称": "沪深300ETF", "最新价": 4.0, "涨跌幅": 0.5, "成交额": 300_000_000},
            {"代码": "510050", "名称": "上证50ETF", "最新价": 3.0, "涨跌幅": 0.2, "成交额": 200_000_000},
            {"代码": "512760", "名称": "半导体ETF", "最新价": 0.8, "涨跌幅": 1.0, "成交额": 500_000_000},
        ]
    )
    histories = {
        "510300": _history(5.0, 4.0, 3.4),
        "510050": _history(4.0, 3.0, 2.6),
    }
    analyzer = MajorMarketETFAnalyzer(
        spot_fetcher=lambda: spot,
        history_fetcher=lambda code, start_date: histories[code],
        market_fetcher=_market,
    )

    result = analyzer.analyze_major_market(MajorMarketETFConfig(top_n=2, history_candidates=3, min_turnover=1))

    assert result["success"] is True
    assert result["universe_count"] == 2
    assert {item["代码"] for item in result["candidates"]} == {"510300", "510050"}
    assert "主要市场大盘ETF指数分析报告" in result["report"]
    assert "大盘配置评分" in result["candidates"][0]


def test_etf_toolkit_builds_screener_rotation_and_portfolios() -> None:
    spot = pd.DataFrame(
        [
            {"代码": "510300", "名称": "沪深300ETF", "最新价": 4.0, "涨跌幅": 0.5, "成交额": 300_000_000, "IOPV实时估值": 4.01, "基金折价率": 0.25, "总市值": 10_000_000_000, "量比": 1.2},
            {"代码": "512760", "名称": "半导体ETF", "最新价": 0.8, "涨跌幅": 1.0, "成交额": 500_000_000, "IOPV实时估值": 0.79, "基金折价率": -1.25, "总市值": 8_000_000_000, "量比": 2.4},
            {"代码": "159992", "名称": "创新药ETF", "最新价": 0.7, "涨跌幅": -0.5, "成交额": 120_000_000, "IOPV实时估值": 0.71, "基金折价率": 1.1, "总市值": 2_000_000_000, "量比": 0.9},
            {"代码": "515790", "名称": "光伏ETF", "最新价": 0.9, "涨跌幅": 0.2, "成交额": 90_000_000, "IOPV实时估值": 0.88, "基金折价率": -2.2, "总市值": 1_000_000_000, "量比": 2.1},
        ]
    )
    histories = {
        "510300": _history(5.0, 4.0, 3.4),
        "512760": _history(1.7, 0.86, 0.68),
        "159992": _history(1.5, 0.75, 0.58),
        "515790": _history(1.8, 0.9, 0.72),
    }
    fund_daily = pd.DataFrame(
        [
            {"基金代码": "510300", "2026-06-29-单位净值": 4.01, "市价": 4.0, "折价率": 0.25},
            {"基金代码": "512760", "2026-06-29-单位净值": 0.79, "市价": 0.8, "折价率": -1.25},
        ]
    )
    index_info = pd.DataFrame(
        [
            {"基金代码": "510300", "手续费": "0.12%", "跟踪标的": "沪深300", "跟踪方式": "完全复制"},
            {"基金代码": "512760", "手续费": "0.15%", "跟踪标的": "中证半导体", "跟踪方式": "完全复制"},
        ]
    )

    def holdings(code: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"股票代码": "600519", "股票名称": "贵州茅台", "占净值比例": 5.0, "季度": "2025年4季度"},
                {"股票代码": "300750", "股票名称": "宁德时代", "占净值比例": 4.0, "季度": "2025年4季度"},
            ]
        )

    analyzer = ETFToolkitAnalyzer(
        spot_fetcher=lambda: spot,
        history_fetcher=lambda code, start_date: histories[code],
        market_fetcher=_market,
        fund_daily_fetcher=lambda: fund_daily,
        holdings_fetcher=holdings,
        index_info_fetcher=lambda: index_info,
    )

    result = analyzer.analyze_toolkit(ETFToolkitConfig(max_history=4, min_turnover=1, monthly_budget=3000, holding_top_n=3))

    assert result["success"] is True
    assert result["market_snapshot_count"] == 4
    assert result["analyzed_count"] == 4
    assert result["screener"]
    assert result["rotation"]
    assert set(result["portfolios"]) == {"稳健", "平衡", "进取"}
    assert result["portfolios"]["平衡"]["positions"]
    assert result["dca_plans"][0]["建议月定投金额"] > 0
    assert result["premium_discount"][0]["状态"]
    assert result["holdings"]["ETF持仓明细"]
    assert result["holdings"]["重复暴露"]
    assert result["risk_radar"]
    assert result["comparison"][0]["跟踪指数"] is not None
    assert result["periodic_report"]["总览"]
    assert result["opportunity_pool"]["低估回撤池"]
    assert "ETF策略工具箱报告" in result["report"]
    assert "定投计划" in result["report"]
    assert "溢价/折价监控" in result["report"]
    assert "持仓穿透" in result["report"]
