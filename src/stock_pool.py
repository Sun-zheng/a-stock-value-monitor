from __future__ import annotations

import re

import pandas as pd


SH_MAIN = ("600", "601", "603", "605")
SZ_MAIN = ("000", "001", "002", "003")
EXCLUDED_NAME_PATTERN = re.compile(
    r"\*ST|ST|退市|退整理|摘牌|ETF|LOF|基金|转债|可转债|REIT|B股",
    re.IGNORECASE,
)


def normalize_code(value: object) -> str:
    return re.sub(r"\D", "", str(value))[-6:].zfill(6)


def exchange_and_board(code: str) -> tuple[str, str] | None:
    code = normalize_code(code)
    if code.startswith(SH_MAIN):
        return "上海证券交易所", "沪市主板"
    if code.startswith(SZ_MAIN):
        return "深圳证券交易所", "深市主板"
    return None


def domestic_exchange_and_board(code: str) -> tuple[str, str] | None:
    code = normalize_code(code)
    main_board = exchange_and_board(code)
    if main_board:
        return main_board
    if code.startswith(("688", "689")):
        return "上海证券交易所", "科创板"
    if code.startswith(("300", "301")):
        return "深圳证券交易所", "创业板"
    if code.startswith(("4", "8", "92")):
        return "北京证券交易所", "北交所"
    return None


def classify_code(code: str) -> str:
    code = normalize_code(code)
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith(("4", "8", "92")):
        return "北交所"
    if exchange_and_board(code):
        return "主板"
    return "其他"


def _columns(frame: pd.DataFrame) -> tuple[str, str]:
    code_col = "代码" if "代码" in frame.columns else "code"
    name_col = "名称" if "名称" in frame.columns else "name"
    if code_col not in frame or name_col not in frame:
        raise ValueError("股票池数据缺少代码或名称字段")
    return code_col, name_col


def pool_statistics(raw: pd.DataFrame) -> dict:
    code_col, name_col = _columns(raw)
    codes = raw[code_col].map(normalize_code)
    names = raw[name_col].fillna("").astype(str)
    classes = codes.map(classify_code)
    st_mask = names.str.contains(r"\*ST|ST|退市|退整理|摘牌", case=False, regex=True)
    return {
        "原始股票数量": int(len(raw)),
        "排除科创板数量": int((classes == "科创板").sum()),
        "排除创业板数量": int((classes == "创业板").sum()),
        "排除北交所数量": int((classes == "北交所").sum()),
        "排除ST数量": int(st_mask.sum()),
    }


def build_main_board_pool(spot: pd.DataFrame) -> pd.DataFrame:
    code_col, name_col = _columns(spot)
    frame = spot.copy()
    frame["代码"] = frame[code_col].map(normalize_code)
    frame["名称"] = frame[name_col].fillna("").astype(str)
    frame = frame[frame["代码"].map(lambda value: exchange_and_board(value) is not None)]
    excluded = frame["名称"].map(
        lambda value: bool(EXCLUDED_NAME_PATTERN.search(value))
    ).astype(bool)
    frame = frame.loc[~excluded].copy()
    if frame.empty:
        frame["交易所"] = pd.Series(dtype=str)
        frame["上市板块"] = pd.Series(dtype=str)
        return frame.reset_index(drop=True)
    frame["交易所"] = frame["代码"].map(lambda code: exchange_and_board(code)[0])
    frame["上市板块"] = frame["代码"].map(lambda code: exchange_and_board(code)[1])
    return frame.reset_index(drop=True)


def build_domestic_a_pool(spot: pd.DataFrame) -> pd.DataFrame:
    code_col, name_col = _columns(spot)
    frame = spot.copy()
    frame["代码"] = frame[code_col].map(normalize_code)
    frame["名称"] = frame[name_col].fillna("").astype(str)
    frame = frame[
        frame["代码"].map(lambda value: domestic_exchange_and_board(value) is not None)
    ]
    excluded = frame["名称"].map(
        lambda value: bool(EXCLUDED_NAME_PATTERN.search(value))
    ).astype(bool)
    frame = frame.loc[~excluded].copy()
    if frame.empty:
        frame["交易所"] = pd.Series(dtype=str)
        frame["上市板块"] = pd.Series(dtype=str)
        return frame.reset_index(drop=True)
    frame["交易所"] = frame["代码"].map(
        lambda code: domestic_exchange_and_board(code)[0]
    )
    frame["上市板块"] = frame["代码"].map(
        lambda code: domestic_exchange_and_board(code)[1]
    )
    return frame.reset_index(drop=True)
