from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend.strategies.index_fund_research.major_market_etf_analyzer import (
    MajorMarketETFAnalyzer,
    MajorMarketETFConfig,
)
from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore
from frontend.strategies.index_fund_research_ui import (
    PROJECT_ROOT,
    _create_lark_doc,
    _send_report_email,
)


def _save_major_report(result: dict) -> Path:
    report_dir = PROJECT_ROOT / "reports" / "major_market_etf"
    report_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    markdown_path = report_dir / f"{day}.md"
    json_path = report_dir / f"{day}.json"
    markdown_path.write_text(result.get("report", ""), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path


def display_major_market_etf() -> None:
    st.subheader("大盘ETF指数分析")
    st.caption("只分析主要宽基指数ETF，覆盖A股、港股和海外主要市场，不混入行业主题ETF。")

    with st.form("major_market_etf_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.number_input("展示数量", min_value=5, max_value=20, value=12, step=1)
            history_candidates = st.number_input("历史候选数", min_value=10, max_value=100, value=40, step=10)
        with col2:
            min_turnover_wan = st.number_input("最低成交额(万元)", min_value=100, max_value=100000, value=3000, step=100)
            start_date = st.text_input("历史起始日", value="20210101", help="格式：YYYYMMDD")
        with col3:
            send_email_checked = st.checkbox("完成后发送邮件", value=False)
            create_lark_doc_checked = st.checkbox("完成后创建飞书文档", value=False)
        submitted = st.form_submit_button("开始大盘ETF分析", type="primary", width="stretch")

    if submitted:
        config = MajorMarketETFConfig(
            top_n=int(top_n),
            history_candidates=int(history_candidates),
            min_turnover=float(min_turnover_wan) * 10_000,
            start_date=start_date.strip() or "20210101",
        )
        with st.spinner("正在抓取主要宽基ETF并分析大盘配置价值..."):
            result = MajorMarketETFAnalyzer().analyze_major_market(config)
            report_path = _save_major_report(result)
            result["report_path"] = str(report_path)
            result.update(ETFToolkitStore(PROJECT_ROOT).save_history_result(result, module="大盘ETF指数分析"))
            st.session_state.major_market_etf_result = result
        st.success(f"分析完成，报告已保存：{report_path}") if result.get("success") else st.warning("分析完成，但暂无可展示结果。")

        if send_email_checked:
            subject = f"主要市场大盘ETF指数分析报告 - {datetime.now().strftime('%Y-%m-%d')}"
            ok, message = _send_report_email(subject, result.get("report", ""))
            st.success(message) if ok else st.error(message)
        if create_lark_doc_checked:
            ok, message = _create_lark_doc(result)
            st.success(message) if ok else st.error(message)

    result = st.session_state.get("major_market_etf_result")
    if not result:
        st.info("点击开始后，系统会用真实行情抓取主要宽基ETF，生成大盘配置分析报告。")
        return

    metrics = st.columns(4)
    metrics[0].metric("宽基ETF候选", result.get("universe_count", 0))
    metrics[1].metric("完成分析", result.get("analyzed_count", 0))
    metrics[2].metric("历史错误", result.get("error_count", 0))
    metrics[3].metric("推荐展示", len(result.get("candidates", [])))

    tabs = st.tabs(["推荐列表", "大盘环境", "智能体流程", "完整报告", "数据说明"])
    with tabs[0]:
        frame = pd.DataFrame(result.get("candidates", []))
        if frame.empty:
            st.info("暂无结果。")
        else:
            columns = [
                "代码", "名称", "最新价", "高点回撤", "近一年收益", "低点反弹",
                "年化波动", "大盘配置评分", "预测最低点", "回涨确认点", "预计修复周期", "配置观点",
            ]
            st.dataframe(frame[[c for c in columns if c in frame.columns]], width="stretch", hide_index=True)
    with tabs[1]:
        context = result.get("market_context", {})
        st.markdown(f"**状态**：{context.get('status', '-')}")
        st.markdown(f"**判断**：{context.get('summary', '-')}")
        if context.get("indices"):
            st.dataframe(pd.DataFrame(context["indices"]), width="stretch", hide_index=True)
        st.json(context.get("etf_breadth", {}))
    with tabs[2]:
        for step in result.get("workflow", []):
            st.markdown(f"- {step}")
    with tabs[3]:
        st.markdown(result.get("report", ""))
    with tabs[4]:
        st.json(
            {
                "config": result.get("config", {}),
                "report_path": result.get("report_path"),
                "errors": result.get("errors", []),
            }
        )
