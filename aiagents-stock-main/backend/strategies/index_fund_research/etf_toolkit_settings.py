from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitConfig


DEFAULT_ETF_TOOLKIT_SETTINGS = {
    "analysis": {
        "max_history": 40,
        "min_turnover_wan": 3000,
        "min_price": 0.0,
        "monthly_budget": 5000.0,
        "holding_top_n": 3,
        "start_date": "20210101",
        "include_premium_discount": True,
        "include_holdings": False,
        "include_index_info": False,
        "cache_ttl_minutes": 30,
    },
    "monitor": {
        "enabled": False,
        "schedule_times": ["15:20"],
        "frequency": "工作日",
        "modules": {
            "dca": True,
            "premium_discount": True,
            "periodic_report": True,
        },
        "dca": {
            "enabled": True,
            "trigger_drawdown_pct": -20.0,
            "increase_drawdown_pct": -35.0,
            "focus_drawdown_pct": -50.0,
            "min_score": 35.0,
        },
        "premium_discount": {
            "enabled": True,
            "premium_alert_pct": -1.5,
            "discount_alert_pct": 1.5,
            "min_turnover_wan": 3000,
        },
        "periodic_report": {
            "enabled": True,
            "send_daily": True,
            "send_weekly": True,
            "weekly_day": "Friday",
            "min_pool_changes": 1,
        },
    },
    "delivery": {
        "email_enabled": False,
        "lark_doc_enabled": False,
        "lark_bitable_enabled": False,
        "lark_bitable_config_path": "data/etf_toolkit_lark_table.json",
        "send_only_when_alert": False,
    },
    "storage": {
        "history_enabled": True,
        "history_limit": 120,
        "cache_enabled": True,
        "reuse_cached_result": True,
        "cache_policy": "same_day",
    },
}


def config_path(project_root: Path) -> Path:
    return project_root / "data" / "etf_toolkit_settings.json"


def load_etf_toolkit_settings(project_root: Path) -> dict:
    path = config_path(project_root)
    settings = deepcopy(DEFAULT_ETF_TOOLKIT_SETTINGS)
    if not path.exists():
        return settings
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    return _merge(settings, payload)


def save_etf_toolkit_settings(project_root: Path, settings: dict) -> Path:
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_merge(deepcopy(DEFAULT_ETF_TOOLKIT_SETTINGS), settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_analyzer_config(settings: dict) -> ETFToolkitConfig:
    analysis = settings.get("analysis", {})
    return ETFToolkitConfig(
        max_history=int(analysis.get("max_history", 40)),
        min_turnover=float(analysis.get("min_turnover_wan", 3000)) * 10_000,
        min_price=float(analysis.get("min_price", 0.0)),
        monthly_budget=float(analysis.get("monthly_budget", 5000.0)),
        holding_top_n=int(analysis.get("holding_top_n", 3)),
        include_premium_discount=bool(analysis.get("include_premium_discount", True)),
        include_holdings=bool(analysis.get("include_holdings", False)),
        include_index_info=bool(analysis.get("include_index_info", False)),
        cache_ttl_minutes=int(analysis.get("cache_ttl_minutes", 30)),
        start_date=str(analysis.get("start_date", "20210101") or "20210101"),
    )


def build_alerts(result: dict, settings: dict) -> list[dict]:
    monitor = settings.get("monitor", {})
    alerts: list[dict] = []
    modules = monitor.get("modules", {})
    if modules.get("dca", True) and monitor.get("dca", {}).get("enabled", True):
        alerts.extend(_dca_alerts(result, monitor.get("dca", {})))
    if modules.get("premium_discount", True) and monitor.get("premium_discount", {}).get("enabled", True):
        alerts.extend(_premium_alerts(result, monitor.get("premium_discount", {})))
    if modules.get("periodic_report", True) and monitor.get("periodic_report", {}).get("enabled", True):
        alerts.append({
            "类型": "ETF日报周报",
            "代码": "",
            "名称": "ETF市场摘要",
            "触发原因": "按配置生成ETF定时日报/周报摘要",
            "触发值": "",
            "建议": "查看强势方向、深回撤ETF、放量ETF和机会池变化。",
        })
    return alerts


def _dca_alerts(result: dict, config: dict) -> list[dict]:
    trigger = float(config.get("trigger_drawdown_pct", -20.0))
    min_score = float(config.get("min_score", 35.0))
    alerts = []
    for item in result.get("dca_plans", []):
        drawdown = float(item.get("当前回撤") or 0)
        score = _score_for_code(result, item.get("代码"))
        if drawdown <= trigger and score >= min_score:
            alerts.append({
                "类型": "ETF定投触发",
                "代码": item.get("代码", ""),
                "名称": item.get("名称", ""),
                "触发原因": item.get("定投档位", ""),
                "触发值": f"回撤 {drawdown}%，评分 {score}",
                "建议": f"{item.get('加仓条件', '')} 停止条件：{item.get('停止条件', '')}",
            })
    return alerts


def _premium_alerts(result: dict, config: dict) -> list[dict]:
    premium = float(config.get("premium_alert_pct", -1.5))
    discount = float(config.get("discount_alert_pct", 1.5))
    min_turnover = float(config.get("min_turnover_wan", 3000)) * 10_000
    alerts = []
    for item in result.get("premium_discount", []):
        value = item.get("实时折价率")
        if value is None:
            value = item.get("日频折价率")
        value = float(value or 0)
        turnover = float(item.get("成交额") or 0)
        if turnover < min_turnover:
            continue
        if value <= premium or value >= discount:
            alerts.append({
                "类型": "ETF溢价折价触发",
                "代码": item.get("代码", ""),
                "名称": item.get("名称", ""),
                "触发原因": item.get("状态", ""),
                "触发值": f"折价率 {value}%",
                "建议": item.get("监控建议", ""),
            })
    return alerts


def _score_for_code(result: dict, code: object) -> float:
    for item in result.get("screener", []):
        if str(item.get("代码")) == str(code):
            return float(item.get("筛选评分") or 0)
    return 0.0


def _merge(base: dict, update: dict) -> dict:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base
