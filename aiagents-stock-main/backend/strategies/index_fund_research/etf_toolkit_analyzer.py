from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from backend.strategies.index_fund_research.index_fund_analyzer import (
    FundResearchConfig,
    IndexFundResearchAnalyzer,
    _num,
)


RISK_PROFILES = {
    "稳健": {"core": 0.75, "satellite": 0.25, "max_single": 0.25, "min_risk_score": 45},
    "平衡": {"core": 0.60, "satellite": 0.40, "max_single": 0.22, "min_risk_score": 35},
    "进取": {"core": 0.45, "satellite": 0.55, "max_single": 0.20, "min_risk_score": 25},
}


@dataclass(frozen=True)
class ETFToolkitConfig:
    max_history: int = 80
    min_turnover: float = 20_000_000
    min_price: float = 0.0
    start_date: str = "20210101"


class ETFToolkitAnalyzer(IndexFundResearchAnalyzer):
    """ETF screener, rotation, and portfolio construction workflow."""

    def analyze_toolkit(self, config: ETFToolkitConfig | None = None) -> dict:
        config = config or ETFToolkitConfig()
        base_config = FundResearchConfig(
            history_candidates=config.max_history,
            min_turnover=config.min_turnover,
            start_date=config.start_date,
        )
        snapshot = self.fetch_market_snapshot(base_config)
        if not snapshot.empty:
            snapshot = snapshot[pd.to_numeric(snapshot["最新价"], errors="coerce").fillna(0).ge(config.min_price)]
        universe = self.fetch_universe(base_config, snapshot)
        rows: list[dict] = []
        errors: list[str] = []
        for _, fund in universe.iterrows():
            code = str(fund["代码"]).zfill(6)
            try:
                history = self.history_fetcher(code, config.start_date)
                row = self._analyze_one(fund.to_dict(), history, base_config)
                if row:
                    rows.append(self._enrich_toolkit_row(row))
            except Exception as exc:
                errors.append(f"{code}: {type(exc).__name__}: {exc}")

        frame = pd.DataFrame(rows)
        screener = self._build_screener(frame)
        rotation = self._build_rotation(frame)
        portfolios = {
            profile: self._build_portfolio(frame, profile)
            for profile in RISK_PROFILES
        }
        report = self.build_toolkit_report(screener, rotation, portfolios, errors)
        return {
            "success": bool(rows),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": config.__dict__,
            "market_snapshot_count": int(len(snapshot)),
            "analyzed_count": int(len(rows)),
            "error_count": len(errors),
            "errors": errors[:20],
            "screener": screener,
            "rotation": rotation,
            "portfolios": portfolios,
            "report": report,
            "workflow": [
                "全市场ETF快照: 过滤可交易ETF，保留价格、成交额、市值、涨跌幅和分类。",
                "历史指标计算: 拉取真实日线，计算1/3/6/12月收益、回撤、波动、均线趋势。",
                "筛选器: 支持按类型、成交额、回撤、收益、波动和价格进行二次过滤。",
                "轮动策略: 按分类聚合动量、趋势、风险和成交额，识别强势、改善、滞后方向。",
                "组合配置: 采用核心-卫星框架，根据稳健/平衡/进取风险偏好生成ETF权重。",
            ],
        }

    @staticmethod
    def _enrich_toolkit_row(row: dict) -> dict:
        one_year = _num(row.get("近一年收益"))
        drawdown = _num(row.get("高点回撤"))
        rebound = _num(row.get("低点反弹"))
        vol = _num(row.get("年化波动"))
        current = _num(row.get("最新价"))
        ma20 = _num(row.get("MA20"))
        ma60 = _num(row.get("MA60"))
        ma120 = _num(row.get("MA120"))
        trend_score = 0
        trend_score += 25 if current >= ma20 else 0
        trend_score += 30 if current >= ma60 else 0
        trend_score += 20 if ma20 >= ma60 else 0
        trend_score += 25 if ma60 >= ma120 else 0
        momentum_score = max(0, min(100, one_year + rebound * 0.4 + trend_score * 0.5))
        row["趋势评分"] = round(trend_score, 2)
        row["动量评分"] = round(momentum_score, 2)
        row["筛选评分"] = round(
            momentum_score * 0.34
            + max(0, min(100, abs(drawdown) * 1.5)) * 0.22
            + _num(row.get("风险评分")) * 0.24
            + min(100, _num(row.get("成交额")) / 50_000_000) * 0.20,
            2,
        )
        row["风险标签"] = ETFToolkitAnalyzer._risk_label(vol, _num(row.get("成交额")), drawdown)
        return row

    @staticmethod
    def _risk_label(vol: float, turnover: float, drawdown: float) -> str:
        labels = []
        if turnover < 30_000_000:
            labels.append("流动性偏弱")
        if vol >= 35:
            labels.append("高波动")
        if drawdown <= -50:
            labels.append("深回撤")
        return "、".join(labels) or "正常"

    @staticmethod
    def _build_screener(frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []
        return frame.sort_values(["筛选评分", "成交额"], ascending=[False, False]).to_dict("records")

    @staticmethod
    def _build_rotation(frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []
        rows = []
        for category, group in frame.groupby("分类"):
            momentum = float(group["动量评分"].mean())
            trend = float(group["趋势评分"].mean())
            risk = float(group["风险评分"].mean())
            turnover = float(group["成交额"].sum())
            score = momentum * 0.45 + trend * 0.25 + risk * 0.15 + min(100, turnover / 200_000_000) * 0.15
            if momentum >= 65 and trend >= 65:
                phase = "强势领先"
            elif momentum >= 55 and trend < 65:
                phase = "改善中"
            elif momentum < 40 and trend < 50:
                phase = "滞后"
            else:
                phase = "震荡观察"
            leader = group.sort_values("筛选评分", ascending=False).iloc[0]
            rows.append({
                "分类": category,
                "轮动评分": round(score, 2),
                "平均动量": round(momentum, 2),
                "平均趋势": round(trend, 2),
                "平均风险": round(risk, 2),
                "成交额合计": round(turnover, 2),
                "阶段": phase,
                "代表ETF": f"{leader['名称']}（{leader['代码']}）",
            })
        return sorted(rows, key=lambda item: item["轮动评分"], reverse=True)

    @staticmethod
    def _build_portfolio(frame: pd.DataFrame, profile: str) -> dict:
        if frame.empty:
            return {"profile": profile, "positions": [], "notes": "无可用ETF"}
        rule = RISK_PROFILES[profile]
        eligible = frame[frame["风险评分"].ge(rule["min_risk_score"])].copy()
        if eligible.empty:
            eligible = frame.copy()
        core = eligible[eligible["分类"].isin(["红利/宽基", "港股/海外", "其他"])].sort_values("筛选评分", ascending=False)
        satellite = eligible[~eligible.index.isin(core.index)].sort_values("筛选评分", ascending=False)
        positions = []
        core_count = min(3, len(core))
        satellite_count = min(4, len(satellite))
        if core_count:
            weight = rule["core"] / core_count
            for _, item in core.head(core_count).iterrows():
                positions.append(ETFToolkitAnalyzer._position(item, min(weight, rule["max_single"]), "核心"))
        if satellite_count:
            weight = rule["satellite"] / satellite_count
            for _, item in satellite.head(satellite_count).iterrows():
                positions.append(ETFToolkitAnalyzer._position(item, min(weight, rule["max_single"]), "卫星"))
        total = sum(item["权重"] for item in positions) or 1
        for item in positions:
            item["权重"] = round(item["权重"] / total * 100, 2)
        return {
            "profile": profile,
            "positions": positions,
            "notes": "核心-卫星配置；建议月度观察、季度再平衡，单只ETF偏离目标权重5个百分点以上再调整。",
        }

    @staticmethod
    def _position(item: pd.Series, weight: float, bucket: str) -> dict:
        return {
            "代码": item["代码"],
            "名称": item["名称"],
            "分类": item["分类"],
            "层级": bucket,
            "权重": weight,
            "筛选评分": round(float(item["筛选评分"]), 2),
            "风险标签": item["风险标签"],
        }

    @staticmethod
    def build_toolkit_report(
        screener: list[dict],
        rotation: list[dict],
        portfolios: dict,
        errors: list[str] | None = None,
    ) -> str:
        errors = errors or []
        lines = [
            "# ETF策略工具箱报告",
            "",
            "## 总览",
            "",
            f"- 全市场筛选候选：{len(screener)} 只。",
            f"- 轮动分类数量：{len(rotation)} 个。",
            "- 组合框架：核心-卫星，按风险偏好生成权重并建议季度再平衡。",
            "",
            "## 轮动方向",
            "",
            "| 排名 | 分类 | 阶段 | 轮动评分 | 代表ETF |",
            "|---:|---|---|---:|---|",
        ]
        for index, item in enumerate(rotation[:8], start=1):
            lines.append(f"| {index} | {item['分类']} | {item['阶段']} | {item['轮动评分']} | {item['代表ETF']} |")
        lines.extend(["", "## 筛选器Top ETF", "", "| 排名 | 代码 | 名称 | 分类 | 筛选评分 | 风险标签 |", "|---:|---|---|---|---:|---|"])
        for index, item in enumerate(screener[:10], start=1):
            lines.append(f"| {index} | {item['代码']} | {item['名称']} | {item['分类']} | {item['筛选评分']} | {item['风险标签']} |")
        lines.extend(["", "## 组合配置", ""])
        for profile, portfolio in portfolios.items():
            lines.extend([f"### {profile}", "", portfolio.get("notes", "")])
            for item in portfolio.get("positions", []):
                lines.append(f"- {item['层级']}：{item['名称']}（{item['代码']}） {item['权重']}%，{item['风险标签']}。")
            lines.append("")
        if errors:
            lines.extend(["## 数据问题", "", f"- 历史行情失败 {len(errors)} 条，样例：{errors[:3]}"])
        return "\n".join(lines)
