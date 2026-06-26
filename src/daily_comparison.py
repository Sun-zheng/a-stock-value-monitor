from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path


SUMMARY_FIELDS = [
    "原始股票数量",
    "推荐范围",
    "推荐范围股票数量",
    "主板股票数量",
    "国内全市场基准股票数量",
    "行情覆盖率",
    "估值覆盖率",
    "财报覆盖率",
    "现金流覆盖率",
    "分红覆盖率",
    "估值轻筛通过数量",
    "财务快筛通过数量",
    "一票否决后数量",
    "正式条件检查数量",
    "最终推荐数量",
    "观察股票数量",
    "估值数据交易日",
    "行情交易日",
    "财报数据报告期",
    "现金流数据报告期",
]

REPORT_DIFF_PREFIXES = (
    "- 上一报告日:",
    "- 新进入观察池:",
    "- 移出观察池:",
    "- 连续重复天数:",
    "- 策略健康告警:",
    "- 变化说明:",
)


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _scan(payload: dict) -> dict:
    return payload.get("scan_summary", payload)


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _normalize_code(value: object) -> str:
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else ""


def _stock_codes(items: list[dict]) -> list[str]:
    codes: list[str] = []
    for item in items:
        code = _normalize_code(item.get("代码") or item.get("code") or item.get("股票代码"))
        if code:
            codes.append(code)
    return codes


def _payload_lists(payload: dict, scan: dict) -> dict[str, list[str]]:
    recommendation = payload.get("recommendation")
    formal_items = (
        [recommendation]
        if isinstance(recommendation, dict) and recommendation
        else scan.get("正式推荐股票", [])
    )
    observation_items = payload.get("observations") or scan.get("观察股票", [])
    top_items = scan.get("候选Top10", [])
    formal = _stock_codes(formal_items if isinstance(formal_items, list) else [])
    observations = _stock_codes(
        observation_items if isinstance(observation_items, list) else []
    )
    top10 = _stock_codes(top_items if isinstance(top_items, list) else [])
    return {
        "formal": formal,
        "observations": observations,
        "combined": formal + observations,
        "top10": top10,
    }


def _metric_snapshot(scan: dict) -> dict:
    return {field: scan.get(field, "数据不足") for field in SUMMARY_FIELDS}


def _metric_changes(current: dict, previous: dict) -> dict:
    changes: dict[str, dict] = {}
    for field in SUMMARY_FIELDS:
        current_value = current.get(field, "数据不足")
        previous_value = previous.get(field, "数据不足")
        if current_value == previous_value:
            continue
        entry = {"current": current_value, "previous": previous_value}
        if isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)):
            entry["delta"] = round(current_value - previous_value, 4)
        changes[field] = entry
    return changes


def _report_digest(text: str) -> dict:
    normalized = "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith(REPORT_DIFF_PREFIXES)
    )
    return {
        "hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else "",
        "length": len(normalized),
    }


def _report_text(
    reports_dir: Path,
    day: str,
    preferred: str | None = None,
) -> str:
    if preferred is not None:
        return preferred
    base_path = reports_dir / f"{day}_report_base.md"
    if base_path.exists():
        return _text(base_path)
    final_path = reports_dir / f"{day}_report.md"
    return _text(final_path)


def _describe_changes(
    current_lists: dict[str, list[str]],
    previous_lists: dict[str, list[str]],
    metric_changes: dict,
    report_changed: bool,
    current_conclusion: str,
    previous_conclusion: str,
    previous_date: str,
) -> str:
    if not previous_date:
        return "首次生成对比摘要，后续将按前一报告日逐项比较结果、关键指标和报告内容。"
    notes: list[str] = []
    if current_conclusion != previous_conclusion:
        notes.append(f"结论由“{previous_conclusion or '无'}”变为“{current_conclusion or '无'}”")
    if current_lists["formal"] != previous_lists["formal"]:
        notes.append(
            f"正式推荐变化: {previous_lists['formal'] or ['无']} -> {current_lists['formal'] or ['无']}"
        )
    if current_lists["observations"] != previous_lists["observations"]:
        entered = [code for code in current_lists["observations"] if code not in previous_lists["observations"]]
        exited = [code for code in previous_lists["observations"] if code not in current_lists["observations"]]
        notes.append(
            f"观察池变化: 新进{entered or ['无']}，移出{exited or ['无']}"
        )
    if current_lists["top10"] != previous_lists["top10"]:
        notes.append("候选Top10顺序或成员发生变化")
    if metric_changes:
        focus = []
        for field in (
            "估值轻筛通过数量",
            "一票否决后数量",
            "最终推荐数量",
            "观察股票数量",
            "估值覆盖率",
            "财报覆盖率",
            "现金流覆盖率",
            "估值数据交易日",
            "行情交易日",
        ):
            change = metric_changes.get(field)
            if change:
                focus.append(f"{field}:{change['previous']}->{change['current']}")
        if focus:
            notes.append("关键指标变化: " + "；".join(focus[:6]))
    if report_changed:
        notes.append("报告正文发生变化")
    if not notes:
        return "与前一报告日相比，正式推荐、观察池、候选Top10、关键指标和报告正文均无实质变化。"
    return "；".join(notes)


