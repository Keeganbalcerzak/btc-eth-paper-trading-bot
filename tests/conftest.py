from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from bot.models import Portfolio, Position, Quote


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_bars(
    count: int = 80,
    start_price: float = 100.0,
    step: float = 0.5,
    start: datetime | None = None,
) -> pd.DataFrame:
    start = start or datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    price = start_price
    for index in range(count):
        price = price + step + float(np.sin(index / 5.0) * 0.05)
        rows.append(
            {
                "symbol": "BTC/USD",
                "timestamp": start + timedelta(minutes=15 * index),
                "open": price - 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 10.0 + index,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def trending_bars() -> pd.DataFrame:
    return make_bars()


@pytest.fixture
def normal_quote(now: datetime) -> Quote:
    return Quote(
        symbol="BTC/USD",
        bid=100.0,
        ask=100.1,
        bid_size=5.0,
        ask_size=4.0,
        timestamp=now,
    )


@pytest.fixture
def fresh_portfolio() -> Portfolio:
    return Portfolio(
        cash=10_000.0,
        equity=10_000.0,
        starting_equity=10_000.0,
        day_start_equity=10_000.0,
        positions={"BTC/USD": Position(symbol="BTC/USD")},
    )
