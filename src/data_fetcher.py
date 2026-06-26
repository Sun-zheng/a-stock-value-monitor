from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from src.freshness import market_cache_status, read_metadata


def safe_number(value):
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def retry_call(fn: Callable, attempts: int = 3, delay: float = 1.5):
    error = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (attempt + 1))
    raise error


def _previous_close_market_kind(cache: bool = False) -> str:
    return "previous_trading_day_close_cache" if cache else "previous_trading_day_close"


def analysis_reference_date(target_date: date | None = None) -> date:
    reference = target_date or date.today()
    return reference - timedelta(days=1)


def cache_matches_requested_trade_date(
    cached_trade_date: str, requested_date: date
) -> bool:
    if not cached_trade_date:
        return False
    target = requested_date.strftime("%Y%m%d")
    if cached_trade_date == target:
        return True
    return requested_date.weekday() >= 5 and cached_trade_date < target


def trusted_previous_close_cache(
    cache_path: Path, requested_date: date, timezone: str
) -> tuple[bool, dict]:
    status = market_cache_status(cache_path, requested_date, timezone)
    metadata = read_metadata(cache_path)
    source = str(metadata.get("source") or status.get("source") or "")
    trusted_source = source.startswith("Tushare daily_basic")
    trusted_kind = str(metadata.get("market_data_kind") or "").startswith(
        "previous_trading_day_close"
    )
    return bool(status["valid_previous_close"] and trusted_source and trusted_kind), status


def fetch_market_snapshot(
    cache_path: Path | None = None,
    prefer_cache: bool = False,
    target_date: date | None = None,
    timezone: str = "Asia/Shanghai",
) -> tuple[pd.DataFrame, dict]:
    from src.tushare_client import TushareClient

    requested_date = analysis_reference_date(target_date)
    failures: list[str] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if prefer_cache and cache_path and cache_path.exists():
        cache_ok, status = trusted_previous_close_cache(
            cache_path, requested_date, timezone
        )
        if cache_ok:
            return pd.read_csv(cache_path, dtype={"代码": str}), {
                "source": status["source"],
                "data_time": status["trade_date"],
                "fetched_at": status["fetched_at"],
                "trade_date": status["trade_date"],
                "report_period": "",
                "cache_age": status["cache_age_seconds"],
                "cache_hit": True,
                "failures": [],
                "degraded": status["degraded"],
                "degradation_reason": status["degradation_reason"],
                "market_data_kind": _previous_close_market_kind(cache=True),
            }
    try:
        client = TushareClient()
        daily_basic, trade_date = client.latest_daily_basic(target=requested_date)
        stock_basic = client.stock_basic()
        normalized = stock_basic[
            ["代码", "名称", "行业"]
        ].merge(
            daily_basic.drop(columns=["ts_code"], errors="ignore"),
            on="代码",
            how="left",
        )
        normalized = normalized.rename(columns={"估值收盘价": "当前价格"})
        normalized["涨跌幅"] = None
        source = "Tushare daily_basic 前一交易日收盘"
        degraded = False
    except Exception as exc:
        failures.append(f"Tushare前一交易日收盘: {type(exc).__name__}: {exc}")
        if cache_path and cache_path.exists():
            cache_ok, status = trusted_previous_close_cache(
                cache_path, requested_date, timezone
            )
            if cache_ok:
                frame = pd.read_csv(cache_path, dtype={"代码": str})
                return frame, {
                    "source": status["source"],
                    "data_time": status["trade_date"],
                    "fetched_at": status["fetched_at"],
                    "trade_date": status["trade_date"],
                    "report_period": "",
                    "cache_age": status["cache_age_seconds"],
                    "cache_hit": True,
                    "failures": failures,
                    "degraded": True,
                    "degradation_reason": "前一交易日行情抓取失败，回退到本地收盘缓存",
                    "market_data_kind": _previous_close_market_kind(cache=True),
                }
        raise RuntimeError("; ".join(failures)) from exc

    if len(normalized) < 1000:
        failures.append(f"{source}: 返回数量异常({len(normalized)})")
        degraded = True
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{cache_path.name}.", suffix=".tmp", dir=cache_path.parent
        )
        os.close(fd)
        temporary_path = Path(temporary)
        try:
            normalized.to_csv(temporary_path, index=False, encoding="utf-8-sig")
            os.replace(temporary_path, cache_path)
        finally:
            temporary_path.unlink(missing_ok=True)
    metadata = {
        "source": source,
        "data_time": trade_date,
        "fetched_at": now,
        "trade_date": trade_date,
        "report_period": "",
        "cache_age": 0,
        "cache_hit": False,
        "failures": failures,
        "degraded": degraded,
        "degradation_reason": (
            "前一交易日收盘数据返回数量异常，需复核 Tushare 数据完整性"
            if degraded else ""
        ),
        "market_data_kind": _previous_close_market_kind(),
    }
    if cache_path:
        metadata_path = cache_path.with_suffix(".meta.json")
        temporary_path = metadata_path.with_suffix(".meta.json.tmp")
        temporary_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary_path, metadata_path)
    return normalized, metadata


def fetch_stock_list() -> tuple[pd.DataFrame, str]:
    import akshare as ak

    frame = retry_call(ak.stock_info_a_code_name, attempts=2)
    return frame.rename(columns={"code": "代码", "name": "名称"}), "AkShare/A股代码名称"


def fetch_financial_indicators(code: str) -> tuple[pd.DataFrame, str]:
    import akshare as ak

    frame = retry_call(
        lambda: ak.stock_financial_analysis_indicator(symbol=code), attempts=2
    )
    return frame, "AkShare/新浪财务指标"


def fetch_dividends(code: str) -> tuple[pd.DataFrame, str]:
    import akshare as ak

    frame = retry_call(lambda: ak.stock_dividend_cninfo(symbol=code), attempts=2)
    return frame, "AkShare/巨潮资讯分红"
