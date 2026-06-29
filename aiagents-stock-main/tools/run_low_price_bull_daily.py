from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.strategies.low_price_bull.low_price_bull_selector import LowPriceBullSelector  # noqa: E402
from tools.generate_value_stock_analysis import generate as generate_stock_analysis  # noqa: E402


def _pick(record: dict, *patterns: str):
    for pattern in patterns:
        for key, value in record.items():
            if pattern in str(key):
                return value
    return "数据不足"


def _analysis_code(value) -> str:
    text = str(value or "").strip()
    return text.split(".")[0] if "." in text else text


def _stock_context(record: dict, index: int) -> dict:
    code = _pick(record, "股票代码", "代码")
    return {
        "股票类型": "低价擒牛观察",
        "观察排名": index,
        "代码": code,
        "分析代码": _analysis_code(code),
        "名称": _pick(record, "股票简称", "名称"),
        "行业": _pick(record, "所属行业", "所属同花顺行业", "行业"),
        "上市板块": _pick(record, "上市板块"),
        "当前价格": _pick(record, "股价", "最新价", "收盘价"),
        "股价": _pick(record, "股价", "最新价", "收盘价"),
        "净利润增长率": _pick(record, "净利润增长率", "净利润同比增长率", "归属母公司股东的净利润"),
        "营业收入增长率": _pick(record, "营业收入增长率", "营业收入同比增长率"),
        "成交额": _pick(record, "成交额"),
        "ROE": _pick(record, "ROE"),
        "综合评分": _pick(record, "综合评分"),
        "安全边际": _pick(record, "安全边际"),
        "下一步观察重点": "低价擒牛策略筛选后，需结合多智能体分析结论、风险警示、资金流和新闻催化跟踪。",
    }


def _analysis_payload(day: str, records: list[dict], models: list[str], period: str) -> dict:
    stocks = [_stock_context(record, index) for index, record in enumerate(records, start=1)]
    return {
        "day": day,
        "scan": {
            "策略名称": "低价擒牛",
            "正式推荐股票": [],
            "观察股票": stocks,
            "最终推荐数量": 0,
            "观察股票数量": len(stocks),
        },
        "stocks": stocks,
        "models": models,
        "period": period,
        "enabled_analysts": {
            "technical": True,
            "fundamental": True,
            "fund_flow": True,
            "risk": True,
            "sentiment": True,
            "news": True,
        },
    }


def _analyze_records(day: str, records: list[dict], models: list[str], period: str) -> dict:
    if not records:
        return {"success": False, "reason": "no_records", "analyses": []}
    if not models:
        return {"success": False, "reason": "no_models", "analyses": []}
    return generate_stock_analysis(_analysis_payload(day, records, models, period))


def run(top_n: int, with_analysis: bool = False, models: list[str] | None = None, period: str = "1y") -> dict:
    selector = LowPriceBullSelector()
    fetch_n = max(top_n * 4, top_n)
    success, frame, message = selector.get_low_price_stocks(top_n=fetch_n)
    if not success or frame is None:
        return {"success": False, "message": message, "rows": 0, "records": []}
    original_rows = int(len(frame))
    if not frame.empty:
        name = frame.get("股票简称", pd.Series("", index=frame.index)).astype(str)
        market_type = frame.get("股票市场类型", pd.Series("", index=frame.index)).astype(str)
        risky = (
            name.str.contains("ST|退", case=False, na=False)
            | market_type.str.contains("退市|风险警示", na=False)
        )
        frame = frame[~risky].head(top_n).copy()
    final_rows = int(len(frame))
    records = frame.fillna("数据不足").to_dict("records")
    result = {
        "success": True,
        "message": (
            f"成功筛选出{final_rows}只低价高成长股票"
            f"；原始候选{original_rows}只"
            "；已二次过滤ST/退市/风险警示股票"
        ),
        "rows": final_rows,
        "columns": list(frame.columns),
        "records": records,
    }
    if with_analysis:
        from datetime import datetime

        result["analysis"] = _analyze_records(
            datetime.now().date().isoformat(),
            records,
            models or ["stepfun-ai/Step-3.5-Flash"],
            period,
        )
        result["analysis_flow"] = "low_price_bull_selector -> frontend.app.analyze_single_stock_for_batch -> StockAnalysisAgents"
    return {
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily low-price bull selector.")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output", required=True)
    parser.add_argument("--with-analysis", action="store_true")
    parser.add_argument("--models", default="stepfun-ai/Step-3.5-Flash")
    parser.add_argument("--period", default="1y")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env", override=False)
    result = run(
        args.top_n,
        with_analysis=args.with_analysis,
        models=[model.strip() for model in args.models.split(",") if model.strip()],
        period=args.period,
    )
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
