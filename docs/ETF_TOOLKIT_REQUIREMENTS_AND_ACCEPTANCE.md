# ETF策略工具箱需求、设计与验收说明

更新时间：2026-06-30

## 目标用户与使用场景

目标用户是希望用网页工具筛选、跟踪和定期复盘场内ETF的个人投资者或研究者。核心诉求不是给出确定收益承诺，而是把真实行情、历史表现、溢价折价、持仓暴露和风险标签串成可复核的观察流程。

主要场景：

- 每日或每周查看全市场ETF筛选结果，发现强势、深回撤、放量和长期定投候选。
- 对同类ETF做横向比较，优先排除高溢价、流动性弱、规模偏小或重复暴露过高的标的。
- 对计划长期跟踪的ETF生成分层定投方案，明确加仓、暂停和停止条件。
- 将ETF日报/周报内容复用到邮件和飞书推送。

## 外部调研结论

- 定投适合降低择时压力，但不保证收益，仍需要风险预算、停止条件和复盘机制。参考：Vanguard dollar-cost averaging、Fidelity dollar-cost averaging、Schwab dollar-cost averaging。
- ETF二级市场价格可能偏离NAV/IOPV，溢价买入会降低后续收益弹性，折价也可能反映流动性或底层资产交易问题。参考：Fidelity ETF premium/discount、Vanguard ETF premiums and discounts、BlackRock iShares ETF premium/discount。
- 持仓重叠会让多个ETF实际暴露到同一批股票，组合配置需要看穿前十大持仓和重复暴露。参考：ETF Research Center overlap、InvestmentNews ETF overlap、Mezzi ETF overlap analyzer。
- ETF风险不只来自净值波动，还包括流动性、跟踪误差、溢价折价、集中行业、规模和成立时间。参考：FINRA ETF说明、Investopedia ETF risks。
- ETF对比工具需要覆盖收益、回撤、波动、成交额、规模、费用和跟踪指数。参考：ETF.com ETF comparison。

## 已实现功能

1. ETF全市场筛选器
   - 数据源：`ak.fund_etf_spot_em` + ETF历史行情。
   - 指标：分类、最新价、收益、回撤、波动、成交额、趋势评分、动量评分、筛选评分、风险标签。

2. ETF轮动策略
   - 按ETF分类聚合动量、趋势、风险和成交额。
   - 输出强势领先、改善中、震荡观察、滞后等阶段。

3. ETF组合配置器
   - 稳健、平衡、进取三类核心-卫星权重。
   - 单只ETF权重上限与风险评分门槛随风险偏好变化。

4. ETF定投计划生成器
   - 按回撤分层：
     - 回撤20%：开始小额定投。
     - 回撤35%：提高定投。
     - 回撤50%：重点观察/分批。
   - 输出每月金额、加仓条件、停止条件和复核频率。

5. ETF溢价/折价监控
   - 数据源：实时IOPV、基金折价率、ETF日频净值表。
   - 输出高溢价、明显折价、接近净值、轻微偏离。

6. ETF持仓穿透分析
   - 数据源：`ak.fund_portfolio_hold_em`。
   - 输出每只ETF前十大持仓、集中度和跨ETF重复暴露股票。

7. ETF风险雷达
   - 标签：流动性差、波动过高、规模太小、成立时间太短、高溢价、明显折价、单一行业风险、跟踪误差数据待补充。
   - 输出高/中/低风险等级。

8. ETF对比工具
   - 指标：收益、回撤、波动、成交额、总市值、手续费、跟踪指数、跟踪方式。
   - 基金档案匹配不到场内ETF时，只用名称推断跟踪指数候选，并标记`指数来源=名称推断`；费率不造数。

9. ETF定时日报/周报
   - 汇总大盘/行业表现、强势方向、深回撤ETF、放量ETF和观察池变化。
   - 当前作为工具箱结果和报告段落输出，可复用现有邮件/飞书发送流程。

10. ETF机会池
   - 池子：低估回撤池、趋势突破池、放量异动池、长期定投池。
   - 当前运行内生成首次进入日期、连续观察天数和排名变化；后续定时任务持久化后可滚动维护。

## 数据真实性与边界

