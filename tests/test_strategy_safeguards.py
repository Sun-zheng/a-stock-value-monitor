import numpy as np
import pandas as pd

from src.universe_scanner import (
    _select_deep_review_candidates,
    add_decision_fields,
    apply_intraday_market_cap,
    attach_industry_benchmarks,
    financial_filter_details,
    score_candidates,
)


def financial_row(**overrides):
    row = {
        "代码": "600000",
        "行业": "食品",
        "当前价格": 8.0,
        "估值收盘价": 10.0,
        "总市值": 10_000.0,
        "流通市值": 6_000.0,
        "PE TTM": 10.0,
        "PB": 1.0,
        "PS": 1.0,
        "股息率": 4.0,
        "行业PE TTM中位数": 15.0,
        "行业PB中位数": 1.5,
        "行业PS中位数": 1.5,
        "行业估值样本充足": True,
        "营业收入": 100.0,
        "归母净利润": 10.0,
        "扣非净利润": 9.0,
        "ROE": 15.0,
        "扣非ROE": 14.0,
        "ROIC": 12.0,
        "毛利率": 30.0,
        "净利率": 10.0,
        "资产负债率": 40.0,
        "经营性现金流净额": 12.0,
        "自由现金流": 8.0,
        "经营现金流/净利润": 120.0,
        "标准化归母净利润": 10.0,
        "最近完整年度营业收入": 100.0,
        "最近完整年度归母净资产": 70.0,
        "最近完整年度自由现金流": 8.0,
        "标准化自由现金流": 8.0,
        "自由现金流年度样本数": 3,
        "货币资金": 30.0,
        "有息负债": 10.0,
        "商誉": 2.0,
        "营业收入多年趋势": 8.0,
        "归母净利润多年趋势": 10.0,
        "一次性收益异常": False,
        "报表期间一致": True,
        "对齐报告期": "20251231",
        "财报覆盖率": 100.0,
        "现金流完整": True,
        "一票否决原因": "",
        "特殊行业": False,
        "市值时点一致": True,
    }
    row.update(overrides)
    return row


def test_intraday_market_cap_conversion():
    result = apply_intraday_market_cap(pd.DataFrame([financial_row()]))
    assert result.iloc[0]["总市值"] == 8_000
    assert result.iloc[0]["流通市值"] == 4_800
    assert "上一交易日市值" in result.iloc[0]["市值口径"]


def test_previous_close_market_cap_is_not_re_scaled():
    result = apply_intraday_market_cap(pd.DataFrame([financial_row(当前价格=10.0)]))
    assert result.iloc[0]["总市值"] == 10_000
    assert result.iloc[0]["流通市值"] == 6_000
    assert result.iloc[0]["市值口径"] == "上一交易日收盘市值"


def test_industry_samples_remove_negative_missing_and_extreme_values():
    values = [8, 9, 10, 11, 12, 13, 14, 15, 16, 10_000, -2, np.nan]
    frame = pd.DataFrame({
        "行业": ["食品"] * len(values),
        "PE TTM": values,
        "PB": [1 + i / 10 for i in range(len(values))],
        "PS": [0.8 + i / 20 for i in range(len(values))],
    })
    result = attach_industry_benchmarks(frame, frame)
    assert result["行业PE TTM样本数"].iloc[0] >= 8
    assert result["行业PE TTM中位数"].iloc[0] < 100
    assert bool(result["行业估值样本充足"].iloc[0]) is True


def test_report_period_mismatch_is_vetoed():
    result = financial_filter_details(pd.DataFrame([financial_row(报表期间一致=False)]))
    assert result.iloc[0]["一票否决原因"] == "三大报表及财务指标期间不一致"


def test_quarterly_annualized_roe_is_not_used():
    row = financial_row(ROE=np.nan, 年化ROE=60.0)
    scored = score_candidates(pd.DataFrame([row]))
    assert scored.iloc[0]["质量因子"] < score_candidates(
        pd.DataFrame([financial_row(ROE=20.0)])
    ).iloc[0]["质量因子"]


def test_missing_data_does_not_receive_points():
    complete = score_candidates(pd.DataFrame([financial_row()])).iloc[0]
    missing = score_candidates(pd.DataFrame([financial_row(
        ROE=np.nan,
        扣非ROE=np.nan,
        ROIC=np.nan,
        毛利率=np.nan,
        净利率=np.nan,
        资产负债率=np.nan,
        经营性现金流净额=np.nan,
        标准化自由现金流=np.nan,
        自由现金流年度样本数=np.nan,
        货币资金=np.nan,
        有息负债=np.nan,
        商誉=np.nan,
        归母净利润=np.nan,
        扣非净利润=np.nan,
        **{"经营现金流/净利润": np.nan, "营业收入多年趋势": np.nan, "归母净利润多年趋势": np.nan, "股息率": np.nan},
    )])).iloc[0]
    assert missing["生意质量与护城河评分"] == 0
    assert missing["管理层与资本配置评分"] == 0
    assert missing["盈利能力与韧性评分"] == 0
    assert missing["十年成长跑道评分"] == 0


def test_deep_review_candidates_backfill_from_later_financial_ready_names():
    frame = pd.DataFrame(
        [
            {"代码": "000001", "盈利指标口径": "最近完整年度财务指标", "报表期间一致": True, "对齐报告期": "20251231"},
            {"代码": "000002", "盈利指标口径": "数据不足", "报表期间一致": False, "对齐报告期": None},
            {"代码": "000003", "盈利指标口径": "最近完整年度财务指标", "报表期间一致": True, "对齐报告期": "20251231"},
            {"代码": "000004", "盈利指标口径": "数据不足", "报表期间一致": False, "对齐报告期": None},
            {"代码": "000005", "盈利指标口径": "最近完整年度财务指标", "报表期间一致": True, "对齐报告期": "20251231"},
            {"代码": "000006", "盈利指标口径": "最近完整年度财务指标", "报表期间一致": True, "对齐报告期": "20251231"},
        ]
    )

    selected = _select_deep_review_candidates(frame, 4)

    assert selected["代码"].tolist() == ["000001", "000003", "000005", "000006"]


def test_three_independent_valuation_families_are_required():
    complete = add_decision_fields(score_candidates(pd.DataFrame([financial_row()])))
    missing_fcf = add_decision_fields(score_candidates(pd.DataFrame([
        financial_row(标准化自由现金流=np.nan)
    ])))
    assert complete.iloc[0]["估值方法有效数"] == 3
    assert pd.notna(complete.iloc[0]["安全边际"])
    assert missing_fcf.iloc[0]["估值方法有效数"] == 2
    assert pd.isna(missing_fcf.iloc[0]["安全边际"])
    assert bool(missing_fcf.iloc[0]["是否正式推荐"]) is False
    assert "安全边际=数据不足%" in missing_fcf.iloc[0]["长期投资关键证据"]
    assert "nan" not in missing_fcf.iloc[0]["长期投资关键证据"].lower()


def test_one_off_income_anomaly_blocks_formal_recommendation():
    scored = score_candidates(pd.DataFrame([financial_row(一次性收益异常=True)]))
    result = add_decision_fields(scored)
    assert bool(result.iloc[0]["是否正式推荐"]) is False
    assert bool(result.iloc[0]["财务异常"]) is True


def test_special_industry_cannot_use_generic_formal_model():
    scored = score_candidates(pd.DataFrame([financial_row(行业="银行", 特殊行业=True)]))
    result = add_decision_fields(scored)
    assert bool(result.iloc[0]["是否正式推荐"]) is False
    assert "特殊行业暂无专用模型" in result.iloc[0]["未达推荐原因"]
