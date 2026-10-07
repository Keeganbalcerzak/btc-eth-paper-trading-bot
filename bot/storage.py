from __future__ import annotations

from collections import deque
from dataclasses import asdict
from threading import RLock
from typing import Any

import psycopg

from bot.models import OrderResult, Position, Signal, TradeDecision


class InMemoryState:
    """Small state store for local API visibility and tests."""

    def __init__(self, max_decisions: int = 200) -> None:
        self._lock = RLock()
        self._signals: dict[str, Signal] = {}
        self._positions: dict[str, Position] = {}
        self._decisions: deque[TradeDecision] = deque(maxlen=max_decisions)
        self._metrics: dict[str, float | int | str] = {
            "orders_submitted": 0,
            "orders_blocked": 0,
            "orders_acknowledged": 0,
            "orders_rejected": 0,
            "data_or_execution_errors": 0,
            "kill_switch": 0,
        }

    def record_signal(self, signal: Signal) -> None:
        with self._lock:
            self._signals[signal.symbol] = signal

    def record_position(self, position: Position) -> None:
        with self._lock:
            self._positions[position.symbol] = position

    def record_decision(self, decision: TradeDecision) -> None:
        with self._lock:
            self._decisions.appendleft(decision)
            if decision.blocked:
                self._metrics["orders_blocked"] = int(self._metrics["orders_blocked"]) + 1

    def increment_orders(self) -> None:
        with self._lock:
            self._metrics["orders_submitted"] = int(self._metrics["orders_submitted"]) + 1

    def record_order_ack(self, result: OrderResult, latency_ms: float) -> None:
        with self._lock:
            self._metrics["orders_acknowledged"] = int(self._metrics["orders_acknowledged"]) + 1
            self._metrics["last_order_status"] = result.status
            self._metrics["last_order_ack_latency_ms"] = round(latency_ms, 3)
            current_max = float(self._metrics.get("max_order_ack_latency_ms", 0.0))
            self._metrics["max_order_ack_latency_ms"] = round(max(current_max, latency_ms), 3)
            if result.status.lower() in {"rejected", "canceled", "expired"}:
                self._metrics["orders_rejected"] = int(self._metrics["orders_rejected"]) + 1

    def increment_errors(self) -> None:
        with self._lock:
            self._metrics["data_or_execution_errors"] = (
                int(self._metrics["data_or_execution_errors"]) + 1
            )

    def set_kill_switch(self, active: bool) -> None:
        with self._lock:
            self._metrics["kill_switch"] = int(active)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "signals": {symbol: asdict(signal) for symbol, signal in self._signals.items()},
                "positions": {
                    symbol: asdict(position) for symbol, position in self._positions.items()
                },
                "decisions": [asdict(decision) for decision in self._decisions],
                "metrics": dict(self._metrics),
            }


class PostgresStore:
    """Minimal Timescale/Postgres persistence hook for later 24/7 deployment."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def migrate(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS market_bars (
            symbol TEXT NOT NULL,
            ts TIMESTAMPTZ NOT NULL,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (symbol, ts)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id BIGSERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            reason TEXT NOT NULL,
            signal_score DOUBLE PRECISION NOT NULL,
            notional DOUBLE PRECISION NOT NULL,
            blocked BOOLEAN NOT NULL,
            details JSONB NOT NULL,
            ts TIMESTAMPTZ NOT NULL
        );
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(ddl)
            conn.commit()
