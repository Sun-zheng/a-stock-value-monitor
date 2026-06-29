from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VALUE_FIELDS = [
    "股票类型", "观察排名", "代码", "分析代码", "名称", "行业", "上市板块", "当前价格",
    "股价", "净利润增长率", "净利润同比增长率", "营业收入增长率", "成交额",
    "总市值", "流通市值", "PE TTM", "PB", "PS", "股息率",
    "ROE", "扣非ROE", "ROIC", "毛利率", "净利率", "资产负债率",
    "营业收入", "归母净利润", "扣非净利润", "经营性现金流净额",
    "自由现金流", "标准化自由现金流", "经营现金流/净利润",
    "营业收入多年趋势", "归母净利润多年趋势", "综合评分", "安全边际",
    "估值评分", "现金流评分", "盈利能力评分", "资产负债评分",
    "成长性评分", "分红评分", "保守合理市值", "中性合理市值", "乐观合理市值",
    "市场错配判断", "已计价预期", "为何现在", "长期投资关键证据",
    "芒格反向失败清单", "十年持有质量门槛", "十年持有结论",
    "未达推荐原因", "下一步观察重点", "ROE口径", "ROE报告期",
]


def _compact_stock(item: dict) -> dict:
    return {field: item.get(field, "数据不足") for field in VALUE_FIELDS if field in item}


DEFAULT_ANALYSTS = {
    "technical": True,
    "fundamental": True,
    "fund_flow": True,
    "risk": True,
    "sentiment": True,
    "news": True,
}


def _analysis_symbol(item: dict) -> str:
    symbol = str(item.get("分析代码") or item.get("代码") or item.get("symbol") or item.get("code") or "").strip()
    return symbol.split(".")[0] if "." in symbol else symbol


def _enabled_analysts(payload: dict) -> dict:
    configured = payload.get("enabled_analysts")
    if not isinstance(configured, dict):
        return DEFAULT_ANALYSTS.copy()
    result = DEFAULT_ANALYSTS.copy()
    for key in result:
        if key in configured:
            result[key] = bool(configured[key])
    return result


def _period(payload: dict) -> str:
    return str(payload.get("period") or os.getenv("VALUE_ANALYSIS_PERIOD") or "1y")


def _analyze_single_stock_for_batch(*args, **kwargs) -> dict:
    from frontend.app import analyze_single_stock_for_batch

    return analyze_single_stock_for_batch(*args, **kwargs)


def generate(payload: dict) -> dict:
    day = payload["day"]
    scan = payload["scan"]
    stocks = payload.get("stocks", [])
    models = payload.get("models") or ["stepfun-ai/Step-3.7-Flash"]
    os.environ["AI_MODEL_POOL"] = ",".join(models)
    selected_model = models[0]
    enabled_analysts = _enabled_analysts(payload)
    period = _period(payload)

    analyses = []
    for item in stocks:
        symbol = _analysis_symbol(item)
        if not symbol:
            analyses.append(
                {
                    "code": item.get("代码", "无"),
                    "name": item.get("名称", "无"),
                    "stock_type": item.get("股票类型", "观察股票"),
                    "success": False,
                    "error": "缺少股票代码",
                    "value_context": _compact_stock(item),
                }
            )
            continue

        result = _analyze_single_stock_for_batch(
            symbol=symbol,
            period=period,
            enabled_analysts_config=enabled_analysts,
            selected_model=selected_model,
        )
        analyses.append(
            {
                "code": symbol,
                "name": item.get("名称", "无"),
                "stock_type": item.get("股票类型", "观察股票"),
                "success": bool(result.get("success")),
                "error": result.get("error"),
                "value_context": _compact_stock(item),
                "stock_info": result.get("stock_info", {}),
                "indicators": result.get("indicators", {}),
                "agents_results": result.get("agents_results", {}),
                "discussion_result": result.get("discussion_result", ""),
                "final_decision": result.get("final_decision", {}),
                "saved_to_db": result.get("saved_to_db", False),
                "db_error": result.get("db_error"),
            }
        )

    return {
        "success": any(item.get("success") for item in analyses),
        "models": models,
        "period": period,
        "enabled_analysts": enabled_analysts,
        "analyses": analyses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-stock value analysis with validated AI models.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    load_dotenv(os.getenv("AIAGENTS_ENV_FILE", str(ROOT / ".env")), override=True)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = generate(payload)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
