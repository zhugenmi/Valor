"""Financial data API shim - wraps valor's DataRouter for A_Share agent compatibility.

Agents call get_financial_metrics(), get_price_history(), etc. This module
delegates to valor.adapters.data (DataRouter / AkShareAdapter / akshare_cache).

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

from typing import Any
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from loguru import logger

from valor.adapters.data.akshare_cache import (
    _compute_dividend_years,
    _compute_pb_percentile,
    get_bank_special_indicators,
    get_dividend_history,
    get_dividend_yield,
    get_financial_indicators,
    get_financial_report,
    get_history_pb,
    get_price_history_df,
    get_r_and_d_expense,
    get_valuation_indicator,
)
from valor.tools.market_snapshot import get_market_snapshot
from valor.utils.config_loader import get_cache_refresh_flag

_REPORT_BALANCE_SHEET = "资产负债表"
_REPORT_INCOME_STATEMENT = "利润表"
_REPORT_CASH_FLOW = "现金流量表"


def _default_agent_metrics() -> dict[str, float]:
    return {
        "return_on_equity": 0.0,
        "net_margin": 0.0,
        "operating_margin": 0.0,
        "revenue_growth": 0.0,
        "earnings_growth": 0.0,
        "book_value_growth": 0.0,
        "current_ratio": 0.0,
        "debt_to_equity": 0.0,
        "free_cash_flow_per_share": 0.0,
        "earnings_per_share": 0.0,
        "pe_ratio": 0.0,
        "price_to_book": 0.0,
        "price_to_sales": 0.0,
        "dividend_yield": 0.0,
        "book_value_per_share": 0.0,
        "payout_ratio": 0.0,
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    """Robust float conversion supporting None, NaN, '--', '1,234.56' etc."""
    if value is None:
        return default
    if isinstance(value, (int, float, np.number)):
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text in {"--", "None", "nan", "NaN"}:
            return default
        try:
            return float(text.replace(",", ""))
        except Exception:
            return default
    try:
        return float(value)
    except Exception:
        return default


def _convert_percentage(value: Any) -> float:
    """Convert percentage value to decimal."""
    try:
        v = _to_float(value, 0.0)
        return v / 100.0
    except Exception:
        return 0.0


def get_financial_metrics(
    symbol: str,
    *,
    trace_state: dict | None = None,
    as_of_date: str | None = None,
    snapshot: dict[str, Any] | None = None,
    cluster_hint: str | None = None,
) -> list[dict[str, Any]]:
    """Get financial indicator data for a ticker.

    Delegates to valor's akshare_cache layer via A_Share's original pattern.
    """
    logger.info("Getting financial indicators for {s}...", s=symbol)
    refresh_financial_indicators = get_cache_refresh_flag("market_data_agent", "financial_indicators")
    refresh_financial_reports = get_cache_refresh_flag("market_data_agent", "financial_reports")
    cutoff = None
    if as_of_date:
        try:
            cutoff = pd.to_datetime(as_of_date)
        except Exception:
            cutoff = None

    try:
        if snapshot is None:
            logger.info("Fetching market snapshot...")
            try:
                snapshot = get_market_snapshot(
                    symbol,
                    trace_state=trace_state,
                    agent_name="market_data_agent",
                    as_of_date=as_of_date,
                )
            except Exception:
                snapshot = {}

        stock_data = {
            "总市值": snapshot.get("market_cap", 0),
            "流通市值": snapshot.get("market_cap", 0),
        }

        logger.info("Fetching Baidu valuation indicators (PE-TTM/PB/market_cap)...")
        valuation = get_valuation_indicator(symbol)
        pe_ratio_val = _to_float(valuation.get("pe_ttm", 0.0)) if valuation else 0.0
        price_to_book_val = _to_float(valuation.get("pb", 0.0)) if valuation else 0.0
        realtime_market_cap = _to_float(valuation.get("market_cap", 0.0)) if valuation else 0.0
        current_price = _to_float(valuation.get("price", 0.0)) if valuation else 0.0

        logger.info("Fetching Sina financial indicators...")
        financial_data = get_financial_indicators(
            symbol=symbol,
            force_refresh=refresh_financial_indicators,
        )
        if cutoff is not None:
            try:
                financial_data["日期"] = pd.to_datetime(financial_data["日期"])
                financial_data = financial_data[financial_data["日期"] <= cutoff]
            except Exception:
                pass
        if financial_data is None or financial_data.empty:
            logger.warning("No financial indicator data, using defaults.")
            return [_default_agent_metrics()]

        financial_data["日期"] = pd.to_datetime(financial_data["日期"])
        financial_data = financial_data.sort_values("日期", ascending=False)
        latest_financial = financial_data.iloc[0] if not financial_data.empty else pd.Series(dtype=float)

        logger.info("Fetching income statement...")
        try:
            income_statement = get_financial_report(
                symbol, _REPORT_INCOME_STATEMENT, force_refresh=refresh_financial_reports,
            )
            if cutoff is not None and not income_statement.empty and "报告日" in income_statement.columns:
                try:
                    income_statement["报告日"] = pd.to_datetime(income_statement["报告日"])
                    income_statement = income_statement[income_statement["报告日"] <= cutoff]
                except Exception:
                    pass
            if "报告日" in income_statement.columns:
                income_statement = income_statement.sort_values("报告日", ascending=False)
            latest_income = income_statement.iloc[0] if not income_statement.empty else pd.Series(dtype=float)
        except Exception:
            latest_income = pd.Series(dtype=float)

        total_revenue = _to_float(latest_income.get("营业总收入", 0))
        net_inc = _to_float(latest_income.get("净利润", 0))
        eps = _to_float(latest_financial.get("加权每股收益(元)", 0))

        # Market cap priority: Baidu valuation -> snapshot -> net_income * 20 fallback
        total_market_cap = realtime_market_cap or _to_float(stock_data.get("总市值", 0))
        if total_market_cap <= 0:
            if net_inc > 0:
                total_market_cap = net_inc * 20.0  # default PE = 20 for mature A-share companies
            elif eps > 0:
                total_market_cap = eps * 20.0  # rough fallback (EPS is per-share, assumes ~1 share)

        # PE/PB: prefer Baidu valuation (TTM-based), fallback to self-computed
        if pe_ratio_val <= 0 and total_market_cap > 0 and net_inc > 0:
            pe_ratio_val = total_market_cap / net_inc
        if price_to_book_val <= 0:
            roe_val = _convert_percentage(latest_financial.get("净资产收益率(%)", 0))
            price_to_book_val = pe_ratio_val * roe_val if pe_ratio_val > 0 and roe_val > 0 else 0.0

        # Dividend yield (TTM) from Sina dividend detail
        dividend_yield_val = get_dividend_yield(symbol, current_price) if current_price > 0 else 0.0

        # Book value per share = price / PB
        book_value_per_share_val = (
            current_price / price_to_book_val
            if current_price > 0 and price_to_book_val > 0 else 0.0
        )

        # Payout ratio = dividend_yield × PE-TTM (反推: 分红/盈利 = (分红/股价) × (股价/盈利))
        payout_ratio_val = (
            dividend_yield_val * pe_ratio_val
            if dividend_yield_val > 0 and pe_ratio_val > 0 else 0.0
        )

        all_metrics = {
            "market_cap": total_market_cap,
            "float_market_cap": _to_float(stock_data.get("流通市值", 0)),
            "revenue": total_revenue,
            "net_income": net_inc,
            "return_on_equity": _convert_percentage(latest_financial.get("净资产收益率(%)", 0)),
            "net_margin": _convert_percentage(latest_financial.get("销售净利率(%)", 0)),
            "operating_margin": _convert_percentage(latest_financial.get("营业利润率(%)", 0)),
            "revenue_growth": _convert_percentage(latest_financial.get("主营业务收入增长率(%)", 0)),
            "earnings_growth": _convert_percentage(latest_financial.get("净利润增长率(%)", 0)),
            "book_value_growth": _convert_percentage(latest_financial.get("净资产增长率(%)", 0)),
            "current_ratio": _to_float(latest_financial.get("流动比率", 0)),
            "debt_to_equity": _convert_percentage(latest_financial.get("资产负债率(%)", 0)),
            "free_cash_flow_per_share": _to_float(latest_financial.get("每股经营性现金流(元)", 0)),
            "earnings_per_share": eps,
            "pe_ratio": pe_ratio_val,
            "price_to_book": price_to_book_val,
            "price_to_sales": total_market_cap / total_revenue if total_revenue > 0 else 0.0,
            "dividend_yield": dividend_yield_val,
            "book_value_per_share": book_value_per_share_val,
            "payout_ratio": payout_ratio_val,
        }

        agent_metrics = {k: all_metrics[k] for k in _default_agent_metrics()}

        # 按集群追加专属指标 (带 fallback) + 衍生指标
        cluster_extras: dict[str, Any] = {}
        try:
            balance_sheet_df = get_financial_report(
                symbol, _REPORT_BALANCE_SHEET, force_refresh=refresh_financial_reports,
            )
            if cutoff is not None and not balance_sheet_df.empty and "报告日" in balance_sheet_df.columns:
                try:
                    balance_sheet_df["报告日"] = pd.to_datetime(balance_sheet_df["报告日"])
                    balance_sheet_df = balance_sheet_df[balance_sheet_df["报告日"] <= cutoff]
                except Exception:
                    pass
            if "报告日" in balance_sheet_df.columns:
                balance_sheet_df = balance_sheet_df.sort_values("报告日", ascending=False)
        except Exception:
            balance_sheet_df = pd.DataFrame()

        try:
            cashflow_df = get_financial_report(
                symbol, _REPORT_CASH_FLOW, force_refresh=refresh_financial_reports,
            )
            if cutoff is not None and not cashflow_df.empty and "报告日" in cashflow_df.columns:
                try:
                    cashflow_df["报告日"] = pd.to_datetime(cashflow_df["报告日"])
                    cashflow_df = cashflow_df[cashflow_df["报告日"] <= cutoff]
                except Exception:
                    pass
            if "报告日" in cashflow_df.columns:
                cashflow_df = cashflow_df.sort_values("报告日", ascending=False)
        except Exception:
            cashflow_df = pd.DataFrame()

        latest_cashflow = cashflow_df.iloc[0] if not cashflow_df.empty else pd.Series(dtype=float)

        _CAPEX_FIELDS = [
            "购建固定资产、无形资产和其他长期资产支付的现金",
            "购建固定资产、无形资产和其他长期资产所支付的现金",
        ]

        # 集群专属指标
        if cluster_hint == "financial":
            cluster_extras.update(get_bank_special_indicators(symbol))
        if cluster_hint == "cyclical_resource":
            pb_series = get_history_pb(symbol, years=5)
            pb_pct = _compute_pb_percentile(
                pb_series,
                current_price / price_to_book_val if price_to_book_val > 0 else 0,
            )
            if pb_pct is not None:
                cluster_extras["pb_percentile_5y"] = pb_pct
        if cluster_hint in ("pharma", "tmt"):
            cluster_extras.update(get_r_and_d_expense(symbol))
        if cluster_hint == "utility_transport":
            cluster_extras["dividend_years"] = _compute_dividend_years(
                get_dividend_history(symbol),
            )

        # 衍生指标 (COMPUTED, 所有集群都算)
        try:
            ext_balance = _extract_extended_balance_sheet_fields(balance_sheet_df, 0)
            ext_income = _extract_extended_income_fields(income_statement, 0)
            ext_prev = {
                **_extract_extended_balance_sheet_fields(balance_sheet_df, 1),
                **_extract_extended_income_fields(income_statement, 1),
            }
            derived = _compute_derived_metrics(
                {
                    **ext_balance,
                    **ext_income,
                    "operating_cash_flow": _to_float(latest_cashflow.get("经营活动产生的现金流量净额", 0)),
                    "capital_expenditure": abs(_to_float(latest_cashflow.get(_CAPEX_FIELDS[0], 0))),
                },
                ext_prev,
            )
            cluster_extras.update(derived)
        except Exception as exc:
            logger.warning("derived metrics computation failed: {err}", err=exc)

        agent_metrics.update(cluster_extras)

        logger.info("✓ Indicators built for {s}", s=symbol)
        return [agent_metrics]

    except Exception as e:
        logger.error("Error getting financial metrics: {err}", err=e)
        return [_default_agent_metrics()]


def get_financial_statements(
    symbol: str,
    *,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get financial statement data (balance sheet, income, cash flow)."""
    logger.info("Getting financial statements for {s}...", s=symbol)
    refresh = get_cache_refresh_flag("market_data_agent", "financial_reports")
    cutoff = None
    if as_of_date:
        try:
            cutoff = pd.to_datetime(as_of_date)
        except Exception:
            cutoff = None

    def _get_report(report_type: str) -> pd.DataFrame:
        try:
            df = get_financial_report(symbol, report_type, force_refresh=refresh)
            if cutoff is not None and not df.empty and "报告日" in df.columns:
                try:
                    df["报告日"] = pd.to_datetime(df["报告日"])
                    df = df[df["报告日"] <= cutoff]
                except Exception:
                    pass
            if "报告日" in df.columns:
                df = df.sort_values("报告日", ascending=False)
            return df
        except Exception:
            return pd.DataFrame()

    def _safe_get(df: pd.DataFrame, idx: int, key: str, default: float = 0.0) -> float:
        if df.empty or idx >= len(df):
            return default
        return _to_float(df.iloc[idx].get(key, default), default)

    def _safe_get_any(df: pd.DataFrame, idx: int, keys: list[str], default: float = 0.0) -> float:
        """Try multiple candidate field names; return first non-zero match.

        Different data sources (Sina vs THS) and different stocks use slightly
        different field names (e.g., '支付的现金' vs '所支付的现金'). Try each
        candidate in order and return the first non-zero value.
        """
        if df.empty or idx >= len(df):
            return default
        row = df.iloc[idx]
        for k in keys:
            if k in row:
                val = _to_float(row.get(k), default)
                if val != 0.0:
                    return val
        return default

    balance_sheet = _get_report(_REPORT_BALANCE_SHEET)
    income_statement = _get_report(_REPORT_INCOME_STATEMENT)
    cash_flow = _get_report(_REPORT_CASH_FLOW)

    # Field name candidates: Sina and THS use slightly different names for the same concept.
    _CAPEX_FIELDS = [
        "购建固定资产、无形资产和其他长期资产支付的现金",  # 新浪(部分股票)
        "购建固定资产、无形资产和其他长期资产所支付的现金",  # 新浪(601728 等,带"所")
    ]
    _DEPRECIATION_FIELDS = [
        "固定资产折旧、油气资产折耗、生产性生物资产折旧",  # 新浪间接法
        "固定资产折旧、油气资产折耗和生产性生物资产折旧",  # 同花顺
        "资产折旧、摊销",  # 简化版
    ]

    def _build_item(idx: int) -> dict[str, float]:
        return {
            "net_income": _safe_get(income_statement, idx, "净利润"),
            "operating_revenue": _safe_get(income_statement, idx, "营业总收入"),
            "operating_profit": _safe_get(income_statement, idx, "营业利润"),
            "working_capital": _safe_get(balance_sheet, idx, "流动资产合计")
            - _safe_get(balance_sheet, idx, "流动负债合计"),
            "depreciation_and_amortization": _safe_get_any(cash_flow, idx, _DEPRECIATION_FIELDS),
            "capital_expenditure": abs(_safe_get_any(cash_flow, idx, _CAPEX_FIELDS)),
            "free_cash_flow": _safe_get(cash_flow, idx, "经营活动产生的现金流量净额")
            - abs(_safe_get_any(cash_flow, idx, _CAPEX_FIELDS)),
        }

    return [_build_item(0), _build_item(1)]


