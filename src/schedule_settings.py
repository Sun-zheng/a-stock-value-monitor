from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


DEFAULT_SCHEDULE_SETTINGS = {
    "daily_analysis": {"enabled": True, "time": "14:10", "frequency": "工作日"},
    "low_price_bull": {"enabled": True, "time": "14:00", "frequency": "工作日"},
    "final_delivery": {"enabled": True, "offset_minutes": 30, "frequency": "工作日"},
    "etf_toolkit": {"enabled": True, "times": ["15:20"], "frequency": "工作日"},
}


def schedule_settings_path(project_root: Path) -> Path:
    return project_root / "data" / "schedule_settings.json"


def load_schedule_settings(project_root: Path) -> dict:
    settings = deepcopy(DEFAULT_SCHEDULE_SETTINGS)
    path = schedule_settings_path(project_root)
    if not path.exists():
        return settings
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    return _merge(settings, payload)


def save_schedule_settings(project_root: Path, settings: dict) -> dict:
    merged = _merge(deepcopy(DEFAULT_SCHEDULE_SETTINGS), settings)
    _validate_time(merged["daily_analysis"]["time"])
    _validate_time(merged["low_price_bull"]["time"])
    for time_str in merged["etf_toolkit"].get("times", []):
        _validate_time(time_str)
    merged["final_delivery"]["offset_minutes"] = int(merged["final_delivery"].get("offset_minutes", 30))
    path = schedule_settings_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def frequency_calendar_prefix(value: str) -> str:
    return "*" if value == "每天" else "Mon..Fri"


def _validate_time(value: str) -> None:
    hour, minute = str(value).split(":", 1)
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise ValueError(f"无效时间: {value}")


def _merge(base: dict, update: dict) -> dict:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base
