from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from html import escape
from pathlib import Path

from config.settings import settings as root_settings
from src.email_sender import send_email


def run_etf_toolkit_monitor(project_root: Path) -> dict:
    aiagents_root = project_root / "aiagents-stock-main"
    if str(aiagents_root) not in sys.path:
        sys.path.insert(0, str(aiagents_root))

    from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitAnalyzer
    from backend.strategies.index_fund_research.etf_toolkit_settings import (
        build_alerts,
        build_analyzer_config,
        load_etf_toolkit_settings,
    )
    from backend.strategies.index_fund_research.etf_toolkit_store import ETFToolkitStore

    etf_settings = load_etf_toolkit_settings(project_root)
    if not etf_settings.get("monitor", {}).get("enabled", False):
        return {"success": True, "skipped": True, "message": "ETF定时监控未启用"}

    store = ETFToolkitStore(project_root)
    result = store.load_cached_result(etf_settings)
    if result is None:
        result = ETFToolkitAnalyzer().analyze_toolkit(build_analyzer_config(etf_settings))
        result["cache_hit"] = False
    result["alerts"] = build_alerts(result, etf_settings)
    report_path = _save_report(project_root, result)
    result["report_path"] = str(report_path)
    result.update(store.save_result(result, etf_settings))

    delivery = etf_settings.get("delivery", {})
    delivery_results = []
    should_deliver = not delivery.get("send_only_when_alert") or bool(result["alerts"])
    if should_deliver and delivery.get("email_enabled"):
        ok, message = send_email(root_settings, f"ETF策略工具箱监控 - {datetime.now().strftime('%Y-%m-%d')}", result.get("report", ""))
        delivery_results.append({"channel": "email", "ok": ok, "message": message})
    if should_deliver and delivery.get("lark_doc_enabled"):
        ok, message = _create_lark_doc(result)
        delivery_results.append({"channel": "lark_doc", "ok": ok, "message": message})
    if should_deliver and delivery.get("lark_bitable_enabled"):
        ok, message = _write_lark_bitable(project_root, result, etf_settings)
        delivery_results.append({"channel": "lark_bitable", "ok": ok, "message": message})

    return {
        "success": bool(result.get("success")),
        "skipped": False,
        "cache_hit": bool(result.get("cache_hit")),
        "market_snapshot_count": result.get("market_snapshot_count", 0),
        "analyzed_count": result.get("analyzed_count", 0),
        "alert_count": len(result.get("alerts", [])),
        "report_path": str(report_path),
        "history_path": result.get("history_path"),
        "delivery": delivery_results,
    }


def etf_schedule_times(project_root: Path) -> list[str]:
    path = project_root / "data" / "etf_toolkit_settings.json"
    if not path.exists():
        return ["15:20"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["15:20"]
    times = payload.get("monitor", {}).get("schedule_times", [])
    return [str(item).strip() for item in times if str(item).strip()] or ["15:20"]


def etf_schedule_frequency(project_root: Path) -> str:
    path = project_root / "data" / "etf_toolkit_settings.json"
    if not path.exists():
        return "工作日"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "工作日"
    return str(payload.get("monitor", {}).get("frequency", "工作日"))


def _save_report(project_root: Path, result: dict) -> Path:
    report_dir = project_root / "reports" / "etf_toolkit"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    markdown_path = report_dir / f"{stamp}_monitor.md"
    json_path = report_dir / f"{stamp}_monitor.json"
    markdown_path.write_text(result.get("report", ""), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return markdown_path


def _create_lark_doc(result: dict) -> tuple[bool, str]:
    if shutil.which("lark-cli") is None:
        return False, "未找到 lark-cli"
    title = f"ETF策略工具箱监控 - {datetime.now().strftime('%Y-%m-%d')}"
    alerts = result.get("alerts", [])
    alert_html = "".join(
        f"<li>{escape(item.get('类型', ''))} {escape(item.get('名称', ''))}: {escape(item.get('触发值', ''))}</li>"
        for item in alerts
    ) or "<li>本次无触发提醒。</li>"
    body = escape(result.get("report", "")).replace("\n", "<br/>")
    content = f"""
<title>{escape(title)}</title>
<h1>{escape(title)}</h1>
<h2>触发提醒</h2>
<ul>{alert_html}</ul>
<h2>完整报告</h2>
<p>{body}</p>
"""
    completed = subprocess.run(
        ["lark-cli", "docs", "+create", "--as", "user", "--content", "-", "--format", "json"],
        input=content,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        return False, f"飞书文档创建失败: {(completed.stderr or completed.stdout)[-1000:]}"
    return True, "飞书文档已创建"


def _write_lark_bitable(project_root: Path, result: dict, etf_settings: dict) -> tuple[bool, str]:
    config_path = Path(str(etf_settings.get("delivery", {}).get("lark_bitable_config_path") or "data/etf_toolkit_lark_table.json"))
    if not config_path.is_absolute():
        config_path = project_root / config_path
    if not config_path.exists():
        return False, f"飞书多维表格配置不存在: {config_path}"
    if shutil.which("lark-cli") is None:
        return False, "未找到 lark-cli"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"飞书多维表格配置读取失败: {exc}"
    alerts = result.get("alerts", []) or [{"类型": "ETF报告", "代码": "", "名称": "ETF策略工具箱", "触发原因": "无触发提醒", "触发值": "", "建议": "查看完整报告。"}]
    written = 0
    for alert in alerts:
        fields = {
            "执行日期": datetime.now().strftime("%Y-%m-%d"),
            "模块": "ETF策略工具箱",
            "类型": alert.get("类型", ""),
            "代码": alert.get("代码", ""),
            "名称": alert.get("名称", ""),
            "触发原因": alert.get("触发原因", ""),
            "触发值": alert.get("触发值", ""),
            "建议": alert.get("建议", ""),
            "完整报告": result.get("report", "")[:20000],
        }
        completed = subprocess.run(
            [
                "lark-cli", "base", "+record-upsert",
                "--base-token", config["base_token"],
                "--table-id", config["table_id"],
                "--json", json.dumps(fields, ensure_ascii=False),
                "--as", "user",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if completed.returncode != 0:
            return False, f"飞书多维表格写入失败: {(completed.stderr or completed.stdout)[-1000:]}"
        written += 1
    return True, f"飞书多维表格已写入 {written} 条记录"
