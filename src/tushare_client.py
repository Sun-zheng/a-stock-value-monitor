from __future__ import annotations

import os
import time
from datetime import date, timedelta

import pandas as pd


class TushareClient:
    def __init__(self):
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TUSHARE_TOKEN 未配置")
        import tushare as ts

        self.pro = ts.pro_api(token)

    @staticmethod
    def ts_code(code: str) -> str:
        code = str(code).zfill(6)
        return f"{code}.SH" if code.startswith(("6", "9")) else f"{code}.SZ"

    def stock_basic(self) -> pd.DataFrame:
        frame = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,exchange,list_date",
        )
        return frame.rename(
            columns={
                "symbol": "代码", "name": "名称", "industry": "行业",
                "market": "Tushare市场", "exchange": "Tushare交易所",
                "list_date": "上市日期",
            }
        )

    def latest_daily_basic(self, target: date | None = None) -> tuple[pd.DataFrame, str]:
        target = target or date.today()
        for offset in range(10):
            trade_date = (target - timedelta(days=offset)).strftime("%Y%m%d")
            frame = self.pro.daily_basic(
                trade_date=trade_date,
                fields=(
                    "ts_code,trade_date,close,turnover_rate,pe,pe_ttm,pb,ps,"
                    "dv_ratio,total_mv,circ_mv"
                ),
            )
            if not frame.empty:
                mapped = frame.rename(
                    columns={
                        "close": "估值收盘价", "pe": "PE", "pe_ttm": "PE TTM",
                        "pb": "PB", "ps": "PS", "dv_ratio": "股息率",
                        "total_mv": "总市值", "circ_mv": "流通市值",
                    }
                )
                mapped["代码"] = mapped["ts_code"].str[:6]
                # Tushare market value unit is CNY 10,000.
                mapped["总市值"] = pd.to_numeric(mapped["总市值"], errors="coerce") * 10000
                mapped["流通市值"] = pd.to_numeric(mapped["流通市值"], errors="coerce") * 10000
                mapped["估值数据交易日"] = trade_date
                mapped["估值数据来源"] = "Tushare daily_basic"
                return mapped, trade_date
        raise RuntimeError("最近10个自然日均无 Tushare daily_basic 数据")

    def trade_dates(self, end: date | None = None, count: int = 20) -> list[str]:
        end = end or date.today()
        start = end - timedelta(days=max(count * 3, 60))
        frame = self.pro.trade_cal(
            exchange="SSE",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            is_open="1",
            fields="cal_date,is_open",
        )
        return sorted(frame["cal_date"].astype(str).tolist())[-count:]

    def daily_basic_on(self, trade_date: str) -> pd.DataFrame:
        frame = self.pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,close,pe,pe_ttm,pb,ps,dv_ratio,total_mv,circ_mv",
        )
        frame = frame.rename(
            columns={
                "close": "当前价格", "pe": "PE", "pe_ttm": "PE TTM",
                "pb": "PB", "ps": "PS", "dv_ratio": "股息率",
                "total_mv": "总市值", "circ_mv": "流通市值",
            }
        )
        frame["代码"] = frame["ts_code"].str[:6]
        frame["总市值"] = pd.to_numeric(frame["总市值"], errors="coerce") * 10000
        frame["流通市值"] = pd.to_numeric(frame["流通市值"], errors="coerce") * 10000
        return frame

    def financial_metrics(self, code: str) -> dict:
        ts_code = self.ts_code(code)
        indicator = self.pro.fina_indicator(
            ts_code=ts_code,
            fields=(
                "ts_code,ann_date,end_date,roe,roe_dt,grossprofit_margin,"
                "netprofit_margin,debt_to_assets,profit_dedt,ocf_to_profit,"
                "fcff,roic"
            ),
            limit=16,
        )
        income = self.pro.income(
            ts_code=ts_code,
            fields="ts_code,ann_date,end_date,total_revenue,n_income_attr_p,non_oper_income",
            limit=16,
        )
        cashflow = self.pro.cashflow(
            ts_code=ts_code,
            fields="ts_code,ann_date,end_date,n_cashflow_act",
            limit=16,
        )
        balance = self.pro.balancesheet(
            ts_code=ts_code,
            fields=(
                "ts_code,ann_date,end_date,total_assets,total_liab,money_cap,"
                "goodwill,accounts_receiv,inventories,total_ncl,total_cur_liab,"
                "st_borr,lt_borr,bond_payable,non_cur_liab_due_1y,"
                "total_hldr_eqy_exc_min_int"
            ),
            limit=16,
        )
        row: dict = {"代码": code, "财务数据来源": "Tushare Pro"}

        def normalize(frame: pd.DataFrame) -> pd.DataFrame:
            if frame.empty:
                return frame
            result = frame.copy()
            result["end_date"] = result["end_date"].astype(str)
            result["ann_date"] = result["ann_date"].fillna("").astype(str)
            return (
                result.sort_values(["end_date", "ann_date"], ascending=False)
                .drop_duplicates("end_date", keep="first")
            )

        indicator, income, cashflow, balance = map(
            normalize, (indicator, income, cashflow, balance)
        )
        date_sets = [
            set(frame["end_date"]) for frame in (indicator, income, cashflow, balance)
            if not frame.empty
        ]
        common_dates = set.intersection(*date_sets) if len(date_sets) == 4 else set()
        aligned_date = max(common_dates) if common_dates else ""
        latest_dates = [
            frame.iloc[0]["end_date"] if not frame.empty else None
            for frame in (indicator, income, cashflow, balance)
        ]
        row["报表期间一致"] = bool(
            aligned_date and all(value == aligned_date for value in latest_dates)
        )
        row["对齐报告期"] = aligned_date or None
        row["财务指标报告期"] = indicator.iloc[0]["end_date"] if not indicator.empty else None
        row["利润表报告期"] = income.iloc[0]["end_date"] if not income.empty else None
        row["现金流数据报告期"] = cashflow.iloc[0]["end_date"] if not cashflow.empty else None
        row["资产负债表报告期"] = balance.iloc[0]["end_date"] if not balance.empty else None

        if aligned_date:
            ind_item = indicator[indicator["end_date"] == aligned_date].iloc[0]
            income_item = income[income["end_date"] == aligned_date].iloc[0]
            cash_item = cashflow[cashflow["end_date"] == aligned_date].iloc[0]
            balance_item = balance[balance["end_date"] == aligned_date].iloc[0]
            row.update({
                "财报数据报告期": aligned_date,
                "营业收入": income_item.get("total_revenue"),
                "归母净利润": income_item.get("n_income_attr_p"),
                "扣非净利润": ind_item.get("profit_dedt"),
                "ROIC": ind_item.get("roic"),
                "毛利率": ind_item.get("grossprofit_margin"),
                "净利率": ind_item.get("netprofit_margin"),
                "资产负债率": ind_item.get("debt_to_assets"),
                "经营现金流/净利润": ind_item.get("ocf_to_profit"),
                "自由现金流": ind_item.get("fcff"),
                "经营性现金流净额": cash_item.get("n_cashflow_act"),
                "总资产": balance_item.get("total_assets"),
                "总负债": balance_item.get("total_liab"),
                "归母净资产": balance_item.get("total_hldr_eqy_exc_min_int"),
                "货币资金": balance_item.get("money_cap"),
                "商誉": balance_item.get("goodwill"),
                "应收账款": balance_item.get("accounts_receiv"),
                "存货": balance_item.get("inventories"),
                "有息负债": (
                    sum(
                        float(balance_item.get(field) or 0)
                        for field in ("st_borr", "lt_borr", "bond_payable", "non_cur_liab_due_1y")
                    )
                    if any(
                        pd.notna(balance_item.get(field))
                        for field in ("st_borr", "lt_borr", "bond_payable", "non_cur_liab_due_1y")
                    )
                    else None
                ),
            })

        annual_indicator = indicator[indicator["end_date"].str.endswith("1231")].copy()
        annual_income = income[income["end_date"].str.endswith("1231")].copy()
        annual_cash = cashflow[cashflow["end_date"].str.endswith("1231")].copy()
        annual_balance = balance[balance["end_date"].str.endswith("1231")].copy()
        if not annual_indicator.empty:
            annual_ind = annual_indicator.iloc[0]
            row.update({
                "ROE": annual_ind.get("roe"),
                "扣非ROE": annual_ind.get("roe_dt"),
                "ROIC": annual_ind.get("roic"),
                "毛利率": annual_ind.get("grossprofit_margin"),
                "净利率": annual_ind.get("netprofit_margin"),
                "经营现金流/净利润": annual_ind.get("ocf_to_profit"),
                "ROE口径": "最近完整年度ROE",
                "ROE报告期": annual_ind.get("end_date"),
                "盈利指标口径": "最近完整年度财务指标",
            })
        else:
            row.update({
                "ROE": None,
                "扣非ROE": None,
                "ROE口径": "数据不足，不年化季度ROE",
                "盈利指标口径": "数据不足",
            })

        annual_income = annual_income.sort_values("end_date", ascending=False).head(3)
        if not annual_income.empty:
            latest_annual = annual_income.iloc[0]
            row["最近完整年度营业收入"] = latest_annual.get("total_revenue")
            profits = pd.to_numeric(annual_income["n_income_attr_p"], errors="coerce")
            row["标准化归母净利润"] = (
                float(profits.median())
                if len(profits.dropna()) >= 2 and float(profits.median()) > 0
                else None
            )
            for target, field in (
                ("营业收入多年趋势", "total_revenue"),
                ("归母净利润多年趋势", "n_income_attr_p"),
            ):
                values = pd.to_numeric(
                    annual_income.sort_values("end_date")[field], errors="coerce"
                ).dropna()
                if (
                    len(values) >= 2
                    and float(values.iloc[0]) > 0
                    and float(values.iloc[-1]) > 0
                ):
                    years = len(values) - 1
                    ratio = float(values.iloc[-1]) / float(values.iloc[0])
                    row[target] = (ratio ** (1 / years) - 1) * 100
                else:
                    row[target] = None
        if not annual_cash.empty:
            annual_date = annual_cash.iloc[0]["end_date"]
            annual_ind_match = annual_indicator[annual_indicator["end_date"] == annual_date]
            row["最近完整年度自由现金流"] = (
                annual_ind_match.iloc[0].get("fcff") if not annual_ind_match.empty else None
            )
        annual_fcf_values = pd.to_numeric(
            annual_indicator.sort_values("end_date", ascending=False).head(3).get(
                "fcff", pd.Series(dtype=float)
            ),
            errors="coerce",
        ).dropna()
        positive_fcf = annual_fcf_values[annual_fcf_values > 0]
        row["自由现金流年度样本数"] = int(len(annual_fcf_values))
        row["标准化自由现金流"] = (
            float(annual_fcf_values.median())
            if len(annual_fcf_values) >= 3
            and len(positive_fcf) == len(annual_fcf_values)
            and float(annual_fcf_values.median()) > 0
            else None
        )
        if not annual_balance.empty:
            row["最近完整年度归母净资产"] = annual_balance.iloc[0].get(
                "total_hldr_eqy_exc_min_int"
            )

        parent_profit = pd.to_numeric(pd.Series([row.get("归母净利润")]), errors="coerce").iloc[0]
        adjusted_profit = pd.to_numeric(pd.Series([row.get("扣非净利润")]), errors="coerce").iloc[0]
        margin = pd.to_numeric(pd.Series([row.get("净利率")]), errors="coerce").iloc[0]
        one_off = (
            pd.notna(parent_profit)
            and pd.notna(adjusted_profit)
            and abs(adjusted_profit) < abs(parent_profit) * 0.3
        ) or (pd.notna(margin) and abs(margin) > 100)
        row["一次性收益异常"] = bool(one_off)
        row["成长数据置信度"] = (
            "高" if pd.notna(row.get("营业收入多年趋势")) and pd.notna(row.get("归母净利润多年趋势"))
            else "低：缺少2至3年完整年度趋势"
        )
        row["数据时间"] = pd.Timestamp.now().isoformat()
        return row

    def financial_metrics_many(self, codes: list[str]) -> pd.DataFrame:
        rows = []
        for index, code in enumerate(codes):
            try:
                rows.append(self.financial_metrics(code))
            except Exception as exc:
                rows.append({"代码": code, "财务数据错误": f"{type(exc).__name__}: {exc}"})
            if index and index % 20 == 0:
                time.sleep(1)
        return pd.DataFrame(rows)
