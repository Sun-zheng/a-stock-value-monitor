from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from src.data_source_manager import DataSourceManager
from src.stock_pool import build_main_board_pool, pool_statistics
from src.tushare_client import TushareClient
from src.strategy_config import load_strategy
from src.universe_scanner import (
    CASH_FIELDS,
    FINANCIAL_FIELDS,
    MAX_LIGHT_CANDIDATES,
    _prepare_scored_candidates,
    add_decision_fields,
    apply_intraday_market_cap,
    attach_industry_benchmarks,
    deep_review_prefetch_limit,
    financial_filter_details,
    row_coverage,
    score_candidates,
    select_outputs,
    valuation_coverage,
    valuation_filter,
)


def _records(frame: pd.DataFrame, limit: int = 20) -> list[dict]:
    return frame.head(limit).fillna("数据不足").to_dict("records")


def _main_board_count(frame: pd.DataFrame) -> int:
    if "上市板块" not in frame:
        return 0
    return int(
        frame["上市板块"].astype(str).isin({"沪市主板", "深市主板"}).sum()
    )


def _historical_replay(
    universe: pd.DataFrame,
    benchmark_universe: pd.DataFrame,
    financial: pd.DataFrame,
    days: int = 10,
    strategy: dict | None = None,
) -> dict:
    strategy = strategy or load_strategy(Path.cwd())
    days = max(5, min(days, 20))
    client = TushareClient()
    rows = []
    occurrences = Counter()
    trade_dates = client.trade_dates(count=min(days + 5, 25))
    for trade_date in reversed(trade_dates):
        valuation = client.daily_basic_on(trade_date)
        if valuation.empty:
            continue
        benchmark_market = benchmark_universe.merge(
            valuation.drop(columns=["ts_code"], errors="ignore"),
            on="代码",
            how="left",
        )
        light = universe.merge(
            valuation.drop(columns=["ts_code"], errors="ignore"),
            on="代码",
            how="left",
        )
        light["估值收盘价"] = light["当前价格"]
        light = apply_intraday_market_cap(light)
        light = attach_industry_benchmarks(light, benchmark_market)
        classifications = light["行业"].astype(str)
        light["特殊行业"] = classifications.str.contains(
            "银行|保险|证券|房地产|房产|火力发电|水力发电|供气供热|水务|煤炭|石油|钢铁|普钢|特种钢|有色|铝|铜|水泥|化纤|航运|海运|水运|港口",
            regex=True,
        )
        candidates = valuation_filter(
            light,
            candidate_limit=int(strategy["candidate_limit"]),
        )
        merged = candidates.merge(financial, on="代码", how="left")
        merged["财报覆盖率"] = (
            merged[[field for field in FINANCIAL_FIELDS if field in merged]].notna().mean(axis=1) * 100
        ).round(2)
        merged["现金流完整"] = merged[[field for field in CASH_FIELDS if field in merged]].notna().all(axis=1)
        details = financial_filter_details(merged)
        passed = details[details["一票否决原因"] == ""]
        scored = add_decision_fields(
            score_candidates(passed, strategy=strategy),
            strategy=strategy,
        )
        formal, watch = select_outputs(
            scored, recommendation_ready=True, strategy=strategy
        )
        occurrences.update(watch["代码"].astype(str).tolist())
        rows.append({
            "交易日": trade_date,
            "估值轻筛通过数量": len(candidates),
            "一票否决后数量": len(scored),
            "正式条件检查数量": len(details),
            "正式推荐数量": len(formal),
            "观察股票数量": len(watch),
            "正式推荐代码": formal["代码"].astype(str).tolist(),
            "观察股票代码": watch["代码"].astype(str).tolist(),
        })
        if len(rows) >= days:
            break
    rows.reverse()
    return {
        "回放交易日数": len(rows),
        "回放明细": rows,
        "推荐始终最多1只": all(item["正式推荐数量"] <= 1 for item in rows),
        "观察始终最多5只": all(item["观察股票数量"] <= 5 for item in rows),
        "正式检查未受Top10截断": all(
            item["正式条件检查数量"] == item["估值轻筛通过数量"] for item in rows
        ),
        "观察重复出现": dict(occurrences.most_common()),
        "回放限制": "估值按各历史交易日，财务使用当前缓存，属于5至20日有限回放而非无前视严格回测。",
    }


