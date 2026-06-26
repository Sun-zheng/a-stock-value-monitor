# 统一股票分析系统升级方案

## 当前统一架构

- 根系统负责每日 A 股全市场价值扫描、数据落盘、报告生成、邮件与飞书交付。
- `aiagents-stock-main` 负责统一 Streamlit 控制台、单股多智能体分析、监控和策略页面。
- systemd user 服务统一管理：
  - `stock-site.service`：Web 控制台
  - `stock-daily-analysis.timer`：每日价值扫描
  - `stock-final-delivery.timer`：最终报告交付兜底

## 上游更新评估

上游仓库 `oficcejo/aiagents-stock` 最新浅克隆版本提交为 `9656ab7`，时间为 2026-06-18，说明为“修复bug”。

上游新增或本地未完全接入的能力包括：

- 宏观分析：`macro_analysis_*`
- 宏观周期：`macro_cycle_*`
- 新闻流量：`news_flow_*`
- 低估值量化交易：`value_stock_*`

这些模块仍是平铺式文件结构；本地系统已经重构为 `backend/`、`frontend/`、`interface/`、`database/` 分层目录。因此不建议直接 `git pull` 或整目录覆盖。推荐迁移方式是“按功能吸收”，每个模块进入对应分层目录并补测试。

## 已完成的升级

### AI 多供应商接入

新增 `interface/ai/provider_config.py`，保留原 `DeepSeekClient` 调用名，同时支持 OpenAI-compatible 多供应商：

- DeepSeek
- 阿里百炼
- 硅基流动
- NVIDIA NIM
- ModelScope

新增 `AI_MODEL_POOL`，用于模型轮询。调用时用户选择的模型优先，池中模型作为兜底；遇到限流、配额、超时、502/503/504 等错误时自动退避并切换。

### 密钥管理原则

- 密钥不写入源码。
- 密钥不写入测试。
- 密钥只从 `.env` 或服务环境变量读取。
- 验证工具只输出 provider/model 状态、延迟和错误摘要，不输出密钥。

验证命令：

```bash
cd aiagents-stock-main
.venv/bin/python tools/validate_ai_providers.py
```

### SQLite / Parquet 索引库

每日 CSV 继续保留为审计文件，同时新增：

- SQLite：`data/daily_stock_history/stock_history_index.sqlite3`
- Parquet：`data/daily_stock_history/parquet/<dataset>/<date>.parquet`

SQLite 用于控制台快速查询和智能体读取；Parquet 用于后续批量回测、跨日分析和列式扫描。

### 价值分析表格

每日价值策略页面默认显示核心价值字段：

- ROE、扣非ROE、ROIC
- 毛利率、净利率、资产负债率
- 经营性现金流净额、自由现金流、经营现金流/净利润
- ROE口径、ROE报告期
- 综合评分、安全边际、估值结论

页面保留所有原始列，可通过字段选择器打开。

## ROE 口径

根策略系统使用最近完整年度 ROE：

- `ROE` 来自 Tushare `roe`
- `扣非ROE` 来自 Tushare `roe_dt`
- 不使用季度年化 ROE

该约束已有测试覆盖，避免季度数据造成误判。

## 后续推荐迁移顺序

1. 新闻流量模块：迁移到 `backend/strategies/news_flow/` 和 `frontend/strategies/news_flow_ui.py`，用于短线热度和舆情辅助。
2. 宏观周期模块：迁移到 `backend/strategies/macro_cycle/`，作为每日价值策略的宏观风险过滤器。
3. 上游低估值量化交易模块：不直接作为买卖策略使用，只抽取 RSI/持仓周期作为观察池风险提示。
4. 将每日价值扫描结果暴露成统一数据服务，供所有智能体读取 SQLite/Parquet，而不是各模块重复拉数据。

## 测试状态

- 根系统：47 个测试通过
- AI 子系统新增测试：7 个测试通过
