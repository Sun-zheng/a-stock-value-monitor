from __future__ import annotations

import json
import os
import shutil
import subprocess
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

from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitAnalyzer
from backend.strategies.index_fund_research.etf_toolkit_settings import (
    build_alerts,
    build_analyzer_config,
    load_etf_toolkit_settings,
    save_etf_toolkit_settings,
)
from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore
from src.schedule_settings import load_schedule_settings, save_schedule_settings
from frontend.strategies.index_fund_research_ui import (
    _create_lark_doc,
    _send_report_email,
)


FEATURES = [
    "总览",
    "全市场筛选器",
    "ETF轮动策略",
    "ETF组合配置器",
    "定投计划",
    "溢价折价监控",
    "持仓穿透",
    "风险雷达",
    "ETF对比",
    "日报周报",
    "机会池",
    "触发提醒",
    "历史记录",
    "完整报告",
    "数据说明",
]


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
    st.caption("可配置的ETF筛选、轮动、定投、溢价折价、持仓穿透、风险雷达、对比、日报周报和机会池工作台。")

    settings = st.session_state.get("etf_toolkit_settings")
    if settings is None:
        settings = load_etf_toolkit_settings(PROJECT_ROOT)
        st.session_state.etf_toolkit_settings = settings

    _display_config_panel(settings)

    result = st.session_state.get("etf_toolkit_result")
    if result:
        _display_summary(result)

    col_run, col_save, col_status = st.columns([1.2, 1.2, 3])
    with col_run:
        run_now = st.button("运行ETF策略工具箱", type="primary", width="stretch")
    with col_save:
        save_only = st.button("保存当前配置", width="stretch")
    with col_status:
        st.caption("默认关闭持仓穿透和基金档案，可显著减少响应时间；需要深度分析时再打开。")

    if save_only:
        path = save_etf_toolkit_settings(PROJECT_ROOT, settings)
        _sync_global_etf_schedule(settings)
        st.success(f"配置已保存：{path}")

    if run_now:
        _run_toolkit(settings)

    result = st.session_state.get("etf_toolkit_result")
    if not result:
        st.info("先检查左侧配置，然后点击运行。默认会快速生成筛选、轮动、定投、溢价折价、风险、对比、日报和机会池。")
        return

    feature = st.radio("选择功能", FEATURES, horizontal=True, key="etf_toolkit_feature")
    _display_feature(feature, result, settings)


