from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import settings
from src.ai_value_analysis import append_ai_analysis, generate_ai_value_analysis
from src.analysis_history import write_analysis_history
from src.data_source_manager import DataSourceManager
from src.daily_comparison import compare_previous_day
from src.email_sender import send_email
from src.freshness import freshness_report
from src.lark_bitable_client import LarkBitableClient
from src.logger import build_logger
from src.low_price_bull_daily import run_low_price_bull_daily
from src.runtime_state import PipelineAlreadyRunning, RuntimeState
from src.scheduler import configure_native_schedule, native_schedule_status
from src.source_health_checker import health_check
from src.strategy_config import load_strategy
from src.strategy_validator import run_strategy_validation
from src.trading_calendar import is_a_share_trading_day
from src.universe_scanner import (
    FINANCIAL_FIELDS,
    analyze_top10,
    row_coverage,
    scan_candidates,
    scan_light,
    scan_universe,
    valuation_coverage,
)


NO_PICK = "今日无符合标准的 A 股全市场低估股票，不强行推荐。"
MONEY_FIELDS = {
    "总市值", "流通市值", "上一交易日总市值", "上一交易日流通市值",
    "经营性现金流净额", "自由现金流", "标准化自由现金流", "营业收入",
    "归母净利润", "扣非净利润", "货币资金", "有息负债", "商誉",
    "应收账款", "存货", "保守合理市值", "中性合理市值", "乐观合理市值",
}
PERCENT_FIELDS = {
    "涨跌幅", "股息率", "ROE", "扣非ROE", "ROIC", "毛利率", "净利率",
    "资产负债率", "经营现金流/净利润", "安全边际", "行情覆盖率", "估值覆盖率",
    "财报覆盖率", "现金流覆盖率", "分红覆盖率", "安全边际门槛",
    "可靠估值覆盖率",
}
TEXT_FIELDS = {"代码", "名称", "行业", "交易所", "上市板块"}


