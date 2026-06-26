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
