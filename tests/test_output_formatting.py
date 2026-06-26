from main import build_delivery_email, format_value


def sample_scan() -> dict:
    stock = {
        "代码": "600000",
        "名称": "示例股份",
        "行业": "示例行业",
        "当前价格": 12.3456,
        "总市值": 123456789.0,
        "PE TTM": 10.234,
        "PB": 1.234,
        "PS": 2.345,
        "股息率": 4.567,
        "ROE": 15.678,
        "ROIC": 13.579,
        "经营性现金流净额": 23456789.0,
        "自由现金流": 12345678.0,
        "安全边际": 28.456,
        "综合评分": 82.345,
        "市场错配判断": "优质资产被阶段性低估",
        "已计价预期": "市场已计入短期运价回落",
        "长期投资关键证据": "现金流、ROE 和低负债同时成立",
        "芒格反向失败清单": "需求下滑超预期、资本开支失控",
        "十年持有结论": "满足质量门槛，可继续跟踪",
        "下一步观察重点": "跟踪下季现金流与订单",
    }
    return {
        "策略名称": "Buffett-Munger A股主板十年价值策略",
        "主板股票数量": 3030,
        "国内全市场基准股票数量": 5299,
        "估值轻筛通过数量": 500,
        "正式条件检查数量": 500,
        "一票否决后数量": 251,
        "最终推荐数量": 1,
        "观察股票数量": 1,
        "估值数据交易日": "20260622",
        "行情交易日": "20260622",
        "行情数据时间": "2026-06-23T14:10:13+08:00",
        "无推荐原因": "无",
        "每日变化": {"explanation": "观察池变化"},
        "正式推荐股票": [stock],
        "观察股票": [{**stock, "代码": "600001", "名称": "观察股份"}],
    }


def test_format_value_rounds_and_uses_wan_and_yi():
    assert format_value(123456789, "总市值") == "1.23亿"
    assert format_value(1234567, "总市值") == "123.46万"
    assert format_value(15.678, "ROE") == "15.68%"
    assert format_value(82, "综合评分") == "82.00"


def test_delivery_email_focuses_on_meaningful_analysis():
    scan = sample_scan()
    body = build_delivery_email("2026-06-23", scan, "本地完整报告", ["600000:created"])
    assert "全量前一交易日数据" in body
    assert "正式推荐股票分析" in body
    assert "观察股票分析" in body
    assert "市场错配" in body
    assert "关键证据" in body
    assert "1.23亿" in body
    assert "2345.68万" in body
