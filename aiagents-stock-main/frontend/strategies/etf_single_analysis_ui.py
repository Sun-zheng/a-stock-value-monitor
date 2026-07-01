from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(
    os.getenv("A_STOCK_VALUE_MONITOR_ROOT", Path(__file__).resolve().parents[3])
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env", override=False)

from interface.ai.ai_engine import AIEngine
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

MODELSCOPE_MODELS = [
    "deepseek-ai/DeepSeek-V4-Flash",
    "stepfun-ai/Step-3.7-Flash",
    "ZhipuAI/GLM-5.2",
    "moonshotai/Kimi-K2.7-Code:Moonshot",
    "deepseek-ai/DeepSeek-V4-Pro",
    "MiniMax/MiniMax-M3",
    "inclusionAI/Ring-2.6-1T",
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
    st.subheader("ETF分析")
    st.caption("支持单只或多只ETF批量分析，按股票分析的方式输出多分析师视角、综合结论和明细模块。")

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

    ai_cols = st.columns([1, 1.4, 1.6])
    modelscope_ready = bool(os.getenv("MODELSCOPE_API_KEY", "").strip())
    with ai_cols[0]:
        enable_ai_review = st.checkbox(
            "启用AI复核",
            value=modelscope_ready,
            key="etf_enable_ai_review",
            help="仅调用ModelScope OpenAI兼容接口，不调用DeepSeek。",
        )
    with ai_cols[1]:
        ai_model = st.selectbox(
            "AI复核模型",
            MODELSCOPE_MODELS,
            key="etf_ai_review_model",
            disabled=not enable_ai_review,
        )
    with ai_cols[2]:
        if enable_ai_review and not modelscope_ready:
            st.warning("未检测到 MODELSCOPE_API_KEY，AI复核会跳过。")
        elif enable_ai_review:
            st.caption("AI复核已限制为 ModelScope 模型，不会走 DeepSeek。")

    filtered = _filter_snapshot(snapshot, category, keyword)
    filtered = filtered.sort_values("成交额", ascending=False).head(200)
    if filtered.empty:
        st.info("当前筛选条件下暂无ETF。")
        return

    code_label = _build_code_label_map(snapshot)
    candidate_codes = filtered["代码"].astype(str).tolist()
    analysis_mode = st.radio("分析方式", ["单只ETF", "批量ETF"], horizontal=True, key="etf_analysis_mode")
    selected_code = _get_selected_code(candidate_codes)
    selected_index = candidate_codes.index(selected_code)
    selected_codes: list[str] = []
    if analysis_mode == "单只ETF":
        selected_code = st.selectbox(
            "选择ETF",
            candidate_codes,
            index=selected_index,
            format_func=lambda code: code_label.get(str(code), str(code)),
            help="选择值按ETF代码保存，页面刷新后不会因为实时成交额变化回到第一只ETF。",
        )
        st.session_state.etf_single_selected_code = str(selected_code)
        selected_codes = [str(selected_code)]

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
    else:
        default_batch = _get_batch_default_codes(candidate_codes)
        selected_codes = st.multiselect(
            "选择多只ETF",
            candidate_codes,
            default=default_batch,
            format_func=lambda code: code_label.get(str(code), str(code)),
            key="etf_batch_selected_codes",
            help="可以从筛选后的候选池中选择多只ETF，建议一次不超过10只。",
        )
        batch_input = st.text_area(
            "批量补充代码/名称",
            "",
            placeholder="可粘贴多只ETF代码或名称，每行一个，或用逗号分隔。例如：510300, 159915, 红利ETF",
            height=90,
            key="etf_batch_free_text",
        )
        selected_codes = _merge_selected_codes(snapshot, selected_codes, batch_input)
        max_batch = st.slider("本次最多分析ETF数量", min_value=2, max_value=20, value=8, step=1, key="etf_batch_limit")
        if len(selected_codes) > max_batch:
            st.warning(f"已选择 {len(selected_codes)} 只，本次将按列表顺序分析前 {max_batch} 只。")
            selected_codes = selected_codes[:max_batch]
        if not selected_codes:
            st.info("请选择或输入至少一只ETF。")

    selected_rows = _selected_rows(snapshot, selected_codes)
    _display_selection_summary(selected_rows)

    preview_columns = ["代码", "名称", "分类", "最新价", "成交额", "基金折价率", "IOPV实时估值"]
    selected_label = "、".join(code_label.get(code, code).split(" | ")[0] for code in selected_codes[:8])
    if len(selected_codes) > 8:
        selected_label += f" 等{len(selected_codes)}只"
    st.caption(f"候选ETF {len(filtered)} 只；当前选中：{selected_label or '-'}")
    st.dataframe(filtered[[c for c in preview_columns if c in filtered.columns]].head(100), width="stretch", hide_index=True)

    if st.button("开始ETF分析", type="primary", width="stretch", disabled=not selected_rows):
        analyzer = ETFToolkitAnalyzer()
        result = _analyze_etfs(
            analyzer,
            selected_rows,
            topics,
            settings,
            start_date.strip() or "20210101",
            enable_ai_review=enable_ai_review,
            ai_model=ai_model,
        )
        result.update(ETFToolkitStore(PROJECT_ROOT).save_history_result(result, settings, module="ETF分析", result_type=result.get("result_type", "etf_analysis")))
        st.session_state.etf_single_analysis_result = result
        st.success(f"分析完成，已写入ETF历史记录：{result.get('history_path')}")

    result = st.session_state.get("etf_single_analysis_result")
    if not result:
        return

    _display_etf_analysis_result(result, settings)


def _display_etf_analysis_result(result: dict, settings: dict) -> None:
    metrics = st.columns(5)
    metrics[0].metric("分析ETF", result.get("selected_count", result.get("analyzed_count", 0)))
    metrics[1].metric("成功", result.get("analyzed_count", 0))
    metrics[2].metric("分析模块", len(result.get("selected_topics", [])))
    metrics[3].metric("触发风险", len(result.get("risk_radar", [])))
    metrics[4].metric("历史错误", result.get("error_count", 0))

    summary_tabs = st.tabs(["综合结论", "AI分析师团队", "ETF明细", "功能模块"])
    with summary_tabs[0]:
        _display_final_summary(result)
    with summary_tabs[1]:
        _display_analyst_reports(result)
    with summary_tabs[2]:
        _display_batch_details(result)
    with summary_tabs[3]:
        _display_feature_modules(result, settings)


def _display_feature_modules(result: dict, settings: dict) -> None:

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


def _get_batch_default_codes(candidate_codes: list[str]) -> list[str]:
    current = st.session_state.get("etf_batch_selected_codes") or []
    valid = [str(code) for code in current if str(code) in candidate_codes]
    if valid:
        return valid[:5]
    selected = str(st.session_state.get("etf_single_selected_code") or "")
    if selected in candidate_codes:
        return [selected]
    return candidate_codes[:3]


def _merge_selected_codes(snapshot: pd.DataFrame, selected_codes: list[str], free_text: str) -> list[str]:
    merged = [str(code).zfill(6) for code in selected_codes]
    for token in _parse_code_tokens(free_text):
        matched = _find_first_code(snapshot, token)
        if matched:
            merged.append(matched)
    deduped = []
    seen = set()
    for code in merged:
        if code not in seen:
            deduped.append(code)
            seen.add(code)
    return deduped


def _parse_code_tokens(value: str) -> list[str]:
    normalized = (value or "").replace("，", ",").replace("、", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _selected_rows(snapshot: pd.DataFrame, selected_codes: list[str]) -> list[dict]:
    rows = []
    for code in selected_codes:
        matched = snapshot[snapshot["代码"].astype(str).eq(str(code).zfill(6))]
        if not matched.empty:
            rows.append(matched.iloc[0].to_dict())
    return rows


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


def _display_selection_summary(selected_rows: list[dict]) -> None:
    if not selected_rows:
        return
    if len(selected_rows) == 1:
        _display_selected_summary(selected_rows[0])
        return
    frame = pd.DataFrame(selected_rows)
    metric_cols = st.columns(5)
    metric_cols[0].metric("选中ETF", len(frame))
    metric_cols[1].metric("主题数量", frame["分类"].nunique() if "分类" in frame else "-")
    metric_cols[2].metric("合计成交额(万)", _format_number(float(frame["成交额"].fillna(0).sum()) / 10000))
    metric_cols[3].metric("最高成交额ETF", frame.sort_values("成交额", ascending=False).iloc[0].get("名称", "-"))
    metric_cols[4].metric("平均价格", _format_number(frame["最新价"].fillna(0).mean() if "最新价" in frame else 0))


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


def _display_final_summary(result: dict) -> None:
    summary = result.get("final_summary") or _build_final_summary(result)
    st.markdown("#### 综合结论")
    st.info(summary.get("headline", "暂无综合结论。"))
    col1, col2, col3 = st.columns(3)
    col1.metric("综合评级", summary.get("rating", "-"))
    col2.metric("优先观察", summary.get("top_pick", "-"))
    col3.metric("主要风险", summary.get("main_risk", "-"))
    st.markdown("#### 操作建议")
    for item in summary.get("actions", []):
        st.markdown(f"- {item}")
    if result.get("errors"):
        with st.expander("数据问题与跳过项", expanded=False):
            for error in result.get("errors", [])[:20]:
                st.write(error)


def _display_analyst_reports(result: dict) -> None:
    reports = result.get("analyst_reports") or _build_etf_analyst_reports(result)
    if not reports:
        st.info("暂无分析师报告。")
        return
    ai_review = result.get("ai_review") or {}
    if ai_review:
        if ai_review.get("success"):
            st.success(f"ModelScope AI复核完成：{ai_review.get('model')}")
            with st.expander("ModelScope AI复核结论", expanded=True):
                st.markdown(ai_review.get("content", ""))
        else:
            st.warning(f"ModelScope AI复核未完成：{ai_review.get('error') or ai_review.get('status')}")
    tabs = st.tabs([item["agent_name"] for item in reports])
    for tab, item in zip(tabs, reports):
        with tab:
            st.markdown(f"#### {item['agent_name']}")
            st.caption(f"职责：{item['agent_role']} | 关注：{', '.join(item['focus_areas'])} | 时间：{item['timestamp']}")
            st.markdown(item["analysis"])


def _display_batch_details(result: dict) -> None:
    frame = pd.DataFrame(result.get("screener", []))
    if frame.empty:
        st.info("暂无ETF明细。")
        return
    columns = [
        "代码", "名称", "分类", "最新价", "高点回撤", "近一年收益", "低点反弹",
        "年化波动", "成交额", "筛选评分", "风险标签",
    ]
    st.dataframe(frame[[c for c in columns if c in frame.columns]], width="stretch", hide_index=True)
    if len(frame) > 1:
        st.markdown("#### 批量对比")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            score_frame = frame[["名称", "筛选评分"]].dropna() if {"名称", "筛选评分"}.issubset(frame.columns) else pd.DataFrame()
            if not score_frame.empty:
                st.bar_chart(score_frame.set_index("名称")["筛选评分"])
        with chart_cols[1]:
            risk_frame = frame[["名称", "高点回撤"]].dropna() if {"名称", "高点回撤"}.issubset(frame.columns) else pd.DataFrame()
            if not risk_frame.empty:
                st.bar_chart(risk_frame.set_index("名称")["高点回撤"])


def _build_etf_analyst_reports(result: dict) -> list[dict]:
    now = result.get("generated_at") or datetime.now().isoformat(timespec="seconds")
    screener = result.get("screener", [])
    risk = result.get("risk_radar", [])
    premium = result.get("premium_discount", [])
    dca = result.get("dca_plans", [])
    comparison = result.get("comparison", [])
    top = _top_screener_item(screener)
    return [
        {
            "agent_name": "流动性分析师",
            "agent_role": "评估成交额、规模和交易拥挤度，避免难买难卖的ETF。",
            "focus_areas": ["成交额", "规模", "交易活跃度"],
            "timestamp": now,
            "analysis": _liquidity_analysis(screener),
        },
        {
            "agent_name": "估值回撤分析师",
            "agent_role": "结合高点回撤、低点反弹和近一年表现判断修复空间。",
            "focus_areas": ["高点回撤", "近一年收益", "修复弹性"],
            "timestamp": now,
            "analysis": _valuation_analysis(screener, top),
        },
        {
            "agent_name": "风险控制分析师",
            "agent_role": "识别高波动、高溢价、低流动性和单一行业风险。",
            "focus_areas": ["风险标签", "波动率", "溢价折价"],
            "timestamp": now,
            "analysis": _risk_analysis(risk, premium),
        },
        {
            "agent_name": "配置策略分析师",
            "agent_role": "把分析结果转成定投、观察和组合配置建议。",
            "focus_areas": ["定投计划", "ETF对比", "组合配置"],
            "timestamp": now,
            "analysis": _allocation_analysis(dca, comparison, top),
        },
    ]


def _build_final_summary(result: dict) -> dict:
    screener = result.get("screener", [])
    top = _top_screener_item(screener)
    risk_items = result.get("risk_radar", [])
    high_risk_count = sum(1 for item in risk_items if str(item.get("风险等级", "")).startswith("高"))
    rating = "观察"
    if top and float(top.get("筛选评分") or 0) >= 70 and high_risk_count == 0:
        rating = "积极观察"
    elif high_risk_count >= max(1, len(screener) // 2):
        rating = "谨慎"
    top_pick = f"{top.get('名称')}({top.get('代码')})" if top else "-"
    main_risk = _main_risk_label(risk_items)
    headline = (
        f"本次分析 {result.get('selected_count', len(screener))} 只ETF，成功形成 {len(screener)} 只的分析结果。"
        f"综合评级为“{rating}”，优先观察 {top_pick}。"
    )
    actions = [
        "先看流动性和溢价折价，避免在高溢价或成交额不足时追入。",
        "若用于定投，优先选择回撤充分、风险标签较少、成交额稳定的ETF。",
        "批量选择时注意主题重复暴露，多个ETF重仓同一行业时应降低合计仓位。",
    ]
    if result.get("dca_plans"):
        first_plan = result["dca_plans"][0]
        actions.insert(0, f"定投优先项：{first_plan.get('名称')}，当前档位为{first_plan.get('定投档位')}。")
    return {"rating": rating, "top_pick": top_pick, "main_risk": main_risk, "headline": headline, "actions": actions}


def _top_screener_item(screener: list[dict]) -> dict:
    if not screener:
        return {}
    return sorted(screener, key=lambda item: float(item.get("筛选评分") or 0), reverse=True)[0]


def _liquidity_analysis(screener: list[dict]) -> str:
    if not screener:
        return "暂无可用ETF明细，无法评估流动性。"
    frame = pd.DataFrame(screener)
    total_turnover = float(frame.get("成交额", pd.Series(dtype=float)).fillna(0).sum()) / 10000
    leaders = frame.sort_values("成交额", ascending=False).head(3)
    names = "、".join(f"{row['名称']}({row['代码']})" for _, row in leaders.iterrows())
    return f"本批ETF合计成交额约 {total_turnover:.0f} 万元。成交最活跃的是 {names}。优先使用成交额靠前的ETF执行，低成交额品种只适合观察或小额分批。"


def _valuation_analysis(screener: list[dict], top: dict) -> str:
    if not screener:
        return "暂无历史回撤分析结果。"
    frame = pd.DataFrame(screener)
    avg_drawdown = float(frame.get("高点回撤", pd.Series(dtype=float)).fillna(0).mean())
    top_text = f"{top.get('名称')}({top.get('代码')}) 筛选评分 {top.get('筛选评分')}" if top else "暂无明确优先项"
    return f"平均高点回撤约 {avg_drawdown:.2f}%。当前优先项为 {top_text}。若回撤来自行业周期而非结构性衰退，可进入观察；若反弹已经过高，应降低追涨权重。"


def _risk_analysis(risk: list[dict], premium: list[dict]) -> str:
    risk_labels = [str(item.get("风险标签", "")) for item in risk if item.get("风险标签")]
    premium_alerts = [item for item in premium if "高溢价" in str(item.get("状态", ""))]
    risk_text = "；".join(risk_labels[:5]) or "暂未形成显著风险标签"
    return f"风险标签集中在：{risk_text}。高溢价样本 {len(premium_alerts)} 只。买入前应优先排除高溢价、跟踪误差大、规模过小和成交额异常的ETF。"


def _allocation_analysis(dca: list[dict], comparison: list[dict], top: dict) -> str:
    if dca:
        first = dca[0]
        dca_text = f"{first.get('名称')} 当前建议月定投金额 {first.get('建议月定投金额')}，停止条件：{first.get('停止条件')}"
    else:
        dca_text = "本次未启用或未生成定投计划"
    compare_text = f"已生成 {len(comparison)} 条ETF对比记录。" if comparison else "本次未启用ETF对比。"
    top_text = f"组合核心可先观察 {top.get('名称')}({top.get('代码')})。" if top else "暂无组合核心候选。"
    return f"{dca_text}。{compare_text}{top_text} 执行上建议把批量ETF分成核心、卫星和观察三类，而不是等权买入。"


def _main_risk_label(risk_items: list[dict]) -> str:
    labels = []
    for item in risk_items:
        labels.extend([part.strip() for part in str(item.get("风险标签", "")).split("；") if part.strip()])
    if not labels:
        return "暂无明显集中风险"
    return pd.Series(labels).value_counts().index[0]


def _analyze_etfs(
    analyzer: ETFToolkitAnalyzer,
    selected_rows: list[dict],
    topics: list[str],
    settings: dict,
    start_date: str,
    enable_ai_review: bool = False,
    ai_model: str = MODELSCOPE_MODELS[0],
) -> dict:
    if len(selected_rows) == 1:
        result = _analyze_single_etf(analyzer, selected_rows[0], topics, settings, start_date)
        result["analysis_mode"] = "single"
        result["selected_count"] = 1
        result["selected_etfs"] = [result.get("selected_etf", {})]
        result["result_type"] = str(result.get("selected_etf", {}).get("代码", "single_etf"))
        result["analyst_reports"] = _build_etf_analyst_reports(result)
        result["final_summary"] = _build_final_summary(result)
        result["ai_review"] = _run_modelscope_ai_review(result, ai_model) if enable_ai_review else {"status": "disabled"}
        return result

    errors = []
    screener = []
    for selected_row in selected_rows:
        code = str(selected_row["代码"]).zfill(6)
        try:
            history = analyzer.history_fetcher(code, start_date)
            row = analyzer._analyze_one(selected_row, history, FundResearchConfig(start_date=start_date))
            if row:
                screener.append(analyzer._enrich_toolkit_row(row))
            else:
                errors.append(f"{code}: 历史数据不足，未形成分析结果")
        except Exception as exc:
            errors.append(f"{code}: {type(exc).__name__}: {exc}")

    config = ETFToolkitConfig(
        max_history=len(selected_rows),
        min_turnover=float(settings.get("analysis", {}).get("min_turnover_wan", 3000)) * 10_000,
        monthly_budget=float(settings.get("analysis", {}).get("monthly_budget", 5000)),
        holding_top_n=min(5, max(1, len(screener))),
        include_premium_discount="溢价折价监控" in topics,
        include_holdings="持仓穿透" in topics,
        include_index_info="ETF对比" in topics,
        cache_ttl_minutes=int(settings.get("analysis", {}).get("cache_ttl_minutes", 30)),
        start_date=start_date,
    )
    frame = pd.DataFrame(screener)
    rotation = analyzer._build_rotation(frame) if screener else []
    premium_discount = analyzer._build_premium_discount(screener, config) if screener and "溢价折价监控" in topics else []
    dca_plans = analyzer._build_dca_plans(screener, config.monthly_budget) if screener and "定投计划" in topics else []
    risk_radar = analyzer._build_risk_radar(screener) if screener and "风险雷达" in topics else []
    comparison = analyzer._build_comparison(screener, config) if screener and "ETF对比" in topics else []
    opportunity_pool = analyzer._build_opportunity_pool(screener) if screener else {}
    periodic_report = analyzer._build_periodic_report(screener, rotation, opportunity_pool) if screener and "日报周报" in topics else {}
    holdings = (
        analyzer._build_holdings_analysis(screener, min(5, len(screener)))
        if screener and "持仓穿透" in topics
        else {"ETF持仓明细": [], "重复暴露": [], "errors": [], "skipped": "未选择持仓穿透"}
    )
    portfolios = {profile: analyzer._build_portfolio(frame, profile) for profile in ("稳健", "平衡", "进取")} if screener else {}
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
    selected_etfs = [
        {"代码": str(row.get("代码", "")).zfill(6), "名称": row.get("名称"), "分类": row.get("分类")}
        for row in selected_rows
    ]
    result = {
        "success": bool(screener),
        "analysis_mode": "batch",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_etf": selected_etfs[0] if selected_etfs else {},
        "selected_etfs": selected_etfs,
        "selected_count": len(selected_rows),
        "selected_topics": topics,
        "config": config.__dict__,
        "market_snapshot_count": len(selected_rows),
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
        "result_type": f"batch_{len(selected_rows)}",
    }
    result["analyst_reports"] = _build_etf_analyst_reports(result)
    result["final_summary"] = _build_final_summary(result)
    result["ai_review"] = _run_modelscope_ai_review(result, ai_model) if enable_ai_review else {"status": "disabled"}
    return result


def _run_modelscope_ai_review(result: dict, model: str) -> dict:
    if model not in MODELSCOPE_MODELS:
        return {"success": False, "model": model, "error": "模型不在ModelScope ETF复核白名单"}
    if not os.getenv("MODELSCOPE_API_KEY", "").strip():
        return {"success": False, "model": model, "error": "MODELSCOPE_API_KEY未配置"}
    prompt = _build_ai_review_prompt(result)
    started = datetime.now()
    try:
        response = AIEngine(default_model=model).chat(
            [
                {
                    "role": "system",
                    "content": "你是ETF投研复核智能体。只基于用户给出的结构化数据做审慎分析，不承诺收益，不编造外部事实。",
                },
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.2,
            max_tokens=1400,
            allowed_providers={"modelscope"},
            use_pool=False,
        )
        if not response.ok:
            return {"success": False, "model": model, "provider": response.provider, "error": response.error, "latency_seconds": (datetime.now() - started).total_seconds()}
        return {
            "success": True,
            "model": response.model,
            "provider": response.provider,
            "content": response.content,
            "latency_seconds": (datetime.now() - started).total_seconds(),
        }
    except Exception as exc:
        return {"success": False, "model": model, "error": str(exc), "latency_seconds": (datetime.now() - started).total_seconds()}


def _build_ai_review_prompt(result: dict) -> str:
    screener = pd.DataFrame(result.get("screener", []))
    if not screener.empty:
        columns = [c for c in ["代码", "名称", "分类", "最新价", "高点回撤", "近一年收益", "年化波动", "成交额", "筛选评分", "风险标签"] if c in screener.columns]
        table_text = screener[columns].head(20).to_csv(index=False)
    else:
        table_text = "无成功分析ETF"
    risk = result.get("risk_radar", [])[:10]
    dca = result.get("dca_plans", [])[:10]
    final_summary = result.get("final_summary") or _build_final_summary(result)
    return f"""
请对下面ETF批量分析结果做二次复核，输出总分总结构，控制在900字以内：

要求：
1. 先给一句总判断。
2. 分别从流动性、估值/回撤、风险、配置策略四个角度复核。
3. 指出最值得观察的ETF和必须回避/谨慎的风险点。
4. 不要给确定收益承诺，不要说半年必涨，不构成投资建议。

基础结论：
{final_summary}

ETF明细：
{table_text}

风险雷达样本：
{risk}

定投计划样本：
{dca}
""".strip()


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
