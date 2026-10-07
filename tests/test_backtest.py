from __future__ import annotations

import pytest

from bot.backtest import BacktestConfig, BacktestEngine
from bot.models import Signal


def test_backtest_passes_only_visible_history_to_strategy(trending_bars):
    seen_timestamps = []

    def strategy(symbol, history):
        seen_timestamps.append(history["timestamp"].iloc[-1])
        return Signal(symbol, 0.0, {}, history["timestamp"].iloc[-1])

    engine = BacktestEngine(strategy, config=BacktestConfig(min_lookback=10))
    engine.run(trending_bars, "BTC/USD")

    expected = list(trending_bars["timestamp"].iloc[9:])
    assert seen_timestamps == expected


def test_backtest_buy_fill_includes_fee_slippage_and_spread(trending_bars):
    def strategy(symbol, history):
        return Signal(symbol, 0.8, {}, history["timestamp"].iloc[-1])

    config = BacktestConfig(
        starting_cash=10_000,
        fee_bps=25,
        slippage_bps=5,
        synthetic_spread_bps=10,
        min_lookback=10,
    )
    result = BacktestEngine(strategy, config=config).run(trending_bars, "BTC/USD")

    first_trade = result.trades[0]
    close_at_trade = float(trending_bars["close"].iloc[9])
    assert first_trade.fill_price == pytest.approx(close_at_trade * config.buy_cost_multiplier)
    assert first_trade.notional == pytest.approx(1_000.0)
    assert result.metrics["trade_count"] >= 1
    assert "buy_hold_return_pct" in result.metrics
    assert "sharpe" in result.metrics


def test_synthetic_ohlcv_exercises_backtester():
    from bot.backtest import synthetic_ohlcv

    bars = synthetic_ohlcv(bars=120, seed=7)

    def strategy(symbol, history):
        return Signal(symbol, 0.4, {}, history["timestamp"].iloc[-1])

    result = BacktestEngine(strategy, config=BacktestConfig(min_lookback=40)).run(bars, "BTC/USD")

    assert result.metrics["bars"] == len(bars)
    assert result.metrics["final_equity"] > 0