def output(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _to_float(value):
    if value in (None, "", "数据不足", "无"):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def format_value(value, field: str | None = None) -> str:
    if value is None or value == "":
        return "数据不足"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if field in TEXT_FIELDS or field in {"估值数据交易日", "行情交易日", "财报数据报告期", "现金流数据报告期"}:
        return str(value)
    number = _to_float(value)
    if number is None:
        return str(value)
    if field in MONEY_FIELDS:
        if abs(number) >= 100000000:
            return f"{number / 100000000:.2f}亿"
        if abs(number) >= 10000:
            return f"{number / 10000:.2f}万"
    suffix = "%" if field in PERCENT_FIELDS else ""
    return f"{number:.2f}{suffix}"


def format_summary_line(label: str, value, field: str | None = None) -> str:
    return f"- {label}: {format_value(value, field or label)}"


def report_paths(day: str) -> tuple:
    return (
        settings.reports_dir / f"{day}_result.json",
        settings.reports_dir / f"{day}_report_base.md",
        settings.reports_dir / f"{day}_report.md",
    )


def build_base_report(day: str, scan: dict) -> str:
    comparison = scan.get("每日变化", {})
    scope_label = scan.get("推荐范围", "境内全市场A股")
    strategy_name = scan.get("策略名称", "Buffett-Munger A股全市场十年价值策略")
    header = f"""# A股全市场低估股票分析基础报告

- 执行日期: {day}
- 行情数据时间: {scan['行情数据时间']}
- 行情交易日: {scan.get('行情交易日', '数据不足')}
- 行情数据类型: {scan.get('行情数据类型', '未知')}
- 行情降级: {scan.get('行情是否降级', False)}
- 行情降级原因: {scan.get('行情降级原因', '无') or '无'}
- 估值数据交易日: {scan['估值数据交易日']}
- 财报数据报告期: {scan['财报数据报告期']}
- 数据性质: {scan['数据性质']}
- 行情覆盖率: {format_value(scan['行情覆盖率'], '行情覆盖率')}
- 估值覆盖率: {format_value(scan['估值覆盖率'], '估值覆盖率')}
- 财报覆盖率: {format_value(scan['财报覆盖率'], '财报覆盖率')}
- 现金流覆盖率: {format_value(scan['现金流覆盖率'], '现金流覆盖率')}
- 推荐范围: {scope_label}
- 推荐范围说明: {scan.get('推荐范围说明', '境内全部上市A股')}
- 推荐范围股票数量: {format_value(scan.get('推荐范围股票数量', scan.get('主板股票数量')), '推荐范围股票数量')}
- 策略名称: {strategy_name}
- 正式推荐门槛: 综合评分>={format_value(scan.get('正式推荐分数门槛', 80), '正式推荐分数门槛')}，安全边际>={format_value(scan.get('正式推荐安全边际门槛', 25), '安全边际门槛')}
- 观察门槛: 综合评分>={format_value(scan.get('观察分数门槛', 68), '观察分数门槛')}
- 九维框架: 生意质量、资本配置、盈利韧性、财务安全、现金流、十年成长跑道、估值、股东回报、芒格反向清单
- 财务检查候选数量: {format_value(scan['估值轻筛通过数量'], '估值轻筛通过数量')}
- 正式条件检查数量: {format_value(scan['正式条件检查数量'], '正式条件检查数量')}
- Top10用途: 仅展示，不截断正式条件检查
- 正式估值口径: 全市场同行相对估值、保守盈利估值、标准化自由现金流估值三族齐全；安全边际取最低合理市值
- 最终结论: {NO_PICK if scan['最终推荐数量'] == 0 else '存在待复核候选'}
- 无推荐原因: {scan['无推荐原因']}

## 今日变化摘要

- 上一报告日: {comparison.get('previous_date', '无')}
- 正式推荐变化: 新进 {', '.join(comparison.get('formal_entered', [])) or '无'}；移出 {', '.join(comparison.get('formal_exited', [])) or '无'}
- 观察池变化: 新进 {', '.join(comparison.get('observation_entered', [])) or '无'}；移出 {', '.join(comparison.get('observation_exited', [])) or '无'}
- 候选Top10变化: 新进 {', '.join(comparison.get('top10_entered', [])) or '无'}；移出 {', '.join(comparison.get('top10_exited', [])) or '无'}
- 连续重复天数: {comparison.get('consecutive_repeat_days', 1)}
- 策略健康告警: {comparison.get('strategy_health_warning', False)}
- 报告内容变化: {comparison.get('report_changed', False)}
- 变化说明: {comparison.get('explanation', '首次运行或无可比报告')}

"""
    if scan["最终推荐数量"] > 0:
        stocks = scan.get("正式推荐股票", [])
        section = "\n## 今日正式推荐股票\n\n" + "\n".join(
            format_stock(item, recommendation=True) for item in stocks
        )
    else:
        observations = scan.get("观察股票", [])
        section = (
            "\n## 今日观察股票\n\n"
            "今日无符合标准的 A 股全市场低估股票，不强行推荐。"
            "以下股票为观察股票，不是推荐，不构成买入建议。\n\n"
            + (
                "\n\n".join(format_stock(item, recommendation=False) for item in observations)
                if observations else f"观察股票不足：{scan.get('观察股票不足5只原因', '数据不足')}"
            )
        )
    return header + section + (
        "\n\n飞书多维表格链接："
        "https://my.feishu.cn/base/BOZHbUgxIa2Ls6svZ3tcTvEFn5f\n\n"
        "本报告仅作为投资研究参考，不构成投资建议。数据不足处不得推断或编造。\n"
    )


def format_stock(item: dict, recommendation: bool) -> str:
    fields = [
        "代码", "名称", "行业", "当前价格", "总市值", "PE TTM", "PB", "PS",
        "股息率", "ROE", "扣非ROE", "ROIC", "毛利率", "净利率",
        "经营性现金流净额", "经营现金流/净利润", "自由现金流",
        "资产负债率", "有息负债", "货币资金", "综合评分", "估值评分",
        "现金流评分", "盈利能力评分", "资产负债评分", "成长性评分",
        "分红评分", "保守合理市值", "中性合理市值", "乐观合理市值",
        "安全边际", "生意质量与护城河评分", "管理层与资本配置评分",
        "盈利能力与韧性评分", "财务安全评分", "现金流质量评分",
        "十年成长跑道评分", "估值与安全边际评分", "股东回报评分",
        "芒格反向清单评分", "九维评分明细", "市场错配判断",
        "已计价预期", "为何现在", "长期投资关键证据",
        "芒格反向失败清单", "十年持有质量门槛", "十年持有结论",
        "未达推荐原因", "下一步观察重点",
    ]
    title = (
        f"### 正式推荐：{item.get('名称')}（{item.get('代码')}）"
        if recommendation
        else f"### 观察 #{item.get('观察排名', '')}：{item.get('名称')}（{item.get('代码')}）"
    )
    lines = [title]
    for field in fields:
        lines.append(format_summary_line(field, item.get(field, "数据不足"), field))
    lines.append(
        "- 操作建议: 正式研究结论，仍需人工复核"
        if recommendation else "- 操作建议: 继续观察，不构成推荐"
    )
    return "\n".join(lines)


def email_stock_section(item: dict, recommendation: bool) -> str:
    title = (
        f"### 正式推荐：{item.get('名称', '数据不足')}（{item.get('代码', '数据不足')}）"
        if recommendation
        else f"### 观察股票：{item.get('名称', '数据不足')}（{item.get('代码', '数据不足')}）"
    )
    lines = [
        title,
        format_summary_line("行业", item.get("行业", "数据不足"), "行业"),
        format_summary_line("当前价格", item.get("当前价格", "数据不足"), "当前价格"),
        format_summary_line("总市值", item.get("总市值", "数据不足"), "总市值"),
        format_summary_line("PE TTM", item.get("PE TTM", "数据不足"), "PE TTM"),
        format_summary_line("PB", item.get("PB", "数据不足"), "PB"),
        format_summary_line("PS", item.get("PS", "数据不足"), "PS"),
        format_summary_line("股息率", item.get("股息率", "数据不足"), "股息率"),
        format_summary_line("ROE", item.get("ROE", "数据不足"), "ROE"),
        format_summary_line("ROIC", item.get("ROIC", "数据不足"), "ROIC"),
        format_summary_line("经营性现金流净额", item.get("经营性现金流净额", "数据不足"), "经营性现金流净额"),
        format_summary_line("自由现金流", item.get("标准化自由现金流", item.get("自由现金流", "数据不足")), "自由现金流"),
        format_summary_line("安全边际", item.get("安全边际", "数据不足"), "安全边际"),
        format_summary_line("综合评分", item.get("综合评分", "数据不足"), "综合评分"),
        f"- 市场错配: {item.get('市场错配判断', '数据不足')}",
        f"- 已计价预期: {item.get('已计价预期', '数据不足')}",
        f"- 关键证据: {item.get('长期投资关键证据', '数据不足')}",
        f"- 失败清单: {item.get('芒格反向失败清单', '数据不足')}",
        f"- 十年持有结论: {item.get('十年持有结论', '数据不足')}",
        f"- 下一步观察: {item.get('下一步观察重点', item.get('未达推荐原因', '数据不足'))}",
    ]
    return "\n".join(lines)


def lark_fields(
    day: str,
    scan: dict,
    report: str,
    item: dict | None = None,
    email_status: str = "待发送",
) -> dict:
    item = item or {}
    stock_type = item.get("股票类型") or (
        "正式推荐" if item.get("是否正式推荐") else "观察股票"
    )
    fields = {
        "执行日期": day,
        "是否交易日": "是",
        "执行时间": datetime.now(ZoneInfo(settings.timezone)).strftime("%H:%M:%S %Z"),
        "最终结论": NO_PICK if scan["最终推荐数量"] == 0 else "存在待复核候选",
        "股票代码": item.get("代码", "无"),
        "股票名称": item.get("名称", "无"),
        "所属交易所": item.get("交易所", "数据不足"),
        "上市板块": item.get("上市板块", "数据不足"),
        "所属行业": item.get("行业", "数据不足"),
        "当前价格": format_value(item.get("当前价格", "数据不足"), "当前价格"),
        "涨跌幅": format_value(item.get("涨跌幅", "数据不足"), "涨跌幅"),
        "当前市值": format_value(item.get("总市值", "数据不足"), "总市值"),
        "流通市值": format_value(item.get("流通市值", "数据不足"), "流通市值"),
        "PE TTM": format_value(item.get("PE TTM", "数据不足"), "PE TTM"),
        "PB": format_value(item.get("PB", "数据不足"), "PB"),
        "PS": format_value(item.get("PS", "数据不足"), "PS"),
        "股息率": format_value(item.get("股息率", "数据不足"), "股息率"),
        "ROE": format_value(item.get("ROE", "数据不足"), "ROE"),
        "扣非ROE": format_value(item.get("扣非ROE", "数据不足"), "扣非ROE"),
        "ROIC": format_value(item.get("ROIC", "数据不足"), "ROIC"),
        "毛利率": format_value(item.get("毛利率", "数据不足"), "毛利率"),
        "净利率": format_value(item.get("净利率", "数据不足"), "净利率"),
        "经营现金流净额": format_value(item.get("经营性现金流净额", "数据不足"), "经营性现金流净额"),
        "自由现金流": format_value(item.get("标准化自由现金流", item.get("自由现金流", "数据不足")), "自由现金流"),
        "资产负债率": format_value(item.get("资产负债率", "数据不足"), "资产负债率"),
        "综合评分": format_value(item.get("综合评分", "数据不足"), "综合评分"),
        "安全边际": format_value(item.get("安全边际", "数据不足"), "安全边际"),
        "操作建议": item.get("操作建议", "无"),
        "核心逻辑": item.get("市场错配判断", "未发现明确市场错配"),
        "主要风险": item.get("芒格反向失败清单", "数据不足"),
        "数据来源": json.dumps(scan.get("数据源", {}), ensure_ascii=False, default=str),
        "数据时间": scan.get("行情数据时间", "数据不足"),
        "原始股票数量": format_value(scan["原始股票数量"], "原始股票数量"),
        "主板股票数量": format_value(scan["主板股票数量"], "主板股票数量"),
        "行情覆盖率": format_value(scan["行情覆盖率"], "行情覆盖率"),
        "估值覆盖率": format_value(scan["估值覆盖率"], "估值覆盖率"),
        "财报覆盖率": format_value(scan["财报覆盖率"], "财报覆盖率"),
        "现金流覆盖率": format_value(scan["现金流覆盖率"], "现金流覆盖率"),
        "Tushare是否可用": str(scan["Tushare是否可用"]),
        "Tushare覆盖数量": format_value(scan["Tushare覆盖数量"], "Tushare覆盖数量"),
        "缓存命中率": format_value(scan["缓存命中率"], "缓存命中率"),
        "数据源失败原因": "；".join(scan["东方财富失败原因"]) or "无",
        "是否满足正式推荐条件": str(scan["是否满足正式推荐条件"]),
        "估值数据交易日": str(scan["估值数据交易日"]),
        "财报数据报告期": str(scan["财报数据报告期"]),
        "数据覆盖率说明": (
            f"行情{format_value(scan['行情覆盖率'], '行情覆盖率')}；"
            f"估值{format_value(scan['估值覆盖率'], '估值覆盖率')}；"
            f"财报{format_value(scan['财报覆盖率'], '财报覆盖率')}；"
            f"现金流{format_value(scan['现金流覆盖率'], '现金流覆盖率')}"
        ),
        "通过估值初筛数量": format_value(scan["估值轻筛通过数量"], "估值轻筛通过数量"),
        "通过一票否决数量": format_value(scan["一票否决后数量"], "一票否决后数量"),
        "深度分析数量": format_value(scan["深度分析数量"], "深度分析数量"),
        "最终推荐数量": format_value(scan["最终推荐数量"], "最终推荐数量"),
        "是否正式推荐": "是" if item.get("是否正式推荐") else "否",
        "股票类型": stock_type,
        "观察排名": item.get("观察排名", "无"),
        "未达推荐原因": item.get("未达推荐原因", scan["无推荐原因"]),
        "距离推荐标准差距": item.get("距离推荐标准差距", "无"),
        "下一步观察重点": item.get("下一步观察重点", "无"),
        "是否观察股票": "是" if stock_type == "观察股票" else "否",
        "是否今日休息": "是" if not item else "否",
        "扫描耗时": format_value(scan["总耗时"], "总耗时"),
        "无推荐原因": scan["无推荐原因"],
        "扫描摘要": (
            f"{scan.get('推荐范围', '推荐范围')}{format_value(scan.get('推荐范围股票数量', scan['主板股票数量']), '推荐范围股票数量')}只，"
            f"估值初筛{format_value(scan['估值轻筛通过数量'], '估值轻筛通过数量')}只，"
            f"一票否决后{format_value(scan['一票否决后数量'], '一票否决后数量')}只，"
            f"最终推荐{format_value(scan['最终推荐数量'], '最终推荐数量')}只"
        ),
        "上一日排名": json.dumps(
            scan.get("每日变化", {}).get("previous_codes", []),
            ensure_ascii=False,
        ),
        "排名变化": json.dumps(
            {
                "进入": scan.get("每日变化", {}).get("entered", []),
                "移出": scan.get("每日变化", {}).get("exited", []),
            },
            ensure_ascii=False,
        ),
        "连续观察天数": str(
            scan.get("每日变化", {}).get("consecutive_repeat_days", 1)
        ),
        "首次进入日期": day,
        "今日变化摘要": scan.get("每日变化", {}).get("explanation", ""),
        "完整分析报告": report,
        "飞书表格链接": "https://my.feishu.cn/base/BOZHbUgxIa2Ls6svZ3tcTvEFn5f",
        "邮件发送状态": email_status,
        "飞书写入状态": "已写入",
        "运行日志": str(settings.logs_dir / f"{day}.log"),
        "数据缺失说明": "缺失字段统一填写“数据不足”，缺失数据不加分",
        "观察方向": item.get("下一步观察重点", "无"),
        "策略名称": scan.get("策略名称", "Buffett-Munger A股全市场十年价值策略"),
        "策略版本": scan.get("策略版本", 2),
        "正式推荐分数门槛": format_value(scan.get("正式推荐分数门槛", 80), "正式推荐分数门槛"),
        "安全边际门槛": format_value(scan.get("正式推荐安全边际门槛", 25), "安全边际门槛"),
        "生意质量与护城河评分": format_value(item.get("生意质量与护城河评分", "数据不足"), "生意质量与护城河评分"),
        "管理层与资本配置评分": format_value(item.get("管理层与资本配置评分", "数据不足"), "管理层与资本配置评分"),
        "盈利能力与韧性评分": format_value(item.get("盈利能力与韧性评分", "数据不足"), "盈利能力与韧性评分"),
        "财务安全评分": format_value(item.get("财务安全评分", "数据不足"), "财务安全评分"),
        "现金流质量评分": format_value(item.get("现金流质量评分", "数据不足"), "现金流质量评分"),
        "十年成长跑道评分": format_value(item.get("十年成长跑道评分", "数据不足"), "十年成长跑道评分"),
        "估值与安全边际评分": format_value(item.get("估值与安全边际评分", "数据不足"), "估值与安全边际评分"),
        "股东回报评分": format_value(item.get("股东回报评分", "数据不足"), "股东回报评分"),
        "芒格反向清单评分": format_value(item.get("芒格反向清单评分", "数据不足"), "芒格反向清单评分"),
        "九维评分明细": item.get("九维评分明细", "数据不足"),
        "芒格反向失败清单": item.get("芒格反向失败清单", "数据不足"),
        "市场错配判断": item.get("市场错配判断", "未发现明确市场错配"),
        "十年持有质量门槛": str(item.get("十年持有质量门槛", False)),
        "十年持有结论": item.get("十年持有结论", "数据不足"),
        "估值方法有效数": format_value(item.get("估值方法有效数", "数据不足"), "估值方法有效数"),
        "可靠估值覆盖率": format_value(item.get("可靠估值覆盖率", "数据不足"), "可靠估值覆盖率"),
        "市值口径": item.get("市值口径", scan.get("数据性质", "数据不足")),
        "报表期间一致": str(item.get("报表期间一致", False)),
        "已计价预期": item.get("已计价预期", "数据不足"),
        "长期投资关键证据": item.get("长期投资关键证据", "数据不足"),
        "为何现在": item.get("为何现在", "数据不足"),
        "国内全市场基准股票数量": format_value(
            scan.get("国内全市场基准股票数量", "数据不足"),
            "国内全市场基准股票数量",
        ),
        "行业基准范围": scan.get("行业基准范围", "境内全部上市A股"),
    }
    from src.lark_bitable_client import LARK_FIELDS

    return {
        name: (
            "无"
            if fields.get(name) is None or str(fields.get(name)).strip() == ""
            else str(fields.get(name))
        )
        for name in LARK_FIELDS
    }


def delivery_items(scan: dict) -> list[dict]:
    items = []
    for item in scan.get("正式推荐股票", []):
        items.append({**item, "股票类型": "正式推荐", "是否正式推荐": True})
    for item in scan.get("观察股票", []):
        items.append({**item, "股票类型": "观察股票", "是否正式推荐": False})
    if not items:
        items.append({
            "代码": "无",
            "名称": "今日无符合标准股票",
            "股票类型": "今日休息",
            "是否正式推荐": False,
            "未达推荐原因": scan.get("无推荐原因", "无"),
            "操作建议": "今日无符合标准股票，不强行推荐",
        })
    return items


def build_delivery_email(
    day: str, scan: dict, report: str, lark_results: list[str]
) -> str:
    formal = scan.get("正式推荐股票", [])
    observations = scan.get("观察股票", [])
    formal_section = (
        "\n\n".join(email_stock_section(item, recommendation=True) for item in formal)
        if formal else "无"
    )
    observation_section = (
        "\n\n".join(email_stock_section(item, recommendation=False) for item in observations)
        if observations else "无"
    )
    return f"""# A股全市场 Buffett-Munger 十年价值策略执行邮件

## 执行全过程

1. 确认 {day} 为A股交易日。
2. 扫描推荐范围 {format_value(scan.get('推荐范围股票数量', scan['主板股票数量']), '推荐范围股票数量')} 只股票，范围为 {scan.get('推荐范围', '境内全市场A股')}。
3. 使用境内全A股 {format_value(scan.get('国内全市场基准股票数量', '数据不足'), '国内全市场基准股票数量')} 只股票构建同行估值基准。
4. 生成 {scan['估值轻筛通过数量']} 只候选，并对全部候选完成财务与正式条件检查。
5. 核验完整年度ROE、扣非ROE、四类财务数据期间及现金流。
6. 逐只执行 Buffett-Munger 九维评分和芒格反向失败清单。
7. 使用三类独立估值，按最低合理市值计算保守安全边际。
8. 正式推荐最多1只，观察最多5只且不以低分凑数。
9. 每只正式推荐和观察股票分别写入飞书多维表格。

## 本次结果

- 策略: {scan.get('策略名称')}
- 分析口径: 全量前一交易日数据
- 推荐范围: {scan.get('推荐范围', '境内全市场A股')}
- 数据时间: {scan.get('行情数据时间')}
- 估值交易日: {scan.get('估值数据交易日')}
- 行情交易日: {scan.get('行情交易日')}
- 推荐范围股票数量: {format_value(scan.get('推荐范围股票数量', scan.get('主板股票数量')), '推荐范围股票数量')}
- 主板股票数量: {format_value(scan.get('主板股票数量'), '主板股票数量')}
- 国内全市场基准股票数量: {format_value(scan.get('国内全市场基准股票数量'), '国内全市场基准股票数量')}
- 估值轻筛通过数量: {format_value(scan.get('估值轻筛通过数量'), '估值轻筛通过数量')}
- 正式条件检查数量: {format_value(scan.get('正式条件检查数量'), '正式条件检查数量')}
- 一票否决后数量: {format_value(scan.get('一票否决后数量'), '一票否决后数量')}
- 正式推荐: {', '.join(f"{x.get('名称')}({x.get('代码')})" for x in formal) or '无'}
- 观察股票: {', '.join(f"{x.get('名称')}({x.get('代码')})" for x in observations) or '无'}
- 无推荐原因: {scan.get('无推荐原因')}
- 今日变化: {scan.get('每日变化', {}).get('explanation', '无')}
- 飞书写入: {'；'.join(lark_results) or '未执行'}
- 邮件状态: 本邮件已生成并进入发送动作，收到本邮件即表示发送成功
- 本地报告: {settings.reports_dir / f'{day}_report.md'}
- 飞书表格: https://my.feishu.cn/base/BOZHbUgxIa2Ls6svZ3tcTvEFn5f

## 正式推荐股票分析

{formal_section}

## 观察股票分析

{observation_section}

## 本地留存

- 结构化结果: {settings.reports_dir / f'{day}_result.json'}
- 基础报告: {settings.reports_dir / f'{day}_report_base.md'}
- 最终报告: {settings.reports_dir / f'{day}_report.md'}
- 历史记忆: {settings.project_root / 'data' / 'analysis_history' / f'{day}_analysis.json'}

## 完整分析报告摘要

{report}
"""


def save_pipeline_outputs(scan: dict, codex_mode: bool = False) -> dict:
    day = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    result_path, base_path, final_path = report_paths(day)
    payload = {
        "date": day,
        "scan_summary": scan,
        "recommendation": (
            scan.get("正式推荐股票", [None])[0]
            if scan.get("正式推荐股票")
            else None
        ),
        "observations": scan.get("观察股票", []),
        "conclusion": NO_PICK if scan["最终推荐数量"] == 0 else "存在正式推荐候选",
        "codex_ai_pending": codex_mode,
    }
    scan["每日变化"] = compare_previous_day(
        settings.reports_dir,
        day,
        current_payload=payload,
        current_scan=scan,
    )
    base_report = build_base_report(day, scan)
    scan["每日变化"] = compare_previous_day(
        settings.reports_dir,
        day,
        current_payload=payload,
        current_scan=scan,
        current_report_text=base_report,
    )
    payload["scan_summary"] = scan
    base_report = build_base_report(day, scan)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    base_path.write_text(base_report, encoding="utf-8")
    final_path.write_text(base_report, encoding="utf-8")
    scan_path = settings.reports_dir / f"{day}_scan_summary.json"
    scan_path.write_text(
        json.dumps(scan, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    outputs = {
        "result": str(result_path),
        "base_report": str(base_path),
        "final_report": str(final_path),
        "scan_summary": str(scan_path),
    }
    outputs.update(
        write_analysis_history(
            settings.project_root / "data",
            day,
            scan,
            outputs,
            generated_at=datetime.now(ZoneInfo(settings.timezone)).isoformat(),
        )
    )
    return outputs


def run_full(limit: int | None = None, force: bool = False) -> tuple[int, dict]:
    result = scan_universe(
        settings.project_root, settings.reports_dir, limit=limit,
        financial_limit=500 if limit is None else min(limit, 500), force=force,
    )
    output(result)
    return 0, result


def run_once(codex_mode: bool = False) -> int:
    now = datetime.now(ZoneInfo(settings.timezone))
    logger = build_logger(settings.logs_dir, now.date())
    trading, source = is_a_share_trading_day(now.date(), settings.calendar_cache_path)
    if not trading:
        logger.info("%s 不是A股交易日，来源=%s", now.date(), source)
        return 0
    runtime = RuntimeState(settings.project_root / "data", settings.timezone)
    try:
        with runtime.single_instance():
            run_id = runtime.start_run({"calendar_source": source})
            try:
                runtime.update_run(run_id, "data_fetch")
                fresh = freshness_report(settings.project_root, settings.timezone)
                runtime.update_run(run_id, "light_scan", metadata={"freshness": fresh})
                _, scan = run_full()
                runtime.update_run(run_id, "scoring")
                outputs = save_pipeline_outputs(scan, codex_mode=codex_mode)
                runtime.update_run(
                    run_id,
                    "completed",
                    "completed",
                    metadata={"outputs": outputs},
                )
                logger.info("基础流水线完成: run_id=%s outputs=%s", run_id, outputs)
                output({"成功": True, "run_id": run_id, "交付": "未执行", **outputs})
                return 0
            except Exception as exc:
                runtime.update_run(
                    run_id, "failed", "failed", error=f"{type(exc).__name__}: {exc}"
                )
                logger.exception("基础流水线失败: run_id=%s", run_id)
                return 2
    except PipelineAlreadyRunning as exc:
        logger.warning("跳过重复运行: %s", exc)
        output({"成功": False, "原因": str(exc)})
        return 3


def delivery_test() -> int:
    _, scan = run_full()
    outputs = save_pipeline_outputs(scan)
    output(outputs)
    return 0


def deliver_codex_report() -> int:
    day = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    result_path, _, final_path = report_paths(day)
    scan_path = settings.reports_dir / f"{day}_scan_summary.json"
    if not result_path.exists() or not scan_path.exists() or not final_path.exists():
        output({"成功": False, "原因": "当天结构化结果、扫描统计或最终报告不存在"})
        return 2
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    report = final_path.read_text(encoding="utf-8")
    ai_markdown, ai_status = generate_ai_value_analysis(settings.project_root, day, scan)
    report = append_ai_analysis(report, ai_markdown)
    final_path.write_text(report, encoding="utf-8")
    (settings.reports_dir / f"{day}_ai_value_analysis.json").write_text(
        json.dumps(ai_status, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    runtime = RuntimeState(settings.project_root / "data", settings.timezone)
    content_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
    lark_key = f"{day}:lark:final"
    email_key = f"{day}:email:final"
    actions: list[str] = []
    record_ids: list[str] = []
    delivered_items = delivery_items(scan)
    lark: LarkBitableClient | None = None
    lark_status = "已完成，未重复写入"
    if not runtime.delivery_completed(lark_key, content_hash) and runtime.reserve_delivery(
        lark_key, day, "lark", content_hash
    ):
        try:
            lark = LarkBitableClient(settings.lark_cli, settings.lark_config_path)
            lark.ensure_fields()
            for item in delivered_items:
                stock_code = str(item.get("代码") or "无")
                action, record_id = lark.upsert_daily_stock(
                    day,
                    stock_code,
                    lark_fields(day, scan, report, item=item),
                )
                if not record_id:
                    raise RuntimeError(f"飞书未返回记录ID: {stock_code}")
                actions.append(f"{stock_code}:{action}")
                record_ids.append(record_id)
            runtime.mark_delivery(
                lark_key,
                day,
                "lark",
                content_hash,
                "completed",
                json.dumps(record_ids, ensure_ascii=False),
            )
            lark_status = "；".join(actions)
        except Exception as exc:
            runtime.mark_delivery(
                lark_key,
                day,
                "lark",
                content_hash,
                "failed",
                f"{type(exc).__name__}: {exc}",
            )
            lark_status = f"失败: {type(exc).__name__}: {exc}"
    subject_type = "每日分析报告" if scan["最终推荐数量"] else "观察报告"
    if runtime.delivery_completed(email_key, content_hash):
        email_ok, email_status = True, "已发送，未重复发送"
    elif runtime.reserve_delivery(email_key, day, "email", content_hash):
        email_body = build_delivery_email(day, scan, report, actions or [lark_status])
        (settings.reports_dir / f"{day}_email.md").write_text(
            email_body, encoding="utf-8"
        )
        email_ok, email_status = send_email(
            settings,
            f"A股全市场 Buffett-Munger 十年价值策略{subject_type} - {day}",
            email_body,
        )
        runtime.mark_delivery(
            email_key,
            day,
            "email",
            content_hash,
            "completed" if email_ok else "failed",
            email_status,
        )
    else:
        email_ok, email_status = False, "同日最终邮件正在发送或已被其他进程占用"
    if email_ok and runtime.delivery_completed(lark_key, content_hash):
        try:
            if lark is None:
                lark = LarkBitableClient(
                    settings.lark_cli, settings.lark_config_path
                )
            for item in delivered_items:
                stock_code = str(item.get("代码") or "无")
                lark.upsert_daily_stock(
                    day,
                    stock_code,
                    lark_fields(
                        day,
                        scan,
                        report,
                        item=item,
                        email_status=email_status,
                    ),
                )
            lark_status = f"{lark_status}；邮件状态已回写"
        except Exception as exc:
            lark_status = (
                f"{lark_status}；邮件已发送，但状态回写失败: "
                f"{type(exc).__name__}: {exc}"
            )
    result = {
        "成功": bool(email_ok and runtime.delivery_completed(lark_key, content_hash)),
        "飞书动作": actions or ["已完成，跳过"],
        "飞书记录ID": record_ids,
        "飞书状态": lark_status,
        "邮件状态": email_status,
        "报告路径": str(final_path),
        "内容哈希": content_hash,
        "交付状态": runtime.delivery_status(day),
    }
    (settings.reports_dir / f"{day}_delivery_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    output(result)
    return 0 if result["成功"] else 2


def main() -> int:
    settings.ensure_directories()
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-check", action="store_true")
    parser.add_argument("--test-valuation-sources", action="store_true")
    parser.add_argument("--build-valuation-cache", action="store_true")
    parser.add_argument("--test-financial-sources", action="store_true")
    parser.add_argument("--build-financial-cache", action="store_true")
    parser.add_argument("--scan-light", action="store_true")
    parser.add_argument("--scan-candidates", action="store_true")
    parser.add_argument("--analyze-top10", action="store_true")
    parser.add_argument("--scan-dry-run", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--codex-ai", action="store_true")
    parser.add_argument("--force-test", action="store_true")
    parser.add_argument("--strategy-validation", action="store_true")
    parser.add_argument("--deliver-codex-report", action="store_true")
    parser.add_argument("--data-freshness-check", action="store_true")
    parser.add_argument("--compare-previous-day", action="store_true")
    parser.add_argument("--strategy-health-check", action="store_true")
    parser.add_argument("--run-status", action="store_true")
    parser.add_argument("--validate-delivery", action="store_true")
    parser.add_argument("--server-readiness-check", action="store_true")
    parser.add_argument("--run-pipeline", action="store_true")
    parser.add_argument("--no-delivery", action="store_true")
    parser.add_argument("--deliver-final-report", action="store_true")
    parser.add_argument("--run-low-price-bull", action="store_true")
    parser.add_argument("--apply-schedule", action="store_true")
    parser.add_argument("--schedule-status", action="store_true")
    parser.add_argument("--config-web", action="store_true")
    parser.add_argument("--config-host", default="127.0.0.1")
    parser.add_argument("--config-port", type=int, default=8765)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    manager = DataSourceManager(settings.project_root)

    if args.apply_schedule:
        strategy = load_strategy(settings.project_root)
        result = configure_native_schedule(
            settings.project_root, strategy["run_time"]
        )
        output(result)
        return 0
    if args.schedule_status:
        output(native_schedule_status())
        return 0
    if args.config_web:
        from src.config_server import serve_config

        serve_config(
            settings.project_root,
            host=args.config_host,
            port=args.config_port,
        )
        return 0
    if args.health_check:
        result = health_check(settings); output(result); return 0 if result["健康"] else 2
    if args.run_low_price_bull:
        result = run_low_price_bull_daily(settings.project_root)
        output(result)
        return 0 if result.get("success") else 2
    if args.data_freshness_check:
        result = freshness_report(settings.project_root, settings.timezone)
        output(result)
        return 0 if result["healthy"] else 2
    if args.compare_previous_day:
        result = compare_previous_day(settings.reports_dir)
        output(result)
        return 0
    if args.strategy_health_check:
        result = compare_previous_day(settings.reports_dir)
        output(result)
        return 2 if result["strategy_health_warning"] else 0
    if args.run_status:
        runtime = RuntimeState(settings.project_root / "data", settings.timezone)
        output(
            {
                "最近运行": runtime.latest_run(),
                "最近成功运行": runtime.latest_success(),
                "今日交付": runtime.delivery_status(
                    datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
                ),
            }
        )
        return 0
    if args.validate_delivery:
        runtime = RuntimeState(settings.project_root / "data", settings.timezone)
        day = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
        status = runtime.delivery_status(day)
        _, _, final_path = report_paths(day)
        current_hash = (
            hashlib.sha256(final_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if final_path.exists()
            else ""
        )
        output({"日期": day, "交付": status, "当前报告哈希": current_hash})
        return 0 if all(
            any(
                item["channel"] == channel
                and item["status"] == "completed"
                and item.get("content_hash", "") == current_hash
                for item in status
            )
            for channel in ("lark", "email")
        ) else 2
    if args.server_readiness_check:
        runtime = RuntimeState(settings.project_root / "data", settings.timezone)
        fresh = freshness_report(settings.project_root, settings.timezone)
        result = {
            "运行数据库": str(runtime.db_path),
            "锁文件": str(runtime.lock_path),
            "锁空闲": not runtime.lock_path.exists(),
            "数据新鲜度": fresh,
            "健康检查": health_check(settings),
        }
        output(result)
        return 0 if result["锁空闲"] else 2
    if args.test_valuation_sources:
        frame, meta = manager.build_valuation(force=True)
        covered = int((frame[["PE TTM", "PB", "PS", "总市值", "流通市值"]].notna().sum(axis=1) >= 4).sum())
        result = {"可用": not frame.empty, "覆盖数量": covered, "估值覆盖率": valuation_coverage(frame), **meta}
        output(result); return 0 if result["覆盖数量"] >= 2000 else 2
    if args.build_valuation_cache:
        frame, meta = manager.build_valuation(force=True)
        output({"缓存": str(manager.cache.path("valuation_latest.csv")), "行数": len(frame), **meta})
        return 0
    if args.test_financial_sources:
        candidates, _ = scan_candidates(settings.project_root)
        codes = candidates["代码"].head(args.limit or 20).tolist()
        frame, meta = manager.build_financial(codes, force=True)
        cov = row_coverage(frame, FINANCIAL_FIELDS)
        cash_cov = row_coverage(frame, ["经营性现金流净额"])
        output({"样本数": len(codes), "财报覆盖率": cov, "现金流覆盖率": cash_cov, **meta})
        return 0 if cov >= 70 and cash_cov >= 70 else 2
    if args.build_financial_cache:
        candidates, _ = scan_candidates(settings.project_root)
        codes = candidates["代码"].head(args.limit or 100).tolist()
        frame, meta = manager.build_financial(codes, force=True)
        output({"缓存": str(manager.cache.path("financial_metrics_latest.csv")), "行数": len(frame), "财报覆盖率": row_coverage(frame, FINANCIAL_FIELDS), **meta})
        return 0
    if args.scan_light:
        frame, meta = scan_light(settings.project_root); output({"数量": len(frame), "数据源": meta}); return 0
    if args.scan_candidates:
        frame, meta = scan_candidates(settings.project_root); output({"数量": len(frame), "数据源": meta}); return 0
    if args.analyze_top10:
        frame, meta = analyze_top10(settings.project_root); output({"数量": len(frame), "候选": frame.fillna("数据不足").to_dict("records")}); return 0
    if args.strategy_validation:
        result = run_strategy_validation(settings.project_root, settings.reports_dir)
        output(result)
        return 0 if result["验收结论"]["是否可以继续正式每日运行"] else 2
    if args.deliver_codex_report or args.deliver_final_report:
        return deliver_codex_report()
    if args.scan_dry_run:
        return run_full(None if args.full else args.limit or 200)[0]
    if args.full:
        return run_full(args.limit)[0]
    if args.run_once and args.force_test:
        return delivery_test()
    if args.run_once or args.run_pipeline:
        return run_once(codex_mode=args.codex_ai)
    parser.error("未指定有效命令")


if __name__ == "__main__":
    sys.exit(main())