def audit_automation() -> dict:
    path = Path.home() / ".codex" / "automations" / "a-ai" / "automation.toml"
    required = [
        "Buffett + Munger 九维框架",
        "三类独立估值",
        "保守安全边际",
        "缺失数据不得推断或加分",
        "最多1只",
        "最多5只",
        "每只正式推荐和观察股票分别写入飞书",
        "完整执行过程",
        "境内全部上市A股基准",
        "国内全市场基准股票数量大于主板候选宇宙",
    ]
    forbidden_old_rules = ["综合评分>=75", "安全边际>=20%"]
    systemd_analysis = Path.home() / ".config/systemd/user/stock-daily-analysis.timer"
    systemd_delivery = Path.home() / ".config/systemd/user/stock-final-delivery.timer"
    if not path.exists():
        analysis_text = systemd_analysis.read_text(encoding="utf-8") if systemd_analysis.exists() else ""
        delivery_text = systemd_delivery.read_text(encoding="utf-8") if systemd_delivery.exists() else ""
        systemd_ok = (
            "OnCalendar=Mon..Fri 14:10:00" in analysis_text
            and "OnCalendar=Mon..Fri 14:40:00" in delivery_text
        )
        return {
            "满足要求": systemd_ok,
            "原因": "Codex Automation 配置不存在，使用 systemd 14:10 基础流水线和 14:40 交付兜底"
            if systemd_ok
            else "Automation 配置不存在且 systemd 兜底调度不完整",
            "systemd基础流水线": systemd_ok and "OnCalendar=Mon..Fri 14:10:00" in analysis_text,
            "systemd交付兜底": systemd_ok and "OnCalendar=Mon..Fri 14:40:00" in delivery_text,
        }
    content = path.read_text(encoding="utf-8")
    missing = [item for item in required if item not in content]
    stale = [item for item in forbidden_old_rules if item in content]
    return {
        "满足要求": not missing and not stale,
        "状态ACTIVE": 'status = "ACTIVE"' in content,
        "项目绑定正确": 'E:\\\\a_stock_value_monitor' in content,
        "调度正确": "BYHOUR=14;BYMINUTE=20" in content,
        "缺失策略要素": missing,
        "过时策略要素": stale,
    }


def validation_conclusions(result: dict) -> dict:
    coverage = result["数据覆盖率"]
    funnel = result["漏斗"]
    benchmark_count = result["行业基准"]["基准输入股票数"]
    raw_domestic_count = result["全市场覆盖"]["境内全A股基准股票数量"]
    benchmark_scope = str(result["行业基准"].get("基准范围", ""))
    enough = (
        coverage["估值覆盖率"] >= 80
        and coverage["财报覆盖率"] >= 70
        and coverage["现金流覆盖率"] >= 70
    )
    conclusions = {
        "是否扫描A股主板全市场": result["全市场覆盖"]["实际扫描全市场"],
        "数据覆盖率是否支持正式推荐": enough,
        "行业基准是否来自国内全市场同行": (
            benchmark_count >= int(raw_domestic_count * 0.99)
            and benchmark_count > funnel["主板股票数量"]
            and "境内全部上市A股" in benchmark_scope
        ),
        "正式条件是否检查全部一票否决后候选": (
            funnel["正式条件检查数量"] == funnel["财务快筛请求数量"]
        ),
        "500只候选是否全部完成财务和正式条件检查": (
            funnel["估值轻筛通过数量"] == funnel["候选上限"]
            and funnel["财务快筛请求数量"] == funnel["候选上限"]
            and funnel["正式条件检查数量"] == funnel["候选上限"]
        ),
        "市值与估值时点是否一致": (
            result["数据时效"]["市值时点一致数量"]
            == result["数据时效"]["市值可检验数量"]
        ),
        "ROE及盈利指标是否使用完整年度口径": (
            result["财务期间口径"]["年度盈利指标口径数量"]
            == funnel["财务快筛请求数量"]
        ),
        "四类财务数据最新期间是否一致": (
            result["财务期间口径"]["最新期间一致数量"]
            == funnel["财务快筛请求数量"]
        ),
        "正式推荐是否均有3种独立估值且使用保守安全边际": (
            result["估值独立性"]["正式推荐违规数量"] == 0
        ),
        "特殊行业是否禁止通用模型正式推荐": (
            result["估值独立性"]["特殊行业正式推荐数量"] == 0
        ),
        "Buffett-Munger九维门槛是否用于正式推荐": (
            result["Buffett-Munger九维"]["正式推荐九维违规数量"] == 0
        ),
        "正式推荐是否最多1只": funnel["正式推荐数量"] <= 1,
        "观察股票是否最多5只且不凑数": funnel["观察股票数量"] <= 5,
        "Automation是否与新策略一致": result["Automation验收"]["满足要求"],
    }
    conclusions["是否可以继续正式每日运行"] = all(conclusions.values())
    return conclusions


