from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from bot.backtest import synthetic_ohlcv
from bot.research import MarketRegimeDetector, triple_barrier_labels


def test_triple_barrier_labels_emit_expected_columns_and_labels():
    bars = synthetic_ohlcv(bars=90, seed=21)

    labels = triple_barrier_labels(bars, holding_period=10, profit_atr=1.5, stop_atr=1.0)

    assert set(labels["label"].unique()).issubset({-1, 0, 1})
    assert {
        "timestamp",
        "label",
        "first_touch_timestamp",
        "vertical_timestamp",
        "entry_price",
        "exit_price",
        "return_pct",
        "upper_barrier",
        "lower_barrier",
    }.issubset(labels.columns)
    assert len(labels) == len(bars)


def test_triple_barrier_uses_conservative_stop_first_when_both_touch():
    timestamps = pd.date_range(datetime(2026, 1, 1, tzinfo=UTC), periods=25, freq="15min")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 25,
            "high": [101.0] * 25,
            "low": [99.0] * 25,
            "close": [100.0] * 25,
            "volume": [1.0] * 25,
        }
    )
    bars.loc[15, "high"] = 103.0
    bars.loc[15, "low"] = 97.0

    labels = triple_barrier_labels(
        bars,
        holding_period=5,
        profit_atr=1.0,
        stop_atr=1.0,
        atr_period=14,
    )

    assert labels.loc[14, "label"] == -1


def test_market_regime_detector_identifies_latest_high_volatility_window():
    rng = np.random.default_rng(9)
    low_vol = rng.normal(0.0002, 0.0005, 80)
    high_vol = rng.normal(0.0002, 0.03, 80)
    returns = np.concatenate([low_vol, high_vol])
    close = 100 * np.cumprod(1 + returns)
    timestamps = pd.date_range(datetime(2026, 1, 1, tzinfo=UTC), periods=len(close), freq="15min")
    bars = pd.DataFrame({"timestamp": timestamps, "close": close})

    prediction = MarketRegimeDetector(random_state=4).latest(bars)

    assert prediction.name == "high_volatility"
    assert 0 <= prediction.probability <= 1
    assert prediction.volatility > 0
