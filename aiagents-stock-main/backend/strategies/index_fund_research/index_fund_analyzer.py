from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import log10
from typing import Callable

import pandas as pd


EQUITY_EXCLUDE_KEYWORDS = (
    "货币", "现金", "债", "国债", "可转债", "城投", "信用", "黄金",
    "商品", "豆粕", "能源化工", "REIT", "政金", "短融", "日利",
    "添益", "理财", "收益", "保证金",
)

CATEGORY_KEYWORDS = {
    "半导体/芯片": ("半导体", "芯片", "集成电路", "科创芯片"),
    "人工智能/数字经济": ("人工智能", "AI", "软件", "云计算", "大数据", "通信", "数据"),
    "创新药/医疗": ("创新药", "医药", "医疗", "生物", "疫苗", "中药"),
    "新能源/高端制造": ("新能源", "电池", "光伏", "机器人", "高端制造", "军工"),
    "消费/品牌": ("消费", "食品", "酒", "家电", "旅游", "传媒"),
    "红利/宽基": ("红利", "沪深300", "中证500", "中证1000", "A500", "上证50", "创业板", "科创"),
    "港股/海外": ("港股", "恒生", "中概", "纳指", "标普", "日经", "德国", "法国"),
}

LONG_BULL_CATEGORY_SCORE = {
    "半导体/芯片": 22,
    "人工智能/数字经济": 22,
    "创新药/医疗": 20,
    "新能源/高端制造": 17,
    "消费/品牌": 15,
    "红利/宽基": 14,
    "港股/海外": 12,
    "其他": 10,
}

CATEGORY_THESIS = {
    "半导体/芯片": "国产替代、AI算力和先进制造扩产仍是中长期主线，但行业估值和库存周期波动大。",
    "人工智能/数字经济": "AI应用、云计算、数据要素和通信基础设施构成长期需求，适合在深回撤后跟踪趋势修复。",
    "创新药/医疗": "老龄化、创新药出海和医疗需求韧性提供长期空间，但政策和研发兑现节奏会带来阶段波动。",
    "新能源/高端制造": "电动化、储能、光伏和高端制造仍有产业基础，关键在产能出清和盈利拐点确认。",
    "消费/品牌": "消费龙头具备现金流和品牌壁垒，长期修复依赖居民收入预期和渠道去库存。",
    "红利/宽基": "宽基和红利指数分散度更高，适合作为组合底仓，长牛依赖盈利周期和分红稳定性。",
    "港股/海外": "港股和海外指数估值弹性较大，受美元利率、流动性和平台经济政策预期影响明显。",
    "其他": "缺少明确产业标签，需要更依赖回撤、流动性和趋势确认，不宜单独重仓。",
}

RESEARCH_WORKFLOW = [
    "数据抓取: AkShare 东方财富 ETF 实时行情与前复权日线历史数据。",
    "全市场快照: 先保存可交易指数 ETF 参数，包括代码、名称、价格、成交额、市值、分类等。",
    "初筛过滤: 排除货币、债券、商品、现金管理和低成交额 ETF。",
    "大盘环境: 抓取主要指数行情，判断市场风险偏好；数据源不可用时降级为 ETF 内部广度统计。",
    "指数分类: 按基金名称识别半导体、AI、医疗、新能源、消费、宽基、港股海外等方向。",
    "回撤建模: 计算历史高点、高点后低点、当前高点回撤、低点反弹和一年收益。",
    "分析师复核: 大盘策略、回撤估值、产业长牛、趋势交易、风险控制五类规则分析师分别给观点。",
    "预测输出: 估算预测最低点、回涨确认点、半年上涨 50% 概率和回到高点附近的时间区间。",
    "组合选择: 优先选择接近目标回撤且类别分散的前 5 只，再用综合评分补足。",
]


def _num(value, default: float = 0.0) -> float:
    try:
        if value in (None, "", "N/A", "nan", "None"):
            return default
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return default


def _json_records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    safe = frame.copy()
    for column in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[column]):
            safe[column] = safe[column].dt.strftime("%Y-%m-%d %H:%M:%S")
    safe = safe.where(pd.notnull(safe), None)
    records = safe.to_dict("records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, pd.Timestamp):
                record[key] = value.isoformat()
    return records


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (list, tuple, dict, str, bytes)) else False:
        return None
    if value.__class__.__module__ == "numpy" and hasattr(value, "item"):
        return value.item()
    return value


