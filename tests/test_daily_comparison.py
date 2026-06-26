import json

from src.daily_comparison import compare_previous_day


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_compare_previous_day_uses_live_current_payload(tmp_path):
    reports_dir = tmp_path
    previous_payload = {
        "date": "2026-06-22",
        "scan_summary": {
            "最终推荐数量": 0,
            "观察股票数量": 2,
            "估值轻筛通过数量": 500,
            "一票否决后数量": 250,
            "估值覆盖率": 99.5,
            "财报覆盖率": 100.0,
            "现金流覆盖率": 86.0,
            "估值数据交易日": "20260620",
            "行情交易日": "20260620",
            "候选Top10": [{"代码": "600001"}, {"代码": "600002"}],
            "观察股票": [{"代码": "600001"}, {"代码": "600002"}],
        },
        "recommendation": None,
        "observations": [{"代码": "600001"}, {"代码": "600002"}],
        "conclusion": "无正式推荐",
    }
    _write_json(reports_dir / "2026-06-22_result.json", previous_payload)
    (reports_dir / "2026-06-22_report_base.md").write_text(
        "# 旧报告\n- 内容 A\n", encoding="utf-8"
    )

    current_scan = {
        "最终推荐数量": 1,
        "观察股票数量": 1,
        "估值轻筛通过数量": 500,
        "一票否决后数量": 251,
        "估值覆盖率": 99.7,
        "财报覆盖率": 100.0,
        "现金流覆盖率": 86.4,
        "估值数据交易日": "20260622",
        "行情交易日": "20260622",
        "候选Top10": [{"代码": "600003"}, {"代码": "600002"}],
        "正式推荐股票": [{"代码": "600003"}],
        "观察股票": [{"代码": "600002"}],
    }
    current_payload = {
        "date": "2026-06-23",
        "scan_summary": current_scan,
        "recommendation": {"代码": "600003"},
        "observations": [{"代码": "600002"}],
        "conclusion": "存在正式推荐候选",
    }

    result = compare_previous_day(
        reports_dir,
        "2026-06-23",
        current_payload=current_payload,
        current_scan=current_scan,
        current_report_text="# 新报告\n- 内容 B\n",
    )

    assert result["previous_date"] == "2026-06-22"
    assert result["current_codes"] == ["600003", "600002"]
    assert result["current_formal_codes"] == ["600003"]
    assert result["current_observation_codes"] == ["600002"]
    assert result["formal_entered"] == ["600003"]
    assert result["observation_exited"] == ["600001"]
    assert result["top10_entered"] == ["600003"]
    assert result["metric_changes"]["最终推荐数量"]["delta"] == 1
    assert result["report_changed"] is True
    assert result["conclusion_changed"] is True


def test_compare_previous_day_reports_first_run_when_no_history(tmp_path):
    current_scan = {
        "最终推荐数量": 0,
        "观察股票数量": 0,
        "候选Top10": [],
        "正式推荐股票": [],
        "观察股票": [],
    }
    current_payload = {
        "date": "2026-06-23",
        "scan_summary": current_scan,
        "recommendation": None,
        "observations": [],
        "conclusion": "无正式推荐",
    }

    result = compare_previous_day(
        tmp_path,
        "2026-06-23",
        current_payload=current_payload,
        current_scan=current_scan,
        current_report_text="# 首次报告\n",
    )

    assert result["previous_date"] == ""
    assert result["consecutive_repeat_days"] == 1
    assert "首次生成对比摘要" in result["explanation"]