def _display_config_panel(settings: dict) -> None:
    analysis = settings["analysis"]
    monitor = settings["monitor"]
    delivery = settings["delivery"]
    storage = settings["storage"]
    with st.expander("运行与监控配置", expanded=True):
        tab_analysis, tab_monitor, tab_delivery, tab_storage = st.tabs(["分析参数", "监控触发", "推送与多维表格", "缓存与历史"])
        with tab_analysis:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                analysis["max_history"] = st.number_input("历史分析数量", 10, 200, int(analysis["max_history"]), 10)
                analysis["min_turnover_wan"] = st.number_input("最低成交额(万元)", 100, 100000, int(analysis["min_turnover_wan"]), 100)
            with col2:
                analysis["monthly_budget"] = st.number_input("定投月预算(元)", 100.0, 1_000_000.0, float(analysis["monthly_budget"]), 500.0)
                analysis["holding_top_n"] = st.number_input("持仓穿透ETF数", 0, 20, int(analysis["holding_top_n"]), 1)
            with col3:
                analysis["min_price"] = st.number_input("最低价格", 0.0, 1000.0, float(analysis["min_price"]), 0.1)
                analysis["start_date"] = st.text_input("历史起始日", str(analysis["start_date"]))
            with col4:
                analysis["cache_ttl_minutes"] = st.number_input("缓存分钟数", 1, 240, int(analysis["cache_ttl_minutes"]), 5)
                analysis["include_premium_discount"] = st.checkbox("抓取溢价折价", bool(analysis["include_premium_discount"]))
                analysis["include_index_info"] = st.checkbox("抓取基金档案", bool(analysis["include_index_info"]))
                analysis["include_holdings"] = st.checkbox("抓取持仓穿透", bool(analysis["include_holdings"]))
        with tab_monitor:
            col1, col2, col3 = st.columns(3)
            with col1:
                monitor["enabled"] = st.checkbox("启用ETF定时监控配置", bool(monitor["enabled"]))
                times = st.text_input("定时时间", ",".join(monitor.get("schedule_times", [])), help="多个时间用英文逗号分隔，例如 15:20,20:30")
                monitor["schedule_times"] = [item.strip() for item in times.split(",") if item.strip()]
                monitor["frequency"] = st.selectbox("频率", ["工作日", "每天"], index=0 if monitor.get("frequency") == "工作日" else 1)
            with col2:
                dca = monitor["dca"]
                dca["enabled"] = st.checkbox("定投计划触发", bool(dca["enabled"]))
                dca["trigger_drawdown_pct"] = st.number_input("开始定投回撤(%)", -80.0, -5.0, float(dca["trigger_drawdown_pct"]), 1.0)
                dca["increase_drawdown_pct"] = st.number_input("提高定投回撤(%)", -80.0, -5.0, float(dca["increase_drawdown_pct"]), 1.0)
                dca["focus_drawdown_pct"] = st.number_input("重点观察回撤(%)", -90.0, -10.0, float(dca["focus_drawdown_pct"]), 1.0)
                dca["min_score"] = st.number_input("定投最低评分", 0.0, 100.0, float(dca["min_score"]), 1.0)
            with col3:
                premium = monitor["premium_discount"]
                periodic = monitor["periodic_report"]
                premium["enabled"] = st.checkbox("溢价折价触发", bool(premium["enabled"]))
                premium["premium_alert_pct"] = st.number_input("高溢价阈值(折价率<=)", -10.0, 0.0, float(premium["premium_alert_pct"]), 0.1)
                premium["discount_alert_pct"] = st.number_input("明显折价阈值(折价率>=)", 0.0, 10.0, float(premium["discount_alert_pct"]), 0.1)
                premium["min_turnover_wan"] = st.number_input("提醒最低成交额(万元)", 100, 100000, int(premium["min_turnover_wan"]), 100)
                periodic["enabled"] = st.checkbox("日报/周报摘要", bool(periodic["enabled"]))
        with tab_delivery:
            col1, col2, col3 = st.columns(3)
            with col1:
                delivery["email_enabled"] = st.checkbox("触发后发送邮件", bool(delivery["email_enabled"]))
                delivery["send_only_when_alert"] = st.checkbox("仅有触发提醒才发送", bool(delivery["send_only_when_alert"]))
            with col2:
                delivery["lark_doc_enabled"] = st.checkbox("触发后创建飞书文档", bool(delivery["lark_doc_enabled"]))
                delivery["lark_bitable_enabled"] = st.checkbox("写入飞书多维表格", bool(delivery["lark_bitable_enabled"]))
            with col3:
                delivery["lark_bitable_config_path"] = st.text_input("多维表格配置路径", str(delivery["lark_bitable_config_path"]))
                st.caption("配置文件需包含 base_token、table_id，可复用现有 lark-cli 授权。")
        with tab_storage:
            col1, col2, col3 = st.columns(3)
            with col1:
                storage["cache_enabled"] = st.checkbox("启用结果缓存", bool(storage["cache_enabled"]))
                storage["reuse_cached_result"] = st.checkbox("优先复用未过期缓存", bool(storage["reuse_cached_result"]))
                policy_options = ["same_day", "ttl", "off"]
                storage["cache_policy"] = st.selectbox(
                    "缓存策略",
                    policy_options,
                    index=policy_options.index(storage.get("cache_policy", "same_day")) if storage.get("cache_policy", "same_day") in policy_options else 0,
                    format_func=lambda value: {"same_day": "同日复用", "ttl": "按分钟TTL", "off": "不复用缓存"}[value],
                )
            with col2:
                storage["history_enabled"] = st.checkbox("保存ETF历史记录", bool(storage["history_enabled"]))
                storage["history_limit"] = st.number_input("最多保留历史记录", 10, 1000, int(storage["history_limit"]), 10)
            with col3:
                st.caption("缓存用于加速相同参数重复运行；历史记录用于回看、机会池连续观察和定时任务审计。")
                st.code("data/etf_toolkit/cache\ndata/etf_toolkit/history")


def _run_toolkit(settings: dict) -> None:
    save_etf_toolkit_settings(PROJECT_ROOT, settings)
    _sync_global_etf_schedule(settings)
    config = build_analyzer_config(settings)
    store = ETFToolkitStore(PROJECT_ROOT)
    with st.spinner("正在运行ETF策略工具箱..."):
        result = store.load_cached_result(settings)
        if result is None:
            result = ETFToolkitAnalyzer().analyze_toolkit(config)
            result["cache_hit"] = False
        result["alerts"] = build_alerts(result, settings)
        report_path = _save_toolkit_report(result)
        result["report_path"] = str(report_path)
        storage_paths = store.save_result(result, settings)
        result.update(storage_paths)
        st.session_state.etf_toolkit_result = result
    if result.get("success"):
        cache_label = "（使用缓存）" if result.get("cache_hit") else ""
        st.success(f"分析完成{cache_label}，报告已保存：{report_path}")
    else:
        st.warning("分析完成，但暂无可展示结果。")
    _deliver_if_needed(result, settings)