def classify_fund(name: str) -> str:
    upper_name = str(name or "").upper()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.upper() in upper_name for keyword in keywords):
            return category
    return "其他"


def is_equity_index_fund(name: str) -> bool:
    text = str(name or "")
    if any(keyword in text for keyword in EQUITY_EXCLUDE_KEYWORDS):
        return False
    return "ETF" in text.upper() or "指数" in text


@dataclass(frozen=True)
class FundResearchConfig:
    top_n: int = 5
    history_candidates: int = 80
    min_turnover: float = 20_000_000
    target_drawdown_pct: float = -50.0
    min_drawdown_pct: float = -20.0
    diversify_categories: bool = True
    start_date: str = "20180101"


class IndexFundResearchAnalyzer:
    """Research index ETFs with rule-based analyst agents."""

    def __init__(
        self,
        spot_fetcher: Callable[[], pd.DataFrame] | None = None,
        history_fetcher: Callable[[str, str], pd.DataFrame] | None = None,
        market_fetcher: Callable[[], pd.DataFrame] | None = None,
    ):
        self.spot_fetcher = spot_fetcher or self._ak_spot
        self.history_fetcher = history_fetcher or self._ak_history
        self.market_fetcher = market_fetcher or self._ak_market

    @staticmethod
    def _ak_spot() -> pd.DataFrame:
        import akshare as ak

        return ak.fund_etf_spot_em()

    @staticmethod
    def _ak_market() -> pd.DataFrame:
        import akshare as ak

        frames = []
        for symbol in ("上证系列指数", "深证系列指数"):
            try:
                frames.append(ak.stock_zh_index_spot_em(symbol=symbol))
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _ak_history(code: str, start_date: str) -> pd.DataFrame:
        import akshare as ak

        code = str(code).zfill(6)
        try:
            return ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start_date,
                adjust="qfq",
            )
        except Exception as em_error:
            exchange = "sh" if code.startswith(("5", "6")) else "sz"
            try:
                frame = ak.fund_etf_hist_sina(symbol=f"{exchange}{code}")
            except Exception as sina_error:
                raise RuntimeError(
                    f"Eastmoney failed: {type(em_error).__name__}: {em_error}; "
                    f"Sina failed: {type(sina_error).__name__}: {sina_error}"
                ) from sina_error
            if frame.empty:
                return frame
            renamed = frame.rename(
                columns={
                    "date": "日期",
                    "open": "开盘",
                    "high": "最高",
                    "low": "最低",
                    "close": "收盘",
                    "volume": "成交量",
                    "amount": "成交额",
                }
            )
            renamed["日期"] = pd.to_datetime(renamed["日期"])
            start = pd.to_datetime(start_date)
            renamed = renamed[renamed["日期"].ge(start)].copy()
            renamed["涨跌幅"] = pd.to_numeric(renamed["收盘"], errors="coerce").pct_change() * 100
            renamed["日期"] = renamed["日期"].dt.strftime("%Y-%m-%d")
            return renamed

    def fetch_market_snapshot(self, config: FundResearchConfig) -> pd.DataFrame:
        spot = self.spot_fetcher().copy()
        if spot.empty:
            return spot
        spot["代码"] = spot["代码"].astype(str).str.zfill(6)
        spot["名称"] = spot["名称"].astype(str)
        spot["成交额"] = pd.to_numeric(spot.get("成交额"), errors="coerce").fillna(0)
        spot["最新价"] = pd.to_numeric(spot.get("最新价"), errors="coerce")
        mask = (
            spot["名称"].map(is_equity_index_fund)
            & spot["最新价"].gt(0)
            & spot["成交额"].ge(config.min_turnover)
        )
        data = spot[mask].copy()
        data["分类"] = data["名称"].map(classify_fund)
        keep = [
            column for column in [
                "代码", "名称", "分类", "最新价", "涨跌幅", "成交额", "流通市值",
                "总市值", "换手率", "IOPV实时估值", "基金折价率", "最新份额",
                "量比", "数据日期", "更新时间",
            ] if column in data.columns
        ]
        data = data[keep].sort_values("成交额", ascending=False)
        return data

    def fetch_universe(
        self,
        config: FundResearchConfig,
        market_snapshot: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        data = (market_snapshot.copy() if market_snapshot is not None else self.fetch_market_snapshot(config))
        if not config.diversify_categories:
            return data.head(config.history_candidates)
        return self._diversify_universe(data, config.history_candidates)

    @staticmethod
    def _diversify_universe(data: pd.DataFrame, limit: int) -> pd.DataFrame:
        if data.empty or limit <= 0:
            return data.head(0)
        groups = [
            group
            for _, group in data.groupby("分类", sort=False)
            if not group.empty
        ]
        selected_indices = []
        offset = 0
        while len(selected_indices) < limit:
            appended = False
            for group in groups:
                if offset < len(group):
                    selected_indices.append(group.index[offset])
                    appended = True
                    if len(selected_indices) >= limit:
                        break
            if not appended:
                break
            offset += 1
        return data.loc[selected_indices]

    def analyze(self, config: FundResearchConfig | None = None) -> dict:
        config = config or FundResearchConfig()
        market_snapshot = self.fetch_market_snapshot(config)
        universe = self.fetch_universe(config, market_snapshot)
        market_context = self._build_market_context(market_snapshot)
        rows: list[dict] = []
        errors: list[str] = []
        for _, fund in universe.iterrows():
            code = str(fund["代码"]).zfill(6)
            try:
                history = self.history_fetcher(code, config.start_date)
                row = self._analyze_one(fund.to_dict(), history, config)
                if row:
                    rows.append(row)
            except Exception as exc:
                errors.append(f"{code}: {type(exc).__name__}: {exc}")

        frame = pd.DataFrame(rows)
        if frame.empty:
            selected = []
        else:
            eligible = frame[frame["高点回撤"].le(config.min_drawdown_pct)]
            if eligible.empty:
                eligible = frame
            eligible = eligible.sort_values(
                ["综合评分", "回撤贴合度", "成交额"],
                ascending=[False, False, False],
            )
            selected = self._select_candidates(eligible, config)
        report = self.build_report(selected, config, errors, market_context)
        return _json_safe({
            "success": bool(selected),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": config.__dict__,
            "workflow": RESEARCH_WORKFLOW,
            "market_context": market_context,
            "market_snapshot_count": int(len(market_snapshot)),
            "market_snapshot": _json_records(market_snapshot),
            "category_distribution": market_snapshot["分类"].value_counts().to_dict() if "分类" in market_snapshot else {},
            "universe_count": int(len(universe)),
            "analyzed_count": int(len(rows)),
            "error_count": len(errors),
            "errors": errors[:20],
            "candidates": selected,
            "report": report,
        })

    @staticmethod
    def _select_candidates(frame: pd.DataFrame, config: FundResearchConfig) -> list[dict]:
        if frame.empty:
            return []
        if not config.diversify_categories:
            return frame.head(config.top_n).to_dict("records")

        selected_indices: list[int] = []
        for _, group in frame.groupby("分类", sort=False):
            selected_indices.append(int(group.index[0]))
            if len(selected_indices) >= config.top_n:
                break

        if len(selected_indices) < config.top_n:
            for index in frame.index:
                index = int(index)
                if index not in selected_indices:
                    selected_indices.append(index)
                if len(selected_indices) >= config.top_n:
                    break

        selected = frame.loc[selected_indices].sort_values(
            ["综合评分", "回撤贴合度", "成交额"],
            ascending=[False, False, False],
        )
        return selected.head(config.top_n).to_dict("records")

    def _analyze_one(self, fund: dict, history: pd.DataFrame, config: FundResearchConfig) -> dict | None:
        if history is None or history.empty or len(history) < 120:
            return None
        data = history.copy()
        data["日期"] = pd.to_datetime(data["日期"])
        for field in ("收盘", "最高", "最低", "成交额", "涨跌幅"):
            data[field] = pd.to_numeric(data[field], errors="coerce")
        data = data.dropna(subset=["收盘", "最高", "最低"])
        if data.empty:
            return None

        current = float(data["收盘"].iloc[-1])
        high_idx = data["最高"].idxmax()
        high_price = float(data.loc[high_idx, "最高"])
        high_date = data.loc[high_idx, "日期"]
        after_high = data[data["日期"].ge(high_date)]
        low_idx = after_high["最低"].idxmin()
        low_price = float(after_high.loc[low_idx, "最低"])
        low_date = after_high.loc[low_idx, "日期"]

        drawdown_pct = (current / high_price - 1) * 100 if high_price else 0
        max_drawdown_pct = (low_price / high_price - 1) * 100 if high_price else 0
        rebound_from_low_pct = (current / low_price - 1) * 100 if low_price else 0
        one_year_ago = data[data["日期"].ge(data["日期"].iloc[-1] - pd.Timedelta(days=365))]
        one_year_return = (current / float(one_year_ago["收盘"].iloc[0]) - 1) * 100 if len(one_year_ago) > 2 else 0
        returns = data["收盘"].pct_change().dropna()
        annual_vol = float(returns.tail(252).std() * (252 ** 0.5) * 100) if not returns.empty else 0

        ma20 = float(data["收盘"].tail(20).mean())
        ma60 = float(data["收盘"].tail(60).mean())
        ma120 = float(data["收盘"].tail(120).mean())
        category = str(fund.get("分类") or classify_fund(fund.get("名称", "")))
        turnover = _num(fund.get("成交额"))
        fit = max(0.0, 100 - abs(abs(drawdown_pct) - abs(config.target_drawdown_pct)) * 4)
        liquidity = min(100.0, max(0.0, log10(max(turnover, 1)) * 18 - 90))
        trend = self._trend_score(current, ma20, ma60, ma120, rebound_from_low_pct)
        risk = max(0.0, 100 - annual_vol * 1.4 - max(0, abs(max_drawdown_pct) - 60) * 1.2)
        long_bull = LONG_BULL_CATEGORY_SCORE.get(category, 10) + trend * 0.35 + liquidity * 0.2 + risk * 0.15
        score = fit * 0.36 + long_bull * 0.38 + liquidity * 0.16 + risk * 0.10
        low_estimate, rebound_trigger, recovery_months = self._forecast(
            current=current,
            low_price=low_price,
            high_price=high_price,
            ma60=ma60,
            annual_vol=annual_vol,
            trend_score=trend,
            drawdown_pct=drawdown_pct,
        )

        return {
            "代码": str(fund["代码"]).zfill(6),
            "名称": fund.get("名称"),
            "分类": category,
            "最新价": round(current, 4),
            "历史高点": round(high_price, 4),
            "高点日期": high_date.date().isoformat(),
            "高点回撤": round(drawdown_pct, 2),
            "高点后最低": round(low_price, 4),
            "低点日期": low_date.date().isoformat(),
            "低点反弹": round(rebound_from_low_pct, 2),
            "近一年收益": round(one_year_return, 2),
            "年化波动": round(annual_vol, 2),
            "历史最大回撤": round(max_drawdown_pct, 2),
            "成交额": round(turnover, 2),
            "流通市值": round(_num(fund.get("流通市值")), 2),
            "总市值": round(_num(fund.get("总市值")), 2),
            "IOPV实时估值": round(_num(fund.get("IOPV实时估值")), 4),
            "基金折价率": round(_num(fund.get("基金折价率")), 4),
            "最新份额": round(_num(fund.get("最新份额")), 2),
            "量比": round(_num(fund.get("量比")), 2),
            "MA20": round(ma20, 4),
            "MA60": round(ma60, 4),
            "MA120": round(ma120, 4),
            "回撤贴合度": round(fit, 2),
            "长牛潜力": round(long_bull, 2),
            "风险评分": round(risk, 2),
            "综合评分": round(score, 2),
            "预测最低点": round(low_estimate, 4),
            "回涨确认点": round(rebound_trigger, 4),
            "预计修复周期": recovery_months,
            "长牛逻辑": CATEGORY_THESIS.get(category, CATEGORY_THESIS["其他"]),
            "偏离原因": self._deviation_reason(category, drawdown_pct, one_year_return, current, ma60, ma120),
            "半年上涨50%概率": self._half_year_rebound_probability(
                drawdown_pct=drawdown_pct,
                rebound_pct=rebound_from_low_pct,
                trend_score=trend,
                annual_vol=annual_vol,
                risk_score=risk,
                long_bull_score=long_bull,
            ),
            "风险边界": self._risk_boundary(current, low_estimate, rebound_trigger, annual_vol),
            "分析师观点": self._agent_views(
                category, drawdown_pct, rebound_from_low_pct, annual_vol, current, ma60, ma120
            ),
        }

    def _build_market_context(self, market_snapshot: pd.DataFrame) -> dict:
        index_rows: list[dict] = []
        fetch_status = "主要指数接口未返回数据，使用ETF内部广度作为大盘代理"
        try:
            index_frame = self.market_fetcher().copy()
            if not index_frame.empty:
                name_field = "名称" if "名称" in index_frame.columns else index_frame.columns[0]
                target_names = ("上证指数", "深证成指", "沪深300", "创业板指", "科创50", "中证500", "中证1000")
                for _, row in index_frame.iterrows():
                    name = str(row.get(name_field, ""))
                    if not any(target in name for target in target_names):
                        continue
                    index_rows.append({
                        "名称": name,
                        "最新价": round(_num(row.get("最新价", row.get("点位", row.get("收盘")))), 2),
                        "涨跌幅": round(_num(row.get("涨跌幅")), 2),
                        "成交额": round(_num(row.get("成交额")), 2),
                    })
                if index_rows:
                    fetch_status = "主要指数行情抓取成功"
        except Exception as exc:
            fetch_status = f"主要指数接口不可用: {type(exc).__name__}"

        breadth = self._etf_breadth(market_snapshot)
        return {
            "status": fetch_status,
            "indices": index_rows[:8],
            "etf_breadth": breadth,
            "summary": self._market_summary(index_rows, breadth),
        }

    @staticmethod
    def _etf_breadth(market_snapshot: pd.DataFrame) -> dict:
        if market_snapshot.empty:
            return {"可交易指数ETF": 0, "上涨占比": None, "中位涨跌幅": None, "成交额合计": 0}
        if "涨跌幅" in market_snapshot:
            change = pd.to_numeric(market_snapshot["涨跌幅"], errors="coerce")
        else:
            change = pd.Series(dtype=float)
        turnover = pd.to_numeric(market_snapshot.get("成交额", pd.Series(dtype=float)), errors="coerce").fillna(0)
        valid = change.dropna()
        return {
            "可交易指数ETF": int(len(market_snapshot)),
            "上涨占比": round(float((valid > 0).mean() * 100), 2) if not valid.empty else None,
            "中位涨跌幅": round(float(valid.median()), 2) if not valid.empty else None,
            "成交额合计": round(float(turnover.sum()), 2),
        }

    @staticmethod
    def _market_summary(index_rows: list[dict], breadth: dict) -> str:
        if index_rows:
            avg_change = sum(_num(row.get("涨跌幅")) for row in index_rows) / len(index_rows)
            tone = "偏强" if avg_change > 0.5 else "偏弱" if avg_change < -0.5 else "震荡"
            return f"主要指数平均涨跌幅约{avg_change:.2f}%，市场状态偏{tone}；指数基金选择应兼顾回撤深度和趋势确认。"
        up_ratio = breadth.get("上涨占比")
        median_change = breadth.get("中位涨跌幅")
        if up_ratio is None:
            return "未获得有效大盘行情，报告主要依据ETF自身成交、回撤和趋势数据。"
        tone = "风险偏好修复" if up_ratio >= 55 else "风险偏好偏弱" if up_ratio <= 40 else "结构性震荡"
        return f"ETF内部广度显示上涨占比{up_ratio}%，中位涨跌幅{median_change}%，市场处于{tone}。"

    @staticmethod
    def _trend_score(current: float, ma20: float, ma60: float, ma120: float, rebound: float) -> float:
        score = 45.0
        if current > ma20:
            score += 12
        if current > ma60:
            score += 16
        if ma20 > ma60:
            score += 12
        if ma60 > ma120:
            score += 8
        if rebound > 20:
            score += 10
        return min(100.0, score)

    @staticmethod
    def _forecast(
        current: float,
        low_price: float,
        high_price: float,
        ma60: float,
        annual_vol: float,
        trend_score: float,
        drawdown_pct: float,
    ) -> tuple[float, float, str]:
        downside = 0.04 if trend_score >= 80 else 0.08 if trend_score >= 65 else 0.13
        downside += min(0.07, annual_vol / 1000)
        low_estimate = min(current * (1 - downside), max(low_price * 0.96, current * 0.75))
        rebound_trigger = max(ma60, current * (1.06 if trend_score < 70 else 1.035))
        gap_to_high = max(0.0, (high_price / current - 1) * 100)
        months = 6 + int(gap_to_high / 8) + (4 if drawdown_pct < -55 else 0)
        if trend_score >= 75:
            months = max(4, months - 4)
        return low_estimate, rebound_trigger, f"{months}-{months + 6}个月"

    @staticmethod
    def _risk_boundary(current: float, low_estimate: float, rebound_trigger: float, annual_vol: float) -> str:
        if annual_vol >= 35:
            position_note = "高波动，只适合小仓分批观察"
        elif annual_vol >= 22:
            position_note = "中高波动，适合分批并等待确认"
        else:
            position_note = "波动相对可控，但仍需设置失效条件"
        return (
            f"{position_note}；若有效跌破预测最低点{low_estimate:.4f}，需要重新评估；"
            f"若放量站上回涨确认点{rebound_trigger:.4f}，趋势修复可信度提高。"
        )

    @staticmethod
    def _deviation_reason(
        category: str,
        drawdown_pct: float,
        one_year_return: float,
        current: float,
        ma60: float,
        ma120: float,
    ) -> str:
        reasons = []
        if drawdown_pct <= -50:
            reasons.append("历史高点以来估值和风险偏好双重压缩")
        elif drawdown_pct <= -35:
            reasons.append("相对历史高点处于明显折价区间")
        if one_year_return < -10:
            reasons.append("近一年仍处下行趋势，资金风险偏好未完全恢复")
        if current < ma60 or ma60 < ma120:
            reasons.append("均线结构尚未完全修复")
        if category in ("创新药/医疗", "新能源/高端制造", "港股/海外"):
            reasons.append("行业景气、政策预期或海外流动性变化放大了偏离")
        return "；".join(reasons) or "主要偏离来自阶段性交易拥挤和估值回归。"

    @staticmethod
    def _half_year_rebound_probability(
        drawdown_pct: float,
        rebound_pct: float,
        trend_score: float,
        annual_vol: float,
        risk_score: float,
        long_bull_score: float,
    ) -> str:
        score = 20.0
        score += min(25.0, max(0.0, abs(drawdown_pct) - 30) * 0.8)
        score += min(20.0, rebound_pct * 0.5)
        score += max(0.0, trend_score - 55) * 0.45
        score += max(0.0, long_bull_score - 45) * 0.35
        score += max(0.0, risk_score - 45) * 0.2
        score -= max(0.0, annual_vol - 30) * 0.6
        score = max(5.0, min(85.0, score))
        if score >= 65:
            level = "较高"
        elif score >= 45:
            level = "中等"
        elif score >= 30:
            level = "偏低"
        else:
            level = "较低"
        return (
            f"{level}（约{score:.0f}%）：半年涨50%需要市场风险偏好明显修复、"
            "行业催化兑现，并站稳回涨确认点；未站稳前只能按反弹观察处理。"
        )

    @staticmethod
    def _agent_views(
        category: str,
        drawdown_pct: float,
        rebound_pct: float,
        annual_vol: float,
        current: float,
        ma60: float,
        ma120: float,
    ) -> dict:
        return {
            "估值回撤分析师": (
                f"当前距离历史高点回撤{abs(drawdown_pct):.1f}%，"
                "接近腰斩区间，具备左侧研究价值。"
            ),
            "产业长牛分析师": (
                f"所属方向为{category}。若产业景气度能延续，指数基金比单一公司更适合做周期底部跟踪。"
            ),
            "趋势交易分析师": (
                f"当前价{'高于' if current >= ma60 else '低于'}MA60，"
                f"MA60{'高于' if ma60 >= ma120 else '低于'}MA120；"
                f"低点以来反弹{rebound_pct:.1f}%。"
            ),
            "风险控制分析师": (
                f"近一年年化波动约{annual_vol:.1f}%，不适合一次性重仓；应分批、设确认点。"
            ),
        }

    @staticmethod
    def build_report(
        candidates: list[dict],
        config: FundResearchConfig,
        errors: list[str] | None = None,
        market_context: dict | None = None,
    ) -> str:
        errors = errors or []
        market_context = market_context or {}
        if not candidates:
            return "# 指数基金回撤研究报告\n\n今日未找到满足条件的指数基金候选。"
        lines = [
            "# 指数基金回撤研究报告",
            "",
            "## 总览结论",
            "",
            f"- 目标：寻找接近历史高点回撤{abs(config.target_drawdown_pct):.0f}%、且具备长期产业逻辑的指数基金。",
            f"- 推荐数量：{len(candidates)}只。",
            "- 方法：ETF流动性过滤 -> 历史高点回撤 -> 趋势/风险/长牛评分 -> 多分析师规则复核 -> 类别分散选择。",
            "- 风险提示：指数基金仍有行业周期和估值杀跌风险，以下为研究观察，不构成投资建议。",
            "",
            "## 研究流程",
            "",
        ]
        lines.extend(f"- {step}" for step in RESEARCH_WORKFLOW)
        lines.extend([
            "",
            "## 大盘环境",
            "",
            f"- 数据状态：{market_context.get('status', '未获取')}",
            f"- 综合判断：{market_context.get('summary', '暂无')}",
        ])
        breadth = market_context.get("etf_breadth") or {}
        if breadth:
            lines.append(
                f"- ETF内部广度：可交易指数ETF {breadth.get('可交易指数ETF', 0)} 只，"
                f"上涨占比 {breadth.get('上涨占比', 'N/A')}%，中位涨跌幅 {breadth.get('中位涨跌幅', 'N/A')}%。"
            )
        indices = market_context.get("indices") or []
        if indices:
            lines.extend(["", "| 指数 | 最新价 | 涨跌幅 | 成交额 |", "|---|---:|---:|---:|"])
            for item in indices:
                lines.append(
                    f"| {item.get('名称')} | {item.get('最新价')} | {item.get('涨跌幅')}% | {item.get('成交额')} |"
                )
        lines.extend([
            "",
            "## 推荐列表",
            "",
            "| 排名 | 代码 | 名称 | 分类 | 高点回撤 | 综合评分 | 预测最低点 | 回涨确认点 | 半年涨50% | 预计修复周期 |",
            "|---:|---|---|---|---:|---:|---:|---:|---|---|",
        ])
        for index, item in enumerate(candidates, start=1):
            lines.append(
                f"| {index} | {item['代码']} | {item['名称']} | {item['分类']} | "
                f"{item['高点回撤']}% | {item['综合评分']} | {item['预测最低点']} | "
                f"{item['回涨确认点']} | {item['半年上涨50%概率']} | {item['预计修复周期']} |"
            )
        lines.extend(["", "## 分项分析", ""])
        for index, item in enumerate(candidates, start=1):
            lines.extend(
                [
                    f"### {index}. {item['名称']}（{item['代码']}）",
                    "",
                    f"- 历史高点：{item['历史高点']}（{item['高点日期']}），当前回撤：{item['高点回撤']}%。",
                    f"- 高点后最低：{item['高点后最低']}（{item['低点日期']}），低点反弹：{item['低点反弹']}%。",
                    f"- 长牛潜力：{item['长牛潜力']}；风险评分：{item['风险评分']}；成交额：{item['成交额']:.0f}。",
                    f"- 偏离原因：{item['偏离原因']}",
                    f"- 长牛逻辑：{item['长牛逻辑']}",
                    f"- 预测最低点：{item['预测最低点']}；回涨确认点：{item['回涨确认点']}；预计修复周期：{item['预计修复周期']}。",
                    f"- 半年上涨50%判断：{item['半年上涨50%概率']}",
                    f"- 风险边界：{item['风险边界']}",
                ]
            )
            for agent, view in item["分析师观点"].items():
                lines.append(f"- {agent}: {view}")
            lines.append("")
        if errors:
            lines.extend(["## 数据说明", "", f"- 部分基金历史数据获取失败，已跳过 {len(errors)} 条。"])
        lines.extend(["## 总结", "", "优先观察接近腰斩但已出现趋势修复的方向；若跌破预测最低点，应重新评估，不做无条件补仓。"])
        return "\n".join(lines)
