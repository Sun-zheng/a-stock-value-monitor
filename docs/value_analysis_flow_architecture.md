# 价值分析推荐流程架构

## 目标

每天工作日自动完成 A 股价值扫描，保存全量数据，对正式推荐和观察股票生成智能体复核分析，并通过邮件和飞书交付。

## 主流程

1. 定时触发
   - `stock-daily-analysis.timer`：14:10 运行价值扫描。
   - `stock-final-delivery.timer`：14:40 执行最终交付兜底。
   - `stock-low-price-bull.timer`：14:00 运行低价擒牛筛选并发送邮件。

2. 数据采集
   - 行情与估值：东方财富 / AkShare。
   - 财务指标：Tushare。
   - 交易日判断：A 股交易日历缓存。

3. 价值筛选
   - 构建全市场估值基准。
   - 轻筛候选：低估值、质量、高股息、行业内低估。
   - 深度检查：ROE、扣非ROE、ROIC、现金流、负债率、完整年度口径。
   - 九维评分：生意质量、资本配置、盈利韧性、财务安全、现金流、成长跑道、估值、股东回报、芒格反向清单。
   - 输出正式推荐和观察池。

4. 数据保存
   - CSV 审计文件：`data/daily_stock_history/<dataset>/<date>.csv`
   - SQLite 索引：`data/daily_stock_history/stock_history_index.sqlite3`
   - Parquet 列式文件：`data/daily_stock_history/parquet/<dataset>/<date>.parquet`
   - 报告文件：`reports/<date>_report.md`

5. AI 模型启用
   - 交付前执行真实 API 测试。
   - 仅启用本次测试通过的模型。
   - 未通过或未配置的 provider 不参与分析。
   - `AI_MODEL_POOL` 作为限流、超时、配额失败时的轮询池。

6. 股票分析智能体
   - 输入：正式推荐股票 + 观察股票。
   - 约束：只使用结构化数据，不编造缺失数据。
   - 输出结构：核心结论、价值质量、估值与安全边际、现金流与财务安全、主要风险、后续跟踪、结论。
   - 观察股票必须说明未达正式推荐原因和后续触发条件。

7. 交付
   - 最终报告追加智能体复核章节。
   - 飞书多维表格逐只股票 upsert。
   - 邮件发送完整报告。
   - 发送状态写回运行状态库。

## 密钥与安全

- 密钥不写入源码和测试。
- AI 密钥保存在 `/home/sum/.config/a-stock-value-monitor/aiagents.env`。
- systemd 通过 `AIAGENTS_ENV_FILE` 指向安全 env 文件。
- 验证工具只输出状态、延迟和错误摘要，不输出密钥。

## 性能策略

- 每日全量结果用 SQLite 和 Parquet 建索引，页面查询优先走 SQLite。
- CSV 保留为审计文件，不作为高频查询主路径。
- AI 分析只对正式推荐和观察池运行，避免对全市场股票调用模型。
- 模型调用先实测再启用，失败模型不进入交付链路。

## 上游融合原则

上游 `oficcejo/aiagents-stock` 当前最新提交为 `9656ab7 2026-06-18 修复bug`。上游新增宏观周期、新闻流量、低估值量化等能力，但仍是平铺式目录。本项目已经重构为分层架构，因此后续按模块迁移：

1. 新闻流量迁移到 `backend/strategies/news_flow/`。
2. 宏观周期迁移到 `backend/strategies/macro_cycle/`。
3. 低估值量化只抽取风控和观察池逻辑，不直接覆盖价值策略。
