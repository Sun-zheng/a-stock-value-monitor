from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_source_manager import DataSourceManager
from src.strategy_config import (
    DEFAULT_STRATEGY,
    DIMENSIONS,
    load_strategy,
    strategy_scope_config,
)
from src.stock_history_store import write_daily_stock_history


VALUATION_FIELDS = ["PE TTM", "PB", "PS", "总市值", "流通市值"]
FINANCIAL_FIELDS = ["营业收入", "归母净利润", "扣非净利润", "ROE", "净利率", "资产负债率"]
CASH_FIELDS = ["经营性现金流净额", "自由现金流"]
FORMAL_SCORE = DEFAULT_STRATEGY["formal_score"]
FORMAL_MARGIN = DEFAULT_STRATEGY["formal_margin"]
WATCH_SCORE = DEFAULT_STRATEGY["watch_score"]
MIN_INDUSTRY_SAMPLE = 8
MAX_LIGHT_CANDIDATES = DEFAULT_STRATEGY["candidate_limit"]
DEEP_REVIEW_PREFETCH_BUFFER = 200
SPECIAL_INDUSTRY_KEYWORDS = {
    "银行": "银行",
    "保险": "保险",
    "证券": "券商",
    "券商": "券商",
    "房地产": "地产",
    "房产": "地产",
    "火力发电": "公用事业",
    "水力发电": "公用事业",
    "供气供热": "公用事业",
    "水务": "公用事业",
    "煤炭": "强周期",
    "石油": "强周期",
    "钢铁": "强周期",
    "普钢": "强周期",
    "特种钢": "强周期",
    "有色": "强周期",
    "铝": "强周期",
    "铜": "强周期",
    "水泥": "强周期",
    "化纤": "强周期",
    "航运": "强周期",
    "海运": "强周期",
    "水运": "强周期",
    "港口": "强周期",
}


def _numeric(frame: pd.DataFrame, field: str) -> pd.Series:
    if field not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[field], errors="coerce")


def _boolean(frame: pd.DataFrame, field: str, default: bool = False) -> pd.Series:
    if field not in frame:
        return pd.Series(default, index=frame.index, dtype=bool)
    values = frame[field]
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(default).astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    return normalized.isin({"true", "1", "yes", "是"})


def row_coverage(frame: pd.DataFrame, fields: list[str]) -> float:
    if frame.empty or not fields:
        return 0.0
    values = pd.DataFrame({field: _numeric(frame, field) for field in fields})
    return float(round(values.notna().all(axis=1).mean() * 100, 2))


