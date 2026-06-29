from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import settings
from src.ai_value_analysis import (
    append_ai_analysis,
    configured_analysis_models,
    format_ai_analysis_markdown,
    generate_ai_value_analysis,
    validate_ai_models,
)
from src.email_sender import send_email
from src.stock_index_store import query_stock_history
from src.trading_calendar import is_a_share_trading_day


LOW_PRICE_BULL_TIME = "14:00"


def _run_selector(project_root: Path, top_n: int, analysis_models: list[str] | None = None) -> dict:
    ai_root = project_root / "aiagents-stock-main"
    python = ai_root / ".venv/bin/python"
    command = [
        str(python),
        "tools/run_low_price_bull_daily.py",
        "--top-n",
        str(top_n),
        "--output",
    ]
    with tempfile.TemporaryDirectory(prefix="low-price-bull.") as temporary:
        output_path = Path(temporary) / "result.json"
        command.append(str(output_path))
        if analysis_models:
            command.extend(["--with-analysis", "--models", ",".join(analysis_models)])
        result = subprocess.run(
            command,
            cwd=ai_root,
            env={**os.environ, "AIAGENTS_ENV_FILE": str(Path.home() / ".config" / "a-stock-value-monitor" / "aiagents.env")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.getenv("LOW_PRICE_BULL_TOOL_TIMEOUT_SECONDS", "1800" if analysis_models else "600")),
            check=False,
        )
        if result.returncode or not output_path.exists():
            return {
                "success": False,
                "message": (result.stderr or result.stdout or "低价擒牛脚本未返回结果")[-3000:],
                "rows": 0,
                "records": [],
            }
        return json.loads(output_path.read_text(encoding="utf-8"))


def _pick(record: dict, *patterns: str):
    for pattern in patterns:
        for key, value in record.items():
            if pattern in str(key):
                return value
    return "数据不足"


def _to_number(value) -> float | None:
    try:
        if value in (None, "", "数据不足"):
            return None
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _normalized_code(value) -> str:
    text = str(value or "").strip().upper()
    return text.split(".")[0] if "." in text else text


def _record_code(record: dict) -> str:
    return str(_pick(record, "股票代码", "代码")).strip()


def _record_name(record: dict) -> str:
    return str(_pick(record, "股票简称", "名称")).strip()


def _missing(value) -> bool:
    return value in (None, "", "数据不足", "无", "N/A")


def _load_value_index(project_root: Path) -> pd.DataFrame:
    frame = query_stock_history(project_root / "data", "reviewed_candidates", limit=10000)
    if frame.empty:
        frame = query_stock_history(project_root / "data", "all_stocks", limit=10000)
    return frame


def _enrich_records_from_value_index(project_root: Path, records: list[dict]) -> list[dict]:
    if not records:
        return records
    frame = _load_value_index(project_root)
    if frame.empty or "代码" not in frame:
        return records

    indexed = frame.copy()
    indexed["_normalized_code"] = indexed["代码"].map(_normalized_code)
    by_code = indexed.drop_duplicates("_normalized_code").set_index("_normalized_code")
    enriched: list[dict] = []
    fill_pairs = [
        ("所属行业", "行业"),
        ("行业", "行业"),
        ("上市板块", "上市板块"),
        ("ROE", "ROE"),
        ("综合评分", "综合评分"),
        ("安全边际", "安全边际"),
        ("营业收入增长率", "营业收入同比增长率"),
    ]
    for record in records:
        item = dict(record)
        code = _normalized_code(_record_code(item))
        if code in by_code.index:
            source = by_code.loc[code]
            for target, source_field in fill_pairs:
                if source_field in source and _missing(item.get(target)):
                    item[target] = source[source_field]
        enriched.append(item)
    return enriched


