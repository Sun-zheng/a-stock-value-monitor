from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


DIMENSIONS = [
    "生意质量与护城河",
    "管理层与资本配置",
    "盈利能力与韧性",
    "财务安全",
    "现金流质量",
    "十年成长跑道",
    "估值与安全边际",
    "股东回报",
    "芒格反向清单",
]

RECOMMENDATION_SCOPES = {
    "main_board": {
        "key": "main_board",
        "label": "沪深主板",
        "report_label": "A股主板",
        "universe_cache": "mainboard_universe.csv",
        "valuation_cache": "valuation_latest.csv",
        "scope_description": "沪深主板，排除ST、退市及非股票证券",
    },
    "all_a_share": {
        "key": "all_a_share",
        "label": "境内全市场A股",
        "report_label": "A股全市场",
        "universe_cache": "domestic_a_universe.csv",
        "valuation_cache": "domestic_a_valuation_latest.csv",
        "scope_description": (
            "境内全部上市A股，含主板、创业板、科创板、北交所；"
            "排除ST、退市及非股票证券"
        ),
    },
}

DEFAULT_STRATEGY = {
    "version": 2,
    "name": "Buffett-Munger A股全市场十年价值策略",
    "recommendation_scope": "all_a_share",
    "run_time": "14:10",
    "formal_score": 80,
    "formal_margin": 25,
    "watch_score": 68,
    "candidate_limit": 500,
    "max_formal": 1,
    "max_watch": 5,
    "weights": {
        "生意质量与护城河": 15,
        "管理层与资本配置": 10,
        "盈利能力与韧性": 15,
        "财务安全": 10,
        "现金流质量": 15,
        "十年成长跑道": 10,
        "估值与安全边际": 15,
        "股东回报": 5,
        "芒格反向清单": 5,
    },
    "quality_gates": {
        "生意质量与护城河": 8,
        "管理层与资本配置": 5,
        "盈利能力与韧性": 8,
        "财务安全": 5,
        "现金流质量": 8,
        "十年成长跑道": 4,
        "芒格反向清单": 3,
    },
}


def strategy_path(project_root: Path) -> Path:
    return project_root / "config" / "strategy.json"


def _merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_strategy(config: dict) -> dict:
    result = _merge(DEFAULT_STRATEGY, config)
    if result["recommendation_scope"] not in RECOMMENDATION_SCOPES:
        raise ValueError("recommendation_scope 必须为 main_board 或 all_a_share")
    weights = result["weights"]
    if set(weights) != set(DIMENSIONS):
        raise ValueError("九维评分名称不完整或包含未知维度")
    if round(sum(float(weights[name]) for name in DIMENSIONS), 6) != 100:
        raise ValueError("九维评分权重合计必须为100")
    if not 0 <= float(result["watch_score"]) <= float(result["formal_score"]) <= 100:
        raise ValueError("观察分数必须不高于正式推荐分数，且均在0到100之间")
    if not 0 <= float(result["formal_margin"]) <= 100:
        raise ValueError("安全边际门槛必须在0到100之间")
    if not 5 <= int(result["candidate_limit"]) <= 500:
        raise ValueError("候选数量必须在5到500之间")
    if int(result["max_formal"]) != 1:
        raise ValueError("正式推荐上限固定为1只")
    if not 0 <= int(result["max_watch"]) <= 5:
        raise ValueError("观察上限必须在0到5只之间")
    hour, minute = str(result["run_time"]).split(":", 1)
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise ValueError("运行时间必须为HH:MM")
    for name, gate in result["quality_gates"].items():
        if name not in weights or not 0 <= float(gate) <= float(weights[name]):
            raise ValueError(f"{name}质量门槛超出该维度权重")
    return result


def strategy_scope_config(strategy: dict | None = None) -> dict:
    strategy = strategy or DEFAULT_STRATEGY
    return RECOMMENDATION_SCOPES[strategy["recommendation_scope"]]


def load_strategy(project_root: Path) -> dict:
    path = strategy_path(project_root)
    if not path.exists():
        return validate_strategy({})
    return validate_strategy(json.loads(path.read_text(encoding="utf-8")))


def save_strategy(project_root: Path, config: dict) -> dict:
    validated = validate_strategy(config)
    path = strategy_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return validated
