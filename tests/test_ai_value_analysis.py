import subprocess

from src import ai_value_analysis
from src.ai_value_analysis import (
    AI_SECTION_MARKER,
    ai_analysis_max_stocks,
    ai_analysis_timeout,
    analysis_stocks,
    append_ai_analysis,
    configured_analysis_models,
    format_ai_analysis_markdown,
    generate_ai_value_analysis,
)


def test_analysis_stocks_includes_formal_and_observations():
    scan = {
        "正式推荐股票": [{"代码": "000001", "名称": "正式"}],
        "观察股票": [{"代码": "000002", "名称": "观察"}],
    }

    stocks = analysis_stocks(scan)

    assert [item["股票类型"] for item in stocks] == ["正式推荐", "观察股票"]


def test_append_ai_analysis_replaces_existing_section():
    report = f"base\n\n{AI_SECTION_MARKER}\nold"
    updated = append_ai_analysis(report, f"{AI_SECTION_MARKER}\n\n## new\n")

    assert "old" not in updated
    assert "## new" in updated


def test_format_ai_analysis_disabled_when_no_validated_model():
    markdown = format_ai_analysis_markdown({}, {"enabled_models": []})

    assert "AI 分析未启用" in markdown


def test_format_ai_analysis_includes_multi_agent_outputs():
    markdown = format_ai_analysis_markdown(
        {
            "success": True,
            "period": "1y",
            "analyses": [
                {
                    "success": True,
                    "code": "000001",
                    "name": "平安银行",
                    "stock_type": "观察股票",
                    "value_context": {"综合评分": 70, "未达推荐原因": "安全边际不足"},
                    "agents_results": {
                        "technical": {
                            "agent_name": "技术分析师",
                            "agent_role": "技术分析",
                            "focus_areas": ["趋势"],
                            "analysis": "技术报告",
                        }
                    },
                    "discussion_result": "团队讨论内容",
                    "final_decision": {"rating": "持有", "confidence_level": "7"},
                }
            ],
        },
        {"enabled_models": ["stepfun-ai/Step-3.7-Flash"]},
    )

    assert "网页统一股票分析流程" in markdown
    assert "技术分析师" in markdown
    assert "团队讨论内容" in markdown
    assert "评级: 持有" in markdown


def test_format_ai_analysis_defaults_to_readable_summary(monkeypatch):
    monkeypatch.delenv("VALUE_ANALYSIS_EMAIL_DETAIL", raising=False)
    long_text = "风险提示。" * 200

    markdown = format_ai_analysis_markdown(
        {
            "success": True,
            "period": "1y",
            "analyses": [
                {
                    "success": True,
                    "code": "000001",
                    "name": "平安银行",
                    "stock_type": "观察股票",
                    "agents_results": {
                        "technical": {
                            "agent_name": "技术分析师",
                            "agent_role": "技术分析",
                            "analysis": long_text,
                        }
                    },
                    "discussion_result": long_text,
                    "final_decision": {"rating": "观察"},
                }
            ],
        },
        {"enabled_models": ["stepfun-ai/Step-3.7-Flash"]},
    )

    assert "#### 分析师摘要" in markdown
    assert "#### 分析师报告" not in markdown
    assert len(markdown) < len(long_text) * 2


def test_ai_analysis_timeout_defaults_scale_by_stock_count():
    assert ai_analysis_timeout(1) >= 900
    assert ai_analysis_timeout(5) >= 1200


def test_ai_analysis_max_stocks_defaults_to_three(monkeypatch, tmp_path):
    monkeypatch.setenv("AIAGENTS_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("VALUE_ANALYSIS_MAX_STOCKS", raising=False)

    assert ai_analysis_max_stocks() == 3


def test_generate_ai_value_analysis_returns_timeout_status(monkeypatch, tmp_path):
    monkeypatch.setenv("VALUE_ANALYSIS_ENABLED", "1")
    monkeypatch.setattr(
        ai_value_analysis,
        "validate_ai_models",
        lambda project_root: {"enabled_models": ["stepfun-ai/Step-3.7-Flash"], "status": "ok"},
    )

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["tool"], timeout=3)

    monkeypatch.setattr(ai_value_analysis, "_run_ai_tool", raise_timeout)

    markdown, status = generate_ai_value_analysis(
        tmp_path,
        "2026-06-29",
        {"观察股票": [{"代码": "000001", "名称": "平安银行"}], "正式推荐股票": []},
    )

    assert "AI 分析生成失败" in markdown
    assert status["generation"]["timeout_seconds"] == 3


def test_generate_ai_value_analysis_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AIAGENTS_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("VALUE_ANALYSIS_ENABLED", raising=False)

    markdown, status = generate_ai_value_analysis(
        tmp_path,
        "2026-06-29",
        {"观察股票": [{"代码": "000001", "名称": "平安银行"}], "正式推荐股票": []},
    )

    assert "AI 分析未启用" in markdown
    assert status["generation"]["reason"] == "disabled"


def test_configured_analysis_models_filters_deepseek_by_default(monkeypatch):
    monkeypatch.setenv("AIAGENTS_ENV_FILE", "/tmp/nonexistent-aiagents.env")
    monkeypatch.setenv(
        "VALUE_ANALYSIS_MODELS",
        "deepseek-chat,stepfun-ai/Step-3.7-Flash,deepseek-ai/DeepSeek-V4-Pro",
    )
    monkeypatch.delenv("VALUE_ANALYSIS_ALLOW_DEEPSEEK", raising=False)

    assert configured_analysis_models() == ["stepfun-ai/Step-3.7-Flash", "deepseek-ai/DeepSeek-V4-Pro"]


def test_configured_analysis_models_can_allow_deepseek_manually(monkeypatch):
    monkeypatch.setenv("AIAGENTS_ENV_FILE", "/tmp/nonexistent-aiagents.env")
    monkeypatch.setenv("VALUE_ANALYSIS_MODELS", "deepseek-chat,stepfun-ai/Step-3.7-Flash")
    monkeypatch.setenv("VALUE_ANALYSIS_ALLOW_DEEPSEEK", "1")

    assert configured_analysis_models() == ["deepseek-chat", "stepfun-ai/Step-3.7-Flash"]
