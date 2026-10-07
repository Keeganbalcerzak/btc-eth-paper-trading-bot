from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from bot.factory import build_bot
from bot.config import get_settings
from bot.execution import AlpacaPaperExecutor
from bot.ingestion import AlpacaDataClient, bars_to_dataframe
from bot.risk import RiskManager
from bot.strategy import EnsembleStrategy


def build_components():
    settings = get_settings()
    settings.assert_paper_execution()
    data = AlpacaDataClient(
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
        data_base_url=str(settings.alpaca_data_base_url),
    )
    executor = AlpacaPaperExecutor(
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
        trading_base_url=str(settings.alpaca_trading_base_url),
        paper=settings.alpaca_paper,
    )
    return settings, data, executor, EnsembleStrategy(), RiskManager()


def backfill_once(days: int = 30) -> None:
    settings, data, _, _, _ = build_components()
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    for symbol in settings.bot_symbols:
        bars = data.historical_bars(symbol, settings.bot_timeframe, start=start, end=end)
        frame = bars_to_dataframe(bars)
        print(f"{symbol}: backfilled {len(frame)} {settings.bot_timeframe} bars")


def main() -> None:
    parser = argparse.ArgumentParser(description="BTC/ETH paper bot runner")
    parser.add_argument(
        "command",
        choices=("backfill", "trade"),
        help="Run one operational command. API mode is served with uvicorn.",
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one paper-trading cycle and exit.",
    )
    args = parser.parse_args()

    if args.command == "backfill":
        backfill_once(days=args.days)
    elif args.command == "trade":
        bot = build_bot()
        if args.once:
            decisions = bot.cycle_once()
            for decision in decisions:
                print(
                    f"{decision.timestamp.isoformat()} {decision.symbol} "
                    f"{decision.side.value} {decision.reason.value} "
                    f"score={decision.signal_score:.3f} notional={decision.notional:.2f}"
                )
        else:
            bot.run_forever()


if __name__ == "__main__":
    main()
