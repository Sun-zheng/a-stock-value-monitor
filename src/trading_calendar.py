from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def _load_cache(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("trade_dates", []))
    except (OSError, ValueError, TypeError):
        return set()


def is_a_share_trading_day(target: date, cache_path: Path) -> tuple[bool, str]:
    if target.weekday() >= 5:
        return False, "周末"
    cached = _load_cache(cache_path)
    try:
        import akshare as ak

        frame = ak.tool_trade_date_hist_sina()
        dates = sorted({str(value)[:10] for value in frame["trade_date"].tolist()})
        if dates:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {"source": "AkShare/新浪交易日历", "trade_dates": dates},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return target.isoformat() in dates, "AkShare/新浪交易日历"
    except Exception:
        pass
    if cached:
        return target.isoformat() in cached, "本地交易日历缓存"
    return False, "无法确认交易日，按保守规则不执行"
