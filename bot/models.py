from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class DecisionReason(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    HOLD = "hold"
    RISK_BLOCK = "risk_block"
    KILL_SWITCH = "kill_switch"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    bid_size: float = 0.0
    ask_size: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        if self.mid <= 0:
            return float("inf")
        return ((self.ask - self.bid) / self.mid) * 10_000

    def age_seconds(self, now: datetime | None = None) -> float:
        reference = now or datetime.now(UTC)
        return max((reference - self.timestamp).total_seconds(), 0.0)


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    score: float
    components: dict[str, float]
    timestamp: datetime

    def clipped(self) -> "Signal":
        return Signal(
            symbol=self.symbol,
            score=max(min(self.score, 1.0), -1.0),
            components={key: max(min(value, 1.0), -1.0) for key, value in self.components.items()},
            timestamp=self.timestamp,
        )


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_entry_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.qty > 0

    def market_value(self, price: float) -> float:
        return self.qty * price

    def unrealized_pnl_pct(self, price: float) -> float:
        if not self.is_open or self.avg_entry_price <= 0:
            return 0.0
        return (price - self.avg_entry_price) / self.avg_entry_price


@dataclass
class Portfolio:
    cash: float
    equity: float
    starting_equity: float
    day_start_equity: float
    positions: dict[str, Position] = field(default_factory=dict)

    def position_for(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol=symbol))

    @property
    def total_drawdown_pct(self) -> float:
        if self.starting_equity <= 0:
            return 0.0
        return max((self.starting_equity - self.equity) / self.starting_equity, 0.0)

    @property
    def daily_drawdown_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return max((self.day_start_equity - self.equity) / self.day_start_equity, 0.0)


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    notional: float | None = None
    qty: float | None = None
    client_order_id: str | None = None
    order_type: str = "market"
    time_in_force: str = "gtc"


@dataclass(frozen=True)
class OrderResult:
    id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    status: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class TradeDecision:
    symbol: str
    side: OrderSide
    reason: DecisionReason
    signal_score: float
    notional: float
    timestamp: datetime
    blocked: bool = False
    details: dict[str, Any] = field(default_factory=dict)
