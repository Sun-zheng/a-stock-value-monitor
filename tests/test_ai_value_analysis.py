from src.ai_value_analysis import AI_SECTION_MARKER, analysis_stocks, append_ai_analysis, format_ai_analysis_markdown


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
        {"enabled_models": ["deepseek-chat"]},
    )

    assert "网页统一股票分析流程" in markdown
    assert "技术分析师" in markdown
    assert "团队讨论内容" in markdown
    assert "评级: 持有" in markdown
