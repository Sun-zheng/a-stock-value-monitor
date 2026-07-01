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


@st.cache_data(ttl=600, show_spinner=False)
def _load_market_snapshot(min_turnover_wan: int, start_date: str) -> pd.DataFrame:
    analyzer = ETFToolkitAnalyzer()
    base_config = FundResearchConfig(
        history_candidates=500,
        min_turnover=float(min_turnover_wan) * 10_000,
        start_date=start_date.strip() or "20210101",
    )
    return analyzer.fetch_market_snapshot(base_config)


def display_etf_single_analysis() -> None:
    st.subheader("单只ETF分析")
    st.caption("像股票单独分析一样，先按主题筛选ETF，再对选中的ETF运行指定分析模块。")

    settings = load_etf_toolkit_settings(PROJECT_ROOT)
    config = settings.get("analysis", {})
    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        min_turnover_wan = st.number_input(
            "最低成交额(万元)",
            min_value=100,
            max_value=100000,
            value=int(config.get("min_turnover_wan", 3000)),
            step=100,
            key="etf_single_min_turnover_wan",
        )
    with col_b:
        start_date = st.text_input(
            "历史起始日",
            value=str(config.get("start_date", "20210101")),
            key="etf_single_start_date",
        )
    with col_c:
        if st.button("刷新ETF快照", width="stretch"):
            _load_market_snapshot.clear()
            st.session_state.pop("etf_single_analysis_result", None)
            st.rerun()

    with st.spinner("正在读取ETF全市场快照..."):
        snapshot = _load_market_snapshot(int(min_turnover_wan), start_date.strip() or "20210101")
    if snapshot.empty:
        st.warning("未获取到ETF快照。")
        return
    snapshot = _prepare_snapshot(snapshot)
    pending_code = st.session_state.pop("etf_single_pending_code", None)
    if pending_code and str(pending_code) in set(snapshot["代码"].astype(str)):
        st.session_state.etf_single_selected_code = str(pending_code)
        st.session_state.etf_single_category = "全部"
        st.session_state.etf_single_keyword = ""

    categories = ["全部"] + sorted(snapshot["分类"].dropna().unique().tolist())
    col1, col2, col3 = st.columns([1, 1.3, 1.5])
    with col1:
        category = st.selectbox("ETF主题", categories, key="etf_single_category")
    with col2:
        keyword = st.text_input(
            "模糊搜索",
            "",
            placeholder="输入代码、名称、主题，例如 300、沪深300、红利、半导体",
            key="etf_single_keyword",
        )
    with col3:
        topics = st.multiselect(
            "分析模块",
            TOPICS,
            default=["基础筛选", "定投计划", "溢价折价监控", "风险雷达"],
            key="etf_single_topics",
        )
    if not topics:
        topics = ["基础筛选"]

    filtered = _filter_snapshot(snapshot, category, keyword)
    filtered = filtered.sort_values("成交额", ascending=False).head(200)
    if filtered.empty:
        st.info("当前筛选条件下暂无ETF。")
        return

    code_label = _build_code_label_map(snapshot)
    candidate_codes = filtered["代码"].astype(str).tolist()
    selected_code = _get_selected_code(candidate_codes)
    selected_index = candidate_codes.index(selected_code)
    selected_code = st.selectbox(
        "选择ETF",
        candidate_codes,
        index=selected_index,
        format_func=lambda code: code_label.get(str(code), str(code)),
        help="选择值按ETF代码保存，页面刷新后不会因为实时成交额变化回到第一只ETF。",
    )
    st.session_state.etf_single_selected_code = str(selected_code)

    direct_cols = st.columns([2, 1])
    with direct_cols[0]:
        direct_keyword = st.text_input(
            "直接定位ETF",
            "",
            placeholder="输入完整/部分代码或名称后点击定位",
            key="etf_single_direct_keyword",
        )
    with direct_cols[1]:
        if st.button("定位ETF", width="stretch"):
            matched_code = _find_first_code(snapshot, direct_keyword)
            if matched_code:
                st.session_state.etf_single_pending_code = matched_code
                st.success(f"已定位到 {code_label.get(matched_code, matched_code)}")
                st.rerun()
            else:
                st.warning("没有找到匹配的ETF。")

    selected_row = snapshot[snapshot["代码"].astype(str).eq(str(selected_code))].iloc[0].to_dict()
    _display_selected_summary(selected_row)

    preview_columns = ["代码", "名称", "分类", "最新价", "成交额", "基金折价率", "IOPV实时估值"]
    st.caption(f"候选ETF {len(filtered)} 只；当前选中：{code_label.get(str(selected_code), str(selected_code))}")
    st.dataframe(filtered[[c for c in preview_columns if c in filtered.columns]].head(100), width="stretch", hide_index=True)

    if st.button("开始单只ETF分析", type="primary", width="stretch"):
        analyzer = ETFToolkitAnalyzer()
        result = _analyze_single_etf(analyzer, selected_row, topics, settings, start_date.strip() or "20210101")
        result.update(ETFToolkitStore(PROJECT_ROOT).save_history_result(result, settings, module="单只ETF分析", result_type=str(selected_code)))
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


