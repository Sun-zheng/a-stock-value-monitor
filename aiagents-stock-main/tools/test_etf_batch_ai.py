from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitAnalyzer  # noqa: E402
from backend.strategies.index_fund_research.etf_toolkit_settings import load_etf_toolkit_settings  # noqa: E402
from frontend.strategies.etf_single_analysis_ui import (  # noqa: E402
    MODELSCOPE_MODELS,
    _analyze_etfs,
    _load_market_snapshot,
    _prepare_snapshot,
    _selected_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real ETF batch analysis and optional ModelScope AI review.")
    parser.add_argument("--counts", default="5,10,20", help="Comma-separated ETF batch sizes.")
    parser.add_argument("--start-date", default="20210101")
    parser.add_argument("--min-turnover-wan", type=int, default=3000)
    parser.add_argument("--with-ai", action="store_true", help="Call ModelScope AI review if MODELSCOPE_API_KEY is configured.")
    parser.add_argument("--model", default=MODELSCOPE_MODELS[0])
    parser.add_argument("--output", default="../reports/etf_batch_ai_test.json")
    args = parser.parse_args()

    load_dotenv(os.getenv("AIAGENTS_ENV_FILE", str(ROOT / ".env")), override=True)
    counts = [int(item.strip()) for item in args.counts.split(",") if item.strip()]
    started = time.perf_counter()
    snapshot = _prepare_snapshot(_load_market_snapshot(args.min_turnover_wan, args.start_date))
    candidates = snapshot.sort_values("成交额", ascending=False)["代码"].astype(str).tolist()
    settings = load_etf_toolkit_settings(ROOT.parent)
    analyzer = ETFToolkitAnalyzer()
    results = []
    for count in counts:
        codes = candidates[:count]
        rows = _selected_rows(snapshot, codes)
        batch_started = time.perf_counter()
        result = _analyze_etfs(
            analyzer,
            rows,
            ["基础筛选", "定投计划", "溢价折价监控", "风险雷达"],
            settings,
            args.start_date,
            enable_ai_review=args.with_ai,
            ai_model=args.model,
        )
        results.append(
            {
                "count": count,
                "requested_codes": codes,
                "selected_count": result.get("selected_count"),
                "analyzed_count": result.get("analyzed_count"),
                "error_count": result.get("error_count"),
                "duration_seconds": round(time.perf_counter() - batch_started, 2),
                "top_pick": result.get("final_summary", {}).get("top_pick"),
                "rating": result.get("final_summary", {}).get("rating"),
                "analyst_reports": [item.get("agent_name") for item in result.get("analyst_reports", [])],
                "ai_review": {
                    "success": result.get("ai_review", {}).get("success"),
                    "status": result.get("ai_review", {}).get("status"),
                    "model": result.get("ai_review", {}).get("model"),
                    "latency_seconds": result.get("ai_review", {}).get("latency_seconds"),
                    "content_chars": len(result.get("ai_review", {}).get("content") or ""),
                    "error": (result.get("ai_review", {}).get("error") or "")[:180],
                },
            }
        )
    summary = {
        "snapshot_count": len(snapshot),
        "counts": counts,
        "with_ai": args.with_ai,
        "modelscope_key_present": bool(os.getenv("MODELSCOPE_API_KEY", "").strip()),
        "model": args.model,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "results": results,
    }
    output_path = (ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = [
        item
        for item in results
        if item["selected_count"] != item["count"]
        or item["analyzed_count"] <= 0
        or len(item["analyst_reports"]) < 4
        or (args.with_ai and bool(os.getenv("MODELSCOPE_API_KEY", "").strip()) and not item["ai_review"]["success"])
    ]
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
