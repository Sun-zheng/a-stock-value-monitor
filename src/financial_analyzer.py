from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.data_fetcher import safe_number


@dataclass
class Candidate:
    code: str
    name: str
    exchange: str
    board: str
    industry: str = "数据不足"
    values: dict = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    veto_reasons: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def from_spot_row(row: pd.Series, exchange: str, board: str) -> Candidate:
    mapping = {
        "当前价格": "最新价",
        "涨跌幅": "涨跌幅",
        "当前市值": "总市值",
        "流通市值": "流通市值",
        "PE TTM": "市盈率-动态",
        "PB": "市净率",
    }
    values = {target: safe_number(row.get(source)) for target, source in mapping.items()}
    return Candidate(
        code=str(row.get("代码")).zfill(6),
        name=str(row.get("名称")),
        exchange=exchange,
        board=board,
        industry=str(row.get("行业") or "数据不足"),
        values=values,
        sources=["AkShare/东方财富 A股实时行情"],
    )


def apply_financial_data(candidate: Candidate, frame: pd.DataFrame, source: str) -> None:
    candidate.sources.append(source)
    if frame.empty:
        candidate.veto_reasons.append("无法获取关键财务数据")
        return
    recent = frame.head(3).copy()
    aliases = {
        "ROE": ["净资产收益率(%)", "加权净资产收益率(%)"],
        "毛利率": ["销售毛利率(%)"],
        "净利率": ["销售净利率(%)"],
        "资产负债率": ["资产负债率(%)"],
        "经营现金流/净利润": ["经营现金净流量与净利润的比率(%)"],
    }
    for target, columns in aliases.items():
        for column in columns:
            if column in recent.columns:
                candidate.values[target] = safe_number(recent.iloc[0][column])
                break

    required = ("ROE", "资产负债率", "经营现金流/净利润")
    if any(candidate.values.get(key) is None for key in required):
        candidate.veto_reasons.append("关键财务数据不完整")
    debt = candidate.values.get("资产负债率")
    if debt is not None and debt > 85:
        candidate.veto_reasons.append("资产负债率过高")
    cash_ratio = candidate.values.get("经营现金流/净利润")
    if cash_ratio is not None and cash_ratio < 0:
        candidate.veto_reasons.append("经营现金流与利润匹配度异常")