def compare_previous_day(
    reports_dir: Path,
    current_day: str | None = None,
    current_payload: dict | None = None,
    current_scan: dict | None = None,
    current_report_text: str | None = None,
) -> dict:
    current_day = current_day or date.today().isoformat()
    current_path = reports_dir / f"{current_day}_result.json"
    previous_paths = sorted(
        (
            path
            for path in reports_dir.glob("*_result.json")
            if path.name < current_path.name and not path.name.startswith("TEST-")
        ),
        reverse=True,
    )
    previous_path = previous_paths[0] if previous_paths else None
    previous_payload = _load(previous_path) if previous_path else {}
    previous_scan = _scan(previous_payload)
    current_payload = current_payload or _load(current_path)
    current_scan = current_scan or _scan(current_payload)

    current_lists = _payload_lists(current_payload, current_scan)
    previous_lists = _payload_lists(previous_payload, previous_scan)
    current_metrics = _metric_snapshot(current_scan)
    previous_metrics = _metric_snapshot(previous_scan)
    metric_changes = _metric_changes(current_metrics, previous_metrics)

    current_report = _report_text(
        reports_dir, current_day, preferred=current_report_text
    )
    previous_day = previous_path.name[:10] if previous_path else ""
    previous_report = _report_text(reports_dir, previous_day) if previous_day else ""
    current_digest = _report_digest(current_report)
    previous_digest = _report_digest(previous_report)
    report_changed = bool(
        previous_day and current_digest["hash"] and current_digest["hash"] != previous_digest["hash"]
    )

    unchanged = bool(
        current_lists["formal"] == previous_lists["formal"]
        and current_lists["observations"] == previous_lists["observations"]
        and current_lists["top10"] == previous_lists["top10"]
        and not metric_changes
        and not report_changed
    )

    repeat_days = 1
    if current_lists["combined"]:
        for path in previous_paths:
            historical_payload = _load(path)
            historical_scan = _scan(historical_payload)
            historical_lists = _payload_lists(historical_payload, historical_scan)
            if historical_lists["combined"] == current_lists["combined"]:
                repeat_days += 1
            else:
                break

    current_conclusion = str(current_payload.get("conclusion") or "")
    previous_conclusion = str(previous_payload.get("conclusion") or "")
    explanation = _describe_changes(
        current_lists,
        previous_lists,
        metric_changes,
        report_changed,
        current_conclusion,
        previous_conclusion,
        previous_day,
    )
    return {
        "current_date": current_day,
        "previous_date": previous_day,
        "current_codes": current_lists["combined"],
        "previous_codes": previous_lists["combined"],
        "current_formal_codes": current_lists["formal"],
        "previous_formal_codes": previous_lists["formal"],
        "current_observation_codes": current_lists["observations"],
        "previous_observation_codes": previous_lists["observations"],
        "current_top10_codes": current_lists["top10"],
        "previous_top10_codes": previous_lists["top10"],
        "entered": [
            code for code in current_lists["combined"] if code not in previous_lists["combined"]
        ],
        "exited": [
            code for code in previous_lists["combined"] if code not in current_lists["combined"]
        ],
        "formal_entered": [
            code for code in current_lists["formal"] if code not in previous_lists["formal"]
        ],
        "formal_exited": [
            code for code in previous_lists["formal"] if code not in current_lists["formal"]
        ],
        "observation_entered": [
            code
            for code in current_lists["observations"]
            if code not in previous_lists["observations"]
        ],
        "observation_exited": [
            code
            for code in previous_lists["observations"]
            if code not in current_lists["observations"]
        ],
        "top10_entered": [
            code for code in current_lists["top10"] if code not in previous_lists["top10"]
        ],
        "top10_exited": [
            code for code in previous_lists["top10"] if code not in current_lists["top10"]
        ],
        "current_conclusion": current_conclusion,
        "previous_conclusion": previous_conclusion,
        "conclusion_changed": bool(previous_day and current_conclusion != previous_conclusion),
        "metric_changes": metric_changes,
        "report_changed": report_changed,
        "report_hash": current_digest["hash"],
        "previous_report_hash": previous_digest["hash"],
        "report_length": current_digest["length"],
        "previous_report_length": previous_digest["length"],
        "unchanged": unchanged,
        "consecutive_repeat_days": repeat_days,
        "strategy_health_warning": repeat_days > 5,
        "explanation": explanation,
    }
