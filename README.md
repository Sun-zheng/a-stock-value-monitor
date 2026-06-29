# A Stock Value Monitor

面向 A 股的每日价值筛选、AI 多分析师复核和自动交付系统。项目由两部分组成：

- 根目录流水线：全市场数据获取、价值筛选、策略验收、报告生成、飞书/邮件交付。
- `aiagents-stock-main/`：Streamlit 股票智能分析系统，提供单股/批量分析、多智能体分析、策略页面和配置界面。

本仓库只应提交源码、测试、配置样例和文档。真实密钥、本地运行数据、SQLite 数据库、日志、报告、邮件内容和个人配置不应提交。

## 核心能力

- A 股全市场扫描，默认范围包含主板、创业板、科创板和北交所。
- Buffett-Munger 九维价值评分和正式推荐/观察池输出。
- 每日最多 1 只正式推荐、最多 5 只观察股票。
- 交付前调用 `aiagents-stock-main` 的网页统一股票分析流程，对正式推荐和观察股票执行技术、基本面、资金面、风险、市场情绪、新闻六类分析师复核。
- 生成本地 Markdown/JSON 报告，并可通过飞书多维表格和 SMTP 邮件交付。
- 提供 Streamlit 管理端查看运行状态、历史数据、每日价值策略和指数基金回撤研究。
- 指数基金研究支持 ETF 流动性过滤、历史高点回撤筛选、行业/类型分散推荐、多分析师规则复核、最低点/回涨确认点/修复周期估算，并可发送邮件报告。

## 项目结构

```text
.
├── main.py                         # 根流水线 CLI 入口
├── config/                         # 根流水线配置
├── src/                            # 筛选、估值、交付、调度、历史状态模块
├── tests/                          # 根流水线测试
├── tools/                          # 辅助工具
├── web/                            # 简单静态页
├── docs/                           # 架构、审计和使用文档
└── aiagents-stock-main/            # Streamlit 多智能体股票分析系统
```

运行时会产生 `data/`、`reports/`、`logs/`、`secrets/`、`*.db` 等本地文件，这些已在 `.gitignore` 中排除。

## 快速开始

建议使用 Python 3.12。

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，至少配置：

```bash
TUSHARE_TOKEN=
EMAIL_TO=
EMAIL_FROM=
EMAIL_SMTP_HOST=
EMAIL_USERNAME=
EMAIL_PASSWORD=
```

AI 多智能体分析使用 `aiagents-stock-main` 的环境变量。可以单独维护本地文件，例如：

```bash
AIAGENTS_ENV_FILE=~/.config/a-stock-value-monitor/aiagents.env
```

该文件不要提交到 Git。

定时任务建议使用 ModelScope 等免费或低成本模型池，避免把付费 DeepSeek 官方 API 放进自动调度。示例配置：

```bash
MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1
MODELSCOPE_API_KEY=
VALUE_ANALYSIS_MODELS=stepfun-ai/Step-3.7-Flash,moonshotai/Kimi-K2.7-Code:Moonshot
VALUE_ANALYSIS_ALLOW_DEEPSEEK=0
```

## 常用命令

```bash
# 运行测试
pytest -q

# 检查数据新鲜度和策略健康
python main.py --data-freshness-check
python main.py --strategy-validation

# 运行基础流水线，不发送邮件/飞书
python main.py --run-pipeline

# 基于当天结果执行最终交付
python main.py --deliver-final-report

# 查看运行状态
python main.py --run-status
python main.py --validate-delivery
```

启动 Streamlit 多智能体分析界面：

```bash
cd aiagents-stock-main
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python run.py
```

默认访问 `http://localhost:8503`。

网页中可进入“指数基金研究”，按推荐数量、目标回撤、最低回撤、候选数、最低成交额和历史起始日运行研究；默认优先分散行业/类型，勾选“完成后发送邮件”后，会使用根目录 `.env` 中的 SMTP 配置发送总分总报告。

## 每日分析流程

1. 读取全市场股票池和前一交易日完整收盘数据。
2. 通过低估、质量、股息、行业相对低估等轻筛逻辑构建候选池。
3. 补齐候选的财务、现金流和估值数据。
4. 执行一票否决：关键财务缺失、扣非净利润非正、经营现金流非正、ROE 非正、资产负债率过高等。
5. 计算同行相对估值、盈利绝对估值和现金流绝对估值，并用保守合理市值计算安全边际。
6. 执行 Buffett-Munger 九维评分，生成正式推荐和观察股票。
7. 交付前调用 `aiagents-stock-main/frontend/app.py::analyze_single_stock_for_batch()`，让多分析师团队输出复核、团队讨论和最终决策。
8. 写入本地结果，并按配置交付到飞书和邮箱。

## 安全与隐私

- 不要提交 `.env`、`secrets/`、`data/`、`reports/`、`logs/`、SQLite 数据库、API Key、邮箱授权码、飞书配置或个人交易数据。
- `.env.example` 只保留空值或示例占位符。
- `aiagents-stock-main` 的测试万能密码默认关闭，只有本地测试需要时才通过环境变量显式开启。
- 提交前建议运行：

```bash
git status --short
git check-ignore -v .env secrets/aiagents.env data/runtime_state.sqlite3 reports/2026-06-26_email.md
rg -n "sk-|API_KEY=|PASSWORD=|TOKEN=|SECRET=" -g '!**/.venv/**' -g '!data/**' -g '!reports/**' -g '!logs/**' -g '!secrets/**'
```

更多说明见 [SECURITY.md](SECURITY.md) 和 [docs/OPEN_SOURCE_AUDIT.md](docs/OPEN_SOURCE_AUDIT.md)。

## 性能优化方向

当前性能瓶颈主要在外部行情/财务 API、候选财务补齐、AI 多模型调用和报告交付。建议优先查看 [docs/PERFORMANCE_AUDIT.md](docs/PERFORMANCE_AUDIT.md)。

## 免责声明

本项目输出仅用于投资研究和软件实验，不构成投资建议。股票市场有风险，任何自动化分析结果都需要人工复核。
