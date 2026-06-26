from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.strategy_config import load_strategy, strategy_scope_config

def parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.astimezone()
    except (TypeError, ValueError):
        return None


def _matches_requested_trade_date(cached_trade_date: str, requested_date: date) -> bool:
    if not cached_trade_date:
        return False
    target = requested_date.strftime("%Y%m%d")
    if cached_trade_date == target:
        return True
    return requested_date.weekday() >= 5 and cached_trade_date < target


def cache_metadata_path(path: Path) -> Path:
    return path.with_suffix(".meta.json")


def read_metadata(path: Path) -> dict:
    metadata_path = cache_metadata_path(path)
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def market_cache_status(
    cache_path: Path,
    target_date: date,
    timezone: str,
    allow_previous_close: bool = True,
) -> dict:
    now = datetime.now(ZoneInfo(timezone))
    metadata = read_metadata(cache_path)
    fetched_at = parse_datetime(
        metadata.get("fetched_at")
        or metadata.get("data_time")
        or (
            datetime.fromtimestamp(cache_path.stat().st_mtime).astimezone().isoformat()
            if cache_path.exists()
            else None
        )
    )
    trade_date = str(metadata.get("trade_date") or "").replace("-", "")
    target = target_date.strftime("%Y%m%d")
    age_seconds = (
        max((now - fetched_at.astimezone(now.tzinfo)).total_seconds(), 0)
        if fetched_at
        else None
    )
    previous_close = bool(
        allow_previous_close
        and trade_date
        and _matches_requested_trade_date(trade_date, target_date)
        and age_seconds is not None
        and age_seconds <= 7 * 24 * 3600
    )
    return {
        "exists": cache_path.exists(),
        "source": metadata.get("source", "local market cache"),
        "fetched_at": fetched_at.isoformat() if fetched_at else "",
        "trade_date": trade_date,
        "report_period": metadata.get("report_period", ""),
        "cache_age_seconds": round(age_seconds, 2) if age_seconds is not None else None,
        "valid_intraday": False,
        "valid_previous_close": previous_close,
        "degraded": bool(metadata.get("degraded", False)),
        "degradation_reason": metadata.get("degradation_reason")
        or metadata.get("degradation")
        or ("previous trading day close" if previous_close else ""),
    }


def freshness_report(project_root: Path, timezone: str) -> dict:
    now = datetime.now(ZoneInfo(timezone))
    market_target = now.date() - timedelta(days=1)
    strategy = load_strategy(project_root)
    scope = strategy_scope_config(strategy)
    targets = {
        "market": project_root / "data" / "market_snapshot.csv",
        "universe": project_root / "data" / "cache" / scope["universe_cache"],
        "valuation": project_root / "data" / "cache" / scope["valuation_cache"],
        "financial": project_root / "data" / "cache" / "financial_metrics_latest.csv",
    }
    policies = {
        "universe": timedelta(days=7),
        "valuation": timedelta(hours=24),
        "financial": timedelta(days=7),
    }
    result = {
        "checked_at": now.isoformat(),
        "recommendation_scope": scope["label"],
        "market": market_cache_status(
            targets["market"], market_target, timezone, allow_previous_close=True
        ),
    }
    for name in ("universe", "valuation", "financial"):
        path = targets[name]
        age = now - datetime.fromtimestamp(path.stat().st_mtime).astimezone(now.tzinfo) if path.exists() else None
        result[name] = {
            "exists": path.exists(),
            "modified_at": (
                datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
                if path.exists()
                else ""
            ),
            "cache_age_seconds": round(age.total_seconds(), 2) if age else None,
            "fresh": bool(age is not None and age <= policies[name]),
        }
    market_directly_valid = bool(
        result["market"]["valid_intraday"]
        or result["market"]["valid_previous_close"]
    )
    valuation_fallback_valid = bool(result["valuation"]["fresh"])
    result["effective_market"] = {
        "usable": market_directly_valid or valuation_fallback_valid,
        "degraded": not market_directly_valid and valuation_fallback_valid,
        "source": (
            result["market"]["source"]
            if market_directly_valid
            else "Tushare daily_basic previous trading day close"
        ),
        "degradation_reason": (
            ""
            if market_directly_valid
            else "前一交易日行情缓存无效；流水线将使用估值收盘价作为回退"
        ),
    }
    result["healthy"] = result["effective_market"]["usable"] and all(
        result[name]["fresh"] for name in ("universe", "valuation", "financial")
    )
    warnings = []
    for name in ("market", "universe", "valuation", "financial"):
        if name == "market" and result["effective_market"]["usable"]:
            continue
        if not (
            result[name].get("valid_intraday")
            or result[name].get("valid_previous_close")
            or result[name].get("fresh")
        ):
            warnings.append(name)
    result["warnings"] = warnings
    return result
