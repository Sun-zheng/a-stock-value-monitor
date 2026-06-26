from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _stock_summary(item: dict) -> dict:
    return {
        "代码": item.get("代码", "数据不足"),
        "名称": item.get("名称", "数据不足"),
        "行业": item.get("行业", "数据不足"),
        "综合评分": item.get("综合评分", "数据不足"),
        "安全边际": item.get("安全边际", "数据不足"),
        "市场错配判断": item.get("市场错配判断", "数据不足"),
        "已计价预期": item.get("已计价预期", "数据不足"),
        "长期投资关键证据": item.get("长期投资关键证据", "数据不足"),
        "芒格反向失败清单": item.get("芒格反向失败清单", "数据不足"),
        "十年持有结论": item.get("十年持有结论", "数据不足"),
        "下一步观察重点": item.get("下一步观察重点", "数据不足"),
        "未达推荐原因": item.get("未达推荐原因", "数据不足"),
    }


def build_history_entry(
    day: str,
    scan: dict,
    outputs: dict,
    generated_at: str,
) -> dict:
    return {
        "date": day,
        "generated_at": generated_at,
        "analysis_scope": "全量前一交易日数据",
        "analysis_trade_date": scan.get("估值数据交易日", "数据不足"),
        "market_trade_date": scan.get("行情交易日", "数据不足"),
        "conclusion": (
            "今日无符合标准的 A 股全市场低估股票，不强行推荐。"
            if scan.get("最终推荐数量", 0) == 0
            else "存在正式推荐候选"
        ),
        "summary": {
            "原始股票数量": scan.get("原始股票数量", "数据不足"),
            "推荐范围": scan.get("推荐范围", "境内全市场A股"),
            "推荐范围股票数量": scan.get("推荐范围股票数量", "数据不足"),
            "主板股票数量": scan.get("主板股票数量", "数据不足"),
            "国内全市场基准股票数量": scan.get("国内全市场基准股票数量", "数据不足"),
            "估值轻筛通过数量": scan.get("估值轻筛通过数量", "数据不足"),
            "正式条件检查数量": scan.get("正式条件检查数量", "数据不足"),
            "一票否决后数量": scan.get("一票否决后数量", "数据不足"),
            "最终推荐数量": scan.get("最终推荐数量", "数据不足"),
            "观察股票数量": scan.get("观察股票数量", "数据不足"),
            "行情覆盖率": scan.get("行情覆盖率", "数据不足"),
            "估值覆盖率": scan.get("估值覆盖率", "数据不足"),
            "财报覆盖率": scan.get("财报覆盖率", "数据不足"),
            "现金流覆盖率": scan.get("现金流覆盖率", "数据不足"),
        },
        "formal_recommendations": [
            _stock_summary(item) for item in scan.get("正式推荐股票", [])
        ],
        "observations": [
            _stock_summary(item) for item in scan.get("观察股票", [])
        ],
        "daily_change": scan.get("每日变化", {}),
        "report_paths": outputs,
    }


def write_analysis_history(
    data_dir: Path,
    day: str,
    scan: dict,
    outputs: dict,
    generated_at: str | None = None,
) -> dict:
    generated_at = generated_at or datetime.now().astimezone().isoformat()
    history_dir = data_dir / "analysis_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    entry = build_history_entry(day, scan, outputs, generated_at)
    daily_path = history_dir / f"{day}_analysis.json"
    latest_path = history_dir / "latest_analysis.json"
    daily_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    latest_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return {
        "history_file": str(daily_path),
        "latest_history_file": str(latest_path),
    }
