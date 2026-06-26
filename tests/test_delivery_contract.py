from main import delivery_items, lark_fields
from src.lark_bitable_client import LARK_FIELDS


def sample_scan() -> dict:
    stock = {
        "代码": "600000.SH",
        "名称": "示例股份",
        "交易所": "SSE",
        "上市板块": "主板",
        "行业": "示例行业",
        "综合评分": 82,
        "安全边际": 28,
        "市场错配判断": "优质成长被低估",
    }
    return {
        "最终推荐数量": 1,
        "正式推荐股票": [stock],
        "观察股票": [{**stock, "代码": "600001.SH", "名称": "观察股份"}],
        "原始股票数量": 5500,
        "主板股票数量": 3000,
        "行情覆盖率": 99.9,
        "估值覆盖率": 99.8,
        "财报覆盖率": 100.0,
        "现金流覆盖率": 90.0,
        "Tushare是否可用": True,
        "Tushare覆盖数量": 500,
        "缓存命中率": 100.0,
        "东方财富失败原因": [],
        "是否满足正式推荐条件": True,
        "估值数据交易日": "20260611",
        "财报数据报告期": "20251231",
        "估值轻筛通过数量": 500,
        "一票否决后数量": 300,
        "深度分析数量": 500,
        "总耗时": 60,
        "无推荐原因": "无",
        "行情数据时间": "2026-06-12T14:10:00+08:00",
        "数据源": {"行情": "测试"},
        "每日变化": {},
        "策略名称": "Buffett-Munger A股主板十年价值策略",
        "策略版本": 2,
        "正式推荐分数门槛": 80,
        "正式推荐安全边际门槛": 25,
        "数据性质": "盘中市值",
        "国内全市场基准股票数量": 5200,
        "行业基准范围": "境内全部上市A股",
    }


def test_delivery_items_are_one_record_per_stock():
    items = delivery_items(sample_scan())
    assert [item["代码"] for item in items] == ["600000.SH", "600001.SH"]
    assert [item["股票类型"] for item in items] == ["正式推荐", "观察股票"]


def test_lark_fields_are_complete_and_non_empty():
    scan = sample_scan()
    fields = lark_fields(
        "2026-06-12",
        scan,
        "完整报告",
        item=delivery_items(scan)[0],
        email_status="发送成功",
    )
    assert list(fields) == LARK_FIELDS
    assert all(str(value).strip() for value in fields.values())
