from __future__ import annotations

from bot.config import Settings, get_settings
from bot.execution import AlpacaPaperExecutor
from bot.ingestion import AlpacaDataClient
from bot.risk import RiskConfig, RiskManager
from bot.storage import InMemoryState
from bot.strategy import EnsembleStrategy, StrategyConfig
from bot.trading_loop import PaperTradingBot, TradingLoopConfig


def build_bot(state: InMemoryState | None = None, settings: Settings | None = None) -> PaperTradingBot:
    settings = settings or get_settings()
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
    strategy = EnsembleStrategy(
        StrategyConfig(
            entry_threshold=0.35,
            exit_threshold=0.10,
        )
    )
    risk = RiskManager(
        RiskConfig(
            max_position_pct=settings.bot_max_position_pct,
            account_risk_per_trade_pct=settings.bot_account_risk_per_trade_pct,
            daily_drawdown_pct=settings.bot_daily_drawdown_pct,
            total_drawdown_pct=settings.bot_total_drawdown_pct,
            max_spread_bps=settings.bot_max_spread_bps,
            max_feed_age_seconds=settings.bot_max_feed_age_seconds,
            stop_loss_atr=settings.bot_stop_loss_atr,
            entry_threshold=0.35,
            exit_threshold=0.10,
        )
    )
    return PaperTradingBot(
        data_client=data,
        executor=executor,
        strategy=strategy,
        risk_manager=risk,
        state=state,
        config=TradingLoopConfig(
            symbols=settings.bot_symbols,
            poll_seconds=settings.bot_poll_seconds,
            backfill_days=settings.bot_backfill_days,
            min_bars=settings.bot_min_bars,
            max_orders_per_cycle=settings.bot_max_orders_per_cycle,
            max_consecutive_error_cycles=settings.bot_max_consecutive_error_cycles,
        ),
    )
