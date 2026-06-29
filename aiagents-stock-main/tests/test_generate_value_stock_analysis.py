from tools import generate_value_stock_analysis as tool
from tools.generate_value_stock_analysis import _compact_stock


def test_compact_stock_keeps_value_fields_only():
    item = {"代码": "000001", "名称": "平安银行", "ROE": 8.1, "无关字段": "x"}

    compact = _compact_stock(item)

    assert compact["代码"] == "000001"
    assert compact["ROE"] == 8.1
    assert "无关字段" not in compact


def test_compact_stock_keeps_low_price_bull_context():
    item = {"代码": "601368.SH", "股价": 4.19, "净利润增长率": 1064.8, "成交额": 15426002}

    compact = _compact_stock(item)

    assert compact["股价"] == 4.19
    assert compact["净利润增长率"] == 1064.8
    assert compact["成交额"] == 15426002


def test_generate_uses_unified_batch_analysis(monkeypatch):
    calls = []

    def fake_analyze(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "stock_info": {"symbol": kwargs["symbol"], "name": "测试股份"},
            "indicators": {"rsi": 50},
            "agents_results": {
                "technical": {
                    "agent_name": "技术分析师",
                    "analysis": "技术报告",
                }
            },
            "discussion_result": "团队讨论",
            "final_decision": {"rating": "持有"},
        }

    monkeypatch.setattr(tool, "_analyze_single_stock_for_batch", fake_analyze)

    result = tool.generate(
        {
            "day": "2026-06-26",
            "scan": {},
            "models": ["deepseek-chat"],
            "stocks": [{"代码": "000001", "名称": "测试股份", "股票类型": "观察股票"}],
        }
    )

    assert result["success"] is True
    assert calls[0]["symbol"] == "000001"
    assert calls[0]["period"] == "1y"
    assert all(calls[0]["enabled_analysts_config"].values())
    assert result["analyses"][0]["agents_results"]["technical"]["analysis"] == "技术报告"
