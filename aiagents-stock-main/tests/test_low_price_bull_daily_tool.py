import pandas as pd

import tools.run_low_price_bull_daily as tool


def test_run_filters_delisted_and_risk_warning(monkeypatch):
    class FakeSelector:
        def get_low_price_stocks(self, top_n):
            return True, pd.DataFrame(
                [
                    {"股票代码": "600193.SH", "股票简称": "退市创兴", "股票市场类型": "退市整理股票"},
                    {"股票代码": "601368.SH", "股票简称": "绿城水务", "股票市场类型": "全部A股"},
                ]
            ), "ok"

    monkeypatch.setattr(tool, "LowPriceBullSelector", FakeSelector)

    result = tool.run(5)

    assert result["rows"] == 1
    assert result["records"][0]["股票代码"] == "601368.SH"


def test_run_with_analysis_uses_low_price_bull_analysis_chain(monkeypatch):
    class FakeSelector:
        def get_low_price_stocks(self, top_n):
            return True, pd.DataFrame(
                [
                    {
                        "股票代码": "601368.SH",
                        "股票简称": "绿城水务",
                        "股价": 4.19,
                        "净利润增长率": 1064.8,
                        "成交额": 15426002,
                    }
                ]
            ), "ok"

    payloads = []

    def fake_generate(payload):
        payloads.append(payload)
        return {
            "success": True,
            "analyses": [
                {
                    "code": payload["stocks"][0]["代码"],
                    "success": True,
                    "agents_results": {"technical": {"analysis": "技术分析"}},
                    "discussion_result": "团队讨论",
                    "final_decision": {"rating": "观察"},
                }
            ],
        }

    monkeypatch.setattr(tool, "LowPriceBullSelector", FakeSelector)
    monkeypatch.setattr(tool, "generate_stock_analysis", fake_generate)

    result = tool.run(5, with_analysis=True, models=["stepfun-ai/Step-3.7-Flash"], period="1y")

    assert result["analysis"]["success"] is True
    assert result["analysis_flow"].startswith("low_price_bull_selector")
    assert payloads[0]["stocks"][0]["股票类型"] == "低价擒牛观察"
    assert payloads[0]["stocks"][0]["分析代码"] == "601368"
    assert all(payloads[0]["enabled_analysts"].values())


def test_run_with_analysis_limit_keeps_screened_rows(monkeypatch):
    class FakeSelector:
        def get_low_price_stocks(self, top_n):
            return True, pd.DataFrame(
                [
                    {"股票代码": "601368.SH", "股票简称": "绿城水务"},
                    {"股票代码": "002200.SZ", "股票简称": "交投生态"},
                ]
            ), "ok"

    payloads = []

    def fake_generate(payload):
        payloads.append(payload)
        return {"success": True, "analyses": []}

    monkeypatch.setattr(tool, "LowPriceBullSelector", FakeSelector)
    monkeypatch.setattr(tool, "generate_stock_analysis", fake_generate)

    result = tool.run(5, with_analysis=True, models=["stepfun-ai/Step-3.7-Flash"], analysis_limit=1)

    assert result["rows"] == 2
    assert result["analysis"]["screened_rows"] == 2
    assert result["analysis"]["analysis_limit"] == 1
    assert len(payloads[0]["stocks"]) == 1