def _fallback_from_value_index(project_root: Path, top_n: int) -> dict:
    frame = _load_value_index(project_root)
    if frame.empty:
        return {"success": False, "message": "问财失败，且本地价值索引为空", "rows": 0, "records": []}
    data = frame.copy()
    def series(field: str, default=None) -> pd.Series:
        if field in data:
            return data[field]
        return pd.Series(default, index=data.index)

    price = pd.to_numeric(series("当前价格"), errors="coerce")
    name = data.get("名称", pd.Series("", index=data.index)).astype(str)
    board = data.get("上市板块", pd.Series("", index=data.index)).astype(str)
    profit_growth = pd.to_numeric(series("归母净利润同比增长率"), errors="coerce")
    revenue_growth = pd.to_numeric(series("营业收入同比增长率"), errors="coerce")
    score = pd.to_numeric(series("综合评分", 0), errors="coerce")
    mask = (
        price.gt(0)
        & price.lt(10)
        & ~name.str.contains("ST", case=False, na=False)
        & ~board.str.contains("科创|创业", na=False)
    )
    growth_mask = profit_growth.ge(100) | revenue_growth.ge(50)
    selected = data[mask & growth_mask].copy()
    if selected.empty:
        selected = data[mask].copy()
        message = "问财失败，使用本地价值索引低价候选兜底；未强制满足净利增长>=100%"
    else:
        message = "问财失败，使用本地价值索引低价高增长候选兜底"
    selected["_sort_growth"] = profit_growth.reindex(selected.index).fillna(revenue_growth.reindex(selected.index)).fillna(-999)
    selected["_sort_score"] = score.reindex(selected.index).fillna(0)
    selected = selected.sort_values(["_sort_growth", "_sort_score"], ascending=[False, False]).head(top_n)
    records = []
    for _, row in selected.drop(columns=["_sort_growth", "_sort_score"], errors="ignore").iterrows():
        records.append(
            {
                "股票代码": row.get("代码", "数据不足"),
                "股票简称": row.get("名称", "数据不足"),
                "股价": row.get("当前价格", "数据不足"),
                "净利润增长率": row.get("归母净利润同比增长率", "数据不足"),
                "营业收入增长率": row.get("营业收入同比增长率", "数据不足"),
                "成交额": "本地索引无成交额",
                "所属行业": row.get("行业", "数据不足"),
                "ROE": row.get("ROE", "数据不足"),
                "综合评分": row.get("综合评分", "数据不足"),
                "安全边际": row.get("安全边际", "数据不足"),
                "数据来源": "本地价值索引兜底",
            }
        )
    return {"success": True, "message": message, "rows": len(records), "records": records}


def _low_price_bull_scan(result: dict) -> dict:
    stocks = []
    for index, record in enumerate(result.get("records", []), start=1):
        stocks.append(
            {
                "股票类型": "低价擒牛观察",
                "观察排名": index,
                "代码": _record_code(record),
                "名称": _record_name(record),
                "行业": _pick(record, "所属行业", "行业"),
                "上市板块": _pick(record, "上市板块"),
                "当前价格": _pick(record, "股价", "最新价", "收盘价"),
                "股价": _pick(record, "股价", "最新价", "收盘价"),
                "净利润增长率": _pick(record, "净利润增长率", "净利润同比增长率", "归属母公司股东的净利润"),
                "营业收入增长率": _pick(record, "营业收入增长率", "营业收入同比增长率"),
                "成交额": _pick(record, "成交额"),
                "ROE": _pick(record, "ROE"),
                "综合评分": _pick(record, "综合评分"),
                "安全边际": _pick(record, "安全边际"),
                "下一步观察重点": "低价高成长短线观察池，需结合成交额、财报质量、风险警示与多分析师复核结果跟踪。",
            }
        )
    return {
        "观察股票": stocks,
        "正式推荐股票": [],
        "策略名称": "低价擒牛",
        "最终推荐数量": 0,
        "观察股票数量": len(stocks),
    }


