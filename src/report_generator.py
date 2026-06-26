from __future__ import annotations

import json
from pathlib import Path


NA = "数据不足"


def show(value, suffix=""):
    if value is None or value == "":
        return NA
    return f"{value:.2f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def build_report(c: dict) -> str:
    item, v = c["selected"], c["selected"].get("values", {})
    risks = item.get("risks") or [
        "公开数据接口可能延迟或缺失", "盘中价格波动导致估值变化",
        "宏观经济与行业景气度变化", "财务报表质量及会计估计风险",
        "政策、监管及公司治理风险",
    ]
    risk_text = "\n".join(f"{i}. {x}" for i, x in enumerate(risks[:8], 1))
    return f"""# A股全市场低估股票每日分析报告

## 【1. 今日执行状态】
执行日期：{c['date']}
是否 A 股交易日：是
执行时间：{c['time']}
数据截止时间：{c['data_time']}
数据性质：{'测试模式，非真实投资分析' if c['test_mode'] else '前一交易日收盘数据'}
股票池范围：境内全部上市 A 股
排除范围：ST、退市、非股票证券
数据来源：{c['data_source']}
飞书多维表格链接：{c['lark_url']}

## 【2. 今日筛选结论】
最终结论：{c['conclusion']}
股票名称：{item.get('name', '无')}
股票代码：{item.get('code', '无')}
上市交易所：{item.get('exchange', NA)}
上市板块：{item.get('board', NA)}
所属行业：{item.get('industry', NA)}
当前价格：{show(v.get('当前价格'))}
涨跌幅：{show(v.get('涨跌幅'), '%')}
当前市值：{show(v.get('当前市值'))}
综合评分：{show(v.get('综合评分'))}
推荐等级：{v.get('推荐等级', '不推荐')}
一句话核心逻辑：{c['core_logic']}

## 【3. 估值分析】
当前 PE TTM：{show(v.get('PE TTM'))}
近 5 年 PE 分位数：{show(v.get('近5年PE分位数'))}
当前 PB：{show(v.get('PB'))}
近 5 年 PB 分位数：{show(v.get('近5年PB分位数'))}
当前 PS：{show(v.get('PS'))}
股息率：{show(v.get('股息率'))}
自由现金流收益率：{show(v.get('自由现金流收益率'))}
行业平均估值：{NA}
同行公司估值对比：{NA}
保守合理市值：{show(v.get('保守合理市值'))}
中性合理市值：{show(v.get('中性合理市值'))}
乐观合理市值：{show(v.get('乐观合理市值'))}
当前市值折价空间：{show(v.get('安全边际'), '%')}
安全边际：{show(v.get('安全边际'), '%')}
估值结论：不足三种独立估值方法或不足 25% 安全边际时不推荐。

## 【4. 财报质量分析】
最近 3 年营业收入趋势：{NA}
最近 3 年归母净利润趋势：{NA}
最近 3 年扣非净利润趋势：{NA}
毛利率趋势：{show(v.get('毛利率'))}
净利率趋势：{show(v.get('净利率'))}
ROE 趋势：{show(v.get('ROE'))}
ROIC 趋势：{show(v.get('ROIC'))}
期间费用率变化：{NA}
非经常性损益影响：{NA}
财报质量判断：关键数据不足时执行一票否决，不强行推荐。

## 【5. 现金流分析】
最近 3 年经营性现金流净额：{show(v.get('经营现金流净额'))}
经营现金流 / 净利润：{show(v.get('经营现金流/净利润'))}
自由现金流：{show(v.get('自由现金流'))}
资本开支：{show(v.get('资本开支'))}
应收账款变化：{show(v.get('应收账款'))}
存货变化：{show(v.get('存货'))}
合同负债变化：{show(v.get('合同负债'))}
现金流是否支撑利润：{NA}
现金流结论：缺少可核验数据时不作肯定判断。

## 【6. 资产负债分析】
资产负债率：{show(v.get('资产负债率'))}
有息负债：{show(v.get('有息负债'))}
货币资金：{show(v.get('货币资金'))}
短期债务压力：{NA}
商誉风险：{show(v.get('商誉'))}
应收账款风险：{show(v.get('应收账款'))}
存货跌价风险：{show(v.get('存货'))}
偿债能力判断：{NA}
资产负债结论：数据不足时不推荐。

## 【7. 盈利能力分析】
ROE：{show(v.get('ROE'))}
扣非 ROE：{show(v.get('扣非ROE'))}
ROIC：{show(v.get('ROIC'))}
毛利率：{show(v.get('毛利率'))}
净利率：{show(v.get('净利率'))}
杜邦分析：{NA}
盈利能力是否可持续：{NA}
盈利能力结论：需由连续财报验证。

## 【8. 成长性分析】
行业空间：{NA}
行业景气度：{NA}
公司竞争优势：{NA}
未来 3—5 年增长逻辑：{NA}
成长性等级：{v.get('成长性等级', NA)}
成长是否已被财报验证：{NA}
成长性结论：未获得充分数据，不作乐观推断。

## 【9. 分红与股东回报】
近 3 年分红情况：{NA}
股息率：{show(v.get('股息率'))}
分红率：{show(v.get('分红率'))}
分红是否可持续：{NA}
是否有回购：{NA}
股东回报评价：数据不足。

## 【10. 风险提示】
{risk_text}

## 【11. 操作建议】
{c['advice']}

仓位原则：单只股票最高不超过总资金的 10%；首次试探仓不超过总资金的 3%—5%；下一期财报不符合预期应退出观察；估值修复到合理区间应重新评估；不得因短期上涨追高。

## 【12. 下一交易日跟踪重点】
1. 更新盘中估值与安全边际
2. 跟踪最新公告、监管问询和重大事项
3. 核验经营现金流与净利润匹配度
4. 跟踪行业景气度及同行估值变化

> 本报告基于公开数据自动整理，不构成投资建议，不承诺收益。
"""


def build_email(c: dict, report: str, lark_status: str, email_status: str) -> str:
    item = c["selected"]
    return f"""A股全市场低估股票每日分析报告

执行日期：{c['date']}
执行时间：{c['time']}
是否 A 股交易日：是
最终结论：{c['conclusion']}
股票名称：{item.get('name', '无')}
股票代码：{item.get('code', '无')}
未推荐原因：{c.get('no_pick_reason', '不适用')}
后续观察方向：核验财报质量、现金流、安全边际和行业景气度
飞书多维表格链接：{c['lark_url']}
当天写入飞书表格的记录摘要：{c['summary']}
飞书写入状态：{lark_status}
邮件发送状态：{email_status}
本地报告路径：{c['report_path']}
数据来源：{c['data_source']}
数据时间：{c['data_time']}

完整分析报告：

{report}
"""


def save_outputs(c: dict, report: str, email_body: str) -> None:
    reports_dir: Path = c["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    day = c["date"]
    (reports_dir / f"{day}_report.md").write_text(report, encoding="utf-8")
    (reports_dir / f"{day}_email.md").write_text(email_body, encoding="utf-8")
    result = dict(c)
    result["reports_dir"] = str(result["reports_dir"])
    (reports_dir / f"{day}_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