def _deliver_if_needed(result: dict, settings: dict) -> None:
    delivery = settings.get("delivery", {})
    alerts = result.get("alerts", [])
    if delivery.get("send_only_when_alert") and not alerts:
        st.info("未触发提醒，已按配置跳过邮件和飞书推送。")
        return
    subject = f"ETF策略工具箱报告 - {datetime.now().strftime('%Y-%m-%d')}"
    if delivery.get("email_enabled"):
        ok, message = _send_report_email(subject, result.get("report", ""))
        st.success(message) if ok else st.error(message)
    if delivery.get("lark_doc_enabled"):
        ok, message = _create_lark_doc(result)
        st.success(message) if ok else st.error(message)
    if delivery.get("lark_bitable_enabled"):
        ok, message = _write_lark_bitable(result, settings)
        st.success(message) if ok else st.error(message)


def _display_summary(result: dict) -> None:
    metrics = st.columns(6)
    metrics[0].metric("ETF快照", result.get("market_snapshot_count", 0))
    metrics[1].metric("完成分析", result.get("analyzed_count", 0))
    metrics[2].metric("轮动分类", len(result.get("rotation", [])))
    metrics[3].metric("机会池", sum(len(v) for v in result.get("opportunity_pool", {}).values() if isinstance(v, list)))
    metrics[4].metric("触发提醒", len(result.get("alerts", [])))
    metrics[5].metric("错误", result.get("error_count", 0))
    if result.get("cache_hit"):
        st.caption(f"本次使用缓存：{result.get('cache_path', '-')}")
    elif result.get("history_path"):
        st.caption(f"本次已写入ETF历史记录：{result.get('history_path')}")


def _display_feature(feature: str, result: dict, settings: dict) -> None:
    if feature == "总览":
        _display_overview(result)
    elif feature == "全市场筛选器":
        _display_screener(result)
    elif feature == "ETF轮动策略":
        _display_table(result.get("rotation", []), "暂无轮动结果。")
    elif feature == "ETF组合配置器":
        _display_portfolio(result)
    elif feature == "定投计划":
        _display_table(result.get("dca_plans", []), "暂无定投计划。")
    elif feature == "溢价折价监控":
        _display_premium(result)
    elif feature == "持仓穿透":
        _display_holdings(result)
    elif feature == "风险雷达":
        _display_risk(result)
    elif feature == "ETF对比":
        _display_compare(result)
    elif feature == "日报周报":
        _display_periodic(result)
    elif feature == "机会池":
        _display_pool(result)
    elif feature == "触发提醒":
        _display_alerts(result, settings)
    elif feature == "历史记录":
        _display_history()
    elif feature == "完整报告":
        st.markdown(result.get("report", ""))
    else:
        st.json({
            "config": result.get("config", {}),
            "settings": settings,
            "workflow": result.get("workflow", []),
            "report_path": result.get("report_path"),
            "cache_path": result.get("cache_path"),
            "history_path": result.get("history_path"),
            "errors": result.get("errors", []),
        })


def _display_overview(result: dict) -> None:
    col1, col2 = st.columns(2)
    with col1:
        rotation = pd.DataFrame(result.get("rotation", []))
        st.markdown("#### 轮动强度")
        if not rotation.empty:
            st.bar_chart(rotation.set_index("分类")["轮动评分"])
        else:
            st.info("暂无轮动结果。")
    with col2:
        risk = pd.DataFrame(result.get("risk_radar", []))
        st.markdown("#### 风险等级")
        if not risk.empty:
            st.bar_chart(risk["风险等级"].value_counts())
        else:
            st.info("暂无风险雷达。")
    st.markdown("#### 触发提醒")
    _display_table(result.get("alerts", []), "暂无触发提醒。")


