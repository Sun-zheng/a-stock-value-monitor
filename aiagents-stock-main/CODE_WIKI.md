# 基于LLM的股票智能分析系统 - Code Wiki

## 目录

1. [项目概述](#项目概述)
2. [技术架构](#技术架构)
3. [目录结构](#目录结构)
4. [核心模块详解](#核心模块详解)
5. [数据库设计](#数据库设计)
6. [API接口](#api接口)
7. [配置说明](#配置说明)
8. [部署指南](#部署指南)
9. [开发规范](#开发规范)
10. [常见问题](#常见问题)

---

## 项目概述

### 项目简介

这是一个基于大语言模型(LLM)的股票智能分析系统，采用多智能体协作方式，从技术面、基本面、资金面、情绪面等多个维度对股票进行深度分析，并提供投资建议。

### 核心功能

- **多智能体分析**：技术分析师、基本面分析师、资金面分析师、风险管理师、情绪分析师、新闻分析师
- **策略选股**：主力选股、低价擒牛、小市值策略、净利增长等
- **策略分析**：智策板块、智瞰龙虎榜
- **投管理**：持仓分析、AI盯盘、实时监控
- **通知系统**：Webhook、邮件通知
- **量化交易**：MiniQMT集成

### 技术栈

- **前端框架**：Streamlit
- **后端语言**：Python 3.8+
- **AI模型**：DeepSeek API (兼容OpenAI API格式)
- **数据库**：SQLite
- **数据源**：
  - yfinance (美股)
  - akshare (A股、港股)
  - Tushare (备选)
  - pywencai (问财)
- **图表库**：Plotly
- **技术指标**：TA-Lib
- **PDF生成**：ReportLab

---

## 技术架构

### 系统分层架构

```
┌─────────────────────────────────────────────────────┐
│                   前端展示层                         │
│              (Streamlit UI)                         │
├─────────────────────────────────────────────────────┤
│                   业务逻辑层                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  选股策略 │  │  分析引擎 │  │  监控系统 │        │
│  └──────────┘  └──────────┘  └──────────┘        │
├─────────────────────────────────────────────────────┤
│                   数据服务层                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 数据获取 │  │ 数据处理 │  │ 数据缓存 │        │
│  └──────────┘  └──────────┘  └──────────┘        │
├─────────────────────────────────────────────────────┤
│                   AI服务层                           │
│  ┌──────────────────────────────────────────┐    │
│  │  DeepSeek API客户端 + 多智能体系统       │    │
│  └──────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────┤
│                   数据持久层                         │
│              (SQLite数据库)                         │
└─────────────────────────────────────────────────────┘
```

### 多智能体架构

```
┌─────────────────────────────────────────────────────────┐
│                  股票分析多智能体系统                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ 技术分析师  │  │基本面分析师 │  │ 资金面分析师│   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │风险管理师   │  │情绪分析师   │  │新闻分析师   │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
│                            │                             │
│                  ┌─────────┴─────────┐                  │
│                  │  团队讨论 & 决策  │                  │
│                  └───────────────────┘                  │
│                            │                             │
│                  ┌─────────┴─────────┐                  │
│                  │  最终投资决策      │                  │
│                  └───────────────────┘                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 目录结构

```
aiagents-stock-main/
├── backend/                    # 后端核心模块
│   ├── ai/                    # AI智能体模块
│   │   ├── ai_agents.py      # 主智能体协调器
│   │   ├── longhubang_agents.py  # 龙虎榜分析智能体
│   │   └── sector_strategy_agents.py  # 板块策略智能体
│   ├── auth/                 # 认证模块
│   │   ├── authentication.py # 认证核心逻辑
│   │   ├── security.py       # 安全工具
│   │   └── user_manager.py   # 用户管理
│   ├── data/                 # 数据获取模块
│   │   ├── stock_data.py     # 股票数据获取
│   │   ├── data_source_manager.py  # 数据源管理
│   │   ├── fund_flow_akshare.py  # 资金流向数据
│   │   ├── market_sentiment_data.py  # 市场情绪数据
│   │   ├── quarterly_report_data.py  # 季报数据
│   │   ├── risk_data_fetcher.py  # 风险数据
│   │   └── qstock_news_data.py  # 新闻数据
│   ├── strategies/           # 策略模块
│   │   ├── longhubang/       # 龙虎榜策略
│   │   ├── low_price_bull/   # 低价擒牛策略
│   │   ├── main_force/       # 主力选股策略
│   │   ├── monitor/          # 监控策略
│   │   ├── portfolio/        # 持仓分析
│   │   ├── profit_growth/    # 净利增长策略
│   │   ├── sector_strategy/  # 板块策略
│   │   ├── small_cap/        # 小市值策略
│   │   └── smart_monitor/    # AI盯盘
│   └── utils/                # 工具模块
│       ├── pdf_generator.py  # PDF生成
│       ├── notification_service.py  # 通知服务
│       └── ...
├── config/                   # 配置模块
│   ├── config.py            # 主配置文件
│   └── model_config.py      # 模型配置
├── database/                # 数据库模块
│   ├── files/              # 数据库文件目录
│   └── managers/           # 数据库管理器
│       ├── database.py     # 主数据库管理
│       ├── user_auth_db.py # 用户认证数据库
│       ├── monitor_db.py   # 监控数据库
│       └── ...
├── docs/                   # 文档目录
│   ├── QUICK_START.md      # 快速开始
│   ├── README.md           # 文档索引
│   └── ...
├── frontend/               # 前端模块
│   ├── app.py             # 主应用入口
│   ├── auth/              # 认证UI
│   │   └── login_ui.py   # 登录界面
│   └── strategies/        # 策略UI
│       ├── main_force_ui.py
│       ├── longhubang_ui.py
│       └── ...
├── interface/             # 接口层
│   ├── ai/               # AI接口
│   │   └── deepseek_client.py
│   ├── config/           # 配置接口
│   ├── data/             # 数据接口
│   └── trading/          # 交易接口
├── run.py               # 启动脚本
├── requirements.txt     # 依赖列表
└── .gitignore
```

---

## 核心模块详解

### 1. AI智能体模块

#### 文件位置
`backend/ai/ai_agents.py`

#### 核心类：StockAnalysisAgents

```python
class StockAnalysisAgents:
    """股票分析AI智能体集合"""
    
    def __init__(self, model="deepseek-chat"):
        self.model = model
        self.deepseek_client = DeepSeekClient(model=model)
```

#### 主要方法

| 方法名 | 功能描述 | 参数 | 返回值 |
|--------|----------|------|--------|
| `technical_analyst_agent()` | 技术面分析 | stock_info, stock_data, indicators | 分析结果字典 |
| `fundamental_analyst_agent()` | 基本面分析 | stock_info, financial_data, quarterly_data | 分析结果字典 |
| `fund_flow_analyst_agent()` | 资金面分析 | stock_info, indicators, fund_flow_data | 分析结果字典 |
| `risk_management_agent()` | 风险管理分析 | stock_info, indicators, risk_data | 分析结果字典 |
| `market_sentiment_agent()` | 市场情绪分析 | stock_info, sentiment_data | 分析结果字典 |
| `news_analyst_agent()` | 新闻分析 | stock_info, news_data | 分析结果字典 |
| `run_multi_agent_analysis()` | 运行多智能体分析 | 股票信息及各类数据 | 各分析师结果字典 |
| `conduct_team_discussion()` | 团队讨论 | agents_results, stock_info | 讨论结果文本 |
| `make_final_decision()` | 最终决策 | discussion_result, stock_info, indicators | 决策结果字典 |

#### 使用示例

```python
from backend.ai.ai_agents import StockAnalysisAgents

# 初始化
agents = StockAnalysisAgents(model="deepseek-chat")

# 运行多智能体分析
results = agents.run_multi_agent_analysis(
    stock_info=stock_info,
    stock_data=stock_data,
    indicators=indicators,
    financial_data=financial_data,
    fund_flow_data=fund_flow_data,
    sentiment_data=sentiment_data,
    news_data=news_data,
    quarterly_data=quarterly_data,
    risk_data=risk_data,
    enabled_analysts={
        'technical': True,
        'fundamental': True,
        'fund_flow': True,
        'risk': True,
        'sentiment': False,
        'news': False
    }
)

# 团队讨论
discussion = agents.conduct_team_discussion(results, stock_info)

# 最终决策
decision = agents.make_final_decision(discussion, stock_info, indicators)
```

### 2. DeepSeek API客户端

#### 文件位置
`interface/ai/deepseek_client.py`

#### 核心类：DeepSeekClient

```python
class DeepSeekClient:
    """DeepSeek API客户端"""
    
    def __init__(self, model="deepseek-chat"):
        self.model = model
        self.client = openai.OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL
        )
        self.cache = {}  # 内存缓存
        self.cache_size = 100
```

#### 主要方法

| 方法名 | 功能描述 |
|--------|----------|
| `call_api()` | 调用DeepSeek API（带缓存） |
| `technical_analysis()` | 技术分析 |
| `fundamental_analysis()` | 基本面分析 |
| `fund_flow_analysis()` | 资金面分析 |
| `comprehensive_discussion()` | 综合讨论 |
| `final_decision()` | 最终决策 |

#### 缓存机制

- 使用MD5哈希生成缓存键
- 最大缓存100条记录
- 自动清理过期缓存

### 3. 股票数据获取模块

#### 文件位置
`backend/data/stock_data.py`

#### 核心类：StockDataFetcher

```python
class StockDataFetcher:
    """股票数据获取类"""
```

#### 支持的市场

| 市场 | 代码格式 | 数据源 |
|------|----------|--------|
| A股 | 6位数字 | akshare / tushare |
| 港股 | 1-5位数字或HK前缀 | akshare |
| 美股 | 字母代码 | yfinance |

#### 主要方法

| 方法名 | 功能描述 |
|--------|----------|
| `get_stock_info()` | 获取股票基本信息 |
| `get_stock_data()` | 获取历史行情数据 |
| `calculate_technical_indicators()` | 计算技术指标 |
| `get_latest_indicators()` | 获取最新技术指标值 |
| `get_financial_data()` | 获取财务数据 |
| `get_risk_data()` | 获取风险数据（限售解禁、减持等） |

#### 技术指标列表

- 移动平均线：MA5、MA10、MA20、MA60
- 相对强弱指标：RSI
- MACD指标：MACD、MACD信号、MACD柱状图
- 布林带：上轨、中轨、下轨
- KDJ指标：K值、D值
- 成交量指标：量比

### 4. 认证模块

#### 文件位置
`backend/auth/authentication.py`

#### 核心类：Authentication

```python
class Authentication:
    """认证核心逻辑"""
    
    def __init__(self):
        self.user_manager = UserManager()
        self.security = Security()
```

#### 主要功能

| 功能 | 描述 |
|------|------|
| 用户登录 | 用户名密码认证，支持万能密码（测试环境） |
| 用户注册 | 验证用户名、邮箱、密码强度 |
| 密码重置 | 邮箱验证码验证后重置 |
| 会话管理 | UUID会话，7天过期 |
| 账户锁定 | 多次登录失败后自动锁定 |

#### 安全机制

- bcrypt密码哈希
- 登录失败次数限制
- 账户自动锁定
- 会话超时
- 验证码机制

### 5. 策略模块

#### 5.1 主力选股策略

**文件位置**：`backend/strategies/main_force/`

**核心组件**：
- `main_force_selector.py` - 选股器
- `main_force_analysis.py` - 分析器
- `main_force_batch_db.py` - 批量数据库

#### 5.2 低价擒牛策略

**文件位置**：`backend/strategies/low_price_bull/`

**核心组件**：
- `low_price_bull_selector.py` - 选股器
- `low_price_bull_strategy.py` - 策略逻辑
- `low_price_bull_monitor.py` - 监控器
- `low_price_bull_service.py` - 服务层

#### 5.3 龙虎榜分析

**文件位置**：`backend/strategies/longhubang/`

**核心组件**：
- `longhubang_data.py` - 数据获取
- `longhubang_engine.py` - 分析引擎
- `longhubang_scoring.py` - 评分系统

#### 5.4 板块策略

**文件位置**：`backend/strategies/sector_strategy/`

**核心组件**：
- `sector_strategy_data.py` - 数据获取
- `sector_strategy_engine.py` - 分析引擎
- `sector_strategy_scheduler.py` - 定时任务

#### 5.5 AI盯盘

**文件位置**：`backend/strategies/smart_monitor/`

**核心组件**：
- `smart_monitor_engine.py` - 监控引擎
- `smart_monitor_deepseek.py` - AI决策
- `smart_monitor_kline.py` - K线分析
- `smart_monitor_data.py` - 数据管理

### 6. 通知服务

#### 文件位置
`backend/utils/notification_service.py`

#### 支持的通知方式

| 方式 | 描述 |
|------|------|
| Webhook | 支持钉钉、企业微信、飞书等 |
| 邮件 | SMTP邮件通知 |

### 7. PDF生成模块

#### 文件位置
`backend/utils/pdf_generator.py`

#### 功能

- 生成分析报告PDF
- 支持图表嵌入
- 支持自定义模板

---

## 数据库设计

### 1. 用户认证数据库

**文件位置**：`database/files/user_auth.db`

#### 表结构

##### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| username | TEXT | 用户名，唯一 |
| password_hash | TEXT | 密码哈希 |
| email | TEXT | 邮箱，唯一 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |
| last_login_at | TEXT | 最后登录时间 |
| login_attempts | INTEGER | 登录尝试次数 |
| locked_until | TEXT | 锁定截止时间 |

##### sessions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| session_id | TEXT | 会话ID，唯一 |
| user_id | INTEGER | 用户ID，外键 |
| created_at | TEXT | 创建时间 |
| expires_at | TEXT | 过期时间 |
| ip_address | TEXT | IP地址 |
| user_agent | TEXT | 用户代理 |

##### verification_codes 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| email | TEXT | 邮箱 |
| code | TEXT | 验证码 |
| created_at | TEXT | 创建时间 |
| expires_at | TEXT | 过期时间 |
| used | INTEGER | 是否已使用（0/1） |

### 2. 股票分析数据库

**文件位置**：`database/files/stock_analysis.db`

#### 表结构

##### analysis_records 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| symbol | TEXT | 股票代码 |
| stock_name | TEXT | 股票名称 |
| analysis_date | TEXT | 分析时间 |
| period | TEXT | 数据周期 |
| stock_info | TEXT | JSON格式股票信息 |
| agents_results | TEXT | JSON格式分析师结果 |
| discussion_result | TEXT | JSON格式讨论结果 |
| final_decision | TEXT | JSON格式最终决策 |
| created_at | TEXT | 创建时间 |

### 3. 其他数据库

| 数据库文件 | 用途 |
|-----------|------|
| longhubang.db | 龙虎榜数据 |
| monitor.db | 实时监控数据 |
| portfolio.db | 持仓数据 |
| sector_strategy.db | 板块策略数据 |
| smart_monitor.db | AI盯盘数据 |
| low_price_bull_monitor.db | 低价擒牛监控 |
| profit_growth_monitor.db | 净利增长监控 |
| main_force_batch.db | 主力批量分析 |

---

## API接口

### 内部接口（函数调用）

#### 数据获取接口

```python
# 获取股票基本信息
from backend.data.stock_data import StockDataFetcher
fetcher = StockDataFetcher()
stock_info = fetcher.get_stock_info(symbol)

# 获取历史数据
stock_data = fetcher.get_stock_data(symbol, period="1y")

# 获取财务数据
financial_data = fetcher.get_financial_data(symbol)
```

#### AI分析接口

```python
from backend.ai.ai_agents import StockAnalysisAgents
agents = StockAnalysisAgents(model="deepseek-chat")

# 技术分析
tech_analysis = agents.technical_analyst_agent(stock_info, stock_data, indicators)

# 多智能体分析
results = agents.run_multi_agent_analysis(...)
```

#### 认证接口

```python
from backend.auth.authentication import Authentication
auth = Authentication()

# 登录
result = auth.login(username, password)

# 注册
result = auth.register(username, password, email)

# 验证会话
result = auth.validate_session(session_id)
```

---

## 配置说明

### 环境变量配置

需要在项目根目录创建 `.env` 文件：

```env
# DeepSeek API配置
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Tushare配置（可选）
TUSHARE_TOKEN=your_tushare_token_here

# 测试环境万能密码
AUTH_TEST_MASTER_PASSWORD_ENABLED=true
AUTH_TEST_MASTER_PASSWORD=123456

# MiniQMT配置（可选）
MINIQMT_ENABLED=false
MINIQMT_ACCOUNT_ID=your_account_id
MINIQMT_HOST=127.0.0.1
MINIQMT_PORT=58610

# TDX API配置（可选）
TDX_ENABLED=false
TDX_BASE_URL=http://192.168.1.222:8181
```

### 配置文件

#### config.py

**文件位置**：`config/config.py`

主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| DEEPSEEK_API_KEY | DeepSeek API密钥 | 从环境变量读取 |
| DEEPSEEK_BASE_URL | DeepSeek API地址 | https://api.deepseek.com/v1 |
| TUSHARE_TOKEN | Tushare Token | 从环境变量读取 |
| DEFAULT_PERIOD | 默认数据周期 | "1y" |
| DEFAULT_INTERVAL | 默认数据间隔 | "1d" |
| AUTH_TEST_MASTER_PASSWORD_ENABLED | 是否启用万能密码 | true |
| AUTH_TEST_MASTER_PASSWORD | 万能密码 | "123456" |

#### model_config.py

**文件位置**：`config/model_config.py`

配置可用的AI模型。

### 功能开关配置

在 `frontend/app.py` 中有 `FEATURE_CONFIG` 字典，可以控制各功能模块的显示/隐藏：

```python
FEATURE_CONFIG = {
    "main_force": True,        # 主力选股
    "low_price_bull": True,    # 低价擒牛
    "small_cap": True,         # 小市值策略
    "profit_growth": True,     # 净利增长
    "sector_strategy": True,   # 智策板块
    "longhubang": True,        # 智瞰龙虎
    "portfolio": True,         # 持仓分析
    "smart_monitor": True,     # AI盯盘
    "monitor": True,           # 实时监控
    "history": True,           # 历史记录
    "config": True             # 环境配置
}
```

---

## 部署指南

### 本地开发部署

#### 1. 环境要求

- Python 3.8 或更高版本
- pip 包管理器

#### 2. 安装依赖

```bash
cd aiagents-stock-main
pip install -r requirements.txt
```

#### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp 归档/.env.example .env
# 编辑 .env 文件，填写必要的配置
```

#### 4. 启动应用

方式一：使用启动脚本
```bash
python run.py
```

方式二：直接启动Streamlit
```bash
streamlit run frontend/app.py --server.port 8503
```

#### 5. 访问应用

浏览器打开：`http://localhost:8503`

### Docker部署

#### Dockerfile

项目提供了Dockerfile用于容器化部署。

#### docker-compose.yml

```yaml
version: '3'
services:
  stock-analyzer:
    build: .
    ports:
      - "8503:8503"
    environment:
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - TUSHARE_TOKEN=${TUSHARE_TOKEN}
    volumes:
      - ./database/files:/app/database/files
    restart: unless-stopped
```

#### 构建和启动

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 生产环境部署建议

1. 使用Gunicorn + Nginx部署
2. 配置HTTPS
3. 使用环境变量管理敏感配置
4. 定期备份数据库
5. 配置日志轮转
6. 设置监控和告警

---

## 开发规范

### 代码风格

遵循PEP 8规范，使用以下工具：

- `black` - 代码格式化
- `flake8` - 代码检查
- `mypy` - 类型检查

### 提交规范

使用Conventional Commits规范：

```
<type>(<scope>): <description>

类型:
- feat: 新功能
- fix: 修复bug
- docs: 文档更新
- style: 代码格式调整
- refactor: 重构
- test: 测试相关
- chore: 构建/工具相关
```

### 目录命名规范

- 模块目录：小写加下划线（snake_case）
- 类名：大驼峰（PascalCase）
- 函数名：小写加下划线（snake_case）
- 常量：全大写下划线分隔（UPPER_SNAKE_CASE）

### 错误处理

- 使用try-except捕获预期异常
- 提供有意义的错误信息
- 记录日志用于调试

### 日志规范

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

---

## 常见问题

### Q1: DeepSeek API调用失败怎么办？

**A**: 检查以下几点：
1. API Key是否正确配置
2. 网络连接是否正常
3. API账户是否有足够额度
4. 查看错误日志获取详细信息

### Q2: 如何添加新的数据源？

**A**: 
1. 在 `backend/data/` 下创建新的数据获取模块
2. 实现类似 `StockDataFetcher` 的接口
3. 在 `data_source_manager.py` 中注册新数据源
4. 更新文档

### Q3: 如何添加新的智能体？

**A**:
1. 在 `backend/ai/ai_agents.py` 中添加新的Agent方法
2. 定义Agent的角色和分析prompt
3. 在 `run_multi_agent_analysis()` 中注册
4. 在前端UI中添加相应选项

### Q4: 如何扩展选股策略？

**A**:
1. 在 `backend/strategies/` 下创建新策略目录
2. 实现选股逻辑、监控逻辑等
3. 在 `frontend/strategies/` 下创建对应的UI
4. 在 `app.py` 中注册新功能

### Q5: 数据库文件太大怎么办？

**A**:
1. 定期清理历史分析记录
2. 归档旧数据到其他位置
3. 考虑使用数据库分区（如切换到PostgreSQL）
4. 实现数据自动清理机制

### Q6: 如何备份数据？

**A**:
```bash
# 备份整个数据库目录
cp -r database/files database/backup_$(date +%Y%m%d)

# 或者使用SQLite的备份命令
sqlite3 database/files/stock_analysis.db ".backup backup.db"
```

---

## 附录

### A. 依赖包完整列表

见 `requirements.txt` 文件。

### B. 相关文档

- [快速开始指南](docs/QUICK_START.md)
- [Docker部署指南](docs/DOCKER_DEPLOYMENT.md)
- [主力选股使用指南](docs/主力选股使用指南.md)
- [智策板块使用指南](docs/智策板块使用指南.md)
- [Webhook通知配置指南](docs/Webhook通知配置指南.md)

### C. 联系方式

如有问题或建议，请查看项目文档或联系维护者。

---

**文档版本**：v1.0  
**最后更新**：2024年  
**维护者**：项目开发团队
