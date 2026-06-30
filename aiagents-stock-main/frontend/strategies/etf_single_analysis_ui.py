from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(
    os.getenv("A_STOCK_VALUE_MONITOR_ROOT", Path(__file__).resolve().parents[3])
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitAnalyzer, ETFToolkitConfig
from backend.strategies.index_fund_research.etf_toolkit_settings import load_etf_toolkit_settings
from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore
from backend.strategies.index_fund_research.index_fund_analyzer import FundResearchConfig
from frontend.strategies.etf_toolkit_ui import _display_feature


TOPICS = [
    "基础筛选",
    "定投计划",
    "溢价折价监控",
    "风险雷达",
    "持仓穿透",
    "ETF对比",
    "日报周报",
    "完整报告",
]


def display_etf_single_analysis() -> None:
    st.subheader("单只ETF分析")
    st.caption("像股票单独分析一样，先按主题筛选ETF，再对选中的ETF运行指定分析模块。")

    settings = load_etf_toolkit_settings(PROJECT_ROOT)
    config = settings.get("analysis", {})
    min_turnover_wan = st.number_input("最低成交额(万元)", min_value=100, max_value=100000, value=int(config.get("min_turnover_wan", 3000)), step=100)
    start_date = st.text_input("历史起始日", value=str(config.get("start_date", "20210101")))

    analyzer = ETFToolkitAnalyzer()
    base_config = FundResearchConfig(
        history_candidates=500,
        min_turnover=float(min_turnover_wan) * 10_000,
        start_date=start_date.strip() or "20210101",
    )
    with st.spinner("正在读取ETF全市场快照..."):
        snapshot = analyzer.fetch_market_snapshot(base_config)
    if snapshot.empty:
        st.warning("未获取到ETF快照。")
        return

    categories = ["全部"] + sorted(snapshot["分类"].dropna().unique().tolist())
    col1, col2, col3 = st.columns(3)
    with col1:
        category = st.selectbox("ETF主题", categories)
    with col2:
        keyword = st.text_input("名称/代码搜索", "")
    with col3:
        topics = st.multiselect("分析模块", TOPICS, default=["基础筛选", "定投计划", "溢价折价监控", "风险雷达"])
    if not topics:
        topics = ["基础筛选"]

    filtered = snapshot.copy()
    if category != "全部":
        filtered = filtered[filtered["分类"].eq(category)]
    if keyword:
        text = filtered["代码"].astype(str) + " " + filtered["名称"].astype(str)
        filtered = filtered[text.str.contains(keyword, case=False, na=False)]
    filtered = filtered.sort_values("成交额", ascending=False).head(200)
    if filtered.empty:
        st.info("当前筛选条件下暂无ETF。")
        return

    options = [
        f"{row['代码']} | {row['名称']} | {row['分类']} | 成交额{float(row['成交额']) / 10000:.0f}万"
        for _, row in filtered.iterrows()
    ]
    selected = st.selectbox("选择ETF", options)
    code = selected.split("|", 1)[0].strip()
    selected_row = filtered[filtered["代码"].astype(str).eq(code)].iloc[0].to_dict()

    preview_columns = ["代码", "名称", "分类", "最新价", "成交额", "基金折价率", "IOPV实时估值"]
    st.dataframe(filtered[[c for c in preview_columns if c in filtered.columns]].head(100), width="stretch", hide_index=True)

    if st.button("开始单只ETF分析", type="primary", width="stretch"):
        result = _analyze_single_etf(analyzer, selected_row, topics, settings, start_date.strip() or "20210101")
        result.update(ETFToolkitStore(PROJECT_ROOT).save_history_result(result, settings, module="单只ETF分析", result_type=code))
        st.session_state.etf_single_analysis_result = result
        st.success(f"分析完成，已写入ETF历史记录：{result.get('history_path')}")

    result = st.session_state.get("etf_single_analysis_result")
    if not result:
        return

    metrics = st.columns(4)
    metrics[0].metric("代码", result.get("selected_etf", {}).get("代码", "-"))
    metrics[1].metric("名称", result.get("selected_etf", {}).get("名称", "-"))
    metrics[2].metric("分析模块", len(result.get("selected_topics", [])))
    metrics[3].metric("历史错误", result.get("error_count", 0))

    feature_map = {
        "基础筛选": "全市场筛选器",
        "定投计划": "定投计划",
        "溢价折价监控": "溢价折价监控",
        "风险雷达": "风险雷达",
        "持仓穿透": "持仓穿透",
        "ETF对比": "ETF对比",
        "日报周报": "日报周报",
        "完整报告": "完整报告",
    }
    tabs = st.tabs(result.get("selected_topics", []))
    for tab, topic in zip(tabs, result.get("selected_topics", [])):
        with tab:
            _display_feature(feature_map.get(topic, "完整报告"), result, settings)


def _analyze_single_etf(
    analyzer: ETFToolkitAnalyzer,
    selected_row: dict,
    topics: list[str],
    settings: dict,
    start_date: str,
) -> dict:
    code = str(selected_row["代码"]).zfill(6)
    errors = []
    row = None
    try:
        history = analyzer.history_fetcher(code, start_date)
        row = analyzer._analyze_one(selected_row, history, FundResearchConfig(start_date=start_date))
        if row:
            row = analyzer._enrich_toolkit_row(row)
    except Exception as exc:
        errors.append(f"{code}: {type(exc).__name__}: {exc}")
    screener = [row] if row else []
    rotation = analyzer._build_rotation(pd.DataFrame(screener)) if screener else []
    config = ETFToolkitConfig(
        max_history=1,
        min_turnover=float(settings.get("analysis", {}).get("min_turnover_wan", 3000)) * 10_000,
        monthly_budget=float(settings.get("analysis", {}).get("monthly_budget", 5000)),
        holding_top_n=1,
        include_premium_discount="溢价折价监控" in topics,
        include_holdings="持仓穿透" in topics,
        include_index_info="ETF对比" in topics,
        cache_ttl_minutes=int(settings.get("analysis", {}).get("cache_ttl_minutes", 30)),
        start_date=start_date,
    )
    premium_discount = analyzer._build_premium_discount(screener, config) if screener and "溢价折价监控" in topics else []
    dca_plans = analyzer._build_dca_plans(screener, config.monthly_budget) if screener and "定投计划" in topics else []
    risk_radar = analyzer._build_risk_radar(screener) if screener and "风险雷达" in topics else []
    comparison = analyzer._build_comparison(screener, config) if screener and "ETF对比" in topics else []
    opportunity_pool = analyzer._build_opportunity_pool(screener) if screener else {}
    periodic_report = analyzer._build_periodic_report(screener, rotation, opportunity_pool) if screener and "日报周报" in topics else {}
    holdings = analyzer._build_holdings_analysis(screener, 1) if screener and "持仓穿透" in topics else {"ETF持仓明细": [], "重复暴露": [], "errors": [], "skipped": "未选择持仓穿透"}
    portfolios = {profile: analyzer._build_portfolio(pd.DataFrame(screener), profile) for profile in ("稳健", "平衡", "进取")} if screener else {}
    report = analyzer.build_toolkit_report(
        screener=screener,
        rotation=rotation,
        portfolios=portfolios,
        dca_plans=dca_plans,
        premium_discount=premium_discount,
        holdings=holdings,
        risk_radar=risk_radar,
        comparison=comparison,
        opportunity_pool=opportunity_pool,
        periodic_report=periodic_report,
        errors=errors,
    )
    return {
        "success": bool(screener),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_etf": {"代码": code, "名称": selected_row.get("名称"), "分类": selected_row.get("分类")},
        "selected_topics": topics,
        "config": config.__dict__,
        "market_snapshot_count": 1,
        "analyzed_count": len(screener),
        "error_count": len(errors),
        "errors": errors,
        "screener": screener,
        "rotation": rotation,
        "portfolios": portfolios,
        "dca_plans": dca_plans,
        "premium_discount": premium_discount,
        "holdings": holdings,
        "risk_radar": risk_radar,
        "comparison": comparison,
        "periodic_report": periodic_report,
        "opportunity_pool": opportunity_pool,
        "report": report,
    }
