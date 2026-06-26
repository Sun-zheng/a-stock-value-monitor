import pandas as pd

from src.strategy_validator import _main_board_count


def test_main_board_count_only_counts_shanghai_and_shenzhen_main_board():
    frame = pd.DataFrame(
        {
            "上市板块": [
                "沪市主板",
                "深市主板",
                "创业板",
                "科创板",
                "北交所",
                "深市主板",
            ]
        }
    )

    assert _main_board_count(frame) == 3
