import pandas as pd

from src.stock_pool import (
    build_domestic_a_pool,
    build_main_board_pool,
    domestic_exchange_and_board,
    exchange_and_board,
)


def test_main_board_prefixes():
    assert exchange_and_board("600000") == ("上海证券交易所", "沪市主板")
    assert exchange_and_board("002001") == ("深圳证券交易所", "深市主板")
    assert exchange_and_board("688001") is None
    assert exchange_and_board("300001") is None


def test_excludes_st():
    frame = pd.DataFrame(
        [{"代码": "600000", "名称": "正常公司"}, {"代码": "600001", "名称": "*ST样例"}]
    )
    result = build_main_board_pool(frame)
    assert result["代码"].tolist() == ["600000"]


def test_all_board_and_name_exclusions():
    frame = pd.DataFrame(
        [
            {"代码": "600000", "名称": "正常公司"},
            {"代码": "688001", "名称": "科创公司"},
            {"代码": "300001", "名称": "创业公司"},
            {"代码": "920001", "名称": "北交公司"},
            {"代码": "600001", "名称": "*ST样例"},
            {"代码": "000001", "名称": "深市公司"},
        ]
    )
    result = build_main_board_pool(frame)
    assert result["代码"].tolist() == ["600000", "000001"]
    assert result["上市板块"].tolist() == ["沪市主板", "深市主板"]


def test_domestic_market_pool_includes_all_a_share_boards():
    frame = pd.DataFrame(
        [
            {"代码": "600000", "名称": "主板公司"},
            {"代码": "688001", "名称": "科创公司"},
            {"代码": "300001", "名称": "创业公司"},
            {"代码": "920001", "名称": "北交公司"},
            {"代码": "600001", "名称": "*ST样例"},
        ]
    )
    result = build_domestic_a_pool(frame)
    assert result["代码"].tolist() == ["600000", "688001", "300001", "920001"]
    assert domestic_exchange_and_board("920001") == ("北京证券交易所", "北交所")
