from valor.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from valor.tools.api import get_financial_metrics, get_financial_statements, get_market_data, get_price_history
from valor.tools.market_snapshot import get_market_snapshot
from valor.tools.summary import build_financial_summary, build_prices_summary
from valor.utils.logging_config import setup_logger
from valor.utils.api_utils import agent_endpoint
from valor.adapters.data.akshare_cache import get_latest_trading_day

from datetime import datetime, timedelta
import pandas as pd

# 设置日志记录
logger = setup_logger('market_data_agent')


@agent_endpoint("market_data", "市场数据收集，负责获取股价历史、财务指标和市场信息")
def market_data_agent(state: AgentState):
    """Responsible for gathering and preprocessing market data"""
    show_workflow_status("Market Data Agent")
    show_reasoning = state["metadata"]["show_reasoning"]

    messages = state["messages"]
    data = state["data"]

    # Set default dates: use most recent A-share trading day (skips weekends/holidays)
    current_date = datetime.now()
    if data["end_date"]:
        end_date = data["end_date"]
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        latest = get_latest_trading_day(current_date.date())
        end_date = latest.strftime('%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

    # Ensure end_date is not in the future
    today = current_date.date()
    if end_date_obj.date() > today:
        latest = get_latest_trading_day(today)
        end_date = latest.strftime('%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

    if not data["start_date"]:
        # Calculate 1 year before end_date
        start_date = end_date_obj - timedelta(days=365)  # 默认获取一年的数据
        start_date = start_date.strftime('%Y-%m-%d')
    else:
        start_date = data["start_date"]

    # Get all required data
    ticker = data["ticker"]

    # 获取价格数据并验证
    prices_df = get_price_history(ticker, start_date, end_date)
    if prices_df is None or prices_df.empty:
        logger.warning(f"警告：无法获取{ticker}的价格数据，将使用空数据继续")
        prices_df = pd.DataFrame(
            columns=['close', 'open', 'high', 'low', 'volume'])

    # 先取一次市场快照，避免重复LLM调用
    snapshot = None
    try:
        snapshot = get_market_snapshot(
            ticker,
            trace_state=state,
            agent_name="market_data_agent",
            as_of_date=end_date,
        )
    except Exception:
        snapshot = None

    # 获取财务指标
    try:
        financial_metrics = get_financial_metrics(
            ticker,
            trace_state=state,
            as_of_date=end_date,
            snapshot=snapshot,
        )
    except Exception as e:
        logger.error(f"获取财务指标失败: {str(e)}")
        financial_metrics = {}

    # 获取财务报表
    try:
        financial_line_items = get_financial_statements(ticker, as_of_date=end_date)
    except Exception as e:
        logger.error(f"获取财务报表失败: {str(e)}")
        financial_line_items = {}

    # 获取市场数据
    try:
        market_data = get_market_data(
            ticker,
            trace_state=state,
            as_of_date=end_date,
            snapshot=snapshot,
        )
    except Exception as e:
        logger.error(f"获取市场数据失败: {str(e)}")
        market_data = {"market_cap": 0}

    # If all market cap sources failed, log warning and keep 0 (downstream agents handle missing data).
    # Previously this fell back to pe_ratio * net_income, but PE itself may come from the same
    # valuation source, creating a circular dependency. Better to surface the missing data.
    market_cap = market_data.get("market_cap", 0) or 0
    if market_cap <= 0:
        logger.warning(
            f"Market cap unavailable for {ticker} (Baidu valuation + LLM snapshot both failed); "
            "downstream valuation agent will skip gap analysis."
        )

    # 确保数据格式正确
    if not isinstance(prices_df, pd.DataFrame):
        prices_df = pd.DataFrame(
            columns=['close', 'open', 'high', 'low', 'volume'])

    # 转换价格数据为字典格式
    prices_dict = prices_df.to_dict('records')

    # 预计算摘要供 SSE/前端展示,避免全量 K 线进入 SSE/DB
    prices_summary = build_prices_summary(prices_df, start_date, end_date)
    financial_summary = build_financial_summary(financial_metrics, financial_line_items)

    # 保存推理信息到metadata供API使用
    market_data_summary = {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "data_collected": {
            "price_history": len(prices_dict) > 0,
            "financial_metrics": len(financial_metrics) > 0,
            "financial_statements": len(financial_line_items) > 0,
            "market_data": len(market_data) > 0
        },
        "summary": f"为{ticker}收集了从{start_date}到{end_date}的市场数据，包括价格历史、财务指标和市场信息"
    }

    if show_reasoning:
        show_agent_reasoning(market_data_summary, "Market Data Agent")
        state["metadata"]["agent_reasoning"] = market_data_summary

    return {
        "messages": messages,
        "data": {
            **data,
            "prices": prices_dict,
            "prices_summary": prices_summary,
            "financial_summary": financial_summary,
            "start_date": start_date,
            "end_date": end_date,
            "financial_metrics": financial_metrics,
            "financial_line_items": financial_line_items,
            "market_cap": market_data.get("market_cap", 0),
            "market_data": market_data,
        },
        "metadata": state["metadata"],
    }
