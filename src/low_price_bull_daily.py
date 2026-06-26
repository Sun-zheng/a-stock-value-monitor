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
from src.email_sender import send_email
from src.stock_index_store import query_stock_history
from src.trading_calendar import is_a_share_trading_day


LOW_PRICE_BULL_TIME = "14:00"


def _run_selector(project_root: Path, top_n: int) -> dict:
    ai_root = project_root / "aiagents-stock-main"
    python = ai_root / ".venv/bin/python"
    with tempfile.TemporaryDirectory(prefix="low-price-bull.") as temporary:
        output_path = Path(temporary) / "result.json"
        result = subprocess.run(
            [
                str(python),
                "tools/run_low_price_bull_daily.py",
                "--top-n",
                str(top_n),
                "--output",
                str(output_path),
            ],
            cwd=ai_root,
            env={**os.environ, "AIAGENTS_ENV_FILE": str(Path.home() / ".config" / "a-stock-value-monitor" / "aiagents.env")},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
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


def _fallback_from_value_index(project_root: Path, top_n: int) -> dict:
    frame = query_stock_history(project_root / "data", "reviewed_candidates", limit=5000)
    if frame.empty:
        frame = query_stock_history(project_root / "data", "all_stocks", limit=5000)
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


def build_low_price_bull_email(day: str, result: dict) -> str:
    records = result.get("records", [])
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
    return f"""# 低价擒牛工作日筛选报告 - {day}

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
- 数量: {result.get('rows', 0)}

{table}

## 风险提示

低价擒牛属于高波动策略，只作为短线观察池，不等同于价值策略正式推荐，不构成投资建议。
"""


def run_low_price_bull_daily(project_root: Path | None = None, top_n: int | None = None, force: bool = False) -> dict:
    project_root = project_root or settings.project_root
    top_n = top_n or int(os.getenv("LOW_PRICE_BULL_TOP_N", "5"))
    now = datetime.now(ZoneInfo(settings.timezone))
    day = now.date().isoformat()
    trading, source = is_a_share_trading_day(now.date(), settings.calendar_cache_path)
    if not trading and not force:
        return {"success": True, "skipped": True, "reason": f"{day} 不是A股交易日", "calendar_source": source}

    result = _run_selector(project_root, top_n)
    if not result.get("success"):
        original_message = result.get("message", "")
        result = _fallback_from_value_index(project_root, top_n)
        result["upstream_error"] = original_message
    output_dir = project_root / "reports" / "low_price_bull"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{day}.json"
    md_path = output_dir / f"{day}.md"
    csv_path = output_dir / f"{day}.csv"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    markdown = build_low_price_bull_email(day, result)
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
