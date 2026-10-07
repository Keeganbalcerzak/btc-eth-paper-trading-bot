from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from bot.models import Bar


def is_stale(last_seen: datetime | None, max_age_seconds: int, now: datetime | None = None) -> bool:
    if last_seen is None:
        return True
    reference = now or datetime.now(UTC)
    return (reference - last_seen).total_seconds() > max_age_seconds


def bars_to_dataframe(bars: list[Bar]) -> pd.DataFrame:
    rows = [
        {
            "symbol": bar.symbol,
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