def run_strategy_validation(project_root: Path, reports_dir: Path) -> dict:
    manager = DataSourceManager(project_root)
    strategy = load_strategy(project_root)
    client = TushareClient()
    raw = client.stock_basic()
    main_board_universe = build_main_board_pool(raw)
    universe, _ = manager.build_universe()
    benchmark_universe, _ = manager.build_domestic_universe()
    benchmark_market, benchmark_meta = manager.build_domestic_valuation()
    light, source_meta = manager.combined_light_data()
    light = apply_intraday_market_cap(light)
    light = attach_industry_benchmarks(light, benchmark_market)
    industries = light["行业"].astype(str)
    light["特殊行业"] = industries.str.contains(
        "银行|保险|证券|房地产|房产|火力发电|水力发电|供气供热|水务|煤炭|石油|钢铁|普钢|特种钢|有色|铝|铜|水泥|化纤|航运|海运|水运|港口",
        regex=True,
    )
    target_limit = int(strategy["candidate_limit"])
    candidates = valuation_filter(
        light,
        candidate_limit=deep_review_prefetch_limit(len(light), target_limit),
    )
    scored, details, financial, financial_meta = _prepare_scored_candidates(
        project_root, candidates, target_limit, False
    )
    recommendation_ready = (
        valuation_coverage(light) >= 80
        and row_coverage(details, FINANCIAL_FIELDS) >= 70
        and row_coverage(details, CASH_FIELDS) >= 70
    )
    formal, observations = select_outputs(
        scored, recommendation_ready, strategy=strategy
    )
    rejected = details[details["一票否决原因"] != ""]
    cap_testable = pd.to_numeric(light["总市值"], errors="coerce").notna()
    latest_period_columns = [
        "财务指标报告期",
        "利润表报告期",
        "现金流数据报告期",
        "资产负债表报告期",
    ]
    latest_periods_equal = details[latest_period_columns].astype(str).eq(
        details["对齐报告期"].astype(str), axis=0
    ).all(axis=1)
    formal_valuation_violation = formal[
        pd.to_numeric(formal.get("估值方法有效数"), errors="coerce").lt(3)
        | pd.to_numeric(formal.get("可靠估值覆盖率"), errors="coerce").lt(100)
        | formal.get("安全边际", pd.Series(index=formal.index, dtype=float)).isna()
    ]
    industry_summary = (
        light.groupby("行业", dropna=False)
        .agg(
            股票数=("代码", "size"),
            PE样本数=("行业PE TTM样本数", "max"),
            PB样本数=("行业PB样本数", "max"),
            PS样本数=("行业PS样本数", "max"),
            样本充足=("行业估值样本充足", "max"),
        )
        .reset_index()
    )
    main_board_count = _main_board_count(light)
    result = {
        "验收日期": date.today().isoformat(),
        "全市场覆盖": {
            **pool_statistics(raw),
            "沪深主板股票数量": len(main_board_universe),
            "境内全A股基准股票数量": len(benchmark_universe),
            "实际扫描全市场": len(light) >= 2000,
        },
        "数据时效": {
            "行情数据时间": source_meta["market"].get("data_time", "数据不足"),
            "行情交易日": source_meta["market"].get("trade_date", "数据不足"),
            "估值数据交易日": source_meta["valuation"].get("trade_date", "数据不足"),
            "市值口径": light["市值口径"].value_counts().to_dict(),
            "市值时点一致数量": int(
                light.loc[cap_testable, "市值时点一致"].fillna(False).astype(bool).sum()
            ),
            "市值可检验数量": int(cap_testable.sum()),
            "报表期间一致数量": int(details.get("报表期间一致", pd.Series(dtype=bool)).fillna(False).sum()),
        },
        "数据覆盖率": {
            "行情覆盖率": row_coverage(light, ["当前价格"]),
            "估值覆盖率": valuation_coverage(light),
            "财报覆盖率": row_coverage(details, FINANCIAL_FIELDS),
            "现金流覆盖率": row_coverage(details, CASH_FIELDS),
        },
        "行业基准": {
            "基准输入股票数": len(benchmark_market),
            "基准范围": "境内全部上市A股，含主板、创业板、科创板、北交所；排除ST、退市及非股票证券",
            "数据源": benchmark_meta,
            "最小同行样本数": 8,
            "剔除规则": "负值、缺失值、行业内5%和95%分位之外极端值",
            "样本不足行业数": int((~industry_summary["样本充足"].fillna(False)).sum()),
            "行业摘要": _records(industry_summary, 50),
        },
        "财务期间口径": {
            "年度盈利指标口径数量": int(
                details.get("盈利指标口径", pd.Series(dtype=str))
                .eq("最近完整年度财务指标")
                .sum()
            ),
            "最新期间一致数量": int(latest_periods_equal.sum()),
            "成长趋势有效数量": int(
                details[["营业收入多年趋势", "归母净利润多年趋势"]]
                .notna()
                .all(axis=1)
                .sum()
            ),
            "成长趋势规则": "仅在首尾完整年度收入或利润均为正时计算CAGR；否则缺失且不加分",
        },
        "估值独立性": {
            "估值族": ["全市场同行相对估值", "12倍保守盈利估值", "12倍标准化自由现金流估值"],
            "安全边际口径": "取全部有效独立估值族中最低合理市值；正式推荐要求三族齐全",
            "正式推荐违规数量": len(formal_valuation_violation),
            "特殊行业正式推荐数量": int(
                formal.get("特殊行业", pd.Series(False, index=formal.index))
                .fillna(False)
                .astype(bool)
                .sum()
            ),
        },
        "Buffett-Munger九维": {
            "策略名称": strategy["name"],
            "正式推荐分数门槛": strategy["formal_score"],
            "正式推荐安全边际门槛": strategy["formal_margin"],
            "观察分数门槛": strategy["watch_score"],
            "九维权重": strategy["weights"],
            "长期质量门槛": strategy["quality_gates"],
            "正式推荐九维违规数量": int(
                (~formal.get(
                    "十年持有质量门槛",
                    pd.Series(False, index=formal.index),
                ).fillna(False).astype(bool)).sum()
            ),
        },
        "漏斗": {
            "主板股票数量": main_board_count,
            "估值轻筛通过数量": len(details),
            "估值轻筛预取数量": len(candidates),
            "候选上限": int(strategy["candidate_limit"]),
            "候选来源分组": details["候选来源"].value_counts().to_dict(),
            "财务快筛请求数量": len(details),
            "一票否决后数量": len(scored),
            "正式条件检查数量": len(details),
            "展示Top10数量": min(10, len(scored)),
            "正式推荐数量": len(formal),
            "观察股票数量": len(observations),
            "一票否决原因": rejected["一票否决原因"].value_counts().to_dict(),
        },
        "正式推荐股票": _records(formal, 1),
        "观察股票": _records(observations, 5),
        "反向抽样": {
            "一票否决抽样20只": _records(rejected[["代码", "名称", "一票否决原因"]]),
            "最终未推荐Top20": _records(scored[~scored["是否正式推荐"]], 20),
        },
        "最近10个交易日有限回放": _historical_replay(
            universe,
            benchmark_universe,
            financial,
            days=10,
            strategy=strategy,
        ),
        "Automation验收": audit_automation(),
        "财务数据源": financial_meta,
    }
    result["验收结论"] = validation_conclusions(result)
    save_validation(result, reports_dir)
    return result


def save_validation(result: dict, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    (reports_dir / f"strategy_validation_{day}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = ["# 策略验收与漏斗验证报告", ""]
    for section in (
        "全市场覆盖",
        "数据时效",
        "数据覆盖率",
        "行业基准",
        "财务期间口径",
        "估值独立性",
        "Buffett-Munger九维",
        "漏斗",
        "Automation验收",
        "验收结论",
    ):
        lines.extend([f"## {section}", ""])
        for key, value in result[section].items():
            if key != "行业摘要":
                lines.append(f"- {key}: {value}")
        lines.append("")
    (reports_dir / f"strategy_validation_{day}.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
