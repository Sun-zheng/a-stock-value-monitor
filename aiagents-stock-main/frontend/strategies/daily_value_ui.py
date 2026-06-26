from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(
    os.getenv("A_STOCK_VALUE_MONITOR_ROOT", Path(__file__).resolve().parents[3])
)
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
HISTORY_PREFERRED_COLUMNS = [
    "运行日期", "估值交易日", "代码", "名称", "行业", "上市板块", "当前价格",
    "总市值", "流通市值", "PE TTM", "PB", "PS", "股息率",
    "ROE", "扣非ROE", "ROIC", "毛利率", "净利率", "资产负债率",
    "营业收入", "归母净利润", "扣非净利润", "经营性现金流净额",
    "自由现金流", "经营现金流/净利润", "标准化自由现金流",
    "营业收入多年趋势", "归母净利润多年趋势", "ROE口径", "ROE报告期",
    "综合评分", "估值评分", "现金流评分", "盈利能力评分", "资产负债评分",
    "成长性评分", "分红评分", "安全边际", "保守合理市值", "中性合理市值",
    "乐观合理市值", "估值结论类型", "一票否决原因", "长期投资关键证据",
    "是否正式推荐", "是否观察股票", "未达推荐原因", "下一步观察重点",
]


def _run_main(*args: str, timeout: int = 900) -> tuple[bool, str]:
    result = subprocess.run(
        [str(PYTHON), "main.py", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return result.returncode == 0, (result.stdout or result.stderr)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _latest_report_day() -> str | None:
    paths = sorted((PROJECT_ROOT / "reports").glob("*_scan_summary.json"), reverse=True)
    return paths[0].name[:10] if paths else None


def _dataset_path(dataset: str, day: str) -> Path:
    return PROJECT_ROOT / "data" / "daily_stock_history" / dataset / f"{day}.csv"


def _sqlite_table_name(dataset: str) -> str:
    return "daily_" + "".join(ch if ch.isalnum() else "_" for ch in dataset.lower())


@st.cache_data(ttl=60)
def _read_dataset(dataset: str, day: str) -> pd.DataFrame:
    db_path = PROJECT_ROOT / "data" / "daily_stock_history" / "stock_history_index.sqlite3"
    if db_path.exists():
        table = _sqlite_table_name(dataset)
        try:
            with sqlite3.connect(db_path) as conn:
                return pd.read_sql_query(
                    f'SELECT * FROM "{table}" WHERE "运行日期" = ?',
                    conn,
                    params=[day],
                    dtype={"代码": str},
                )
        except Exception:
            pass
    path = _dataset_path(dataset, day)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"代码": str})


def _display_schedule_status() -> None:
    ok, output = _run_main("--schedule-status", timeout=30)
    if not ok:
        st.error(output[-2000:])
        return
    try:
        payload = json.loads(output)
    except ValueError:
        st.code(output[-4000:])
        return
    st.caption(f"调度类型：{payload.get('kind', 'unknown')}")
    units = payload.get("status", {}).get("units", [])
    if units:
        table = pd.DataFrame(units)
        keep = [
            field
            for field in ["Id", "ActiveState", "SubState", "UnitFileState", "NextElapseUSecRealtime"]
            if field in table.columns
        ]
        st.dataframe(table[keep], width="stretch", hide_index=True)
    else:
        st.json(payload)


def _display_runtime_status() -> None:
    ok, output = _run_main("--run-status", timeout=30)
    if not ok:
        st.error(output[-2000:])
        return
    try:
        status = json.loads(output)
    except ValueError:
        st.code(output[-4000:])
        return
    latest = status.get("最近成功运行") or status.get("最近运行") or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("最近状态", latest.get("status", "-"))
    c2.metric("阶段", latest.get("stage", "-"))
    c3.metric("运行日期", latest.get("run_date", "-"))
    with st.expander("运行状态明细"):
        st.json(status)