def valuation_coverage(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    values = pd.DataFrame({field: _numeric(frame, field) for field in VALUATION_FIELDS})
    usable = values.notna().sum(axis=1) >= 4
    return float(round(usable.mean() * 100, 2))


def apply_intraday_market_cap(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    current = _numeric(data, "当前价格")
    close = _numeric(data, "估值收盘价")
    intraday_mask = current.notna() & close.gt(0) & ~current.eq(close)
    ratio = current.div(close.where(close > 0))
    for field in ("总市值", "流通市值"):
        previous = _numeric(data, field)
        data[f"上一交易日{field}"] = previous
        data[field] = previous.mul(ratio).where(intraday_mask, previous)
    data["市值口径"] = np.where(
        intraday_mask,
        "盘中市值=上一交易日市值×当前价格/上一交易日收盘价",
        "上一交易日收盘市值",
    )
    data["市值时点一致"] = (
        intraday_mask
        | current.eq(close)
        | (current.isna() & close.notna())
    )
    return data


def _clean_industry_values(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    values = values.where(values > 0).dropna()
    if len(values) < MIN_INDUSTRY_SAMPLE:
        return values.iloc[0:0]
    lower, upper = values.quantile([0.05, 0.95])
    return values[(values >= lower) & (values <= upper)]


def _evidence_value(value) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "数据不足"
    text = str(value).strip()
    return "数据不足" if not text or text.lower() in {"nan", "none"} else text


def build_industry_benchmarks(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if frame.empty or "行业" not in frame:
        return pd.DataFrame()
    for industry, group in frame.groupby("行业", dropna=False):
        row = {"行业": industry}
        available = True
        for field in ("PE TTM", "PB", "PS"):
            clean = _clean_industry_values(group.get(field, pd.Series(dtype=float)))
            row[f"行业{field}中位数"] = float(clean.median()) if len(clean) >= MIN_INDUSTRY_SAMPLE else np.nan
            row[f"行业{field}样本数"] = int(len(clean))
            available = available and len(clean) >= MIN_INDUSTRY_SAMPLE
        row["行业估值样本充足"] = bool(available)
        rows.append(row)
    return pd.DataFrame(rows)


def attach_industry_benchmarks(frame: pd.DataFrame, market: pd.DataFrame | None = None) -> pd.DataFrame:
    data = frame.copy()
    benchmark_source = market if market is not None else data
    benchmarks = build_industry_benchmarks(benchmark_source)
    if benchmarks.empty:
        data["行业估值样本充足"] = False
        return data
    benchmark_fields = [column for column in benchmarks if column != "行业"]
    data = data.drop(columns=benchmark_fields, errors="ignore")
    return data.merge(benchmarks, on="行业", how="left")


def classify_industry(industry: object) -> tuple[str, bool]:
    text = str(industry or "")
    for keyword, category in SPECIAL_INDUSTRY_KEYWORDS.items():
        if keyword in text:
            return category, True
    return "通用行业", False


def _candidate_sleeves(
    frame: pd.DataFrame, candidate_limit: int = MAX_LIGHT_CANDIDATES
) -> pd.DataFrame:
    data = frame.copy()
    if "代码" not in data:
        return data.iloc[0:0].copy()
    data = data[data["代码"].notna() & data["代码"].astype(str).str.strip().ne("")].copy()
    pe, pb, ps = (_numeric(data, field) for field in ("PE TTM", "PB", "PS"))
    dividend = _numeric(data, "股息率")
    cap = _numeric(data, "总市值")
    valid_cap = cap >= 2_000_000_000
    industry_ok = _boolean(data, "行业估值样本充足")
    relative = (
        (pe.gt(0) & pe.lt(_numeric(data, "行业PE TTM中位数")))
        | (pb.gt(0) & pb.lt(_numeric(data, "行业PB中位数")))
        | (ps.gt(0) & ps.lt(_numeric(data, "行业PS中位数")))
    ) & industry_ok
    value_mask = valid_cap & (
        (pe.gt(0) & pe.le(15))
        | (pb.gt(0) & pb.le(1.5))
        | (ps.gt(0) & ps.le(1.5))
    )
    dividend_mask = valid_cap & dividend.ge(2)
    quality_proxy = valid_cap & pe.between(0.01, 25) & pb.between(0.01, 4)
    sleeves = [
        ("价值", data[value_mask].assign(_sleeve_rank=pe.fillna(999) + pb.fillna(99) * 3)),
        ("质量", data[quality_proxy].assign(_sleeve_rank=pe.fillna(999) * 0.6 + pb.fillna(99) * 4)),
        ("高股息", data[dividend_mask].assign(_sleeve_rank=-dividend.fillna(-999))),
        ("行业内低估", data[valid_cap & relative].assign(
            _sleeve_rank=(
                pe.div(_numeric(data, "行业PE TTM中位数")).fillna(2)
                + pb.div(_numeric(data, "行业PB中位数")).fillna(2)
                + ps.div(_numeric(data, "行业PS中位数")).fillna(2)
            )
        )),
    ]
    selected: dict[str, pd.Series] = {}
    reasons: dict[str, list[str]] = {}
    quota = max(candidate_limit // len(sleeves), 1)
    for name, sleeve in sleeves:
        for _, row in sleeve.sort_values("_sleeve_rank").head(quota).iterrows():
            code = str(row["代码"])
            selected[code] = row
            reasons.setdefault(code, []).append(name)
    if len(selected) < candidate_limit:
        fallback = data[valid_cap & (value_mask | dividend_mask | relative)].copy()
        fallback["_sleeve_rank"] = pe.fillna(999) + pb.fillna(99) * 3 - dividend.fillna(0)
        for _, row in fallback.sort_values("_sleeve_rank").iterrows():
            code = str(row["代码"])
            if code not in selected:
                selected[code] = row
                reasons[code] = ["综合补位"]
            if len(selected) >= candidate_limit:
                break
    if not selected:
        return data.iloc[0:0].copy()
    result = pd.DataFrame(selected.values()).drop(columns="_sleeve_rank", errors="ignore")
    result = result[result["代码"].notna() & result["代码"].astype(str).str.strip().ne("")].copy()
    result["候选来源"] = result["代码"].astype(str).map(
        lambda code: "、".join(reasons.get(code, ["综合补位"]))
    )
    return result.head(candidate_limit).reset_index(drop=True)


def valuation_filter(
    frame: pd.DataFrame,
    benchmark_market: pd.DataFrame | None = None,
    candidate_limit: int = MAX_LIGHT_CANDIDATES,
) -> pd.DataFrame:
    benchmark_ready = "行业PE TTM中位数" in frame and "行业估值样本充足" in frame
    data = (
        frame.copy()
        if benchmark_market is None and benchmark_ready
        else attach_industry_benchmarks(frame, benchmark_market)
    )
    return _candidate_sleeves(data, candidate_limit)


def deep_review_prefetch_limit(total_count: int, financial_limit: int) -> int:
    return min(
        total_count,
        max(financial_limit, financial_limit + DEEP_REVIEW_PREFETCH_BUFFER),
    )


def financial_filter_details(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    for field in FINANCIAL_FIELDS + CASH_FIELDS:
        if field not in data:
            data[field] = np.nan
    aligned = _boolean(data, "报表期间一致")
    complete = data[FINANCIAL_FIELDS + CASH_FIELDS].notna().all(axis=1)
    adjusted_profit = _numeric(data, "扣非净利润")
    cash = _numeric(data, "经营性现金流净额")
    roe = _numeric(data, "ROE")
    debt = _numeric(data, "资产负债率")
    data["一票否决原因"] = ""
    data.loc[~aligned, "一票否决原因"] = "三大报表及财务指标期间不一致"
    data.loc[aligned & ~complete, "一票否决原因"] = "关键财务或现金流数据不足"
    data.loc[aligned & complete & adjusted_profit.le(0), "一票否决原因"] = "扣非净利润非正"
    data.loc[aligned & complete & adjusted_profit.gt(0) & cash.le(0), "一票否决原因"] = "经营现金流非正"
    data.loc[aligned & complete & adjusted_profit.gt(0) & cash.gt(0) & roe.le(0), "一票否决原因"] = "可靠ROE非正"
    data.loc[
        aligned & complete & adjusted_profit.gt(0) & cash.gt(0) & roe.gt(0) & debt.gt(85),
        "一票否决原因",
    ] = "资产负债率过高"
    return data


def financial_filter(frame: pd.DataFrame) -> pd.DataFrame:
    details = financial_filter_details(frame)
    return details[details["一票否决原因"] == ""].copy()


def _financial_ready_mask(frame: pd.DataFrame) -> pd.Series:
    annual = frame.get(
        "盈利指标口径", pd.Series("", index=frame.index, dtype=str)
    ).eq("最近完整年度财务指标")
    aligned = frame.get(
        "报表期间一致", pd.Series(False, index=frame.index, dtype=bool)
    ).fillna(False).astype(bool)
    aligned_period = frame.get(
        "对齐报告期", pd.Series(index=frame.index, dtype=object)
    ).notna()
    return annual & aligned & aligned_period


def _select_deep_review_candidates(
    frame: pd.DataFrame, financial_limit: int
) -> pd.DataFrame:
    ready = frame[_financial_ready_mask(frame)].copy()
    if len(ready) >= financial_limit:
        return ready.head(financial_limit).copy()
    fallback = frame.loc[~frame.index.isin(ready.index)].copy()
    selected = pd.concat(
        [ready, fallback.head(max(financial_limit - len(ready), 0))],
        ignore_index=True,
    )
    return selected.head(financial_limit).copy()


def _scaled(series: pd.Series, low: float, high: float, points: float) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return ((numeric - low) / (high - low) * points).clip(0, points).where(numeric.notna(), 0)


def _relative_valuation_score(data: pd.DataFrame) -> pd.Series:
    ratios = []
    for field in ("PE TTM", "PB", "PS"):
        current = _numeric(data, field)
        benchmark = _numeric(data, f"行业{field}中位数")
        ratios.append(current.div(benchmark.where(benchmark > 0)))
    relative = pd.concat(ratios, axis=1).median(axis=1, skipna=True)
    absolute = (
        _scaled(25 - _numeric(data, "PE TTM"), 0, 20, 8)
        + _scaled(4 - _numeric(data, "PB"), 0, 3, 5)
        + _scaled(4 - _numeric(data, "PS"), 0, 3.5, 2)
    )
    industry = _scaled(1.3 - relative, 0, 0.8, 10)
    industry_ok = _boolean(data, "行业估值样本充足")
    return (absolute + industry.where(industry_ok, 0)).clip(0, 25)


def _absolute_valuation(data: pd.DataFrame) -> pd.DataFrame:
    current_cap = _numeric(data, "总市值")
    normalized_profit = _numeric(data, "标准化归母净利润")
    annual_revenue = _numeric(data, "最近完整年度营业收入")
    equity = _numeric(data, "最近完整年度归母净资产")
    annual_fcf = _numeric(data, "标准化自由现金流")
    relative_values = pd.DataFrame(index=data.index)
    relative_values["PE相对估值"] = normalized_profit.mul(_numeric(data, "行业PE TTM中位数"))
    relative_values["PB相对估值"] = equity.mul(_numeric(data, "行业PB中位数"))
    relative_values["PS相对估值"] = annual_revenue.mul(_numeric(data, "行业PS中位数"))
    industry_ok = data.get("行业估值样本充足", pd.Series(False, index=data.index)).fillna(False)
    relative_values = relative_values.where(industry_ok, np.nan)
    relative_family = relative_values.median(axis=1, skipna=True)
    earnings_value = normalized_profit.where(normalized_profit > 0).mul(12)
    fcf_value = annual_fcf.where(annual_fcf > 0).mul(12)
    data["相对估值合理市值"] = relative_family
    data["盈利绝对估值"] = earnings_value
    data["现金流绝对估值"] = fcf_value
    data["可靠估值覆盖率"] = (
        pd.concat(
            [
                relative_family.notna().rename("相对估值族"),
                earnings_value.notna().rename("盈利绝对估值"),
                fcf_value.notna().rename("现金流绝对估值"),
            ],
            axis=1,
        ).mean(axis=1) * 100
    ).round(2)
    data["估值方法有效数"] = (
        relative_family.notna().astype(int)
        + earnings_value.notna().astype(int)
        + fcf_value.notna().astype(int)
    )
    data["支持低估估值方法数"] = (
        relative_family.gt(current_cap).astype(int)
        + earnings_value.gt(current_cap).astype(int)
        + fcf_value.gt(current_cap).astype(int)
    )
    values = pd.concat(
        [
            relative_family.rename("相对估值族"),
            earnings_value.rename("盈利绝对估值"),
            fcf_value.rename("现金流绝对估值"),
        ],
        axis=1,
    )
    data["保守合理市值"] = values.min(axis=1, skipna=True)
    data["中性合理市值"] = values.median(axis=1, skipna=True)
    data["乐观合理市值"] = values.max(axis=1, skipna=True)
    reliable_absolute = (
        relative_family.notna() & earnings_value.notna() & fcf_value.notna()
    )
    data["安全边际"] = (
        (data["保守合理市值"].div(current_cap.where(current_cap > 0)) - 1) * 100
    ).where(reliable_absolute).round(2)
    data["估值结论类型"] = np.where(
        reliable_absolute,
        "同行相对估值+保守盈利估值+现金流绝对估值",
        np.where(
            values.notna().sum(axis=1).gt(0),
            "独立估值族不足3种，不计算正式安全边际",
            "估值数据不足",
        ),
    )
    return data


def score_candidates(
    frame: pd.DataFrame, strategy: dict | None = None
) -> pd.DataFrame:
    strategy = strategy or DEFAULT_STRATEGY
    weights = strategy["weights"]
    data = frame.copy()
    roe = _numeric(data, "ROE")
    adjusted_roe = _numeric(data, "扣非ROE")
    roic = _numeric(data, "ROIC")
    gross_margin = _numeric(data, "毛利率")
    margin = _numeric(data, "净利率")
    cash_ratio = _numeric(data, "经营现金流/净利润")
    debt = _numeric(data, "资产负债率")
    revenue_trend = _numeric(data, "营业收入多年趋势")
    profit_trend = _numeric(data, "归母净利润多年趋势")
    dividend = _numeric(data, "股息率")
    parent_profit = _numeric(data, "归母净利润")
    adjusted_profit = _numeric(data, "扣非净利润")
    adjusted_ratio = adjusted_profit.div(parent_profit.where(parent_profit > 0))
    money = _numeric(data, "货币资金")
    interest_debt = _numeric(data, "有息负债")
    cash_to_debt = money.div(interest_debt.where(interest_debt > 0))
    cash_to_debt = cash_to_debt.where(
        ~(interest_debt.eq(0) & money.notna()), 3.0
    )
    equity = _numeric(data, "最近完整年度归母净资产")
    goodwill = _numeric(data, "商誉")
    goodwill_ratio = goodwill.div(equity.where(equity > 0))
    fcf_samples = _numeric(data, "自由现金流年度样本数")
    standardized_fcf = _numeric(data, "标准化自由现金流")
    operating_cash = _numeric(data, "经营性现金流净额")

    data = _absolute_valuation(data)
    safety_margin = _numeric(data, "安全边际")
    business = weights["生意质量与护城河"] * (
        _scaled(gross_margin, 10, 40, 1) * 0.30
        + _scaled(margin, 2, 18, 1) * 0.25
        + _scaled(roic, 4, 18, 1) * 0.30
        + _scaled(adjusted_ratio, 0.5, 1.0, 1) * 0.15
    )
    capital = weights["管理层与资本配置"] * (
        _scaled(roic, 4, 18, 1) * 0.50
        + _scaled(fcf_samples.where(standardized_fcf > 0), 1, 3, 1) * 0.30
        + _scaled(cash_to_debt, 0.5, 2.0, 1) * 0.20
    )
    profitability = weights["盈利能力与韧性"] * (
        _scaled(roe, 5, 20, 1) * 0.40
        + _scaled(adjusted_roe, 5, 18, 1) * 0.25
        + _scaled(margin, 2, 18, 1) * 0.20
        + _scaled(profit_trend, -5, 15, 1) * 0.15
    )
    financial_strength = weights["财务安全"] * (
        _scaled(80 - debt, 0, 60, 1) * 0.50
        + _scaled(cash_to_debt, 0.3, 1.5, 1) * 0.30
        + _scaled(0.30 - goodwill_ratio, 0, 0.30, 1) * 0.20
    )
    fcf_consistency = (
        standardized_fcf.gt(0) & fcf_samples.ge(3)
    ).astype(float).where(standardized_fcf.notna() & fcf_samples.notna(), 0)
    cash_flow = weights["现金流质量"] * (
        _scaled(cash_ratio, 40, 120, 1) * 0.50
        + fcf_consistency * 0.30
        + operating_cash.gt(0).astype(float).where(operating_cash.notna(), 0) * 0.20
    )
    growth = weights["十年成长跑道"] * (
        _scaled(revenue_trend, -5, 15, 1) * 0.45
        + _scaled(profit_trend, -10, 20, 1) * 0.45
        + (revenue_trend.gt(0) & profit_trend.gt(0)).astype(float) * 0.10
    )
    valuation = weights["估值与安全边际"] * (
        _relative_valuation_score(data).div(25).clip(0, 1) * 0.50
        + _scaled(safety_margin, 0, 50, 1) * 0.50
    )
    shareholder = weights["股东回报"] * _scaled(dividend, 0.5, 5, 1)

    one_off = _boolean(data, "一次性收益异常")
    inverse_evidence = (
        debt.notna()
        & cash_ratio.notna()
        & revenue_trend.notna()
        & profit_trend.notna()
        & roic.notna()
        & data.get("一次性收益异常", pd.Series(np.nan, index=data.index)).notna()
    )
    inverse_deductions = (
        one_off.astype(float) * 2
        + debt.gt(70).astype(float)
        + cash_ratio.lt(80).astype(float)
        + (revenue_trend.le(0) | profit_trend.le(0)).astype(float)
        + roic.lt(8).astype(float)
    ).clip(0, 5)
    inverse = (
        weights["芒格反向清单"] * (1 - inverse_deductions / 5)
    ).where(inverse_evidence, 0)

    dimension_values = {
        "生意质量与护城河": business,
        "管理层与资本配置": capital,
        "盈利能力与韧性": profitability,
        "财务安全": financial_strength,
        "现金流质量": cash_flow,
        "十年成长跑道": growth,
        "估值与安全边际": valuation,
        "股东回报": shareholder,
        "芒格反向清单": inverse,
    }
    for name, values in dimension_values.items():
        data[f"{name}评分"] = values.clip(0, weights[name]).round(2)
    data["综合评分"] = sum(
        data[f"{name}评分"] for name in DIMENSIONS
    ).clip(0, 100).round(2)
    data["质量因子"] = (
        data["生意质量与护城河评分"]
        + data["管理层与资本配置评分"]
        + data["盈利能力与韧性评分"]
    ).round(2)
    data["估值因子"] = data["估值与安全边际评分"]
    data["成长因子"] = data["十年成长跑道评分"]
    data["股东回报因子"] = data["股东回报评分"]
    data["风险扣分"] = (
        weights["芒格反向清单"] - data["芒格反向清单评分"]
    ).round(2)
    data["估值低估程度"] = data["估值与安全边际评分"]
    data["现金流质量"] = data["现金流质量评分"]
    data["盈利能力"] = data["盈利能力与韧性评分"]
    data["资产负债安全"] = data["财务安全评分"]
    data["成长性"] = data["十年成长跑道评分"]
    data["分红与股东回报"] = data["股东回报评分"]
    data = _absolute_valuation(data)
    aligned = _boolean(data, "报表期间一致")
    data["财务异常"] = one_off | ~aligned
    data["估值模型可用于正式推荐"] = (
        data["安全边际"].notna()
        & data["可靠估值覆盖率"].eq(100)
        & data["估值方法有效数"].ge(3)
        & ~data["财务异常"].fillna(True)
        & ~_boolean(data, "特殊行业")
        & _boolean(data, "行业估值样本充足")
        & _boolean(data, "市值时点一致")
    )
    def inverse_checklist(row: pd.Series) -> str:
        failures = []
        required = ("ROIC", "资产负债率", "经营现金流/净利润", "营业收入多年趋势", "归母净利润多年趋势")
        if any(pd.isna(row.get(field)) for field in required):
            failures.append("关键反向证据不足")
        if bool(row.get("一次性收益异常", False)):
            failures.append("利润依赖一次性收益")
        if pd.notna(row.get("资产负债率")) and float(row["资产负债率"]) > 70:
            failures.append("高杠杆")
        if pd.notna(row.get("经营现金流/净利润")) and float(row["经营现金流/净利润"]) < 80:
            failures.append("利润现金含量偏低")
        if (
            pd.notna(row.get("营业收入多年趋势"))
            and pd.notna(row.get("归母净利润多年趋势"))
            and (
                float(row["营业收入多年趋势"]) <= 0
                or float(row["归母净利润多年趋势"]) <= 0
            )
        ):
            failures.append("收入或利润长期趋势非正")
        if pd.notna(row.get("ROIC")) and float(row["ROIC"]) < 8:
            failures.append("资本回报率偏低")
        if int(row.get("估值方法有效数") or 0) < 3:
            failures.append("三类独立估值不完整")
        if bool(row.get("特殊行业", False)):
            failures.append("特殊行业缺少专用模型")
        return "；".join(failures) or "未触发主要反向失败项"

    if data.empty:
        data["芒格反向失败清单"] = pd.Series(index=data.index, dtype=str)
    else:
        data["芒格反向失败清单"] = data.apply(inverse_checklist, axis=1)
    quality_total = (
        data["生意质量与护城河评分"]
        + data["管理层与资本配置评分"]
        + data["盈利能力与韧性评分"]
        + data["现金流质量评分"]
    )
    data["市场错配判断"] = np.select(
        [
            safety_margin.ge(strategy["formal_margin"])
            & quality_total.ge(32)
            & data["十年成长跑道评分"].ge(5),
            dividend.ge(4) & safety_margin.ge(10),
            data["估值与安全边际评分"].ge(10) & quality_total.lt(25),
        ],
        ["优质成长被低估", "高股息价值错配", "便宜但质量尚未证实"],
        default="未发现明确市场错配",
    )
    pe_relative = _numeric(data, "PE TTM").div(
        _numeric(data, "行业PE TTM中位数").where(
            _numeric(data, "行业PE TTM中位数") > 0
        )
    )
    data["已计价预期"] = np.select(
        [
            pe_relative.le(0.70) & revenue_trend.gt(0) & profit_trend.gt(0),
            pe_relative.ge(1.30) | safety_margin.lt(0),
        ],
        [
            "价格隐含偏低的增长或质量预期，需验证是否为误价而非价值陷阱",
            "市场已计入较高预期或当前价格高于保守价值",
        ],
        default="市场预期接近同行中枢，尚无明显预期差",
    )
    data["为何现在"] = np.where(
        data["市场错配判断"].ne("未发现明确市场错配"),
        "当前估值折价与基本面质量同时出现，形成进一步研究窗口",
        "暂不急于行动，等待价格、更强现金流或经营证据改善",
    )
    if data.empty:
        data["长期投资关键证据"] = pd.Series(index=data.index, dtype=str)
    else:
        data["长期投资关键证据"] = data.apply(
            lambda row: (
                f"完整年度ROE={_evidence_value(row.get('ROE'))}%；"
                f"ROIC={_evidence_value(row.get('ROIC'))}%；"
                f"收入多年趋势={_evidence_value(row.get('营业收入多年趋势'))}%；"
                f"利润多年趋势={_evidence_value(row.get('归母净利润多年趋势'))}%；"
                f"经营现金流/净利润={_evidence_value(row.get('经营现金流/净利润'))}%；"
                f"安全边际={_evidence_value(row.get('安全边际'))}%"
            ),
            axis=1,
        )
    if data.empty:
        data["九维评分明细"] = pd.Series(index=data.index, dtype=str)
    else:
        data["九维评分明细"] = data.apply(
            lambda row: "；".join(
                f"{name}{row.get(f'{name}评分', 0)}/{weights[name]}"
                for name in DIMENSIONS
            ),
            axis=1,
        )
    return data.sort_values("综合评分", ascending=False)


def add_decision_fields(
    frame: pd.DataFrame, strategy: dict | None = None
) -> pd.DataFrame:
    strategy = strategy or DEFAULT_STRATEGY
    data = frame.copy()
    score = _numeric(data, "综合评分")
    margin = _numeric(data, "安全边际")
    valuation_cov = _numeric(data, "可靠估值覆盖率")
    report_cov = _numeric(data, "财报覆盖率")
    cash_complete = _boolean(data, "现金流完整")
    no_veto = data.get("一票否决原因", pd.Series("", index=data.index)).fillna("").eq("")
    model_valid = _boolean(data, "估值模型可用于正式推荐")
    quality_gates = strategy["quality_gates"]
    long_term_quality = pd.Series(True, index=data.index)
    for name, threshold in quality_gates.items():
        long_term_quality &= _numeric(data, f"{name}评分").ge(threshold)
    data["十年持有质量门槛"] = long_term_quality
    data["是否正式推荐"] = (
        score.ge(strategy["formal_score"])
        & margin.ge(strategy["formal_margin"])
        & valuation_cov.eq(100)
        & report_cov.ge(70)
        & cash_complete
        & no_veto
        & model_valid
        & long_term_quality
        & data.get("市场错配判断", pd.Series("", index=data.index)).ne("未发现明确市场错配")
    )

    def reason(row: pd.Series) -> str:
        reasons = []
        if pd.isna(row.get("综合评分")) or float(row.get("综合评分") or 0) < strategy["formal_score"]:
            reasons.append(f"综合评分不足{strategy['formal_score']}分")
        if pd.isna(row.get("安全边际")):
            reasons.append("无可靠绝对估值，不计算正式安全边际")
        elif float(row["安全边际"]) < strategy["formal_margin"]:
            reasons.append(f"安全边际不足{strategy['formal_margin']}%")
        if float(row.get("可靠估值覆盖率") or 0) < 100:
            reasons.append("三个独立估值族未全部覆盖")
        if float(row.get("估值方法有效数") or 0) < 3:
            reasons.append("独立估值方法不足3种")
        if float(row.get("财报覆盖率") or 0) < 70:
            reasons.append("财报覆盖率不足70%")
        if not bool(row.get("现金流完整", False)):
            reasons.append("现金流不完整")
        if row.get("一票否决原因"):
            reasons.append(str(row["一票否决原因"]))
        if bool(row.get("特殊行业", False)):
            reasons.append("特殊行业暂无专用模型，仅可观察")
        if not bool(row.get("行业估值样本充足", False)):
            reasons.append("同行样本不足，不生成行业估值结论")
        if not bool(row.get("估值模型可用于正式推荐", False)):
            reasons.append("估值模型仅可用于观察")
        if not bool(row.get("十年持有质量门槛", False)):
            reasons.append("九维长期质量门槛未全部达到")
        if row.get("市场错配判断") == "未发现明确市场错配":
            reasons.append("未发现可验证的市场错配")
        return "；".join(dict.fromkeys(reasons)) or "已达到正式推荐量化条件"

    data["未达推荐原因"] = data.apply(reason, axis=1)
    data["距离推荐标准差距"] = data["未达推荐原因"]
    data["下一步观察重点"] = data.apply(
        lambda row: (
            "验证护城河、资本配置、成长跑道和反向失败清单；等待更大安全边际"
            if row.get("未达推荐原因")
            else "持续跟踪护城河、自由现金流、资本配置和估值修复"
        ),
        axis=1,
    )
    data["十年持有结论"] = np.where(
        data["是否正式推荐"],
        "十年持有研究候选：允许进入人工深度尽调，不代表无条件买入",
        "观察或等待证据：尚未同时满足质量、成长、错配与安全边际",
    )
    data["操作建议"] = np.where(data["是否正式推荐"], "正式研究结论，仍需人工复核", "继续观察，不构成推荐")
    data["估值评分"] = data.get("估值因子", 0)
    data["现金流评分"] = data.get("现金流质量", 0)
    data["盈利能力评分"] = data.get("质量因子", 0)
    data["资产负债评分"] = data.get("资产负债安全", 0)
    data["成长性评分"] = data.get("成长因子", 0)
    data["分红评分"] = data.get("股东回报因子", 0)
    return data


def scan_light(project_root: Path, force: bool = False) -> tuple[pd.DataFrame, dict]:
    manager = DataSourceManager(project_root)
    strategy = load_strategy(project_root)
    frame, meta = manager.combined_light_data(force=force, strategy=strategy)
    benchmark, benchmark_meta = manager.build_domestic_valuation(force=force)
    frame = apply_intraday_market_cap(frame)
    frame = attach_industry_benchmarks(frame, benchmark)
    meta["benchmark"] = {
        **benchmark_meta,
        "scope": "境内全部上市A股，含主板、创业板、科创板、北交所；排除ST、退市及非股票证券",
        "input_count": len(benchmark),
    }
    meta["recommendation_scope"] = strategy_scope_config(strategy)
    classifications = frame["行业"].map(classify_industry)
    frame["行业模型分类"] = classifications.map(lambda value: value[0])
    frame["特殊行业"] = classifications.map(lambda value: value[1])
    manager.cache.write("watchlist.csv", frame)
    return frame, meta


def scan_candidates(project_root: Path, force: bool = False) -> tuple[pd.DataFrame, dict]:
    frame, meta = scan_light(project_root, force=force)
    strategy = load_strategy(project_root)
    candidates = valuation_filter(
        frame,
        candidate_limit=int(strategy["candidate_limit"]),
    )
    DataSourceManager(project_root).cache.write(
        f"daily_candidates_{date.today().isoformat()}.csv", candidates
    )
    return candidates, meta


def _prepare_scored_candidates(
    project_root: Path,
    candidates: pd.DataFrame,
    financial_limit: int,
    force: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    manager = DataSourceManager(project_root)
    strategy = load_strategy(project_root)
    prefetch_limit = min(
        len(candidates),
        max(financial_limit, financial_limit + DEEP_REVIEW_PREFETCH_BUFFER),
    )
    requested = candidates["代码"].head(prefetch_limit).tolist()
    financial, financial_meta = manager.build_financial(requested, force=force)
    merged = candidates.head(prefetch_limit).merge(financial, on="代码", how="left")
    merged["财报覆盖率"] = (
        merged[[field for field in FINANCIAL_FIELDS if field in merged]].notna().mean(axis=1) * 100
    ).round(2)
    merged["现金流完整"] = merged[[field for field in CASH_FIELDS if field in merged]].notna().all(axis=1)
    selected = _select_deep_review_candidates(merged, financial_limit)
    details = financial_filter_details(selected)
    checked = add_decision_fields(
        score_candidates(details, strategy=strategy),
        strategy=strategy,
    )
    passed = checked[checked["一票否决原因"] == ""].copy()
    financial_meta = {
        **financial_meta,
        "financial_prefetch_requested": prefetch_limit,
        "financial_selected_for_review": len(selected),
        "financial_ready_candidates": int(_financial_ready_mask(merged).sum()),
    }
    return passed, checked, financial[financial["代码"].isin(selected["代码"])].copy(), financial_meta


def analyze_top10(
    project_root: Path,
    financial_limit: int = MAX_LIGHT_CANDIDATES,
    force: bool = False,
) -> tuple[pd.DataFrame, dict]:
    manager = DataSourceManager(project_root)
    light, meta = scan_light(project_root, force=force)
    prefetch_limit = deep_review_prefetch_limit(len(light), financial_limit)
    candidates = valuation_filter(light, candidate_limit=prefetch_limit)
    scored, details, financial, financial_meta = _prepare_scored_candidates(
        project_root, candidates, financial_limit, force
    )
    top = scored.head(10).copy()
    manager.cache.write(f"top_candidates_{date.today().isoformat()}.csv", top)
    meta.update({
        "financial": financial_meta,
        "financial_requested": financial_meta.get(
            "financial_selected_for_review", min(len(candidates), financial_limit)
        ),
        "financial_frame": details,
        "passed_frame": scored,
        "all_scored_frame": scored,
    })
    return top, meta


def select_outputs(
    scored: pd.DataFrame,
    recommendation_ready: bool,
    strategy: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    strategy = strategy or DEFAULT_STRATEGY
    formal = (
        scored[scored["是否正式推荐"]]
        .head(int(strategy["max_formal"]))
        .copy()
        if recommendation_ready
        else scored.iloc[0:0].copy()
    )
    no_veto = scored.get(
        "一票否决原因", pd.Series("", index=scored.index)
    ).fillna("").eq("")
    observations = scored[
        (~scored["是否正式推荐"])
        & no_veto
        & _numeric(scored, "综合评分").ge(strategy["watch_score"])
    ].head(int(strategy["max_watch"])).copy()
    if not observations.empty:
        observations["观察排名"] = range(1, len(observations) + 1)
        observations["股票类型"] = "观察股票"
        observations["是否观察股票"] = "是"
        observations["操作建议"] = "继续观察，不构成推荐"
    return formal, observations


def scan_universe(
    project_root: Path,
    reports_dir: Path,
    limit: int | None = None,
    financial_limit: int = MAX_LIGHT_CANDIDATES,
    force: bool = False,
) -> dict:
    started = time.perf_counter()
    manager = DataSourceManager(project_root)
    strategy = load_strategy(project_root)
    scope = strategy_scope_config(strategy)
    try:
        from src.tushare_client import TushareClient

        raw_count = len(TushareClient().stock_basic())
    except Exception:
        raw_count = len(manager.cache.read(scope["universe_cache"]))
    light, source_meta = scan_light(project_root, force=force)
    if limit:
        light = light.head(limit).copy()
    main_board_count = int(
        light.get("上市板块", pd.Series(dtype=str))
        .astype(str)
        .isin({"沪市主板", "深市主板"})
        .sum()
    )
    target_limit = int(strategy["candidate_limit"])
    prefetch_limit = deep_review_prefetch_limit(len(light), target_limit)
    candidates = valuation_filter(
        light,
        candidate_limit=prefetch_limit,
    )
    scored, details, financial, financial_meta = _prepare_scored_candidates(
        project_root, candidates, min(financial_limit, target_limit, len(candidates)), force
    )
    top = scored.head(10).copy()
    formal_run = limit is None
    if formal_run:
        manager.cache.write(f"daily_candidates_{date.today().isoformat()}.csv", candidates)
        manager.cache.write(f"top_candidates_{date.today().isoformat()}.csv", top)
    valuation_cov = valuation_coverage(light)
    financial_cov = row_coverage(details, FINANCIAL_FIELDS)
    cash_cov = row_coverage(details, CASH_FIELDS)
    recommendation_ready = valuation_cov >= 80 and financial_cov >= 70 and cash_cov >= 70
    formal, observations = select_outputs(
        scored, recommendation_ready, strategy=strategy
    )
    market_kind = source_meta.get("market", {}).get("market_data_kind", "")
    no_reason = ""
    if not recommendation_ready:
        no_reason = "数据覆盖率未达到正式推荐门槛"
    elif formal.empty:
        no_reason = "全部通过一票否决的候选中，无股票同时满足评分、安全边际、估值覆盖和现金流要求"
    result = {
        "原始股票数量": raw_count,
        "推荐范围": scope["label"],
        "推荐范围说明": scope["scope_description"],
        "推荐范围股票数量": len(light),
        "主板股票数量": main_board_count,
        "国内全市场基准股票数量": int(
            source_meta.get("benchmark", {}).get("input_count", 0)
        ),
        "行业基准范围": source_meta.get("benchmark", {}).get(
            "scope", scope["scope_description"]
        ),
        "行情覆盖率": row_coverage(light, ["当前价格"]),
        "估值覆盖率": valuation_cov,
        "财报覆盖率": financial_cov,
        "现金流覆盖率": cash_cov,
        "分红覆盖率": row_coverage(light, ["股息率"]),
        "Tushare是否可用": True,
        "Tushare覆盖数量": int((light[VALUATION_FIELDS].notna().sum(axis=1) >= 4).sum()),
        "东方财富失败原因": source_meta.get("market", {}).get("failures", []),
        "估值轻筛通过数量": len(details),
        "估值轻筛预取数量": len(candidates),
        "财务快筛通过数量": int(details[FINANCIAL_FIELDS].notna().all(axis=1).sum()) if not details.empty else 0,
        "一票否决后数量": len(scored),
        "正式条件检查数量": len(details),
        "深度分析数量": min(len(scored), 10),
        "最终推荐数量": len(formal),
        "观察股票数量": len(observations),
        "策略名称": strategy["name"],
        "策略版本": strategy["version"],
        "正式推荐分数门槛": strategy["formal_score"],
        "正式推荐安全边际门槛": strategy["formal_margin"],
        "观察分数门槛": strategy["watch_score"],
        "九维权重": strategy["weights"],
        "无推荐原因": no_reason or "无",
        "缓存命中率": round(
            100 * sum([
                bool(source_meta.get("universe", {}).get("cache_hit")),
                bool(source_meta.get("valuation", {}).get("cache_hit")),
                bool(financial_meta.get("cache_hit")),
            ]) / 3,
            2,
        ),
        "总耗时": round(time.perf_counter() - started, 2),
        "是否满足正式推荐条件": recommendation_ready,
        "估值数据交易日": source_meta.get("valuation", {}).get("trade_date", "数据不足"),
        "财报数据报告期": str(details.get("对齐报告期", pd.Series(dtype=str)).dropna().max()) if not details.empty else "数据不足",
        "现金流数据报告期": str(details.get("对齐报告期", pd.Series(dtype=str)).dropna().max()) if not details.empty else "数据不足",
        "行情数据时间": source_meta.get("market", {}).get("data_time", "数据不足"),
        "行情交易日": source_meta.get("market", {}).get("trade_date", "数据不足"),
        "行情数据类型": market_kind or "未知",
        "行情是否降级": source_meta.get("market", {}).get("degraded", False),
        "行情降级原因": source_meta.get("market", {}).get("degradation_reason", ""),
        "数据性质": (
            "价格、市值和安全边际统一使用前一交易日最新收盘口径"
            if market_kind in (
                "previous_trading_day_close",
                "previous_trading_day_close_cache",
            )
            else "价格、市值和安全边际口径异常，需人工复核"
        ),
        "数据源": {**source_meta, "financial": financial_meta},
        "候选Top10": top.fillna("数据不足").to_dict("records"),
        "正式推荐股票": formal.fillna("数据不足").to_dict("records"),
        "观察股票": observations.fillna("数据不足").to_dict("records"),
        "观察股票不足5只原因": (
            f"综合评分达到{strategy['watch_score']}分且未正式推荐的候选不足"
            f"{strategy['max_watch']}只"
            if len(observations) < int(strategy["max_watch"]) else "无"
        ),
    }
    if formal_run:
        result["每日股票数据"] = write_daily_stock_history(
            project_root / "data",
            run_date=date.today().isoformat(),
            analysis_trade_date=str(result["估值数据交易日"]),
            frames={
                "all_stocks": light,
                "light_candidates": candidates,
                "reviewed_candidates": details,
                "passed_candidates": scored,
            },
            metadata={
                "scope": result["推荐范围说明"],
                "strategy": {
                    "name": result["策略名称"],
                    "version": result["策略版本"],
                    "formal_score": result["正式推荐分数门槛"],
                    "formal_margin": result["正式推荐安全边际门槛"],
                    "watch_score": result["观察分数门槛"],
                    "weights": result["九维权重"],
                },
                "source": result["数据源"],
            },
        )
        save_scan_summary(result, reports_dir)
    else:
        result["调试模式"] = f"limit={limit}，未写入正式日报、候选缓存和每日股票历史"
    return result


def save_scan_summary(result: dict, reports_dir: Path, day: str | None = None) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    day = day or date.today().isoformat()
    (reports_dir / f"{day}_scan_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    lines = [f"# {result.get('推荐范围', 'A股全市场')}扫描统计", ""]
    for key, value in result.items():
        if key not in ("候选Top10", "数据源"):
            lines.append(f"- {key}: {value}")
    (reports_dir / f"{day}_scan_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
