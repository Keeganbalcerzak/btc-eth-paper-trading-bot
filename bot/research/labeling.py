from __future__ import annotations

import pandas as pd

from bot.strategy.indicators import atr


def triple_barrier_labels(
    bars: pd.DataFrame,
    holding_period: int = 20,
    profit_atr: float = 2.0,
    stop_atr: float = 1.0,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Label historical signals with profit, stop, and vertical barriers.

    Labels are for offline research only:
    - `1`: profit barrier touched first.
    - `-1`: stop barrier touched first.
    - `0`: neither barrier touched before the vertical time limit.

    If both price barriers touch on the same bar, this uses the conservative
    stop-first label because intrabar order cannot be known from OHLC bars.
    """

    required = {"timestamp", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")
    if holding_period <= 0:
        raise ValueError("holding_period must be positive")

    history = bars.sort_values("timestamp").reset_index(drop=True).copy()
    volatility = atr(history, period=atr_period)
    rows: list[dict[str, object]] = []

    for index, row in history.iterrows():
        entry_price = float(row["close"])
        barrier_width = float(volatility.iloc[index])
        if barrier_width <= 0:
            rows.append(_neutral_row(history, index, entry_price, holding_period))
            continue

        upper = entry_price + (profit_atr * barrier_width)
        lower = entry_price - (stop_atr * barrier_width)
        end_index = min(index + holding_period, len(history) - 1)
        label = 0
        touch_index = end_index
        exit_price = float(history.loc[end_index, "close"])

        for future_index in range(index + 1, end_index + 1):
            future = history.loc[future_index]
            if float(future["low"]) <= lower:
                label = -1
                touch_index = future_index
                exit_price = lower
                break
            if float(future["high"]) >= upper:
                label = 1
                touch_index = future_index
                exit_price = upper
                break

        rows.append(
            {
                "timestamp": row["timestamp"],
                "label": label,
                "first_touch_timestamp": history.loc[touch_index, "timestamp"],
                "vertical_timestamp": history.loc[end_index, "timestamp"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return_pct": (exit_price / entry_price) - 1 if entry_price else 0.0,
                "upper_barrier": upper,
                "lower_barrier": lower,
            }
        )

    return pd.DataFrame(rows)


def _neutral_row(
    history: pd.DataFrame,
    index: int,
    entry_price: float,
    holding_period: int,
) -> dict[str, object]:
    end_index = min(index + holding_period, len(history) - 1)
    exit_price = float(history.loc[end_index, "close"])
    return {
        "timestamp": history.loc[index, "timestamp"],
        "label": 0,
        "first_touch_timestamp": history.loc[end_index, "timestamp"],
        "vertical_timestamp": history.loc[end_index, "timestamp"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "return_pct": (exit_price / entry_price) - 1 if entry_price else 0.0,
        "upper_barrier": entry_price,
        "lower_barrier": entry_price,
    }
