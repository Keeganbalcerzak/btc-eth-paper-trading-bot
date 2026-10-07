from __future__ import annotations

from bot.models import Quote
from bot.strategy import EnsembleStrategy
from bot.strategy.indicators import adx, atr


def test_ensemble_score_is_clipped_and_positive_for_trend(trending_bars, now):
    strategy = EnsembleStrategy()
    quote = Quote("BTC/USD", bid=140.0, ask=140.1, bid_size=5, ask_size=4, timestamp=now)

    signal = strategy.score(
        "BTC/USD",
        {"15Min": trending_bars, "1Hour": trending_bars.iloc[::4], "6Hour": trending_bars.iloc[::24]},
        quote,
    )

    assert -1 <= signal.score <= 1
    assert signal.score > 0
    assert set(signal.components) == {
        "momentum",
        "breakout",
        "macd",
        "mean_reversion",
        "reactivity",
        "volatility",
    }
    assert all(-1 <= value <= 1 for value in signal.components.values())


def test_mean_reversion_prefers_oversold_range(trending_bars):
    ranged = trending_bars.copy()
    ranged["close"] = 100 + (ranged.index % 6) * 0.1
    ranged.loc[ranged.index[-3:], "close"] = [99.6, 99.3, 99.0]

    score = EnsembleStrategy().mean_reversion(ranged)

    assert score > 0


def test_reactivity_penalizes_wide_spread(trending_bars, now):
    strategy = EnsembleStrategy()
    tight = Quote("BTC/USD", bid=100.0, ask=100.1, bid_size=8, ask_size=1, timestamp=now)
    wide = Quote("BTC/USD", bid=95.0, ask=105.0, bid_size=8, ask_size=1, timestamp=now)

    tight_score = strategy.quick_reactivity(trending_bars, tight)
    wide_score = strategy.quick_reactivity(trending_bars, wide)

    assert wide_score < tight_score


def test_adx_and_atr_stay_in_expected_ranges(trending_bars):
    trend_strength = adx(trending_bars)
    volatility = atr(trending_bars)

    assert trend_strength.between(0, 100).all()
    assert (volatility >= 0).all()


def test_regime_weights_boost_trend_strategies_in_trending_market(trending_bars):
    strategy = EnsembleStrategy()

    weights = strategy._regime_weights(trending_bars)

    assert weights["momentum"] > strategy.config.weights["momentum"]
    assert weights["mean_reversion"] < strategy.config.weights["mean_reversion"]


def test_breakout_uses_prior_channel_without_lookahead(trending_bars):
    bars = trending_bars.copy()
    bars.loc[bars.index[-1], "close"] = bars["high"].iloc[-21:-1].max() + 1

    score = EnsembleStrategy().breakout(bars)

    assert score == 1.0