def _safe_div(numerator: float, denominator: float | None) -> float:
    """Safe division returning 0.0 on zero / None denominator."""
    if denominator is None or denominator == 0:
        return 0.0
    return numerator / denominator


def _compute_derived_metrics(latest: dict, prev: dict | None) -> dict:
    """从三表字段计算衍生指标。latest/prev 为 _build_item 风格的 dict。

    返回字段: adj_debt_to_asset, net_debt_to_equity, cash_to_short_debt,
    inventory_turnover, asset_turnover, asset_turnover_prev,
    capex_to_depreciation, receivable_to_revenue, sales_expense_ratio,
    ocf_to_net_profit, free_cash_flow, capex_to_ocf, gross_margin,
    gross_margin_prev.
    """
    if not latest:
        return {}
    result: dict[str, float] = {}

    total_liab = _to_float(latest.get("total_liabilities", 0))
    total_assets = _to_float(latest.get("total_assets", 0))
    advance = _to_float(latest.get("advance_from_customers", 0))
    if total_assets - advance > 0:
        result["adj_debt_to_asset"] = _safe_div(total_liab - advance, total_assets - advance)

    short_loan = _to_float(latest.get("short_term_loan", 0))
    long_loan = _to_float(latest.get("long_term_loan", 0))
    bonds = _to_float(latest.get("bonds_payable", 0))
    cash = _to_float(latest.get("monetary_capital", 0))
    equity = _to_float(latest.get("total_equity", 0))
    if equity > 0:
        result["net_debt_to_equity"] = _safe_div(short_loan + long_loan + bonds - cash, equity)
    if short_loan > 0:
        result["cash_to_short_debt"] = _safe_div(cash, short_loan)

    op_cost = _to_float(latest.get("operating_cost", 0))
    inv = _to_float(latest.get("inventory", 0))
    prev_inv = _to_float(prev.get("inventory", 0)) if prev else 0
    avg_inv = (inv + prev_inv) / 2 if (inv + prev_inv) > 0 else 0
    if avg_inv > 0:
        result["inventory_turnover"] = _safe_div(op_cost, avg_inv)

    revenue = _to_float(latest.get("operating_revenue", 0))
    if total_assets > 0:
        result["asset_turnover"] = _safe_div(revenue, total_assets)
    if prev:
        prev_revenue = _to_float(prev.get("operating_revenue", 0))
        prev_assets = _to_float(prev.get("total_assets", 0))
        if prev_assets > 0:
            result["asset_turnover_prev"] = _safe_div(prev_revenue, prev_assets)

    dep = _to_float(latest.get("depreciation_and_amortization", 0))
    capex = _to_float(latest.get("capital_expenditure", 0))
    if dep > 0:
        result["capex_to_depreciation"] = _safe_div(capex, dep)

    receivable = _to_float(latest.get("accounts_receivable", 0))
    if revenue > 0:
        result["receivable_to_revenue"] = _safe_div(receivable, revenue)

    sales_exp = _to_float(latest.get("sales_expense", 0))
    if revenue > 0:
        result["sales_expense_ratio"] = _safe_div(sales_exp, revenue)

    ocf = _to_float(latest.get("operating_cash_flow", 0))
    net_inc = _to_float(latest.get("net_income", 0))
    if net_inc > 0:
        result["ocf_to_net_profit"] = _safe_div(ocf, net_inc)
    result["free_cash_flow"] = ocf - capex
    if ocf > 0:
        result["capex_to_ocf"] = _safe_div(capex, ocf)

    op_cost_for_gm = _to_float(latest.get("operating_cost", 0))
    if revenue > 0:
        result["gross_margin"] = _safe_div(revenue - op_cost_for_gm, revenue)
    if prev:
        prev_revenue_gm = _to_float(prev.get("operating_revenue", 0))
        prev_cost = _to_float(prev.get("operating_cost", 0))
        if prev_revenue_gm > 0:
            result["gross_margin_prev"] = _safe_div(prev_revenue_gm - prev_cost, prev_revenue_gm)

    return result


