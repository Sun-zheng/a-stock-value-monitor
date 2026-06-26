from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


AI_SECTION_MARKER = "<!-- AI_VALUE_STOCK_ANALYSIS -->"


def _ai_project_root(project_root: Path) -> Path:
    return project_root / "aiagents-stock-main"


def default_ai_env_file() -> Path:
    return Path.home() / ".config" / "a-stock-value-monitor" / "aiagents.env"


def configured_analysis_models() -> list[str]:
    raw = os.getenv(
        "VALUE_ANALYSIS_MODELS",
        "deepseek-chat,deepseek-ai/deepseek-v3.1-terminus,stepfun-ai/Step-3.5-Flash",
    )
    models: list[str] = []
    for model in (item.strip() for item in raw.split(",")):
        if model and model not in models:
            models.append(model)
    return models


def _run_ai_tool(project_root: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    ai_root = _ai_project_root(project_root)
    python = ai_root / ".venv/bin/python"
    env = os.environ.copy()
    env.setdefault("AIAGENTS_ENV_FILE", str(default_ai_env_file()))
    return subprocess.run(
        [str(python), *args],
        cwd=ai_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def validate_ai_models(project_root: Path, models: list[str] | None = None) -> dict:
    models = models or configured_analysis_models()
    result = _run_ai_tool(
        project_root,
        [
            "tools/validate_ai_providers.py",
            "--models",
            ",".join(models),
            "--prompt",
            "只回复 OK",
        ],
        timeout=120,
    )
    if result.returncode not in (0, 1):
        return {"enabled_models": [], "status": "failed", "error": result.stderr or result.stdout}
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return {"enabled_models": [], "status": "failed", "error": result.stdout[-2000:]}
    enabled = [
        item["model"]
        for item in payload.get("results", [])
        if item.get("status") == "ok"
    ]
    payload["enabled_models"] = enabled
    payload["status"] = "ok" if enabled else "disabled"
    return payload


def analysis_stocks(scan: dict) -> list[dict]:
    stocks: list[dict] = []
    for item in scan.get("正式推荐股票", []):
        stocks.append({**item, "股票类型": "正式推荐", "是否正式推荐": True})
    for item in scan.get("观察股票", []):
        stocks.append({**item, "股票类型": "观察股票", "是否正式推荐": False})
    return stocks


def _format_decision(final_decision: dict) -> list[str]:
    if not isinstance(final_decision, dict) or not final_decision:
        return ["最终决策：暂无。"]
    if final_decision.get("decision_text"):
        return ["最终决策：", "", str(final_decision.get("decision_text"))]
    fields = [
        ("评级", "rating"),
        ("信心度", "confidence_level"),
        ("目标价", "target_price"),
        ("进场区间", "entry_range"),
        ("止盈位", "take_profit"),
        ("止损位", "stop_loss"),
        ("建议仓位", "position_size"),
        ("操作建议", "operation_advice"),
        ("投资建议", "advice"),
    ]
    lines = ["最终决策："]
    for label, key in fields:
        value = final_decision.get(key)
        if value not in (None, ""):
            lines.append(f"- {label}: {value}")
    return lines if len(lines) > 1 else ["最终决策：暂无。"]


def _format_agent_reports(agents_results: dict) -> list[str]:
    if not isinstance(agents_results, dict) or not agents_results:
        return ["#### 分析师报告", "", "未返回分析师报告。", ""]
    lines = ["#### 分析师报告", ""]
    for agent_result in agents_results.values():
        if not isinstance(agent_result, dict):
            continue
        agent_name = agent_result.get("agent_name", "未知分析师")
        role = agent_result.get("agent_role", "未知职责")
        focus = "、".join(agent_result.get("focus_areas", []) or [])
        lines.extend(
            [
                f"##### {agent_name}",
                "",
                f"- 职责: {role}",
                f"- 关注领域: {focus or '无'}",
                "",
                str(agent_result.get("analysis") or "暂无分析"),
                "",
            ]
        )
    return lines


def _format_stock_analysis(item: dict) -> list[str]:
    heading = f"### {item.get('stock_type', '股票')}：{item.get('name')}（{item.get('code')}）"
    if not item.get("success"):
        return [
            heading,
            "",
            f"AI 多分析师流程生成失败：{item.get('error', '未知错误')}。",
            "",
        ]
    lines = [
        heading,
        "",
        "#### 筛选上下文",
        "",
    ]
    value_context = item.get("value_context") or {}
    for key in ("综合评分", "安全边际", "PE TTM", "PB", "ROE", "ROIC", "经营现金流/净利润", "未达推荐原因", "下一步观察重点"):
        value = value_context.get(key)
        if value not in (None, ""):
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.extend(_format_agent_reports(item.get("agents_results", {})))
    lines.extend(["#### 团队讨论", "", str(item.get("discussion_result") or "暂无团队讨论。"), ""])
    lines.extend(["#### 最终决策", ""])
    lines.extend(_format_decision(item.get("final_decision", {})))
    lines.append("")
    return lines


def format_ai_analysis_markdown(result: dict, validation: dict) -> str:
    if not validation.get("enabled_models"):
        return (
            f"{AI_SECTION_MARKER}\n\n"
            "## 股票分析智能体复核\n\n"
            "AI 分析未启用：没有通过实际 API 测试的模型。原始价值筛选报告仍正常发送。\n"
        )
    if not result.get("success"):
        return (
            f"{AI_SECTION_MARKER}\n\n"
            "## 股票分析智能体复核\n\n"
            f"AI 分析生成失败：{result.get('error', '未知错误')}。\n"
        )
    lines = [
        AI_SECTION_MARKER,
        "",
        "## 股票分析智能体复核",
        "",
        f"- 已启用模型: {', '.join(validation.get('enabled_models', []))}",
        f"- 数据周期: {result.get('period', '1y')}",
        "- 分析流程: 网页统一股票分析流程 analyze_single_stock_for_batch",
        "- 分析师: 技术分析师、基本面分析师、资金面分析师、风险管理师、市场情绪分析师、新闻分析师",
        "- 启用条件: 仅使用本次交付前实际 API 测试通过的模型",
        "- 说明: 以下内容仅为价值研究复核，不构成投资建议",
        "",
    ]
    for item in result.get("analyses", []):
        lines.extend(_format_stock_analysis(item))
    return "\n".join(lines).rstrip() + "\n"


def generate_ai_value_analysis(project_root: Path, day: str, scan: dict) -> tuple[str, dict]:
    validation = validate_ai_models(project_root)
    stocks = analysis_stocks(scan)
    if not validation.get("enabled_models") or not stocks:
        markdown = format_ai_analysis_markdown({}, validation)
        return markdown, {"validation": validation, "generation": {"success": False, "reason": "disabled_or_no_stocks"}}

    with tempfile.TemporaryDirectory(prefix="value-ai-analysis.") as temporary:
        input_path = Path(temporary) / "input.json"
        output_path = Path(temporary) / "output.json"
        input_path.write_text(
            json.dumps(
                {
                    "day": day,
                    "scan": scan,
                    "stocks": stocks,
                    "models": validation["enabled_models"],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        result = _run_ai_tool(
            project_root,
            [
                "tools/generate_value_stock_analysis.py",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ],
            timeout=max(240, 90 * len(stocks)),
        )
        if result.returncode or not output_path.exists():
            generation = {
                "success": False,
                "error": (result.stderr or result.stdout or "AI分析工具未返回结果")[-3000:],
            }
        else:
            generation = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = format_ai_analysis_markdown(generation, validation)
    return markdown, {"validation": validation, "generation": generation}


def append_ai_analysis(report: str, ai_markdown: str) -> str:
    base = report.split(AI_SECTION_MARKER)[0].rstrip()
    return f"{base}\n\n{ai_markdown}".rstrip() + "\n"
