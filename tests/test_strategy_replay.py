import pandas as pd

import src.strategy_validator as validator


class FakeClient:
    def trade_dates(self, count):
        assert 5 <= count <= 25
        return [f"2026010{i}" for i in range(1, count + 1)]

    def daily_basic_on(self, trade_date):
        rows = []
        for i in range(12):
            rows.append({
                "ts_code": f"600{i:03d}.SH",
                "代码": f"600{i:03d}",
                "当前价格": 10.0,
                "PE TTM": 10.0 + i / 10,
                "PB": 1.0 + i / 100,
                "PS": 1.0 + i / 100,
                "股息率": 3.0,
                "总市值": 5_000_000_000,
                "流通市值": 4_000_000_000,
            })
        return pd.DataFrame(rows)


def test_limited_replay_accepts_5_to_20_days(monkeypatch):
    monkeypatch.setattr(validator, "TushareClient", FakeClient)
    universe = pd.DataFrame({
        "代码": [f"600{i:03d}" for i in range(12)],
        "名称": [f"股票{i}" for i in range(12)],
        "行业": ["食品"] * 12,
    })
    financial = pd.DataFrame({"代码": universe["代码"]})
    result = validator._historical_replay(universe, universe, financial, days=3)
    assert result["回放交易日数"] == 5
    assert result["推荐始终最多1只"] is True
    assert result["观察始终最多5只"] is True


class FakeClientWithEmptyLatest(FakeClient):
    def daily_basic_on(self, trade_date):
        if trade_date.endswith("10"):
            return pd.DataFrame()
        return super().daily_basic_on(trade_date)


def test_limited_replay_skips_dates_without_daily_valuation(monkeypatch):
    monkeypatch.setattr(validator, "TushareClient", FakeClientWithEmptyLatest)
    universe = pd.DataFrame({
        "代码": [f"600{i:03d}" for i in range(12)],
        "名称": [f"股票{i}" for i in range(12)],
        "行业": ["食品"] * 12,
    })
    financial = pd.DataFrame({"代码": universe["代码"]})
    result = validator._historical_replay(universe, universe, financial, days=5)
    assert result["回放交易日数"] == 5
    assert all(item["估值轻筛通过数量"] > 0 for item in result["回放明细"])