def _extract_extended_balance_sheet_fields(balance_df, idx: int = 0) -> dict:
    """从资产负债表提取扩展字段。"""
    if balance_df is None or balance_df.empty or idx >= len(balance_df):
        return {}
    row = balance_df.iloc[idx]
    _candidates = {
        "total_liabilities": ["负债合计", "负债总计"],
        "total_assets": ["资产总计", "资产合计"],
        "total_equity": ["所有者权益合计", "股东权益合计", "净资产合计"],
        "advance_from_customers": ["预收款项", "预收账款", "合同负债"],
        "inventory": ["存货"],
        "accounts_receivable": ["应收账款", "应收帐款"],
        "short_term_loan": ["短期借款"],
        "long_term_loan": ["长期借款"],
        "bonds_payable": ["应付债券"],
        "monetary_capital": ["货币资金"],
    }
    result = {}
    for key, candidates in _candidates.items():
        for c in candidates:
            if c in row:
                result[key] = _to_float(row.get(c), 0)
                break
    return result


def _extract_extended_income_fields(income_df, idx: int = 0) -> dict:
    """从利润表提取扩展字段。"""
    if income_df is None or income_df.empty or idx >= len(income_df):
        return {}
    row = income_df.iloc[idx]
    _candidates = {
        "operating_cost": ["营业成本", "营业总成本"],
        "sales_expense": ["销售费用"],
        "operating_revenue": ["营业总收入", "营业收入"],
        "net_income": ["净利润"],
    }
    result = {}
    for key, candidates in _candidates.items():
        for c in candidates:
            if c in row:
                result[key] = _to_float(row.get(c), 0)
                break
    return result


