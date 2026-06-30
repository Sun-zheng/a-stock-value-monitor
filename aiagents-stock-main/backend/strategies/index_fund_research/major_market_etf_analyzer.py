from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from backend.strategies.index_fund_research.index_fund_analyzer import (
    FundResearchConfig,
    IndexFundResearchAnalyzer,
    _num,
)


MAJOR_INDEX_KEYWORDS = (
    "沪深300", "中证A500", "A500", "中证500", "中证1000", "上证50",
    "上证指数", "上证综指", "深证100", "创业板", "科创50", "科创100",
    "恒生", "恒生科技", "港股通", "纳指", "纳斯达克", "标普", "标普500",
)

MAJOR_INDEX_EXCLUDE_KEYWORDS = (
    "增强", "红利", "行业", "证券", "银行", "医药", "创新药", "半导体",
    "芯片", "通信", "光伏", "新能源", "机器人", "消费", "旅游", "军工",
)


@dataclass(frozen=True)
class MajorMarketETFConfig:
    top_n: int = 12
    history_candidates: int = 40
    min_turnover: float = 30_000_000
    start_date: str = "20210101"


class MajorMarketETFAnalyzer(IndexFundResearchAnalyzer):
    """Analyze major broad-market ETF indices with real market data."""

    @staticmethod
    def _is_major_market_etf(name: str) -> bool:
        text = str(name or "")
        if not any(keyword.upper() in text.upper() for keyword in MAJOR_INDEX_KEYWORDS):
            return False
        if any(keyword in text for keyword in MAJOR_INDEX_EXCLUDE_KEYWORDS):
            return False
        return True

    def fetch_major_universe(self, config: MajorMarketETFConfig) -> pd.DataFrame:
        base_config = FundResearchConfig(
            top_n=config.top_n,
            history_candidates=500,
            min_turnover=config.min_turnover,
            start_date=config.start_date,
            diversify_categories=False,
        )
        snapshot = self.fetch_market_snapshot(base_config)
        if snapshot.empty:
            return snapshot
        major = snapshot[snapshot["名称"].map(self._is_major_market_etf)].copy()
        return major.sort_values("成交额", ascending=False).head(config.history_candidates)

    def analyze_major_market(self, config: MajorMarketETFConfig | None = None) -> dict:
        config = config or MajorMarketETFConfig()
        universe = self.fetch_major_universe(config)
        market_context = self._build_market_context(universe)
        rows: list[dict] = []
        errors: list[str] = []
        base_config = FundResearchConfig(
            top_n=config.top_n,
            history_candidates=config.history_candidates,
            min_turnover=config.min_turnover,
            start_date=config.start_date,
            min_drawdown_pct=0,
            diversify_categories=False,
        )
        for _, fund in universe.iterrows():
            code = str(fund["代码"]).zfill(6)
            try:
                history = self.history_fetcher(code, config.start_date)
                row = self._analyze_major_one(fund.to_dict(), history, base_config)
                if row:
                    rows.append(row)
            except Exception as exc:
                errors.append(f"{code}: {type(exc).__name__}: {exc}")

        frame = pd.DataFrame(rows)
        if frame.empty:
            selected: list[dict] = []
        else:
            frame = frame.sort_values(
                ["大盘配置评分", "成交额"],
                ascending=[False, False],
            )
            selected = frame.head(config.top_n).to_dict("records")
        report = self.build_major_report(selected, config, market_context, errors)
        return {
            "success": bool(selected),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": config.__dict__,
            "workflow": [
                "抓取全市场 ETF 实时行情，过滤主要宽基指数 ETF。",
                "对每只宽基 ETF 拉取真实日线历史行情，东方财富失败时切换新浪真实行情。",
                "计算历史高点回撤、低点反弹、近一年收益、波动率、均线趋势和成交额。",
                "由大盘策略、趋势配置、风险控制三类智能体给出配置观点。",
                "按大盘配置评分排序，形成网页、邮件和飞书可读报告。",
            ],
            "market_context": market_context,
            "universe_count": int(len(universe)),
            "analyzed_count": int(len(rows)),
            "error_count": len(errors),
            "errors": errors[:20],
            "candidates": selected,
            "report": report,
        }

    def _analyze_major_one(self, fund: dict, history: pd.DataFrame, config: FundResearchConfig) -> dict | None:
        row = self._analyze_one(fund, history, config)
        if not row:
            return None
        liquidity_score = min(100.0, max(0.0, _num(row.get("成交额")) / 50_000_000))
        valuation_score = max(0.0, min(100.0, abs(_num(row.get("高点回撤"))) * 1.6))
        trend_score = self._major_trend_score(row)
        risk_score = _num(row.get("风险评分"))
        allocation_score = valuation_score * 0.28 + trend_score * 0.32 + risk_score * 0.20 + liquidity_score * 0.20
        row["大盘配置评分"] = round(allocation_score, 2)
        row["配置观点"] = self._allocation_view(row, trend_score)
        row["智能体观点"] = {
            "大盘策略智能体": self._market_agent_view(row),
            "趋势配置智能体": row["配置观点"],
            "风险控制智能体": row["风险边界"],
        }
        return row

    @staticmethod
    def _major_trend_score(row: dict) -> float:
        current = _num(row.get("最新价"))
        ma20 = _num(row.get("MA20"))
        ma60 = _num(row.get("MA60"))
        ma120 = _num(row.get("MA120"))
        score = 40.0
        if current >= ma20:
            score += 15
        if current >= ma60:
            score += 20
        if ma20 >= ma60:
            score += 12
        if ma60 >= ma120:
            score += 13
        return min(100.0, score)

    @staticmethod
    def _allocation_view(row: dict, trend_score: float) -> str:
        drawdown = _num(row.get("高点回撤"))
        if trend_score >= 75 and drawdown <= -20:
            return "回撤后趋势已修复，适合作为宽基配置重点观察。"
        if trend_score >= 65:
            return "趋势偏强，可等回踩或放量确认后分批配置。"
        if drawdown <= -35:
            return "估值回撤明显但趋势尚弱，适合观察而非追高。"
        return "当前性价比一般，优先等待更清晰的回撤或趋势信号。"

    @staticmethod
    def _market_agent_view(row: dict) -> str:
        return (
            f"{row['名称']}当前高点回撤{row['高点回撤']}%，近一年收益{row['近一年收益']}%，"
            f"低点反弹{row['低点反弹']}%，可作为大盘风险偏好观察锚。"
        )

    @staticmethod
    def build_major_report(
        candidates: list[dict],
        config: MajorMarketETFConfig,
        market_context: dict,
        errors: list[str] | None = None,
    ) -> str:
        errors = errors or []
        lines = [
            "# 主要市场大盘ETF指数分析报告",
            "",
            "## 总览",
            "",
            f"- 分析目标：主要宽基指数 ETF，不包含行业主题 ETF。",
            f"- 推荐展示：按大盘配置评分展示前 {len(candidates)} 只。",
            f"- 大盘判断：{market_context.get('summary', '暂无')}",
            "- 风险提示：宽基 ETF 仍受市场系统性波动影响，本报告仅用于研究观察。",
            "",
            "## 推荐列表",
            "",
            "| 排名 | 代码 | 名称 | 高点回撤 | 近一年收益 | 大盘配置评分 | 回涨确认点 | 配置观点 |",
            "|---:|---|---|---:|---:|---:|---:|---|",
        ]
        for index, item in enumerate(candidates, start=1):
            lines.append(
                f"| {index} | {item['代码']} | {item['名称']} | {item['高点回撤']}% | "
                f"{item['近一年收益']}% | {item['大盘配置评分']} | {item['回涨确认点']} | {item['配置观点']} |"
            )
        lines.extend(["", "## 智能体分项分析", ""])
        for index, item in enumerate(candidates, start=1):
            lines.extend([
                f"### {index}. {item['名称']}（{item['代码']}）",
                "",
                f"- 历史高点：{item['历史高点']}（{item['高点日期']}），当前价：{item['最新价']}。",
                f"- 高点回撤：{item['高点回撤']}%；低点反弹：{item['低点反弹']}%；年化波动：{item['年化波动']}%。",
                f"- 预测最低点：{item['预测最低点']}；回涨确认点：{item['回涨确认点']}；预计修复周期：{item['预计修复周期']}。",
            ])
            for agent, view in item.get("智能体观点", {}).items():
                lines.append(f"- {agent}: {view}")
            lines.append("")
        if errors:
            lines.extend(["## 数据问题", "", f"- 历史行情失败 {len(errors)} 条，样例：{errors[:3]}"])
        return "\n".join(lines)
