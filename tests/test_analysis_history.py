import json

from src.analysis_history import write_analysis_history


def test_write_analysis_history_creates_daily_and_latest_files(tmp_path):
    scan = {
        "估值数据交易日": "20260622",
        "行情交易日": "20260622",
        "原始股票数量": 5528,
        "主板股票数量": 3030,
        "国内全市场基准股票数量": 5299,
        "估值轻筛通过数量": 500,
        "正式条件检查数量": 500,
        "一票否决后数量": 251,
        "最终推荐数量": 0,
        "观察股票数量": 2,
        "行情覆盖率": 100.0,
        "估值覆盖率": 99.67,
        "财报覆盖率": 100.0,
        "现金流覆盖率": 86.4,
        "正式推荐股票": [],
        "观察股票": [
            {"代码": "601083", "名称": "锦江航运", "综合评分": 75, "安全边际": 28},
            {"代码": "605599", "名称": "菜百股份", "综合评分": 74, "安全边际": 26},
        ],
        "每日变化": {"explanation": "观察池变化"},
    }
    outputs = {
        "result": "reports/2026-06-23_result.json",
        "base_report": "reports/2026-06-23_report_base.md",
        "final_report": "reports/2026-06-23_report.md",
        "scan_summary": "reports/2026-06-23_scan_summary.json",
    }

    paths = write_analysis_history(
        tmp_path,
        "2026-06-23",
        scan,
        outputs,
        generated_at="2026-06-23T16:00:00+08:00",
    )

    daily_path = tmp_path / "analysis_history" / "2026-06-23_analysis.json"
    latest_path = tmp_path / "analysis_history" / "latest_analysis.json"
    assert daily_path.exists()
    assert latest_path.exists()
    assert paths["history_file"].endswith("2026-06-23_analysis.json")
    payload = json.loads(daily_path.read_text(encoding="utf-8"))
    assert payload["analysis_scope"] == "全量前一交易日数据"
    assert payload["analysis_trade_date"] == "20260622"
    assert payload["summary"]["观察股票数量"] == 2
    assert payload["observations"][0]["代码"] == "601083"
