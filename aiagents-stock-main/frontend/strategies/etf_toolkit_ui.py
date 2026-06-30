from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend.strategies.index_fund_research.etf_toolkit_analyzer import (
    ETFToolkitAnalyzer,
    ETFToolkitConfig,
)
from frontend.strategies.index_fund_research_ui import (
    PROJECT_ROOT,
    _create_lark_doc,
    _send_report_email,
)


def _save_toolkit_report(result: dict) -> Path:
    report_dir = PROJECT_ROOT / "reports" / "etf_toolkit"
    report_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    markdown_path = report_dir / f"{day}.md"
    json_path = report_dir / f"{day}.json"
    markdown_path.write_text(result.get("report", ""), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path


def display_etf_toolkit() -> None:
    st.subheader("ETF策略工具箱")
    st.caption("ETF全市场筛选器、轮动策略、组合配置器。数据来自真实ETF行情和真实历史日线。")

    with st.form("etf_toolkit_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            max_history = st.number_input("历史分析数量", min_value=20, max_value=200, value=80, step=10)
            min_turnover_wan = st.number_input("最低成交额(万元)", min_value=100, max_value=100000, value=2000, step=100)
        with col2:
            min_price = st.number_input("最低价格", min_value=0.0, max_value=1000.0, value=0.0, step=0.1)
            start_date = st.text_input("历史起始日", value="20210101", help="格式：YYYYMMDD")
        with col3:
            send_email_checked = st.checkbox("完成后发送邮件", value=False)
            create_lark_doc_checked = st.checkbox("完成后创建飞书文档", value=False)
        submitted = st.form_submit_button("运行ETF策略工具箱", type="primary", width="stretch")

    if submitted:
        config = ETFToolkitConfig(
            max_history=int(max_history),
            min_turnover=float(min_turnover_wan) * 10_000,
            min_price=float(min_price),
            start_date=start_date.strip() or "20210101",
        )
        with st.spinner("正在抓取ETF全市场快照、计算轮动和组合配置..."):
            result = ETFToolkitAnalyzer().analyze_toolkit(config)
            report_path = _save_toolkit_report(result)
            result["report_path"] = str(report_path)
            st.session_state.etf_toolkit_result = result
        st.success(f"分析完成，报告已保存：{report_path}") if result.get("success") else st.warning("分析完成，但暂无可展示结果。")

        if send_email_checked:
            subject = f"ETF策略工具箱报告 - {datetime.now().strftime('%Y-%m-%d')}"
            ok, message = _send_report_email(subject, result.get("report", ""))
            st.success(message) if ok else st.error(message)
        if create_lark_doc_checked:
            ok, message = _create_lark_doc(result)
            st.success(message) if ok else st.error(message)

    result = st.session_state.get("etf_toolkit_result")
    if not result:
        st.info("点击运行后，将生成全市场ETF筛选、轮动排名和三类风险偏好的ETF组合。")
        return

    metrics = st.columns(4)
    metrics[0].metric("全市场ETF快照", result.get("market_snapshot_count", 0))
    metrics[1].metric("完成历史分析", result.get("analyzed_count", 0))
    metrics[2].metric("轮动分类", len(result.get("rotation", [])))
    metrics[3].metric("历史错误", result.get("error_count", 0))

    tab_screen, tab_rotation, tab_portfolio, tab_report, tab_meta = st.tabs(
        ["全市场筛选器", "ETF轮动策略", "ETF组合配置器", "完整报告", "数据说明"]
    )
    with tab_screen:
        frame = pd.DataFrame(result.get("screener", []))
        if frame.empty:
            st.info("暂无筛选结果。")
        else:
            categories = ["全部"] + sorted(frame["分类"].dropna().unique().tolist())
            selected_category = st.selectbox("分类", categories)
            min_score = st.slider("最低筛选评分", 0, 100, 0)
            max_vol = st.slider("最高年化波动", 0, 120, 120)
            filtered = frame[
                frame["筛选评分"].ge(min_score)
                & frame["年化波动"].le(max_vol)
            ]
            if selected_category != "全部":
                filtered = filtered[filtered["分类"].eq(selected_category)]
            columns = [
                "代码", "名称", "分类", "最新价", "高点回撤", "近一年收益",
                "低点反弹", "年化波动", "成交额", "筛选评分", "风险标签",
            ]
            st.caption(f"{len(filtered)} / {len(frame)} 只")
            st.dataframe(filtered[[c for c in columns if c in filtered.columns]], width="stretch", hide_index=True)
    with tab_rotation:
        rotation = pd.DataFrame(result.get("rotation", []))
        if rotation.empty:
            st.info("暂无轮动结果。")
        else:
            st.dataframe(rotation, width="stretch", hide_index=True)
    with tab_portfolio:
        portfolios = result.get("portfolios", {})
        profile = st.radio("风险偏好", list(portfolios.keys()), horizontal=True)
        selected = portfolios.get(profile, {})
        st.markdown(selected.get("notes", ""))
        positions = pd.DataFrame(selected.get("positions", []))
        if positions.empty:
            st.info("暂无组合。")
        else:
            st.dataframe(positions, width="stretch", hide_index=True)
    with tab_report:
        st.markdown(result.get("report", ""))
    with tab_meta:
        st.json(
            {
                "config": result.get("config", {}),
                "workflow": result.get("workflow", []),
                "report_path": result.get("report_path"),
                "errors": result.get("errors", []),
            }
        )
