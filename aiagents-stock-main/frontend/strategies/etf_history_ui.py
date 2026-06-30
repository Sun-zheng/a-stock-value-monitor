from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(
    os.getenv("A_STOCK_VALUE_MONITOR_ROOT", Path(__file__).resolve().parents[3])
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore


def display_etf_history() -> None:
    st.subheader("ETF历史记录")
    st.caption("集中查看 ETF策略工具箱、指数基金研究、大盘ETF分析和单只ETF分析的每次运行结果。")

    store = ETFToolkitStore(PROJECT_ROOT)
    rows = store.list_history(limit=500)
    st.info("历史文件位置：data/etf_toolkit/history；索引文件：data/etf_toolkit/history/index.json")
    if not rows:
        st.warning("暂无ETF历史记录。运行任意ETF功能后会自动写入。")
        return

    frame = pd.DataFrame(rows)
    modules = ["全部"] + sorted(frame.get("module", pd.Series(dtype=str)).dropna().unique().tolist())
    col1, col2, col3 = st.columns(3)
    with col1:
        module = st.selectbox("模块", modules)
    with col2:
        only_success = st.checkbox("仅成功结果", value=False)
    with col3:
        limit = st.number_input("显示条数", min_value=10, max_value=500, value=100, step=10)

    filtered = frame.copy()
    if module != "全部" and "module" in filtered:
        filtered = filtered[filtered["module"].eq(module)]
    if only_success and "success" in filtered:
        filtered = filtered[filtered["success"].eq(True)]
    filtered = filtered.head(int(limit))

    display_columns = [
        "created_at", "module", "result_type", "success", "market_snapshot_count",
        "analyzed_count", "candidate_count", "alert_count", "error_count", "cache_hit", "path",
    ]
    st.dataframe(filtered[[c for c in display_columns if c in filtered.columns]], width="stretch", hide_index=True)
    if filtered.empty:
        st.info("筛选后暂无记录。")
        return

    path = st.selectbox("选择记录", filtered["path"].tolist())
    result = store.load_history_result(path)
    if not result:
        st.error("历史结果读取失败。")
        return

    metrics = st.columns(5)
    metrics[0].metric("快照", result.get("market_snapshot_count", result.get("universe_count", 0)))
    metrics[1].metric("完成分析", result.get("analyzed_count", 0))
    metrics[2].metric("候选/推荐", len(result.get("candidates", [])))
    metrics[3].metric("提醒", len(result.get("alerts", [])))
    metrics[4].metric("错误", result.get("error_count", 0))

    tab_report, tab_candidates, tab_alerts, tab_json = st.tabs(["完整报告", "候选/结果", "触发提醒", "原始JSON"])
    with tab_report:
        st.markdown(result.get("report", "该记录暂无 Markdown 报告。"))
    with tab_candidates:
        candidates = result.get("candidates") or result.get("screener") or []
        table = pd.DataFrame(candidates)
        if table.empty:
            st.info("暂无候选表。")
        else:
            st.dataframe(table.head(500), width="stretch", hide_index=True)
    with tab_alerts:
        alerts = pd.DataFrame(result.get("alerts", []))
        if alerts.empty:
            st.info("暂无触发提醒。")
        else:
            st.dataframe(alerts, width="stretch", hide_index=True)
    with tab_json:
        st.json(result)