def _generate_low_price_bull_ai_analysis(project_root: Path, day: str, result: dict) -> tuple[str, dict]:
    if os.getenv("LOW_PRICE_BULL_AI_ANALYSIS", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return "", {"success": False, "reason": "disabled"}
    validation = result.get("ai_validation") or validate_ai_models(project_root)
    if result.get("analysis"):
        markdown = format_ai_analysis_markdown(result["analysis"], validation)
        return markdown, {"validation": validation, "generation": result["analysis"], "source": "aiagents_low_price_bull_tool"}
    if not validation.get("enabled_models"):
        markdown = format_ai_analysis_markdown({}, validation)
        return markdown, {"validation": validation, "generation": {"success": False, "reason": "disabled_or_no_models"}}
    scan = _low_price_bull_scan(result)
    markdown, meta = generate_ai_value_analysis(project_root, day, scan)
    meta["source"] = "root_fallback_for_local_value_index"
    return markdown, meta


def build_low_price_bull_email(day: str, result: dict, ai_markdown: str = "") -> str:
    records = result.get("records", [])
    display_rows = len(records)
    result_rows = result.get("rows", display_rows)
    if not records:
        table = "今日未筛选到符合条件的低价擒牛股票。"
    else:
        lines = ["| 排名 | 代码 | 名称 | 股价 | 净利增长 | 成交额 | 行业 |", "|---:|---|---|---:|---:|---:|---|"]
        for index, item in enumerate(records, start=1):
            lines.append(
                "| {rank} | {code} | {name} | {price} | {growth} | {turnover} | {industry} |".format(
                    rank=index,
                    code=_pick(item, "股票代码", "代码"),
                    name=_pick(item, "股票简称", "名称"),
                    price=_pick(item, "股价", "最新价", "收盘价"),
                    growth=_pick(item, "净利润增长率", "净利润同比增长率", "归属母公司股东的净利润"),
                    turnover=_pick(item, "成交额"),
                    industry=_pick(item, "所属行业", "行业"),
                )
            )
        table = "\n".join(lines)
    markdown = f"""# 低价擒牛工作日筛选报告 - {day}

## 策略条件

- 股价 < 10 元
- 净利润增长率 >= 100%
- 非 ST
- 非科创板
- 非创业板
- 沪深 A 股
- 按成交额由小到大排序

## 筛选结果

- 状态: {'成功' if result.get('success') else '失败'}
- 说明: {result.get('message', '无')}
- 数量: {display_rows}

{table}

## 风险提示

低价擒牛属于高波动策略，只作为短线观察池，不等同于价值策略正式推荐，不构成投资建议。
"""
    if result_rows != display_rows:
        markdown = markdown.replace(
            f"- 数量: {display_rows}",
            f"- 数量: {display_rows}\n- 原始返回数量: {result_rows}",
        )
    if ai_markdown:
        markdown = append_ai_analysis(markdown, ai_markdown)
    return markdown


def run_low_price_bull_daily(project_root: Path | None = None, top_n: int | None = None, force: bool = False) -> dict:
    project_root = project_root or settings.project_root
    top_n = top_n or int(os.getenv("LOW_PRICE_BULL_TOP_N", "5"))
    now = datetime.now(ZoneInfo(settings.timezone))
    day = now.date().isoformat()
    trading, source = is_a_share_trading_day(now.date(), settings.calendar_cache_path)
    if not trading and not force:
        return {"success": True, "skipped": True, "reason": f"{day} 不是A股交易日", "calendar_source": source}

    analysis_enabled = os.getenv("LOW_PRICE_BULL_AI_ANALYSIS", "0").strip().lower() in {"1", "true", "yes", "on"}
    ai_validation = validate_ai_models(project_root, configured_analysis_models()) if analysis_enabled else {"enabled_models": []}
    result = _run_selector(project_root, top_n, ai_validation.get("enabled_models") if analysis_enabled else None)
    if not result.get("success"):
        original_message = result.get("message", "")
        result = _fallback_from_value_index(project_root, top_n)
        result["upstream_error"] = original_message
    result["ai_validation"] = ai_validation
    if result.get("records"):
        result["records"] = _enrich_records_from_value_index(project_root, result["records"])
        result["rows"] = len(result["records"])
    output_dir = project_root / "reports" / "low_price_bull"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{day}.json"
    md_path = output_dir / f"{day}.md"
    csv_path = output_dir / f"{day}.csv"
    ai_markdown, ai_meta = _generate_low_price_bull_ai_analysis(project_root, day, result)
    result["ai_analysis"] = ai_meta
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    markdown = build_low_price_bull_email(day, result, ai_markdown)
    md_path.write_text(markdown, encoding="utf-8")
    if result.get("records"):
        pd.DataFrame(result["records"]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    email_ok, email_status = send_email(
        settings,
        f"低价擒牛工作日筛选报告 - {day}",
        markdown,
    )
    return {
        "success": bool(result.get("success") and email_ok),
        "selector_success": bool(result.get("success")),
        "email_ok": email_ok,
        "email_status": email_status,
        "rows": result.get("rows", 0),
        "json": str(json_path),
        "markdown": str(md_path),
        "csv": str(csv_path) if csv_path.exists() else "",
    }
