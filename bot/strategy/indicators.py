from __future__ import annotations

import numpy as np
import pandas as pd


def clip_score(value: float) -> float:
    if np.isnan(value) or np.isinf(value):
        return 0.0
    return float(np.clip(value, -1.0, 1.0))


def require_close_series(bars: pd.DataFrame) -> pd.Series:
    if "close" not in bars:
        raise ValueError("bars must include a close column")
    close = pd.to_numeric(bars["close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("bars must include at least one valid close")
    return close


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(50.0)


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def roc(close: pd.Series, period: int) -> pd.Series:
    return close.pct_change(period)


def rolling_zscore(close: pd.Series, window: int = 20) -> pd.Series:
    mean = close.rolling(window=window, min_periods=max(window // 2, 2)).mean()
    std = close.rolling(window=window, min_periods=max(window // 2, 2)).std(ddof=0)
    return ((close - mean) / std.replace(0, np.nan)).fillna(0.0)


def realized_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    returns = close.pct_change().fillna(0.0)
    return returns.rolling(window=window, min_periods=max(window // 2, 2)).std(ddof=0).fillna(0.0)


def true_range(bars: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(bars["high"], errors="coerce")
    low = pd.to_numeric(bars["low"], errors="coerce")
    close = pd.to_numeric(bars["close"], errors="coerce")
    previous_close = close.shift(1)
    ranges = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1).fillna(0.0)


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(bars).ewm(alpha=1 / period, min_periods=period, adjust=False).mean().fillna(0.0)


def donchian(bars: pd.DataFrame, window: int = 20) -> tuple[pd.Series, pd.Series]:
    low = pd.to_numeric(bars["low"], errors="coerce")
    high = pd.to_numeric(bars["high"], errors="coerce")
    lower = low.rolling(window=window, min_periods=window).min()
    upper = high.rolling(window=window, min_periods=window).max()
    return lower, upper


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal_period)
    return macd_line, signal_line, macd_line - signal_line


def adx(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(bars["high"], errors="coerce")
    low = pd.to_numeric(bars["low"], errors="coerce")
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move.clip(lower=0)
    average_true_range = true_range(bars).ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / average_true_range)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / average_true_range)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0).clip(0, 100)


def trend_strength(close: pd.Series, lookback: int = 20) -> float:
    if len(close) < lookback + 1:
        return 0.0
    returns = close.pct_change(lookback).iloc[-1]
    vol = realized_volatility(close, lookback).iloc[-1]
    if vol <= 0:
        return 0.0
    return clip_score(float(returns / (vol * np.sqrt(lookback))))
