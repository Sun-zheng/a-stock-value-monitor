from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from src.data_fetcher import (
    fetch_dividends,
    fetch_financial_indicators,
    fetch_market_snapshot,
)
from src.stock_pool import build_main_board_pool, pool_statistics
from src.trading_calendar import is_a_share_trading_day
from src.universe_scanner import coverage


def run_data_fetch_test(reports_dir: Path, cache_path: Path, calendar_cache: Path) -> dict:
    started = time.perf_counter()
    failures: list[str] = []
    missing: list[str] = []
    trading_day, calendar_source = is_a_share_trading_day(date.today(), calendar_cache)
    calendar_ok = calendar_source not in ("无法确认交易日，按保守规则不执行",)

    try:
        snapshot, meta = fetch_market_snapshot(cache_path)
        failures.extend(meta["failures"])
        raw_stats = pool_statistics(snapshot)
        pool = build_main_board_pool(snapshot)
    except Exception as exc:
        meta = {
            "source": "不可用", "data_time": str(date.today()),
            "degradation": "所有股票池/行情源均失败",
        }
        failures.append(f"股票池/行情: {type(exc).__name__}: {exc}")
        import pandas as pd
        pool = pd.DataFrame()
        raw_stats = {
            "原始股票数量": 0, "排除科创板数量": 0, "排除创业板数量": 0,
            "排除北交所数量": 0, "排除ST数量": 0,
        }
    market_fields = ["代码", "名称", "当前价格", "涨跌幅", "总市值"]
    valuation_fields = ["PE TTM", "PB", "PS", "股息率"]
    for field in market_fields + valuation_fields:
        if field not in pool or pool[field].notna().sum() == 0:
            missing.append(field)

    financial_ok = 0
    dividend_ok = 0
    financial_samples = []
    sample_codes = pool["代码"].head(3).tolist() if "代码" in pool else []
    for code in sample_codes:
        try:
            frame, source = fetch_financial_indicators(code)
            ok = not frame.empty
            financial_ok += int(ok)
            financial_samples.append({"代码": code, "ok": ok, "source": source, "rows": len(frame)})
        except Exception as exc:
            failures.append(f"财务指标/{code}: {type(exc).__name__}: {exc}")
        try:
            frame, _ = fetch_dividends(code)
            dividend_ok += int(not frame.empty)
        except Exception as exc:
            failures.append(f"分红/{code}: {type(exc).__name__}: {exc}")

    main_count = len(pool)
    result = {
        **raw_stats,
        "最终主板股票池数量": main_count,
        "交易日历可获取": calendar_ok,
        "交易日历来源": calendar_source,
        "今日是否交易日": trading_day,
        "行情数据覆盖率": coverage(pool, market_fields),
        "估值数据覆盖率": coverage(pool, valuation_fields),
        "财报数据覆盖率": round(financial_ok / min(max(main_count, 1), 3) * 100, 2),
        "现金流数据覆盖率": round(financial_ok / min(max(main_count, 1), 3) * 100, 2),
        "分红数据覆盖率": round(dividend_ok / min(max(main_count, 1), 3) * 100, 2),
        "数据来源": [meta["source"], calendar_source],
        "数据时间": meta["data_time"],
        "失败数据源": failures,
        "缺失字段列表": sorted(set(missing)),
        "降级处理说明": meta.get("degradation_reason", meta.get("degradation", "")) or "无",
        "财务样本": financial_samples,
    }
    result["测试耗时"] = round(time.perf_counter() - started, 2)
    result["是否满足正式运行要求"] = bool(
        calendar_ok
        and main_count >= 2000
        and result["行情数据覆盖率"] >= 80
        and result["估值数据覆盖率"] >= 60
        and result["财报数据覆盖率"] > 0
    )
    if main_count < 2000:
        result["异常"] = "主板股票池不是数千级，停止正式推荐"
        result["是否满足正式运行要求"] = False
    save_data_fetch_report(result, reports_dir)
    return result


def save_data_fetch_report(result: dict, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    (reports_dir / f"data_fetch_test_{day}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    lines = ["# 数据获取测试报告", ""]
    for key, value in result.items():
        if key != "财务样本":
            lines.append(f"- {key}: {value}")
    (reports_dir / f"data_fetch_test_{day}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
