from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd


def synthetic_ohlcv(
    bars: int = 600,
    seed: int = 42,
    symbol: str = "BTC/USD",
    start_price: float = 30_000.0,
    timeframe_minutes: int = 15,
) -> pd.DataFrame:
    """Generate deterministic OHLCV with alternating trend and range regimes."""

    rng = np.random.default_rng(seed)
    closes = [start_price]
    block = max(50, bars // 12)
    drift_cycle = [0.0008, 0.0, -0.0006, 0.0, 0.0010, -0.0009]
    drifts = [drift_cycle[(index // block) % len(drift_cycle)] for index in range(bars)]
    volatility = 0.012

    for index in range(1, bars):
        shock = rng.normal(drifts[index], volatility)
        closes.append(max(1.0, closes[-1] * (1 + shock)))

    close = np.array(closes)
    open_ = np.empty(bars)
    open_[0] = start_price
    open_[1:] = close[:-1]
    intrabar = np.abs(rng.normal(0, volatility, bars)) * close
    high = np.maximum(open_, close) + intrabar
    low = np.maximum(np.minimum(open_, close) - intrabar, 1.0)
    volume = rng.uniform(10, 100, bars) * (1 + np.abs(close - open_) / close)
    timestamp = pd.date_range(
        datetime(2024, 1, 1, tzinfo=UTC),
        periods=bars,
        freq=f"{timeframe_minutes}min",
    )

    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
