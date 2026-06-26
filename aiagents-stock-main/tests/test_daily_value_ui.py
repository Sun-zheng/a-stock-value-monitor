from frontend.strategies.daily_value_ui import HISTORY_PREFERRED_COLUMNS


def test_history_preferred_columns_include_core_value_metrics():
    for field in ["ROE", "扣非ROE", "ROIC", "经营性现金流净额", "自由现金流", "ROE口径"]:
        assert field in HISTORY_PREFERRED_COLUMNS