- 所有筛选、历史行情、溢价折价和持仓穿透均来自真实接口。
- 无法获取的字段保持空值或明确标注来源，不使用假数据补齐。
- 输出是研究和观察工具，不构成投资建议，不承诺半年上涨50%或任何确定收益。
- ETF快照和历史行情入口会做数据清洗：缺核心列返回空结果，价格/成交额/市值/IOPV/折价率统一转数值，非正价格和无效代码过滤，单只ETF历史数据异常时跳过该ETF并记录错误，不中断全局分析。

## 缓存与历史记录

- 配置文件：`data/etf_toolkit_settings.json`。
- 结果缓存：`data/etf_toolkit/cache/`。
- 历史记录：`data/etf_toolkit/history/`，索引文件为 `data/etf_toolkit/history/index.json`。
- 网页入口：`ETF板块 -> ETF历史记录`，可查看 ETF策略工具箱、指数基金研究、大盘ETF指数分析、单只ETF分析的运行历史。
- 单只ETF入口：`ETF板块 -> 单只ETF分析`，可按 ETF 主题筛选后选择具体 ETF，并选择基础筛选、定投计划、溢价折价、风险雷达、持仓穿透、ETF对比等分析模块。
- 默认缓存策略为`同日复用`：同一天、同一分析参数再次运行时优先读取缓存；跨日期自动重新抓取真实数据。
- 可在网页切换为`按分钟TTL`或`不复用缓存`。盘中需要更高频刷新时使用TTL或关闭缓存；收盘后日报/周报适合使用同日复用。
- 每次成功运行都会写入历史记录，用于回看、定时任务审计，以及后续机会池连续观察天数和排名变化的持久化计算。

## 开发实现位置

- 后端分析器：`aiagents-stock-main/backend/strategies/index_fund_research/etf_toolkit_analyzer.py`
- 网页入口：`aiagents-stock-main/frontend/strategies/etf_toolkit_ui.py`
- ETF板块路由：`aiagents-stock-main/frontend/app.py`
- 测试：`aiagents-stock-main/tests/test_index_fund_research.py`

## 测试与验收记录

单元测试：

```bash
cd aiagents-stock-main
.venv/bin/python -m py_compile backend/strategies/index_fund_research/etf_toolkit_analyzer.py frontend/strategies/etf_toolkit_ui.py frontend/app.py
.venv/bin/python -m pytest tests/test_daily_value_ui.py tests/test_low_price_bull_daily_tool.py tests/test_index_fund_research.py -q
```

结果：11项通过。

真实数据端到端测试：

```bash
cd aiagents-stock-main
.venv/bin/python - <<'PY'
from backend.strategies.index_fund_research.etf_toolkit_analyzer import ETFToolkitAnalyzer, ETFToolkitConfig
result = ETFToolkitAnalyzer().analyze_toolkit(
    ETFToolkitConfig(max_history=20, min_turnover=30_000_000, monthly_budget=5000, holding_top_n=3, start_date="20210101")
)
print(result["success"], result["market_snapshot_count"], result["analyzed_count"], result["error_count"])
PY
```

2026-06-30验收结果：

- 成功：`True`
- ETF快照：458只
- 完成历史分析：20只
- 历史错误：0
- 持仓穿透：3只ETF，重复暴露3项
- 报告长度：5532字符

## 部署与运维建议

- 网页端默认放在`ETF板块 -> ETF策略工具箱`。
- 定时任务通过根目录 `main.py --run-etf-toolkit-monitor` 执行，不依赖网页是否开启；网页只负责保存配置和应用系统后台定时。
- 全局后台定时配置在`每日价值策略控制台 -> 运行与调度 -> 全局后台定时配置`中维护，覆盖每日价值扫描、低价擒牛、最终交付兜底和ETF工具箱监控。
- 定时任务建议复用现有邮件/飞书发送方法，工作日收盘后生成日报，周末或周五生成周报。
- 机会池需要下一步接入持久化状态文件或数据库表，才能准确计算连续观察天数和排名变化。
- AkShare接口偶发慢或不可用时，应保留错误样例并继续输出已成功的ETF，不让单个接口拖垮整个日报。