def _prepare_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    frame = snapshot.copy()
    frame["代码"] = frame["代码"].astype(str).str.extract(r"(\d+)", expand=False).fillna("").str.zfill(6)
    frame["名称"] = frame["名称"].astype(str).str.strip()
    frame["分类"] = frame["分类"].fillna("其他").astype(str)
    return frame[frame["代码"].ne("000000")].drop_duplicates("代码", keep="first")


def _filter_snapshot(snapshot: pd.DataFrame, category: str, keyword: str) -> pd.DataFrame:
    filtered = snapshot.copy()
    if category != "全部":
        filtered = filtered[filtered["分类"].eq(category)]
    keyword = (keyword or "").strip()
    if keyword:
        normalized = keyword.lower()
        text = (
            filtered["代码"].astype(str)
            + " "
            + filtered["名称"].astype(str)
            + " "
            + filtered["分类"].astype(str)
        ).str.lower()
        filtered = filtered[text.str.contains(normalized, regex=False, na=False)]
    return filtered


def _build_code_label_map(snapshot: pd.DataFrame) -> dict[str, str]:
    labels = {}
    for row in snapshot.to_dict("records"):
        turnover_wan = float(row.get("成交额") or 0) / 10000
        labels[str(row["代码"])] = f"{row['代码']} | {row['名称']} | {row['分类']} | 成交额{turnover_wan:.0f}万"
    return labels


def _get_selected_code(candidate_codes: list[str]) -> str:
    current = str(st.session_state.get("etf_single_selected_code") or "")
    if current in candidate_codes:
        return current
    st.session_state.etf_single_selected_code = candidate_codes[0]
    return candidate_codes[0]


def _find_first_code(snapshot: pd.DataFrame, keyword: str) -> str | None:
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return None
    text = (
        snapshot["代码"].astype(str)
        + " "
        + snapshot["名称"].astype(str)
        + " "
        + snapshot["分类"].astype(str)
    ).str.lower()
    matched = snapshot[text.str.contains(keyword, regex=False, na=False)]
    if matched.empty:
        return None
    return str(matched.sort_values("成交额", ascending=False).iloc[0]["代码"])


def _display_selected_summary(selected_row: dict) -> None:
    metric_cols = st.columns(5)
    metric_cols[0].metric("选中代码", selected_row.get("代码", "-"))
    metric_cols[1].metric("ETF名称", selected_row.get("名称", "-"))
    metric_cols[2].metric("主题", selected_row.get("分类", "-"))
    metric_cols[3].metric("最新价", _format_number(selected_row.get("最新价")))
    metric_cols[4].metric("成交额(万)", _format_number(float(selected_row.get("成交额") or 0) / 10000))


def _format_number(value) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "-"


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
