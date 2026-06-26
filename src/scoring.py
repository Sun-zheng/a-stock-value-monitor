from __future__ import annotations

from src.financial_analyzer import Candidate


def _bounded(value: float, low: float, high: float, points: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return points
    return points * (value - low) / (high - low)


def score(candidate: Candidate) -> None:
    pe = candidate.values.get("PE TTM")
    pb = candidate.values.get("PB")
    roe = candidate.values.get("ROE")
    cash_ratio = candidate.values.get("经营现金流/净利润")
    debt = candidate.values.get("资产负债率")
    margin = candidate.values.get("净利率")

    valuation = 0.0
    if pe is not None and 0 < pe <= 20:
        valuation += 15 if pe <= 12 else 10
    if pb is not None and 0 < pb <= 2:
        valuation += 10 if pb <= 1.2 else 6
    cash = _bounded(cash_ratio or 0, 0, 120, 20)
    profitability = _bounded(roe or 0, 0, 18, 14) + _bounded(margin or 0, 0, 15, 6)
    balance = _bounded(100 - (debt if debt is not None else 100), 15, 70, 15)
    growth = 0.0
    dividend = 0.0

    parts = {
        "估值评分": round(valuation, 2),
        "现金流评分": round(cash, 2),
        "盈利能力评分": round(profitability, 2),
        "资产负债评分": round(balance, 2),
        "成长性评分": round(growth, 2),
        "分红评分": round(dividend, 2),
    }
    total = round(sum(parts.values()), 2)
    candidate.values.update(parts)
    candidate.values["综合评分"] = total
    if total >= 85:
        level = "高关注"
    elif total >= 75:
        level = "可关注"
    elif total >= 65:
        level = "观察"
    else:
        level = "不推荐"
    candidate.values["推荐等级"] = level

