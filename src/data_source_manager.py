from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.cache_manager import CacheManager
from src.data_fetcher import (
    analysis_reference_date,
    cache_matches_requested_trade_date,
    fetch_market_snapshot,
)
from src.stock_pool import build_domestic_a_pool, build_main_board_pool
from src.stock_pool import normalize_code
from src.strategy_config import load_strategy, strategy_scope_config
from src.tushare_client import TushareClient


class DataSourceManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache = CacheManager(project_root / "data" / "cache")
        self.market_cache = project_root / "data" / "market_snapshot.csv"

    def _scope(self, strategy: dict | None = None) -> dict:
        return strategy_scope_config(strategy or load_strategy(self.project_root))

    def build_universe(
        self, force: bool = False, strategy: dict | None = None
    ) -> tuple[pd.DataFrame, dict]:
        scope = self._scope(strategy)
        if scope["key"] == "all_a_share":
            frame, meta = self.build_domestic_universe(force=force)
            return frame, {**meta, "scope": scope["label"]}
        name = scope["universe_cache"]
        if not force and self.cache.is_fresh(name, timedelta(days=7)):
            frame = self.cache.read(name)
            return frame, {
                "source": "本地主板股票池缓存",
                "cache_hit": True,
                "scope": scope["label"],
            }
        client = TushareClient()
        raw = client.stock_basic()
        pool = build_main_board_pool(raw)
        self.cache.write(name, pool)
        return pool, {
            "source": "Tushare stock_basic",
            "cache_hit": False,
            "scope": scope["label"],
        }

    def build_domestic_universe(
        self, force: bool = False
    ) -> tuple[pd.DataFrame, dict]:
        name = "domestic_a_universe.csv"
        if not force and self.cache.is_fresh(name, timedelta(days=7)):
            frame = self.cache.read(name)
            return frame, {"source": "本地境内全A股股票池缓存", "cache_hit": True}
        raw = TushareClient().stock_basic()
        pool = build_domestic_a_pool(raw)
        self.cache.write(name, pool)
        return pool, {"source": "Tushare stock_basic", "cache_hit": False}

    def build_domestic_valuation(
        self, force: bool = False, target_date: date | None = None
    ) -> tuple[pd.DataFrame, dict]:
        name = "domestic_a_valuation_latest.csv"
        cached = self.cache.read(name)
        requested_date = analysis_reference_date(target_date)
        cached_trade_date = str(
            cached.get("估值数据交易日", pd.Series([""])).iloc[0]
        )
        if (
            not force
            and cache_matches_requested_trade_date(cached_trade_date, requested_date)
            and self.cache.is_fresh(name, timedelta(hours=20))
        ):
            return cached, {
                "source": "本地境内全A股估值缓存",
                "cache_hit": True,
                "trade_date": cached_trade_date,
            }
        universe, _ = self.build_domestic_universe(force=force)
        frame, trade_date = TushareClient().latest_daily_basic(target=requested_date)
        frame = universe[
            ["代码", "名称", "交易所", "上市板块", "行业"]
        ].merge(frame.drop(columns=["ts_code"], errors="ignore"), on="代码", how="left")
        self.cache.write(name, frame)
        return frame, {
            "source": "Tushare境内全A股 daily_basic",
            "cache_hit": False,
            "trade_date": trade_date,
        }

    def market(
        self, force: bool = False, target_date: date | None = None
    ) -> tuple[pd.DataFrame, dict]:
        frame, meta = fetch_market_snapshot(
            self.market_cache,
            prefer_cache=not force,
            target_date=target_date,
        )
        if "代码" in frame:
            frame["代码"] = frame["代码"].map(normalize_code)
        return frame, meta

    def build_valuation(
        self,
        force: bool = False,
        target_date: date | None = None,
        strategy: dict | None = None,
    ) -> tuple[pd.DataFrame, dict]:
        scope = self._scope(strategy)
        if scope["key"] == "all_a_share":
            frame, meta = self.build_domestic_valuation(
                force=force, target_date=target_date
            )
            return frame, {**meta, "scope": scope["label"]}
        name = scope["valuation_cache"]
        cached = self.cache.read(name)
        requested_date = analysis_reference_date(target_date)
        cached_trade_date = str(
            cached.get("估值数据交易日", pd.Series([""])).iloc[0]
        )
        if (
            not force
            and cache_matches_requested_trade_date(cached_trade_date, requested_date)
            and self.cache.is_fresh(name, timedelta(hours=20))
        ):
            return cached, {
                "source": "本地估值缓存",
                "cache_hit": True,
                "trade_date": cached_trade_date,
            }
        client = TushareClient()
        frame, trade_date = client.latest_daily_basic(target=requested_date)
        universe, _ = self.build_universe(strategy=strategy)
        frame = universe[["代码", "名称", "交易所", "上市板块", "行业"]].merge(
            frame, on="代码", how="left"
        )
        self.cache.write(name, frame)
        return frame, {
            "source": "Tushare daily_basic",
            "cache_hit": False,
            "scope": scope["label"],
            "trade_date": trade_date,
        }

    def combined_light_data(
        self,
        force: bool = False,
        target_date: date | None = None,
        strategy: dict | None = None,
    ) -> tuple[pd.DataFrame, dict]:
        universe, universe_meta = self.build_universe(force=force, strategy=strategy)
        valuation, valuation_meta = self.build_valuation(
            force=force, target_date=target_date, strategy=strategy
        )
        try:
            market, market_meta = self.market(
                force=force, target_date=target_date
            )
        except RuntimeError as exc:
            market = valuation[["代码", "估值收盘价"]].rename(
                columns={"估值收盘价": "当前价格"}
            )
            market["涨跌幅"] = None
            market_meta = {
                "source": "Tushare daily_basic close",
                "data_time": valuation_meta.get("trade_date", ""),
                "fetched_at": "",
                "trade_date": valuation_meta.get("trade_date", ""),
                "report_period": "",
                "cache_age": None,
                "cache_hit": bool(valuation_meta.get("cache_hit")),
                "failures": [f"{type(exc).__name__}: {exc}"],
                "degraded": True,
                "degradation_reason": (
                    "前一交易日行情抓取失败；当前价格回退为估值收盘价，涨跌幅留空"
                ),
                "market_data_kind": "previous_trading_day_close",
            }
        market_cols = ["代码", "当前价格", "涨跌幅"]
        market = market[[c for c in market_cols if c in market.columns]].drop_duplicates("代码")
        frame = universe.merge(market, on="代码", how="left").merge(
            valuation.drop(columns=["名称", "交易所", "上市板块", "行业"], errors="ignore"),
            on="代码", how="left",
        )
        if market_meta.get("market_data_kind") == "previous_trading_day_close":
            valuation_trade_date = str(valuation_meta.get("trade_date", ""))
            market_trade_date = str(market_meta.get("trade_date", ""))
            if "估值收盘价" in frame and (
                market_trade_date != valuation_trade_date
                or frame["当前价格"].isna().any()
            ):
                frame["当前价格"] = pd.to_numeric(
                    frame["估值收盘价"], errors="coerce"
                )
            frame["涨跌幅"] = None
            if market_trade_date != valuation_trade_date:
                market_meta["degraded"] = True
                market_meta["source"] = (
                    f"{market_meta.get('source', '')}+Tushare daily_basic close"
                ).strip("+")
                market_meta["data_time"] = valuation_trade_date
                market_meta["trade_date"] = valuation_trade_date
                market_meta["degradation_reason"] = (
                    "行情交易日与估值交易日不一致；已统一回退为估值收盘口径"
                )
        return frame, {
            "universe": universe_meta, "market": market_meta,
            "valuation": valuation_meta,
        }

    def build_financial(self, codes: list[str], force: bool = False) -> tuple[pd.DataFrame, dict]:
        name = "financial_metrics_latest.csv"
        cached = self.cache.read(name)
        if not force and self.cache.is_fresh(name, timedelta(days=7)):
            available = set(cached.get("代码", pd.Series(dtype=str)).astype(str))
            if set(codes).issubset(available):
                return cached[cached["代码"].isin(codes)].copy(), {
                    "source": "本地财务缓存", "cache_hit": True
                }
        client = TushareClient()
        new = client.financial_metrics_many(codes)
        if not cached.empty:
            new = pd.concat([cached[~cached["代码"].isin(codes)], new], ignore_index=True)
        self.cache.write(name, new)
        return new[new["代码"].isin(codes)].copy(), {
            "source": "Tushare财务指标/三大报表", "cache_hit": False
        }
