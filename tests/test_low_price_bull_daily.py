from pathlib import Path

import pandas as pd

from src.low_price_bull_daily import (
    _enrich_records_from_value_index,
    _fallback_from_value_index,
    _generate_low_price_bull_ai_analysis,
    _low_price_bull_scan,
    build_low_price_bull_email,
)
from src.stock_history_store import write_daily_stock_history


def test_build_low_price_bull_email_contains_records():
    body = build_low_price_bull_email(
        "2026-06-26",
        {
            "success": True,
            "message": "ok",
            "rows": 1,
            "records": [{"股票代码": "000001", "股票简称": "平安银行", "股价": 9.9, "净利润增长率": 120, "成交额": 1000}],
        },
    )

    assert "低价擒牛工作日筛选报告" in body
    assert "000001" in body
    assert "平安银行" in body


def test_build_low_price_bull_email_uses_display_count_and_ai_section():
    body = build_low_price_bull_email(
        "2026-06-26",
        {
            "success": True,
            "message": "成功筛选出1只低价高成长股票",
            "rows": 20,
            "records": [{"股票代码": "000001", "股票简称": "平安银行"}],
        },
        "<!-- AI_VALUE_STOCK_ANALYSIS -->\n\n## 股票分析智能体复核\n\nAI内容",
    )

    assert "- 数量: 1" in body
    assert "- 原始返回数量: 20" in body
    assert "## 股票分析智能体复核" in body


def test_low_price_bull_fallback_uses_value_index(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "当前价格": 9.8,
                "归母净利润同比增长率": 120,
                "营业收入同比增长率": 30,
                "上市板块": "主板",
                "行业": "银行",
            }
        ]
    )
    data_dir = tmp_path / "data"
    write_daily_stock_history(
        data_dir,
        "2026-06-26",
        "2026-06-26",
        {"reviewed_candidates": frame},
    )

    result = _fallback_from_value_index(tmp_path, 3)

    assert result["success"] is True
    assert result["records"][0]["股票代码"] == "000001"


def test_enrich_records_from_value_index_fills_industry(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {
                "代码": "601368.SH",
                "名称": "绿城水务",
                "行业": "公用事业",
                "上市板块": "主板",
                "ROE": 7.5,
            }
        ]
    )
    data_dir = tmp_path / "data"
    write_daily_stock_history(
        data_dir,
        "2026-06-26",
        "2026-06-26",
        {"reviewed_candidates": frame},
    )

    records = _enrich_records_from_value_index(
        tmp_path,
        [{"股票代码": "601368.SH", "股票简称": "绿城水务", "所属行业": "数据不足"}],
    )

    assert records[0]["所属行业"] == "公用事业"
    assert records[0]["上市板块"] == "主板"


def test_low_price_bull_scan_maps_records_for_ai_analysis():
    scan = _low_price_bull_scan(
        {
            "records": [
                {
                    "股票代码": "601368.SH",
                    "股票简称": "绿城水务",
                    "股价": 4.19,
                    "净利润增长率": 1064.8,
                    "成交额": 15426002,
                    "所属行业": "公用事业",
                }
            ]
        }
    )

    stock = scan["观察股票"][0]
    assert stock["股票类型"] == "低价擒牛观察"
    assert stock["代码"] == "601368.SH"
    assert stock["净利润增长率"] == 1064.8
    assert stock["行业"] == "公用事业"


def test_generate_low_price_bull_ai_analysis_uses_tool_analysis(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LOW_PRICE_BULL_AI_ANALYSIS", "1")
    monkeypatch.setattr(
        "src.low_price_bull_daily.validate_ai_models",
        lambda project_root: {"enabled_models": ["stepfun-ai/Step-3.5-Flash"], "status": "ok"},
    )
    result = {
        "analysis": {
            "success": True,
            "period": "1y",
            "analyses": [
                {
                    "stock_type": "低价擒牛观察",
                    "code": "601368.SH",
                    "name": "绿城水务",
                    "success": True,
                    "value_context": {"净利润增长率": 1064.8},
                    "agents_results": {
                        "technical": {
                            "agent_name": "技术分析师",
                            "agent_role": "技术面",
                            "focus_areas": ["趋势"],
                            "analysis": "技术分析内容",
                        }
                    },
                    "discussion_result": "团队讨论内容",
                    "final_decision": {"rating": "观察"},
                }
            ],
        },
        "ai_validation": {"enabled_models": ["stepfun-ai/Step-3.5-Flash"], "status": "ok"},
    }

    markdown, meta = _generate_low_price_bull_ai_analysis(tmp_path, "2026-06-29", result)

    assert meta["source"] == "aiagents_low_price_bull_tool"
    assert "技术分析内容" in markdown
    assert "团队讨论内容" in markdown
    assert "最终决策" in markdown


def test_generate_low_price_bull_ai_analysis_disabled_by_default(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("LOW_PRICE_BULL_AI_ANALYSIS", raising=False)

    markdown, meta = _generate_low_price_bull_ai_analysis(tmp_path, "2026-06-29", {"analysis": {"success": True}})

    assert markdown == ""
    assert meta["reason"] == "disabled"
