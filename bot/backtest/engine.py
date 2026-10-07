from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from bot.models import OrderSide, Portfolio, Position, Quote, Signal
from bot.risk import RiskConfig, RiskManager
from bot.strategy.indicators import atr


StrategyFn = Callable[[str, pd.DataFrame], Signal]


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float = 10_000.0
    fee_bps: float = 25.0
    slippage_bps: float = 5.0
    synthetic_spread_bps: float = 10.0
    min_lookback: int = 40
    timeframe: str = "15Min"

    @property
    def buy_cost_multiplier(self) -> float:
        return 1 + ((self.fee_bps + self.slippage_bps + self.synthetic_spread_bps / 2) / 10_000)

    @property
    def sell_cost_multiplier(self) -> float:
        return 1 - ((self.fee_bps + self.slippage_bps + self.synthetic_spread_bps / 2) / 10_000)


@dataclass(frozen=True)
class SimulatedTrade:
    symbol: str
    side: OrderSide
    timestamp: datetime
    qty: float
    fill_price: float
    notional: float
    signal_score: float


@dataclass(frozen=True)
class BacktestResult:
    trades: list[SimulatedTrade]
    equity_curve: pd.DataFrame
    metrics: dict[str, float]


class BacktestEngine:
    def __init__(
        self,
        strategy_fn: StrategyFn,
        risk_manager: RiskManager | None = None,
        config: BacktestConfig | None = None,
    ) -> None:
        self.strategy_fn = strategy_fn
        self.risk_manager = risk_manager or RiskManager(RiskConfig())
        self.config = config or BacktestConfig()

    def run(self, bars: pd.DataFrame, symbol: str) -> BacktestResult:
        required = {"timestamp", "open", "high", "low", "close"}
        missing = required - set(bars.columns)
        if missing:
            raise ValueError(f"bars missing required columns: {sorted(missing)}")

        history = bars.sort_values("timestamp").reset_index(drop=True).copy()
        cash = self.config.starting_cash
        position = Position(symbol=symbol)
        trades: list[SimulatedTrade] = []
        equity_rows: list[dict[str, float | datetime]] = []

        for index in range(len(history)):
            current = history.iloc[index]
            timestamp = _as_datetime(current["timestamp"])
            mark_price = float(current["close"])
            equity = cash + position.market_value(mark_price)
            portfolio = Portfolio(
                cash=cash,
                equity=equity,
                starting_equity=self.config.starting_cash,
                day_start_equity=self.config.starting_cash,
                positions={symbol: position},
            )

            if index + 1 < self.config.min_lookback:
                equity_rows.append({"timestamp": timestamp, "equity": equity, "cash": cash})
                continue

            visible_history = history.iloc[: index + 1].copy()
            signal = self.strategy_fn(symbol, visible_history)
            quote = self._quote_from_bar(symbol, current, timestamp)
            atr_value = self._latest_atr(visible_history)
            decision = self.risk_manager.make_decision(
                portfolio,
                signal,
                quote,
                timestamp,
                atr_value=atr_value,
            )

            if decision.side == OrderSide.BUY and decision.notional > 0:
                fill_price = mark_price * self.config.buy_cost_multiplier
                qty = min(decision.notional, cash) / fill_price
                if qty > 0:
                    cash -= qty * fill_price
                    position = Position(symbol=symbol, qty=qty, avg_entry_price=fill_price)
                    trades.append(
                        SimulatedTrade(
                            symbol=symbol,
                            side=OrderSide.BUY,
                            timestamp=timestamp,
                            qty=qty,
                            fill_price=fill_price,
                            notional=qty * fill_price,
                            signal_score=signal.score,
                        )
                    )
            elif decision.side == OrderSide.SELL and position.is_open:
                fill_price = mark_price * self.config.sell_cost_multiplier
                notional = position.qty * fill_price
                cash += notional
                trades.append(
                    SimulatedTrade(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        timestamp=timestamp,
                        qty=position.qty,
                        fill_price=fill_price,
                        notional=notional,
                        signal_score=signal.score,
                    )
                )
                position = Position(symbol=symbol)

            equity = cash + position.market_value(mark_price)
            equity_rows.append({"timestamp": timestamp, "equity": equity, "cash": cash})

        equity_curve = pd.DataFrame(equity_rows)
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            metrics=self._metrics(equity_curve, trades, history, self.config),
        )

    def _quote_from_bar(self, symbol: str, row: pd.Series, timestamp: datetime) -> Quote:
        close = float(row["close"])
        half_spread = self.config.synthetic_spread_bps / 2 / 10_000
        return Quote(
            symbol=symbol,
            bid=close * (1 - half_spread),
            ask=close * (1 + half_spread),
            timestamp=timestamp,
            bid_size=1.0,
            ask_size=1.0,
        )

    @staticmethod
    def _latest_atr(history: pd.DataFrame) -> float | None:
        if len(history) < 15:
            return None
        value = atr(history, period=14).iloc[-1]
        if pd.isna(value) or value <= 0:
            return None
        return float(value)

    @staticmethod
    def _metrics(
        equity_curve: pd.DataFrame,
        trades: list[SimulatedTrade],
        bars: pd.DataFrame,
        config: BacktestConfig,
    ) -> dict[str, float]:
        if equity_curve.empty:
            return {"total_return_pct": 0.0, "max_drawdown_pct": 0.0, "trade_count": 0.0}
        equity = equity_curve["equity"]
        total_return = (equity.iloc[-1] / equity.iloc[0]) - 1 if equity.iloc[0] else 0.0
        rolling_peak = equity.cummax()
        drawdown = ((rolling_peak - equity) / rolling_peak.replace(0, pd.NA)).fillna(0.0)
        returns = equity.pct_change().dropna()
        bars_per_year = _bars_per_year(config.timeframe)
        volatility = returns.std(ddof=0)
        sharpe = (
            float((returns.mean() / volatility) * (bars_per_year**0.5))
            if volatility and volatility > 0
            else 0.0
        )
        buy_hold = bars["close"] / bars["close"].iloc[0] * config.starting_cash
        buy_hold_return = (buy_hold.iloc[-1] / buy_hold.iloc[0]) - 1 if buy_hold.iloc[0] else 0.0
        return {
            "total_return_pct": float(total_return),
            "max_drawdown_pct": float(drawdown.max()),
            "trade_count": float(len(trades)),
            "final_equity": float(equity.iloc[-1]),
            "annualized_volatility_pct": float(volatility * (bars_per_year**0.5)) if volatility else 0.0,
            "sharpe": sharpe,
            "buy_hold_return_pct": float(buy_hold_return),
            "bars": float(len(equity_curve)),
        }


def _as_datetime(value) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _bars_per_year(timeframe: str) -> int:
    normalized = timeframe.lower()
    return {
        "1min": 525_600,
        "5min": 105_120,
        "15min": 35_040,
        "30min": 17_520,
        "1hour": 8_760,
        "6hour": 1_460,
        "1day": 365,
    }.get(normalized, 35_040)
