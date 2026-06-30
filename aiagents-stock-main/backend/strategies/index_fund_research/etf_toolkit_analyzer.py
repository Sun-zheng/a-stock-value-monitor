from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

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
    monthly_budget: float = 5000.0
    holding_top_n: int = 5
    start_date: str = "20210101"


class ETFToolkitAnalyzer(IndexFundResearchAnalyzer):
    """ETF screener, rotation, and portfolio construction workflow."""

    def __init__(
        self,
        spot_fetcher: Callable[[], pd.DataFrame] | None = None,
        history_fetcher: Callable[[str, str], pd.DataFrame] | None = None,
        market_fetcher: Callable[[], pd.DataFrame] | None = None,
        fund_daily_fetcher: Callable[[], pd.DataFrame] | None = None,
        holdings_fetcher: Callable[[str], pd.DataFrame] | None = None,
        index_info_fetcher: Callable[[], pd.DataFrame] | None = None,
    ):
        super().__init__(spot_fetcher=spot_fetcher, history_fetcher=history_fetcher, market_fetcher=market_fetcher)
        self.fund_daily_fetcher = fund_daily_fetcher or self._ak_fund_daily
        self.holdings_fetcher = holdings_fetcher or self._ak_holdings
        self.index_info_fetcher = index_info_fetcher or self._ak_index_info

    @staticmethod
    def _ak_fund_daily() -> pd.DataFrame:
        import akshare as ak

        return ak.fund_etf_fund_daily_em()

    @staticmethod
    def _ak_holdings(code: str) -> pd.DataFrame:
        import akshare as ak

        year = datetime.now().year
        for query_year in (year, year - 1, year - 2):
            try:
                frame = ak.fund_portfolio_hold_em(symbol=str(code).zfill(6), date=str(query_year))
            except Exception:
                continue
            if frame is not None and not frame.empty:
                return frame
        return pd.DataFrame()

    @staticmethod
    def _ak_index_info() -> pd.DataFrame:
        import akshare as ak

        return ak.fund_info_index_em(symbol="全部", indicator="全部")

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
        premium_discount = self._build_premium_discount(screener)
        dca_plans = self._build_dca_plans(screener, config.monthly_budget)
        risk_radar = self._build_risk_radar(screener)
        comparison = self._build_comparison(screener)
        opportunity_pool = self._build_opportunity_pool(screener)
        periodic_report = self._build_periodic_report(screener, rotation, opportunity_pool)
        holdings = self._build_holdings_analysis(screener, config.holding_top_n)
        report = self.build_toolkit_report(
            screener=screener,
            rotation=rotation,
            portfolios=portfolios,
            dca_plans=dca_plans,
            premium_discount=premium_discount,
            holdings=holdings,
            risk_radar=risk_radar,
            comparison=comparison,
            opportunity_pool=opportunity_pool,
            periodic_report=periodic_report,
            errors=errors,
        )
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
            "dca_plans": dca_plans,
            "premium_discount": premium_discount,
            "holdings": holdings,
            "risk_radar": risk_radar,
            "comparison": comparison,
            "periodic_report": periodic_report,
            "opportunity_pool": opportunity_pool,
            "report": report,
            "workflow": [
                "全市场ETF快照: 过滤可交易ETF，保留价格、成交额、市值、涨跌幅和分类。",
                "历史指标计算: 拉取真实日线，计算1/3/6/12月收益、回撤、波动、均线趋势。",
                "筛选器: 支持按类型、成交额、回撤、收益、波动和价格进行二次过滤。",
                "轮动策略: 按分类聚合动量、趋势、风险和成交额，识别强势、改善、滞后方向。",
                "组合配置: 采用核心-卫星框架，根据稳健/平衡/进取风险偏好生成ETF权重。",
                "定投计划: 按20%/35%/50%回撤区间生成月度金额、加仓条件和停止条件。",
                "溢价折价监控: 使用实时IOPV和基金折价率识别高溢价、折价和价格偏离。",
                "持仓穿透: 对Top ETF读取季度持仓，识别重仓股、重叠和集中度。",
                "风险雷达/对比/机会池: 输出风险标签、横向对比、日报周报和观察池变化。",
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
        row["风险标签"] = ETFToolkitAnalyzer._risk_label(
            vol=vol,
            turnover=_num(row.get("成交额")),
            drawdown=drawdown,
            market_cap=_num(row.get("总市值")),
            discount=_num(row.get("基金折价率")),
        )
        return row

    @staticmethod
    def _risk_label(vol: float, turnover: float, drawdown: float, market_cap: float = 0, discount: float = 0) -> str:
        labels = []
        if turnover < 30_000_000:
            labels.append("流动性偏弱")
        if vol >= 35:
            labels.append("高波动")
        if market_cap and market_cap < 300_000_000:
            labels.append("规模偏小")
        if abs(discount) >= 1.5:
            labels.append("高溢价/折价")
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
    def _discount_status(discount: float) -> str:
        if discount <= -1.5:
            return "高溢价"
        if discount >= 1.5:
            return "明显折价"
        if abs(discount) <= 0.5:
            return "接近净值"
        return "轻微偏离"

    @staticmethod
    def _premium_advice(status: str) -> str:
        if status == "高溢价":
            return "避免追买，等待价格回到IOPV附近或确认底层市场流动性。"
        if status == "明显折价":
            return "先确认成交额和底层市场是否正常，折价收敛前分批观察。"
        return "可纳入常规观察，重点跟踪成交额、量比和趋势变化。"

    def _daily_discount_map(self) -> dict[str, dict]:
        try:
            daily = self.fund_daily_fetcher()
        except Exception:
            return {}
        if daily is None or daily.empty or "基金代码" not in daily.columns:
            return {}
        nav_columns = [col for col in daily.columns if str(col).endswith("-单位净值")]
        nav_col = nav_columns[0] if nav_columns else None
        mapping: dict[str, dict] = {}
        for _, item in daily.iterrows():
            code = str(item.get("基金代码", "")).zfill(6)
            if not code:
                continue
            mapping[code] = {
                "场内市价": _num(item.get("市价")),
                "单位净值": _num(item.get(nav_col)) if nav_col else 0,
                "日频折价率": _num(item.get("折价率")),
            }
        return mapping

    def _index_info_map(self) -> dict[str, dict]:
        try:
            info = self.index_info_fetcher()
        except Exception:
            return {}
        if info is None or info.empty or "基金代码" not in info.columns:
            return {}
        mapping: dict[str, dict] = {}
        for _, item in info.iterrows():
            code = str(item.get("基金代码", "")).zfill(6)
            if not code:
                continue
            mapping[code] = {
                "手续费": item.get("手续费"),
                "跟踪标的": item.get("跟踪标的"),
                "跟踪方式": item.get("跟踪方式"),
                "基金净值日期": item.get("日期"),
            }
        return mapping

    def _build_premium_discount(self, screener: list[dict]) -> list[dict]:
        daily_map = self._daily_discount_map()
        rows = []
        for item in screener:
            code = str(item.get("代码", "")).zfill(6)
            latest = _num(item.get("最新价"))
            iopv = _num(item.get("IOPV实时估值"))
            discount = _num(item.get("基金折价率"))
            if not discount and latest and iopv:
                discount = (iopv / latest - 1) * 100
            price_gap = (latest / iopv - 1) * 100 if latest and iopv else 0
            daily = daily_map.get(code, {})
            daily_discount = _num(daily.get("日频折价率"))
            status = self._discount_status(discount or daily_discount)
            rows.append({
                "代码": code,
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "最新价": round(latest, 4),
                "IOPV实时估值": round(iopv, 4) if iopv else None,
                "实时折价率": round(discount, 4) if discount else None,
                "日频折价率": round(daily_discount, 4) if daily_discount else None,
                "价格偏离IOPV": round(price_gap, 4) if price_gap else None,
                "成交额": round(_num(item.get("成交额")), 2),
                "量比": round(_num(item.get("量比")), 2) if _num(item.get("量比")) else None,
                "状态": status,
                "监控建议": self._premium_advice(status),
            })
        return rows

    @staticmethod
    def _build_dca_plans(screener: list[dict], monthly_budget: float) -> list[dict]:
        plans = []
        for item in screener:
            drawdown = _num(item.get("高点回撤"))
            discount = _num(item.get("基金折价率"))
            if drawdown <= -50:
                tier = "重点观察/分批"
                ratio = 1.8
                add_rule = "回撤维持50%附近且溢价不高时，分3-5批执行。"
            elif drawdown <= -35:
                tier = "提高定投"
                ratio = 1.4
                add_rule = "回撤达到35%后，月度金额提高；放量跌破前低则暂停加码。"
            elif drawdown <= -20:
                tier = "开始小额定投"
                ratio = 1.0
                add_rule = "回撤达到20%后开始小额定投，突破MA60后再提高频率。"
            else:
                tier = "等待触发"
                ratio = 0.3
                add_rule = "尚未达到深回撤区间，仅保留观察或小额试投。"
            premium_stop = "或出现高溢价" if discount <= -1.5 else ""
            plans.append({
                "代码": item.get("代码"),
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "当前回撤": round(drawdown, 2),
                "定投档位": tier,
                "建议月定投金额": round(monthly_budget * ratio, 2),
                "加仓条件": add_rule,
                "停止条件": f"趋势评分跌破30、成交额连续萎缩{premium_stop}；单只ETF达到目标仓位后停止。",
                "复核频率": "每周观察，每月执行；季度复盘是否继续。",
            })
        return plans

    @staticmethod
    def _risk_tags(item: dict) -> list[str]:
        tags = []
        if _num(item.get("成交额")) < 30_000_000:
            tags.append("流动性差")
        if _num(item.get("年化波动")) >= 35:
            tags.append("波动过高")
        if _num(item.get("总市值")) and _num(item.get("总市值")) < 300_000_000:
            tags.append("规模太小")
        if _num(item.get("成立年限")) and _num(item.get("成立年限")) < 1:
            tags.append("成立时间太短")
        if _num(item.get("基金折价率")) <= -1.5:
            tags.append("高溢价")
        if _num(item.get("基金折价率")) >= 1.5:
            tags.append("明显折价")
        if item.get("分类") not in {"红利/宽基", "港股/海外", "其他"}:
            tags.append("单一行业风险")
        if not _num(item.get("IOPV实时估值")):
            tags.append("跟踪误差数据待补充")
        return tags or ["正常"]

    def _build_risk_radar(self, screener: list[dict]) -> list[dict]:
        rows = []
        for item in screener:
            tags = self._risk_tags(item)
            risk_level = "高" if len(tags) >= 3 or "高溢价" in tags else "中" if len(tags) == 2 else "低"
            rows.append({
                "代码": item.get("代码"),
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "风险等级": risk_level,
                "风险标签": "、".join(tags),
                "年化波动": round(_num(item.get("年化波动")), 2),
                "高点回撤": round(_num(item.get("高点回撤")), 2),
                "成交额": round(_num(item.get("成交额")), 2),
                "总市值": round(_num(item.get("总市值")), 2) if _num(item.get("总市值")) else None,
                "实时折价率": round(_num(item.get("基金折价率")), 4) if _num(item.get("基金折价率")) else None,
            })
        level_order = {"高": 0, "中": 1, "低": 2}
        return sorted(rows, key=lambda item: (level_order[item["风险等级"]], -_num(item.get("高点回撤"))))

    def _build_comparison(self, screener: list[dict]) -> list[dict]:
        info_map = self._index_info_map()
        rows = []
        for item in screener[:20]:
            code = str(item.get("代码", "")).zfill(6)
            info = info_map.get(code, {})
            inferred_index = self._infer_tracking_index(str(item.get("名称", "")))
            rows.append({
                "代码": code,
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "近一月收益": round(_num(item.get("近一月收益")), 2),
                "近三月收益": round(_num(item.get("近三月收益")), 2),
                "近半年收益": round(_num(item.get("近半年收益")), 2),
                "近一年收益": round(_num(item.get("近一年收益")), 2),
                "高点回撤": round(_num(item.get("高点回撤")), 2),
                "年化波动": round(_num(item.get("年化波动")), 2),
                "成交额": round(_num(item.get("成交额")), 2),
                "总市值": round(_num(item.get("总市值")), 2) if _num(item.get("总市值")) else None,
                "手续费": info.get("手续费"),
                "跟踪指数": info.get("跟踪标的") or inferred_index,
                "跟踪方式": info.get("跟踪方式"),
                "指数来源": "基金档案" if info.get("跟踪标的") else "名称推断" if inferred_index else "未获取到",
                "筛选评分": round(_num(item.get("筛选评分")), 2),
            })
        return rows

    @staticmethod
    def _infer_tracking_index(name: str) -> str | None:
        if not name:
            return None
        suffixes = [
            "ETF联接",
            "ETF基金",
            "ETF",
            "华夏",
            "易方达",
            "嘉实",
            "华泰柏瑞",
            "南方",
            "广发",
            "富国",
            "国泰",
            "招商",
            "博时",
            "汇添富",
            "天弘",
        ]
        value = name
        for suffix in suffixes:
            value = value.replace(suffix, "")
        value = value.strip(" -_（）()：:")
        return value or None

    @staticmethod
    def _build_opportunity_pool(screener: list[dict]) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")

        def pool_row(item: dict, reason: str) -> dict:
            return {
                "代码": item.get("代码"),
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "入池原因": reason,
                "首次进入日期": today,
                "连续观察天数": 1,
                "排名变化": "新进入",
                "筛选评分": round(_num(item.get("筛选评分")), 2),
                "高点回撤": round(_num(item.get("高点回撤")), 2),
                "近一年收益": round(_num(item.get("近一年收益")), 2),
            }

        low_value = [pool_row(item, "回撤达到35%以上") for item in screener if _num(item.get("高点回撤")) <= -35][:10]
        breakout = [
            pool_row(item, "趋势评分高且价格站上中期均线")
            for item in screener
            if _num(item.get("趋势评分")) >= 75 and _num(item.get("最新价")) >= _num(item.get("MA60"))
        ][:10]
        volume = [
            pool_row(item, "量比或成交额放大")
            for item in screener
            if _num(item.get("量比")) >= 2 or _num(item.get("成交额")) >= 300_000_000
        ][:10]
        dca = [
            pool_row(item, "适合长期分批跟踪")
            for item in screener
            if _num(item.get("高点回撤")) <= -20 and "高溢价" not in ETFToolkitAnalyzer._risk_tags(item)
        ][:10]
        return {
            "低估回撤池": low_value,
            "趋势突破池": breakout,
            "放量异动池": volume,
            "长期定投池": dca,
            "说明": "首次进入日期、连续观察天数和排名变化当前基于本次运行生成；接入持久化定时任务后可自动滚动维护。",
        }

    @staticmethod
    def _build_periodic_report(screener: list[dict], rotation: list[dict], opportunity_pool: dict) -> dict:
        strong = [item for item in rotation if item.get("阶段") == "强势领先"][:5]
        deep_drawdown = [item for item in screener if _num(item.get("高点回撤")) <= -35][:8]
        volume = [item for item in screener if _num(item.get("量比")) >= 2 or _num(item.get("成交额")) >= 300_000_000][:8]
        summary = [
            f"本次覆盖ETF {len(screener)} 只，轮动分类 {len(rotation)} 个。",
            f"强势方向：{', '.join(item['分类'] for item in strong[:3]) or '暂无明确强势方向'}。",
            f"深回撤观察：{len(deep_drawdown)} 只；放量观察：{len(volume)} 只。",
        ]
        return {
            "标题": f"ETF定时日报/周报 - {datetime.now().strftime('%Y-%m-%d')}",
            "总览": summary,
            "强势行业ETF": [
                {"分类": item.get("分类"), "阶段": item.get("阶段"), "轮动评分": item.get("轮动评分"), "代表ETF": item.get("代表ETF")}
                for item in strong
            ],
            "深回撤ETF": [
                {"代码": item.get("代码"), "名称": item.get("名称"), "分类": item.get("分类"), "高点回撤": round(_num(item.get("高点回撤")), 2)}
                for item in deep_drawdown
            ],
            "放量ETF": [
                {"代码": item.get("代码"), "名称": item.get("名称"), "成交额": round(_num(item.get("成交额")), 2), "量比": round(_num(item.get("量比")), 2)}
                for item in volume
            ],
            "观察池变化": {
                name: len(items) for name, items in opportunity_pool.items() if isinstance(items, list)
            },
        }

    def _build_holdings_analysis(self, screener: list[dict], top_n: int) -> dict:
        etfs = screener[:max(0, top_n)]
        details = []
        exposure: dict[str, dict] = {}
        errors = []
        for item in etfs:
            code = str(item.get("代码", "")).zfill(6)
            try:
                holdings = self.holdings_fetcher(code)
            except Exception as exc:
                errors.append(f"{code}: {type(exc).__name__}: {exc}")
                continue
            if holdings is None or holdings.empty:
                details.append({"代码": code, "名称": item.get("名称"), "前十大持仓": [], "前十大集中度": 0, "季度": None})
                continue
            top = holdings.head(10).copy()
            rows = []
            for _, holding in top.iterrows():
                stock_code = str(holding.get("股票代码", ""))
                stock_name = holding.get("股票名称")
                weight = _num(holding.get("占净值比例"))
                quarter = holding.get("季度")
                rows.append({
                    "股票代码": stock_code,
                    "股票名称": stock_name,
                    "占净值比例": round(weight, 4),
                    "季度": quarter,
                })
                key = f"{stock_code}-{stock_name}"
                bucket = exposure.setdefault(key, {"股票代码": stock_code, "股票名称": stock_name, "合计权重": 0.0, "覆盖ETF": set()})
                bucket["合计权重"] += weight
                bucket["覆盖ETF"].add(f"{item.get('名称')}({code})")
            details.append({
                "代码": code,
                "名称": item.get("名称"),
                "分类": item.get("分类"),
                "前十大持仓": rows,
                "前十大集中度": round(sum(row["占净值比例"] for row in rows), 4),
                "季度": rows[0]["季度"] if rows else None,
            })
        overlap = []
        for value in exposure.values():
            if len(value["覆盖ETF"]) < 2:
                continue
            overlap.append({
                "股票代码": value["股票代码"],
                "股票名称": value["股票名称"],
                "合计权重": round(value["合计权重"], 4),
                "覆盖ETF数量": len(value["覆盖ETF"]),
                "覆盖ETF": "、".join(sorted(value["覆盖ETF"])),
            })
        return {
            "ETF持仓明细": details,
            "重复暴露": sorted(overlap, key=lambda item: item["合计权重"], reverse=True),
            "errors": errors,
        }

    def build_toolkit_report(
        self,
        screener: list[dict],
        rotation: list[dict],
        portfolios: dict,
        dca_plans: list[dict],
        premium_discount: list[dict],
        holdings: dict,
        risk_radar: list[dict],
        comparison: list[dict],
        opportunity_pool: dict,
        periodic_report: dict,
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
        lines.extend(["", "## 定投计划", "", "| ETF | 回撤 | 档位 | 月定投金额 | 停止条件 |", "|---|---:|---|---:|---|"])
        for item in dca_plans[:10]:
            lines.append(f"| {item['名称']}（{item['代码']}） | {item['当前回撤']} | {item['定投档位']} | {item['建议月定投金额']} | {item['停止条件']} |")
        lines.extend(["", "## 溢价/折价监控", "", "| ETF | 状态 | 实时折价率 | 价格偏离IOPV | 建议 |", "|---|---|---:|---:|---|"])
        for item in premium_discount[:10]:
            lines.append(f"| {item['名称']}（{item['代码']}） | {item['状态']} | {item.get('实时折价率', '')} | {item.get('价格偏离IOPV', '')} | {item['监控建议']} |")
        lines.extend(["", "## 风险雷达", "", "| ETF | 等级 | 风险标签 | 波动 | 回撤 |", "|---|---|---|---:|---:|"])
        for item in risk_radar[:10]:
            lines.append(f"| {item['名称']}（{item['代码']}） | {item['风险等级']} | {item['风险标签']} | {item['年化波动']} | {item['高点回撤']} |")
        lines.extend(["", "## ETF对比", "", "| ETF | 跟踪指数 | 近一年收益 | 回撤 | 波动 | 手续费 |", "|---|---|---:|---:|---:|---|"])
        for item in comparison[:10]:
            lines.append(f"| {item['名称']}（{item['代码']}） | {item.get('跟踪指数') or ''} | {item['近一年收益']} | {item['高点回撤']} | {item['年化波动']} | {item.get('手续费') or ''} |")
        lines.extend(["", "## 机会池", ""])
        for name, items in opportunity_pool.items():
            if not isinstance(items, list):
                continue
            names = "、".join(f"{item['名称']}({item['代码']})" for item in items[:5]) or "暂无"
            lines.append(f"- {name}：{names}")
        lines.extend(["", "## 定时日报/周报摘要", ""])
        for sentence in periodic_report.get("总览", []):
            lines.append(f"- {sentence}")
        overlap = holdings.get("重复暴露", []) if isinstance(holdings, dict) else []
        lines.extend(["", "## 持仓穿透", ""])
        lines.append(f"- 已读取 {len(holdings.get('ETF持仓明细', [])) if isinstance(holdings, dict) else 0} 只ETF持仓；重复暴露股票 {len(overlap)} 个。")
        for item in overlap[:5]:
            lines.append(f"- {item['股票名称']}：合计权重 {item['合计权重']}%，覆盖 {item['覆盖ETF数量']} 只ETF。")
        lines.extend(["", "## 组合配置", ""])
        for profile, portfolio in portfolios.items():
            lines.extend([f"### {profile}", "", portfolio.get("notes", "")])
            for item in portfolio.get("positions", []):
                lines.append(f"- {item['层级']}：{item['名称']}（{item['代码']}） {item['权重']}%，{item['风险标签']}。")
            lines.append("")
        if errors:
            lines.extend(["## 数据问题", "", f"- 历史行情失败 {len(errors)} 条，样例：{errors[:3]}"])
        return "\n".join(lines)
