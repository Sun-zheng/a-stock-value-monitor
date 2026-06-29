from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.strategies.low_price_bull.low_price_bull_selector import LowPriceBullSelector  # noqa: E402


def run(top_n: int) -> dict:
    selector = LowPriceBullSelector()
    fetch_n = max(top_n * 4, top_n)
    success, frame, message = selector.get_low_price_stocks(top_n=fetch_n)
    if not success or frame is None:
        return {"success": False, "message": message, "rows": 0, "records": []}
    original_rows = int(len(frame))
    if not frame.empty:
        name = frame.get("股票简称", "").astype(str)
        market_type = frame.get("股票市场类型", "").astype(str)
        risky = (
            name.str.contains("ST|退", case=False, na=False)
            | market_type.str.contains("退市|风险警示", na=False)
        )
        frame = frame[~risky].head(top_n).copy()
    final_rows = int(len(frame))
    return {
        "success": True,
        "message": (
            f"成功筛选出{final_rows}只低价高成长股票"
            f"；原始候选{original_rows}只"
            "；已二次过滤ST/退市/风险警示股票"
        ),
        "rows": final_rows,
        "columns": list(frame.columns),
        "records": frame.fillna("数据不足").to_dict("records"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily low-price bull selector.")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env", override=False)
    result = run(args.top_n)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
