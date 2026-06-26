from datetime import date, datetime, timedelta, timezone
import json

from src.freshness import market_cache_status
from src.data_fetcher import _previous_close_market_kind, analysis_reference_date


def write_cache(tmp_path, trade_date: str, fetched_at: datetime):
    path = tmp_path / "market_snapshot.csv"
    path.write_text("代码,当前价格\n600000,10\n", encoding="utf-8")
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "source": "test",
                "fetched_at": fetched_at.isoformat(),
                "trade_date": trade_date,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_previous_close_cache_is_valid_for_requested_day(tmp_path):
    now = datetime.now(timezone.utc)
    previous = now.date() - timedelta(days=1)
    path = write_cache(tmp_path, previous.strftime("%Y%m%d"), now - timedelta(minutes=5))
    status = market_cache_status(path, previous, "UTC")
    assert status["valid_previous_close"] is True
    assert status["valid_intraday"] is False


def test_weekend_target_accepts_last_available_previous_close(tmp_path):
    fetched_at = datetime.now(timezone.utc)
    path = write_cache(
        tmp_path, "20260619", fetched_at - timedelta(hours=12)
    )
    status = market_cache_status(path, date(2026, 6, 21), "UTC")
    assert status["valid_previous_close"] is True


def test_multi_day_old_cache_is_rejected(tmp_path):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=10)
    path = write_cache(tmp_path, old.strftime("%Y%m%d"), old)
    status = market_cache_status(path, date.today(), "UTC")
    assert status["valid_intraday"] is False
    assert status["valid_previous_close"] is False


def test_previous_close_market_kind_is_stable():
    assert _previous_close_market_kind() == "previous_trading_day_close"
    assert _previous_close_market_kind(cache=True) == "previous_trading_day_close_cache"


def test_analysis_reference_date_uses_previous_calendar_day():
    assert analysis_reference_date(date(2026, 6, 23)) == date(2026, 6, 22)
