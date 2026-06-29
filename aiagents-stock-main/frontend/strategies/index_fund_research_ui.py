from __future__ import annotations

import json
import os
import sys
import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backend.strategies.index_fund_research.index_fund_analyzer import (
    FundResearchConfig,
    IndexFundResearchAnalyzer,
)


PROJECT_ROOT = Path(
    os.getenv("A_STOCK_VALUE_MONITOR_ROOT", Path(__file__).resolve().parents[3])
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _save_report(result: dict) -> Path:
    report_dir = PROJECT_ROOT / "reports" / "index_fund_research"
    report_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    markdown_path = report_dir / f"{day}.md"
    json_path = report_dir / f"{day}.json"
    markdown_path.write_text(result.get("report", ""), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path


def _send_report_email(subject: str, body: str) -> tuple[bool, str]:
    try:
        settings_spec = importlib.util.spec_from_file_location(
            "a_stock_root_settings", PROJECT_ROOT / "config" / "settings.py"
        )
        email_spec = importlib.util.spec_from_file_location(
            "a_stock_root_email_sender", PROJECT_ROOT / "src" / "email_sender.py"
        )
        if not settings_spec or not settings_spec.loader or not email_spec or not email_spec.loader:
            return False, "邮件模块加载失败: 模块路径不可用"
        settings_module = importlib.util.module_from_spec(settings_spec)
        email_module = importlib.util.module_from_spec(email_spec)
        settings_spec.loader.exec_module(settings_module)
        email_spec.loader.exec_module(email_module)
    except Exception as exc:
        return False, f"邮件模块加载失败: {type(exc).__name__}: {exc}"
    return email_module.send_email(settings_module.settings, subject, body)


def _display_candidates(candidates: list[dict]) -> None:
    if not candidates:
        st.info("暂无候选结果。")
        return
    frame = pd.DataFrame(candidates)
    columns = [
        "代码", "名称", "分类", "最新价", "历史高点", "高点回撤",
        "低点反弹", "近一年收益", "年化波动", "成交额",
        "综合评分", "预测最低点", "回涨确认点", "预计修复周期",
        "长牛逻辑", "风险边界",
    ]
    display_columns = [column for column in columns if column in frame.columns]
    st.dataframe(frame[display_columns], width="stretch", hide_index=True)


def display_index_fund_research() -> None:
    st.subheader("指数基金回撤研究")
    st.caption("筛选接近历史高点腰斩、流动性可交易、具备长期产业逻辑的指数基金，并生成可邮件发送的总分总报告。")

    with st.form("index_fund_research_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.number_input("推荐数量", min_value=3, max_value=10, value=5, step=1)
            target_drawdown = st.number_input("目标回撤(%)", min_value=-80.0, max_value=-20.0, value=-50.0, step=1.0)
        with col2:
            history_candidates = st.number_input("历史候选数", min_value=10, max_value=200, value=80, step=10)
            min_turnover_wan = st.number_input("最低成交额(万元)", min_value=100, max_value=100000, value=2000, step=100)
        with col3:
            min_drawdown = st.number_input("最低回撤(%)", min_value=-80.0, max_value=-5.0, value=-20.0, step=1.0)
            start_date = st.text_input("历史起始日", value="20180101", help="格式：YYYYMMDD")
            diversify_categories = st.checkbox("优先分散行业/类型", value=True)
            send_email_checked = st.checkbox("完成后发送邮件", value=False)
        submitted = st.form_submit_button("开始指数基金研究", type="primary", width="stretch")

    if submitted:
        config = FundResearchConfig(
            top_n=int(top_n),
            history_candidates=int(history_candidates),
            min_turnover=float(min_turnover_wan) * 10_000,
            target_drawdown_pct=float(target_drawdown),
            min_drawdown_pct=float(min_drawdown),
            diversify_categories=bool(diversify_categories),
            start_date=start_date.strip() or "20180101",
        )
        with st.spinner("正在拉取 ETF 行情、计算回撤和生成分析报告..."):
            result = IndexFundResearchAnalyzer().analyze(config)
            report_path = _save_report(result)
            result["report_path"] = str(report_path)
            st.session_state.index_fund_research_result = result
        if result.get("success"):
            st.success(f"研究完成，报告已保存：{report_path}")
        else:
            st.warning("研究完成，但未找到满足条件的候选。")

        if send_email_checked:
            subject = f"指数基金回撤研究报告 - {datetime.now().strftime('%Y-%m-%d')}"
            ok, message = _send_report_email(subject, result.get("report", ""))
            st.success(message) if ok else st.error(message)

    result = st.session_state.get("index_fund_research_result")
    if not result:
        st.info("设置参数后点击开始，系统会自动完成流动性过滤、历史回撤分析、多分析师规则复核和报告生成。")
        return

    metrics = st.columns(4)
    metrics[0].metric("ETF候选池", result.get("universe_count", 0))
    metrics[1].metric("完成分析", result.get("analyzed_count", 0))
    metrics[2].metric("推荐数量", len(result.get("candidates", [])))
    metrics[3].metric("生成时间", str(result.get("generated_at", "-"))[-8:])

    tabs = st.tabs(["推荐结果", "研究流程", "完整报告", "数据说明"])
    with tabs[0]:
        _display_candidates(result.get("candidates", []))
    with tabs[1]:
        for step in result.get("workflow", []):
            st.markdown(f"- {step}")
    with tabs[2]:
        st.markdown(result.get("report", ""))
    with tabs[3]:
        st.json(
            {
                "config": result.get("config", {}),
                "report_path": result.get("report_path"),
                "errors": result.get("errors", []),
            }
        )