def get_market_data(
    symbol: str,
    *,
    trace_state: dict | None = None,
    as_of_date: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get market data (market cap, volume, etc.).

    Market cap priority:
      1. Baidu valuation endpoint (stock_zh_valuation_baidu, via get_valuation_indicator)
      2. LLM-generated snapshot (get_market_snapshot)
    """
    try:
        # 1. Try Baidu valuation first for market cap (stable, single-ticker)
        valuation = get_valuation_indicator(symbol)
        market_cap = _to_float(valuation.get("market_cap", 0.0)) if valuation else 0.0

        # 2. Fall back to LLM snapshot
        if market_cap <= 0:
            if snapshot is None:
                snapshot = get_market_snapshot(
                    symbol, trace_state=trace_state, agent_name="market_data_agent", as_of_date=as_of_date,
                )
            market_cap = snapshot.get("market_cap", 0.0) if snapshot else 0.0
            volume = snapshot.get("volume", 0.0) if snapshot else 0.0
            avg_vol = snapshot.get("average_volume", volume) if snapshot else 0.0
            high = snapshot.get("fifty_two_week_high", 0.0) if snapshot else 0.0
            low = snapshot.get("fifty_two_week_low", 0.0) if snapshot else 0.0
            summary = str(snapshot.get("summary", "")) if snapshot else ""
            confidence = float(snapshot.get("confidence", 0.0)) if snapshot else 0.0
            news_count = int(snapshot.get("news_count", 0)) if snapshot else 0
        else:
            volume = 0.0
            avg_vol = 0.0
            high = 0.0
            low = 0.0
            summary = ""
            confidence = 0.0
            news_count = 0

        return {
            "market_cap": market_cap,
            "volume": volume,
            "average_volume": avg_vol,
            "fifty_two_week_high": high,
            "fifty_two_week_low": low,
            "summary": summary,
            "confidence": confidence,
            "news_count": news_count,
        }
    except Exception as e:
        logger.error("Error getting market data: {err}", err=e)
        return {}


def get_price_history(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Get historical price data with technical indicators."""
    try:
        current_date = datetime.now()
        yesterday = current_date - timedelta(days=1)

        if not end_date:
            end_date_obj = yesterday
        else:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
            if end_date_obj > yesterday:
                end_date_obj = yesterday

        if not start_date:
            start_date_obj = end_date_obj - timedelta(days=365)
        else:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")

        logger.info("Getting price history for {s} [{start} -> {end}]",
                     s=symbol, start=start_date_obj.strftime("%Y-%m-%d"),
                     end=end_date_obj.strftime("%Y-%m-%d"))

        refresh = get_cache_refresh_flag("market_data_agent", "price_history")

        def _fetch(start, end):
            df = get_price_history_df(
                symbol=symbol,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                adjust=adjust,
                force_refresh=refresh,
            )
            if df is not None and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
            return df

        df = _fetch(start_date_obj, end_date_obj)
        if df is None or df.empty:
            logger.warning("No price history for {s}", s=symbol)
            return pd.DataFrame()

        min_required_days = 120
        widen_performed = False
        if len(df) < min_required_days:
            logger.warning("Insufficient data ({n} days), extending range...", n=len(df))
            wider_start = end_date_obj - timedelta(days=730)
            df = _fetch(wider_start, end_date_obj)
            widen_performed = True

        df["momentum_1m"] = df["close"].pct_change(periods=20)
        df["momentum_3m"] = df["close"].pct_change(periods=60)
        df["momentum_6m"] = df["close"].pct_change(periods=120)
        df["volume_ma20"] = df["volume"].rolling(window=20).mean()
        df["volume_momentum"] = df["volume"] / df["volume_ma20"].replace(0, pd.NA)

        returns = df["close"].pct_change()
        df["historical_volatility"] = returns.rolling(window=20).std() * np.sqrt(252)

        vol_120d = returns.rolling(window=120).std() * np.sqrt(252)
        vol_min = vol_120d.rolling(window=120).min()
        vol_max = vol_120d.rolling(window=120).max()
        vol_range = vol_max - vol_min
        df["volatility_regime"] = np.where(
            vol_range > 0, (df["historical_volatility"] - vol_min) / vol_range, 0
        )
        vol_mean = df["historical_volatility"].rolling(window=120).mean()
        vol_std = df["historical_volatility"].rolling(window=120).std()
        df["volatility_z_score"] = (df["historical_volatility"] - vol_mean) / vol_std.replace(0, pd.NA)

        tr = pd.DataFrame({
            "h-l": df["high"] - df["low"],
            "h-pc": abs(df["high"] - df["close"].shift(1)),
            "l-pc": abs(df["low"] - df["close"].shift(1)),
        }).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()
        df["atr_ratio"] = df["atr"] / df["close"].replace(0, pd.NA)

        log_returns = np.log(df["close"] / df["close"].shift(1))
        df["hurst_exponent"] = log_returns.rolling(window=120, min_periods=60).apply(
            _calculate_hurst, raw=False
        )
        df["skewness"] = returns.rolling(window=20).skew()
        df["kurtosis"] = returns.rolling(window=20).kurt()

        if widen_performed:
            original_mask = (df["date"] >= pd.Timestamp(start_date_obj)) & (
                df["date"] <= pd.Timestamp(end_date_obj)
            )
            df = df.loc[original_mask].copy()
            logger.info(
                "Widen range trimmed back to original window: {n} rows for {s}",
                n=len(df), s=symbol,
            )

        df = df.sort_values("date").reset_index(drop=True)
        logger.info("Price history fetched: {n} records for {s}", n=len(df), s=symbol)
        return df

    except Exception as e:
        logger.error("Error getting price history: {err}", err=e)
        return pd.DataFrame()


def _calculate_hurst(series: pd.Series) -> float:
    """Calculate Hurst exponent for a price series."""
    try:
        series = series.dropna()
        if len(series) < 30:
            return 0.5
        log_returns = np.log(series / series.shift(1)).dropna()
        if len(log_returns) < 30:
            return 0.5
        lags = range(2, min(11, len(log_returns) // 4))
        tau = []
        for lag in lags:
            std = log_returns.rolling(window=lag).std().dropna()
            if len(std) > 0:
                tau.append(np.mean(std))
        if len(tau) < 3:
            return 0.5
        reg = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        h = reg[0] / 2.0
        if np.isnan(h) or np.isinf(h):
            return 0.5
        return max(0.0, min(1.0, h))
    except Exception:
        return 0.5


def prices_to_df(prices: list | pd.DataFrame) -> pd.DataFrame:
    """Convert price data to a standardized DataFrame."""
    try:
        if isinstance(prices, pd.DataFrame):
            return prices
        df = pd.DataFrame(prices)
        column_mapping = {
            "收盘": "close",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "change_percent",
            "涨跌额": "change_amount",
            "换手率": "turnover_rate",
        }
        for cn, en in column_mapping.items():
            if cn in df.columns:
                df[en] = df[cn]
        for col in ["close", "open", "high", "low", "volume"]:
            if col not in df.columns:
                df[col] = 0.0
        return df
    except Exception as e:
        logger.error("Error converting price data: {err}", err=e)
        return pd.DataFrame(columns=["close", "open", "high", "low", "volume"])


def get_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Convenience wrapper for get_price_history."""
    return get_price_history(ticker, start_date, end_date)
