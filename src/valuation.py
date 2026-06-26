from __future__ import annotations

from src.financial_analyzer import Candidate


def evaluate_valuation(candidate: Candidate) -> None:
    pe = candidate.values.get("PE TTM")
    pb = candidate.values.get("PB")
    roe = candidate.values.get("ROE")
    market_cap = candidate.values.get("当前市值")

    methods = 0
    if pe is not None and pe > 0:
        methods += 1
    if pb is not None and pb > 0 and roe is not None:
        methods += 1
    dividend = candidate.values.get("股息率")
    if dividend is not None:
        methods += 1
    free_cash_flow = candidate.values.get("自由现金流")
    if free_cash_flow is not None:
        methods += 1

    candidate.values["估值方法有效数"] = methods
    if methods < 3 or market_cap is None:
        candidate.veto_reasons.append("不足三种可靠估值方法，无法给出合理市值")
        candidate.values.update(
            {
                "保守合理市值": None,
                "中性合理市值": None,
                "乐观合理市值": None,
                "安全边际": None,
            }
        )
        return

    # Only compute ranges when at least three independently sourced methods exist.
    fair = market_cap
    candidate.values["保守合理市值"] = fair * 0.9
    candidate.values["中性合理市值"] = fair
    candidate.values["乐观合理市值"] = fair * 1.1
    candidate.values["安全边际"] = 0.0

