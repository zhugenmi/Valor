"""Valor CLI entry point.

Phase 1A: fetch and print data for a single ticker.
Phase 1B: run the full agent workflow.

License: GPL-3.0-or-later WITH GPL-3.0-NonCommercial
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from loguru import logger

from valor.adapters.data.akshare_adapter import AkShareAdapter
from valor.adapters.data.baostock_adapter import BaoStockAdapter
from valor.adapters.data.router import DataRouter


def get_data_router() -> DataRouter:
    """Construct the default DataRouter (AkShare primary, BaoStock fallback for history)."""
    akshare = AkShareAdapter()
    baostock = BaoStockAdapter()
    return DataRouter(
        primary=akshare,
        sources={"akshare": akshare, "baostock": baostock},
        fallbacks_by_method={"get_daily_history": ["baostock"]},
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="valor")
    parser.add_argument("--ticker", required=True, help="A-share ticker, e.g. 600519")
    parser.add_argument("--show-reasoning", action="store_true", help="Verbose output")
    parser.add_argument("--model", default="auto", help="LLM model name")
    parser.add_argument(
        "--start-date",
        default="",
        help="Analysis start date (YYYY-MM-DD, auto if omitted)",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Analysis end date (YYYY-MM-DD, auto if omitted)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the full agent workflow instead of fetching raw data",
    )
    parser.add_argument(
        "--portfolio-cash",
        type=float,
        default=100000.0,
        help="Cash in portfolio for risk calculation",
    )
    parser.add_argument(
        "--portfolio-stock",
        type=float,
        default=0,
        help="Shares held for position sizing",
    )
    return parser.parse_args(argv)


async def _run_fetch(args: argparse.Namespace) -> int:
    """Phase 1A: fetch and print raw data."""
    router = get_data_router()
    df = await router.get_realtime_quote(args.ticker)
    if df.empty:
        logger.warning(
            "No realtime data for {ticker}, falling back to recent daily history",
            ticker=args.ticker,
        )
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=10)
        df = await router.get_daily_history(
            args.ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
    if df.empty:
        logger.warning("No data for {ticker}", ticker=args.ticker)
        return 1
    print(df.to_string(index=False))
    return 0


def _run_workflow(args: argparse.Namespace) -> int:
    """Phase 1B: run the full agent workflow."""
    from valor.agents.workflow import run_analysis

    portfolio = {
        "cash": args.portfolio_cash,
        "stock": args.portfolio_stock,
    }

    result = run_analysis(
        ticker=args.ticker,
        start_date=args.start_date or None,
        end_date=args.end_date or None,
        portfolio=portfolio,
        show_reasoning=args.show_reasoning,
        model=args.model,
    )

    # Extract final message (portfolio manager decision)
    final_message = None
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "name") and msg.name == "portfolio_management_agent":
            final_message = msg
            break
        elif hasattr(msg, "name") and msg.name == "portfolio_management_agent":
            final_message = msg
            break

    if final_message:
        try:
            content = json.loads(final_message.content)
            print(
                json.dumps(
                    {"ticker": args.ticker, "decision": content},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception:
            print(final_message.content)
    else:
        # Dump all messages
        output = {}
        for msg in result.get("messages", []):
            name = getattr(msg, "name", "unknown")
            try:
                output[name] = json.loads(msg.content)
            except Exception:
                output[name] = str(msg.content)
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    if args.run:
        return _run_workflow(args)
    return asyncio.run(_run_fetch(args))


if __name__ == "__main__":
    sys.exit(main())
