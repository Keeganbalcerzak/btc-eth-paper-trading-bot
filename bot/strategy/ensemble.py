from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from bot.models import Quote, Signal
from bot.strategy.indicators import (
    adx,
    clip_score,
    donchian,
    ema,
    macd,
    realized_volatility,
    require_close_series,
    rolling_zscore,
    roc,
    rsi,
    trend_strength,
)


@dataclass(frozen=True)
class StrategyConfig:
    entry_threshold: float = 0.35
    exit_threshold: float = 0.10
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "momentum": 0.45,
            "breakout": 0.15,
            "macd": 0.15,
            "mean_reversion": 0.20,
            "reactivity": 0.10,
            "volatility": 0.10,
        }
    )
    adx_period: int = 14
    adx_trend_threshold: float = 25.0
    trend_boost: float = 1.30
    trend_cut: float = 0.70


class EnsembleStrategy:
    """Deterministic long/cash ensemble for BTC and ETH."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    def score(
        self,
        symbol: str,
        bars_by_timeframe: dict[str, pd.DataFrame],
        quote: Quote | None = None,
    ) -> Signal:
        base_bars = self._select_base_bars(bars_by_timeframe)
        timestamp = self._latest_timestamp(base_bars)

        components = {
            "momentum": self.time_series_momentum(bars_by_timeframe),
            "breakout": self.breakout(base_bars),
            "macd": self.macd_trend(base_bars),
            "mean_reversion": self.mean_reversion(base_bars),
            "reactivity": self.quick_reactivity(base_bars, quote),
            "volatility": self.volatility_regime(base_bars),
        }
        weights = self._regime_weights(base_bars)
        weighted_sum = sum(weights[name] * components[name] for name in weights)
        weight_total = sum(abs(value) for value in weights.values())
        weighted = weighted_sum / weight_total if weight_total else 0.0
        return Signal(symbol=symbol, score=clip_score(weighted), components=components, timestamp=timestamp)

    def time_series_momentum(self, bars_by_timeframe: dict[str, pd.DataFrame]) -> float:
        lookbacks = {"15Min": 20, "1Hour": 24, "6Hour": 20}
        scores: list[float] = []
        for timeframe, lookback in lookbacks.items():
            bars = bars_by_timeframe.get(timeframe)
            if bars is None or len(bars) < lookback + 1:
                continue
            close = require_close_series(bars)
            fast = ema(close, max(lookback // 2, 2)).iloc[-1]
            slow = ema(close, lookback).iloc[-1]
            trend = np.sign(fast - slow)
            returns = roc(close, lookback).iloc[-1]
            vol = realized_volatility(close, lookback).iloc[-1]
            if vol <= 0:
                continue
            momentum = clip_score(float(returns / (vol * np.sqrt(lookback))))
            scores.append(clip_score(float((trend + momentum) / 2.0)))
        if not scores:
            return 0.0
        return clip_score(float(np.mean(scores)))

    def breakout(self, bars: pd.DataFrame) -> float:
        if len(bars) < 22:
            return 0.0
        lower, upper = donchian(bars, window=20)
        close = require_close_series(bars)
        upper_prev = upper.shift(1).iloc[-1]
        lower_prev = lower.shift(1).iloc[-1]
        latest = close.iloc[-1]
        if pd.isna(upper_prev) or pd.isna(lower_prev):
            return 0.0
        if latest > upper_prev:
            return 1.0
        if latest < lower_prev:
            return -1.0
        channel_width = upper_prev - lower_prev
        if channel_width <= 0:
            return 0.0
        midpoint = (upper_prev + lower_prev) / 2
        return clip_score(float((latest - midpoint) / (channel_width / 2)))

    def macd_trend(self, bars: pd.DataFrame) -> float:
        close = require_close_series(bars)
        if len(close) < 35:
            return 0.0
        _, _, histogram = macd(close)
        scale = close.rolling(window=50, min_periods=20).std(ddof=0).iloc[-1]
        if scale <= 0 or pd.isna(scale):
            return 0.0
        return clip_score(float(np.tanh(histogram.iloc[-1] / scale)))

    def mean_reversion(self, bars: pd.DataFrame) -> float:
        close = require_close_series(bars)
        if len(close) < 20:
            return 0.0

        latest_rsi = rsi(close, period=14).iloc[-1]
        latest_z = rolling_zscore(close, window=20).iloc[-1]
        trend = abs(trend_strength(close, lookback=20))
        if trend > 0.45 and abs(float(latest_z)) < 1.5 and 35.0 <= float(latest_rsi) <= 65.0:
            return 0.0

        rsi_score = clip_score((50.0 - float(latest_rsi)) / 25.0)
        z_score = clip_score(-float(latest_z) / 2.0)
        return clip_score((rsi_score + z_score) / 2.0)

    def quick_reactivity(self, bars: pd.DataFrame, quote: Quote | None) -> float:
        close = require_close_series(bars)
        if len(close) < 4:
            return 0.0

        returns = close.pct_change().fillna(0.0)
        latest_return = returns.iloc[-1]
        recent_vol = returns.tail(20).std(ddof=0)
        if recent_vol <= 0:
            shock_score = 0.0
        else:
            shock_score = clip_score(float(latest_return / (recent_vol * 3.0)))

        imbalance_score = 0.0
        spread_penalty = 0.0
        if quote is not None:
            total_size = quote.bid_size + quote.ask_size
            if total_size > 0:
                imbalance_score = clip_score((quote.bid_size - quote.ask_size) / total_size)
            spread_penalty = -min(max(quote.spread_bps / 100.0, 0.0), 0.5)

        return clip_score((0.55 * shock_score) + (0.35 * imbalance_score) + spread_penalty)

    def volatility_regime(self, bars: pd.DataFrame) -> float:
        close = require_close_series(bars)
        if len(close) < 40:
            return 0.0

        vol = realized_volatility(close, window=20)
        latest = vol.iloc[-1]
        baseline = vol.tail(120).median()
        if baseline <= 0:
            return 0.0
        ratio = latest / baseline
        if ratio <= 1.5:
            return 0.4
        if ratio >= 3.0:
            return -1.0
        return clip_score(0.4 - ((ratio - 1.5) / 1.5) * 1.4)

    def latest_adx(self, bars: pd.DataFrame) -> float:
        if len(bars) < self.config.adx_period + 2:
            return 0.0
        return float(adx(bars, period=self.config.adx_period).iloc[-1])

    def _regime_weights(self, bars: pd.DataFrame) -> dict[str, float]:
        latest_adx = self.latest_adx(bars)
        trending = latest_adx >= self.config.adx_trend_threshold
        weights = dict(self.config.weights)
        trend_names = {"momentum", "breakout", "macd"}
        reversion_names = {"mean_reversion"}

        for name in trend_names:
            weights[name] = weights.get(name, 0.0) * (
                self.config.trend_boost if trending else self.config.trend_cut
            )
        for name in reversion_names:
            weights[name] = weights.get(name, 0.0) * (
                self.config.trend_cut if trending else self.config.trend_boost
            )
        return weights

    @staticmethod
    def _select_base_bars(bars_by_timeframe: dict[str, pd.DataFrame]) -> pd.DataFrame:
        for timeframe in ("15Min", "1Hour", "6Hour"):
            bars = bars_by_timeframe.get(timeframe)
            if bars is not None and not bars.empty:
                return bars
        raise ValueError("at least one non-empty bars dataframe is required")

    @staticmethod
    def _latest_timestamp(bars: pd.DataFrame) -> datetime:
        if "timestamp" in bars and not bars["timestamp"].empty:
            value = bars["timestamp"].iloc[-1]
            if isinstance(value, pd.Timestamp):
                return value.to_pydatetime()
            if isinstance(value, datetime):
                return value
        return datetime.now(UTC)
