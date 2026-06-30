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
    st.caption("ETF全市场筛选、轮动、组合、定投、溢价折价、持仓穿透、风险雷达、对比、日报周报和机会池。")

    with st.form("etf_toolkit_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            max_history = st.number_input("历史分析数量", min_value=20, max_value=200, value=80, step=10)
            min_turnover_wan = st.number_input("最低成交额(万元)", min_value=100, max_value=100000, value=2000, step=100)
        with col2:
            min_price = st.number_input("最低价格", min_value=0.0, max_value=1000.0, value=0.0, step=0.1)
            start_date = st.text_input("历史起始日", value="20210101", help="格式：YYYYMMDD")
        with col3:
            monthly_budget = st.number_input("定投月预算(元)", min_value=100.0, max_value=1_000_000.0, value=5000.0, step=500.0)
            holding_top_n = st.number_input("持仓穿透ETF数", min_value=1, max_value=20, value=5, step=1)
            send_email_checked = st.checkbox("完成后发送邮件", value=False)
            create_lark_doc_checked = st.checkbox("完成后创建飞书文档", value=False)
        submitted = st.form_submit_button("运行ETF策略工具箱", type="primary", width="stretch")

    if submitted:
        config = ETFToolkitConfig(
            max_history=int(max_history),
            min_turnover=float(min_turnover_wan) * 10_000,
            min_price=float(min_price),
            monthly_budget=float(monthly_budget),
            holding_top_n=int(holding_top_n),
            start_date=start_date.strip() or "20210101",
        )
        with st.spinner("正在抓取ETF全市场快照、历史行情、基金档案和持仓穿透数据..."):
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

    (
        tab_screen,
        tab_rotation,
        tab_portfolio,
        tab_dca,
        tab_premium,
        tab_holdings,
        tab_risk,
        tab_compare,
        tab_periodic,
        tab_pool,
        tab_report,
        tab_meta,
    ) = st.tabs(
        [
            "全市场筛选器",
            "ETF轮动策略",
            "ETF组合配置器",
            "定投计划",
            "溢价折价",
            "持仓穿透",
            "风险雷达",
            "ETF对比",
            "日报周报",
            "机会池",
            "完整报告",
            "数据说明",
        ]
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
    with tab_dca:
        frame = pd.DataFrame(result.get("dca_plans", []))
        if frame.empty:
            st.info("暂无定投计划。")
        else:
            st.dataframe(frame, width="stretch", hide_index=True)
    with tab_premium:
        frame = pd.DataFrame(result.get("premium_discount", []))
        if frame.empty:
            st.info("暂无溢价折价数据。")
        else:
            status = ["全部"] + sorted(frame["状态"].dropna().unique().tolist())
            selected_status = st.selectbox("状态", status)
            filtered = frame if selected_status == "全部" else frame[frame["状态"].eq(selected_status)]
            st.dataframe(filtered, width="stretch", hide_index=True)
    with tab_holdings:
        holdings = result.get("holdings", {})
        overlap = pd.DataFrame(holdings.get("重复暴露", []))
        st.markdown("#### 重复暴露")
        if overlap.empty:
            st.info("暂无重复暴露，或持仓数据暂未返回。")
        else:
            st.dataframe(overlap, width="stretch", hide_index=True)
        st.markdown("#### ETF前十大持仓")
        for item in holdings.get("ETF持仓明细", []):
            with st.expander(f"{item.get('名称')}（{item.get('代码')}） 前十大集中度 {item.get('前十大集中度')}%"):
                detail = pd.DataFrame(item.get("前十大持仓", []))
                if detail.empty:
                    st.info("暂无持仓明细。")
                else:
                    st.dataframe(detail, width="stretch", hide_index=True)
        if holdings.get("errors"):
            st.warning(f"持仓抓取失败样例：{holdings.get('errors')[:3]}")
    with tab_risk:
        frame = pd.DataFrame(result.get("risk_radar", []))
        if frame.empty:
            st.info("暂无风险雷达。")
        else:
            level = st.multiselect("风险等级", sorted(frame["风险等级"].dropna().unique().tolist()), default=sorted(frame["风险等级"].dropna().unique().tolist()))
            filtered = frame[frame["风险等级"].isin(level)] if level else frame
            st.dataframe(filtered, width="stretch", hide_index=True)
    with tab_compare:
        frame = pd.DataFrame(result.get("comparison", []))
        if frame.empty:
            st.info("暂无ETF对比数据。")
        else:
            names = frame["名称"].dropna().tolist()
            selected_names = st.multiselect("选择2-5只ETF对比", names, default=names[: min(5, len(names))], max_selections=5)
            filtered = frame[frame["名称"].isin(selected_names)] if selected_names else frame.head(5)
            st.dataframe(filtered, width="stretch", hide_index=True)
    with tab_periodic:
        periodic = result.get("periodic_report", {})
        st.markdown(f"#### {periodic.get('标题', 'ETF定时日报/周报')}")
        for sentence in periodic.get("总览", []):
            st.markdown(f"- {sentence}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("##### 强势行业ETF")
            st.dataframe(pd.DataFrame(periodic.get("强势行业ETF", [])), width="stretch", hide_index=True)
        with col2:
            st.markdown("##### 深回撤ETF")
            st.dataframe(pd.DataFrame(periodic.get("深回撤ETF", [])), width="stretch", hide_index=True)
        with col3:
            st.markdown("##### 放量ETF")
            st.dataframe(pd.DataFrame(periodic.get("放量ETF", [])), width="stretch", hide_index=True)
    with tab_pool:
        pool = result.get("opportunity_pool", {})
        for name, items in pool.items():
            if isinstance(items, list):
                st.markdown(f"#### {name}")
                frame = pd.DataFrame(items)
                if frame.empty:
                    st.info("暂无入池ETF。")
                else:
                    st.dataframe(frame, width="stretch", hide_index=True)
        if pool.get("说明"):
            st.caption(pool["说明"])
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