def _display_screener(result: dict) -> None:
    frame = pd.DataFrame(result.get("screener", []))
    if frame.empty:
        st.info("暂无筛选结果。")
        return
    col1, col2, col3 = st.columns(3)
    with col1:
        categories = ["全部"] + sorted(frame["分类"].dropna().unique().tolist())
        selected_category = st.selectbox("分类", categories)
    with col2:
        min_score = st.slider("最低筛选评分", 0, 100, 0)
    with col3:
        max_vol = st.slider("最高年化波动", 0, 120, 120)
    filtered = frame[frame["筛选评分"].ge(min_score) & frame["年化波动"].le(max_vol)]
    if selected_category != "全部":
        filtered = filtered[filtered["分类"].eq(selected_category)]
    columns = [
        "代码", "名称", "分类", "最新价", "高点回撤", "近一年收益",
        "低点反弹", "年化波动", "成交额", "筛选评分", "风险标签",
    ]
    st.caption(f"{len(filtered)} / {len(frame)} 只")
    st.dataframe(filtered[[c for c in columns if c in filtered.columns]], width="stretch", hide_index=True)


def _display_portfolio(result: dict) -> None:
    portfolios = result.get("portfolios", {})
    if not portfolios:
        st.info("暂无组合配置。")
        return
    profile = st.radio("风险偏好", list(portfolios.keys()), horizontal=True)
    selected = portfolios.get(profile, {})
    st.markdown(selected.get("notes", ""))
    _display_table(selected.get("positions", []), "暂无组合。")


def _display_premium(result: dict) -> None:
    frame = pd.DataFrame(result.get("premium_discount", []))
    if frame.empty:
        st.info("未启用溢价折价抓取，或暂无数据。")
        return
    status = ["全部"] + sorted(frame["状态"].dropna().unique().tolist())
    selected_status = st.selectbox("状态", status)
    filtered = frame if selected_status == "全部" else frame[frame["状态"].eq(selected_status)]
    st.dataframe(filtered, width="stretch", hide_index=True)


def _display_holdings(result: dict) -> None:
    holdings = result.get("holdings", {})
    if holdings.get("skipped"):
        st.info(holdings["skipped"])
        return
    overlap = pd.DataFrame(holdings.get("重复暴露", []))
    st.markdown("#### 重复暴露")
    _display_table(overlap, "暂无重复暴露，或持仓数据暂未返回。")
    st.markdown("#### ETF前十大持仓")
    for item in holdings.get("ETF持仓明细", []):
        with st.expander(f"{item.get('名称')}（{item.get('代码')}） 前十大集中度 {item.get('前十大集中度')}%"):
            _display_table(item.get("前十大持仓", []), "暂无持仓明细。")
    if holdings.get("errors"):
        st.warning(f"持仓抓取失败样例：{holdings.get('errors')[:3]}")


def _display_risk(result: dict) -> None:
    frame = pd.DataFrame(result.get("risk_radar", []))
    if frame.empty:
        st.info("暂无风险雷达。")
        return
    levels = sorted(frame["风险等级"].dropna().unique().tolist())
    selected = st.multiselect("风险等级", levels, default=levels)
    filtered = frame[frame["风险等级"].isin(selected)] if selected else frame
    st.dataframe(filtered, width="stretch", hide_index=True)


def _display_compare(result: dict) -> None:
    frame = pd.DataFrame(result.get("comparison", []))
    if frame.empty:
        st.info("暂无ETF对比数据。")
        return
    names = frame["名称"].dropna().tolist()
    selected_names = st.multiselect("选择2-5只ETF对比", names, default=names[: min(5, len(names))], max_selections=5)
    filtered = frame[frame["名称"].isin(selected_names)] if selected_names else frame.head(5)
    st.dataframe(filtered, width="stretch", hide_index=True)


def _display_periodic(result: dict) -> None:
    periodic = result.get("periodic_report", {})
    st.markdown(f"#### {periodic.get('标题', 'ETF定时日报/周报')}")
    for sentence in periodic.get("总览", []):
        st.markdown(f"- {sentence}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### 强势行业ETF")
        _display_table(periodic.get("强势行业ETF", []), "暂无强势行业。")
    with col2:
        st.markdown("##### 深回撤ETF")
        _display_table(periodic.get("深回撤ETF", []), "暂无深回撤ETF。")
    with col3:
        st.markdown("##### 放量ETF")
        _display_table(periodic.get("放量ETF", []), "暂无放量ETF。")


def _display_pool(result: dict) -> None:
    pool = result.get("opportunity_pool", {})
    for name, items in pool.items():
        if isinstance(items, list):
            st.markdown(f"#### {name}")
            _display_table(items, "暂无入池ETF。")
    if pool.get("说明"):
        st.caption(pool["说明"])


def _display_alerts(result: dict, settings: dict) -> None:
    st.markdown("#### 本次触发提醒")
    _display_table(result.get("alerts", []), "暂无触发提醒。")
    st.markdown("#### 当前监控配置")
    st.json(settings.get("monitor", {}))