def _display_scan(day: str) -> None:
    scan = _load_json(PROJECT_ROOT / "reports" / f"{day}_scan_summary.json")
    if not scan:
        st.warning("未找到当天扫描摘要。")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("推荐范围股票", scan.get("推荐范围股票数量", "-"))
    c2.metric("候选检查", scan.get("正式条件检查数量", "-"))
    c3.metric("正式推荐", scan.get("最终推荐数量", "-"))
    c4.metric("观察股票", scan.get("观察股票数量", "-"))
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("估值覆盖率", scan.get("估值覆盖率", "-"))
    c6.metric("财报覆盖率", scan.get("财报覆盖率", "-"))
    c7.metric("现金流覆盖率", scan.get("现金流覆盖率", "-"))
    c8.metric("估值交易日", scan.get("估值数据交易日", "-"))

    observations = pd.DataFrame(scan.get("观察股票", []))
    if not observations.empty:
        fields = [
            "观察排名", "代码", "名称", "行业", "综合评分", "安全边际",
            "未达推荐原因", "下一步观察重点",
        ]
        st.markdown("### 今日观察池")
        st.dataframe(observations[[field for field in fields if field in observations]], width="stretch", hide_index=True)

    report_path = PROJECT_ROOT / "reports" / f"{day}_report.md"
    if report_path.exists():
        with st.expander("最终报告"):
            st.markdown(report_path.read_text(encoding="utf-8"))


def _display_history(day: str) -> None:
    st.markdown("### 每日股票数据")
    dataset = st.selectbox(
        "数据集",
        [
            ("all_stocks", "全市场快照"),
            ("light_candidates", "轻筛候选"),
            ("reviewed_candidates", "深度检查候选"),
            ("passed_candidates", "通过一票否决候选"),
        ],
        format_func=lambda value: value[1],
    )[0]
    frame = _read_dataset(dataset, day)
    if frame.empty:
        st.info("暂无该数据集。")
        return
    query = st.text_input("按代码/名称/行业筛选", "")
    filtered = frame
    if query:
        text = frame.astype(str).agg(" ".join, axis=1)
        filtered = frame[text.str.contains(query, case=False, na=False)]
    st.caption(f"{len(filtered)} / {len(frame)} 行")
    columns = [field for field in HISTORY_PREFERRED_COLUMNS if field in filtered.columns]
    columns.extend(field for field in filtered.columns if field not in columns)
    selected_columns = st.multiselect("显示字段", columns, default=columns[: min(len(columns), 36)])
    if not selected_columns:
        selected_columns = columns[: min(len(columns), 36)]
    st.dataframe(filtered[selected_columns].head(1000), width="stretch", hide_index=True)


def display_daily_value_strategy() -> None:
    st.subheader("每日价值策略控制台")
    st.caption(f"项目根目录：{PROJECT_ROOT}")

    day = _latest_report_day()
    selected_day = st.text_input("报告日期", value=day or "")

    actions = st.columns(4)
    if actions[0].button("安装/刷新调度", width="stretch"):
        ok, output = _run_main("--apply-schedule", timeout=120)
        st.success("调度已刷新") if ok else st.error(output[-3000:])
        if ok:
            st.code(output[-4000:])
    if actions[1].button("运行基础流水线", width="stretch"):
        ok, output = _run_main("--run-pipeline", timeout=1800)
        st.success("基础流水线完成") if ok else st.error(output[-4000:])
        st.code(output[-4000:])
        st.cache_data.clear()
    if actions[2].button("执行最终交付", width="stretch"):
        ok, output = _run_main("--deliver-final-report", timeout=900)
        st.success("最终交付完成") if ok else st.error(output[-4000:])
        st.code(output[-4000:])
    if actions[3].button("策略验收", width="stretch"):
        ok, output = _run_main("--strategy-validation", timeout=1200)
        st.success("策略验收通过") if ok else st.error(output[-4000:])
        st.code(output[-4000:])

    tab_status, tab_scan, tab_history = st.tabs(["运行与调度", "日报结果", "每日股票数据"])
    with tab_status:
        _display_runtime_status()
        st.markdown("### 调度状态")
        _display_schedule_status()
    with tab_scan:
        if selected_day:
            _display_scan(selected_day)
    with tab_history:
        if selected_day:
            _display_history(selected_day)