def _display_history() -> None:
    store = ETFToolkitStore(PROJECT_ROOT)
    rows = store.list_history(limit=50)
    if not rows:
        st.info("暂无ETF历史记录。运行一次工具箱后会自动写入。")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(frame, width="stretch", hide_index=True)
    path_options = frame["path"].tolist() if "path" in frame.columns else []
    selected = st.selectbox("选择历史记录", path_options)
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("加载历史结果", width="stretch"):
            result = store.load_history_result(selected)
            if result:
                st.session_state.etf_toolkit_result = result
                st.success("已加载历史结果。")
            else:
                st.error("历史结果读取失败。")
    with col2:
        st.caption("历史记录保存在本地 data/etf_toolkit/history，适合做回看、定时任务审计和后续机会池连续天数计算。")


def _display_table(data: object, empty_message: str) -> None:
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if frame.empty:
        st.info(empty_message)
    else:
        st.dataframe(frame, width="stretch", hide_index=True)


def _sync_global_etf_schedule(settings: dict) -> None:
    schedule_settings = load_schedule_settings(PROJECT_ROOT)
    monitor = settings.get("monitor", {})
    schedule_settings["etf_toolkit"]["enabled"] = bool(monitor.get("enabled", False))
    schedule_settings["etf_toolkit"]["times"] = monitor.get("schedule_times", ["15:20"]) or ["15:20"]
    schedule_settings["etf_toolkit"]["frequency"] = monitor.get("frequency", "工作日")
    save_schedule_settings(PROJECT_ROOT, schedule_settings)


def _write_lark_bitable(result: dict, settings: dict) -> tuple[bool, str]:
    delivery = settings.get("delivery", {})
    config_path = Path(str(delivery.get("lark_bitable_config_path") or "data/etf_toolkit_lark_table.json"))
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        return False, f"飞书多维表格配置不存在: {config_path}"
    if shutil.which("lark-cli") is None:
        return False, "未找到 lark-cli"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"飞书多维表格配置读取失败: {exc}"

    fields = ["执行日期", "模块", "类型", "代码", "名称", "触发原因", "触发值", "建议", "完整报告"]
    ok, message = _ensure_lark_fields(config, fields)
    if not ok:
        return False, message

    alerts = result.get("alerts", []) or [{
        "类型": "ETF报告",
        "代码": "",
        "名称": "ETF策略工具箱",
        "触发原因": "无触发提醒，记录本次运行摘要",
        "触发值": "",
        "建议": "查看完整报告。",
    }]
    written = 0
    for alert in alerts:
        payload = {
            "执行日期": datetime.now().strftime("%Y-%m-%d"),
            "模块": "ETF策略工具箱",
            "类型": alert.get("类型", ""),
            "代码": alert.get("代码", ""),
            "名称": alert.get("名称", ""),
            "触发原因": alert.get("触发原因", ""),
            "触发值": alert.get("触发值", ""),
            "建议": alert.get("建议", ""),
            "完整报告": result.get("report", "")[:20000],
        }
        completed = subprocess.run(
            [
                "lark-cli", "base", "+record-upsert",
                "--base-token", config["base_token"],
                "--table-id", config["table_id"],
                "--json", json.dumps(payload, ensure_ascii=False),
                "--as", "user",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if completed.returncode != 0:
            return False, f"飞书多维表格写入失败: {(completed.stderr or completed.stdout)[-1000:]}"
        written += 1
    return True, f"飞书多维表格已写入 {written} 条记录"


def _ensure_lark_fields(config: dict, fields: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            "lark-cli", "base", "+field-list",
            "--base-token", config["base_token"],
            "--table-id", config["table_id"],
            "--limit", "200",
            "--as", "user",
            "--format", "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    if completed.returncode != 0:
        return False, f"飞书字段读取失败: {(completed.stderr or completed.stdout)[-1000:]}"
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        return False, f"飞书字段读取返回非JSON: {completed.stdout[-1000:]}"
    data = payload.get("data", {})
    existing = {item.get("name") for item in data.get("fields", data.get("items", [])) if isinstance(item, dict)}
    for name in fields:
        if name in existing:
            continue
        created = subprocess.run(
            [
                "lark-cli", "base", "+field-create",
                "--base-token", config["base_token"],
                "--table-id", config["table_id"],
                "--json", json.dumps({"type": "text", "name": name}, ensure_ascii=False),
                "--as", "user",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if created.returncode != 0:
            return False, f"飞书字段创建失败: {(created.stderr or created.stdout)[-1000:]}"
    return True, "字段已就绪"
