from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import pandas as pd

from bot import __version__
from bot.ingestion import bars_to_dataframe
from bot.models import (
    Bar,
    DecisionReason,
    OrderRequest,
    OrderResult,
    OrderSide,
    Portfolio,
    Quote,
    TradeDecision,
)
from bot.risk import RiskManager
from bot.storage import InMemoryState
from bot.strategy.indicators import atr
from bot.strategy import EnsembleStrategy


class MarketDataClient(Protocol):
    def historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        limit: int = 10_000,
    ) -> list[Bar]: ...

    def latest_quote(self, symbol: str) -> Quote: ...


class PaperExecutor(Protocol):
    def get_portfolio(self) -> Portfolio: ...

    def submit_order(self, request: OrderRequest) -> OrderResult | dict[str, Any]: ...


@dataclass(frozen=True)
class TradingLoopConfig:
    symbols: tuple[str, ...] = ("BTC/USD", "ETH/USD")
    timeframes: tuple[str, ...] = ("15Min", "1Hour", "6Hour")
    poll_seconds: int = 60
    backfill_days: int = 30
    min_bars: int = 80
    submit_orders: bool = True
    max_orders_per_cycle: int = 2
    max_consecutive_error_cycles: int = 3


class PaperTradingBot:
    """Continuous deterministic paper-trading orchestrator."""

    def __init__(
        self,
        data_client: MarketDataClient,
        executor: PaperExecutor,
        strategy: EnsembleStrategy,
        risk_manager: RiskManager,
        state: InMemoryState | None = None,
        config: TradingLoopConfig | None = None,
    ) -> None:
        self.data_client = data_client
        self.executor = executor
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.state = state or InMemoryState()
        self.config = config or TradingLoopConfig()
        self._running = False
        self._starting_equity: float | None = None
        self._day_start_equity: float | None = None
        self._day: date | None = None
        self._consecutive_error_cycles = 0

    def cycle_once(self, now: datetime | None = None) -> list[TradeDecision]:
        now = now or datetime.now(UTC)
        portfolio = self._portfolio_with_baselines(self.executor.get_portfolio(), now)
        decisions: list[TradeDecision] = []
        order_count = 0
        cycle_had_error = False

        for symbol in self.config.symbols:
            portfolio.position_for(symbol)
            if self._consecutive_error_cycles >= self.config.max_consecutive_error_cycles:
                decision = self._blocked_circuit_breaker_decision(symbol, now)
                self.state.set_kill_switch(True)
                self.state.record_decision(decision)
                decisions.append(decision)
                continue

            try:
                bars_by_timeframe = self._fetch_bars(symbol, now)
                quote = self.data_client.latest_quote(symbol)
                signal = self.strategy.score(symbol, bars_by_timeframe, quote)
                atr_value = self._latest_atr(bars_by_timeframe)
                self.state.record_signal(signal)
                self.state.record_position(portfolio.position_for(symbol))
                decision = self.risk_manager.make_decision(
                    portfolio,
                    signal,
                    quote,
                    now,
                    atr_value=atr_value,
                )
                decision = self._with_decision_trace(
                    decision,
                    portfolio,
                    quote,
                    bars_by_timeframe,
                    atr_value,
                )
                if self.config.submit_orders and decision.side in (OrderSide.BUY, OrderSide.SELL):
                    if order_count >= self.config.max_orders_per_cycle:
                        decision = self._blocked_order_throttle_decision(decision)
                    else:
                        decision = self._submit(decision, portfolio)
                        self.state.increment_orders()
                        order_count += 1
            except Exception as exc:
                cycle_had_error = True
                self.state.increment_errors()
                decision = self._blocked_data_decision(symbol, now, exc)

            if decision.reason == DecisionReason.KILL_SWITCH:
                self.state.set_kill_switch(True)
            self.state.record_decision(decision)
            decisions.append(decision)

        if cycle_had_error:
            self._consecutive_error_cycles += 1
            if self._consecutive_error_cycles >= self.config.max_consecutive_error_cycles:
                self.state.set_kill_switch(True)
        elif self._consecutive_error_cycles < self.config.max_consecutive_error_cycles:
            self._consecutive_error_cycles = 0

        return decisions

    def run_forever(self) -> None:
        self._running = True
        while self._running:
            self.cycle_once()
            time.sleep(self.config.poll_seconds)

    def stop(self) -> None:
        self._running = False

    def _fetch_bars(self, symbol: str, now: datetime) -> dict[str, pd.DataFrame]:
        start = now - timedelta(days=self.config.backfill_days)
        frames: dict[str, pd.DataFrame] = {}
        for timeframe in self.config.timeframes:
            bars = self.data_client.historical_bars(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=now,
                limit=max(self.config.min_bars, 1_000),
            )
            frame = bars_to_dataframe(bars)
            if len(frame) < self.config.min_bars:
                raise ValueError(
                    f"{symbol} {timeframe} returned {len(frame)} bars; need {self.config.min_bars}"
                )
            frames[timeframe] = frame.tail(self.config.min_bars).reset_index(drop=True)
        return frames

    def _submit(self, decision: TradeDecision, portfolio: Portfolio) -> TradeDecision:
        position = portfolio.position_for(decision.symbol)
        if decision.side == OrderSide.BUY:
            request = OrderRequest(
                symbol=decision.symbol,
                side=OrderSide.BUY,
                notional=decision.notional,
            )
        elif decision.side == OrderSide.SELL:
            request = OrderRequest(
                symbol=decision.symbol,
                side=OrderSide.SELL,
                qty=position.qty,
            )
        else:
            return decision
        start = time.perf_counter()
        raw_result = self.executor.submit_order(request)
        latency_ms = (time.perf_counter() - start) * 1_000
        result = self._coerce_order_result(raw_result, request)
        self.state.record_order_ack(result, latency_ms)
        return TradeDecision(
            symbol=decision.symbol,
            side=decision.side,
            reason=decision.reason,
            signal_score=decision.signal_score,
            notional=decision.notional,
            timestamp=decision.timestamp,
            blocked=decision.blocked,
            details={
                **decision.details,
                "execution": {
                    "order_id": result.id,
                    "client_order_id": result.client_order_id,
                    "status": result.status,
                    "ack_latency_ms": round(latency_ms, 3),
                },
            },
        )

    def _with_decision_trace(
        self,
        decision: TradeDecision,
        portfolio: Portfolio,
        quote: Quote,
        bars_by_timeframe: dict[str, pd.DataFrame],
        atr_value: float | None,
    ) -> TradeDecision:
        position = portfolio.position_for(decision.symbol)
        bar_counts = {timeframe: len(frame) for timeframe, frame in bars_by_timeframe.items()}
        latest_bar_timestamps = {
            timeframe: str(frame["timestamp"].iloc[-1]) if "timestamp" in frame and not frame.empty else ""
            for timeframe, frame in bars_by_timeframe.items()
        }
        return TradeDecision(
            symbol=decision.symbol,
            side=decision.side,
            reason=decision.reason,
            signal_score=decision.signal_score,
            notional=decision.notional,
            timestamp=decision.timestamp,
            blocked=decision.blocked,
            details={
                **decision.details,
                "trace": {
                    "bot_version": __version__,
                    "strategy": self.strategy.__class__.__name__,
                    "risk_manager": self.risk_manager.__class__.__name__,
                    "signal_score": decision.signal_score,
                    "bar_counts": bar_counts,
                    "latest_bar_timestamps": latest_bar_timestamps,
                    "quote_spread_bps": round(quote.spread_bps, 6),
                    "quote_age_seconds": round(quote.age_seconds(decision.timestamp), 3),
                    "atr_value": atr_value,
                    "cash": portfolio.cash,
                    "equity": portfolio.equity,
                    "position_qty": position.qty,
                    "position_avg_entry_price": position.avg_entry_price,
                },
            },
        )

    @staticmethod
    def _coerce_order_result(
        result: OrderResult | dict[str, Any],
        request: OrderRequest,
    ) -> OrderResult:
        if isinstance(result, OrderResult):
            return result
        return OrderResult(
            id=str(result.get("id", "")),
            client_order_id=str(
                result.get("client_order_id", request.client_order_id or "unknown")
            ),
            symbol=str(result.get("symbol", request.symbol)),
            side=OrderSide(str(result.get("side", request.side.value))),
            status=str(result.get("status", "unknown")),
            raw=dict(result),
        )

    @staticmethod
    def _latest_atr(bars_by_timeframe: dict[str, pd.DataFrame]) -> float | None:
        base = bars_by_timeframe.get("15Min")
        if base is None or len(base) < 15:
            return None
        value = atr(base, period=14).iloc[-1]
        if pd.isna(value) or value <= 0:
            return None
        return float(value)

    def _portfolio_with_baselines(self, portfolio: Portfolio, now: datetime) -> Portfolio:
        if self._starting_equity is None:
            self._starting_equity = portfolio.equity
        if self._day != now.date():
            self._day = now.date()
            self._day_start_equity = portfolio.equity
            self.state.set_kill_switch(False)

        portfolio.starting_equity = self._starting_equity
        portfolio.day_start_equity = self._day_start_equity or portfolio.equity
        return portfolio

    @staticmethod
    def _blocked_data_decision(symbol: str, now: datetime, exc: Exception) -> TradeDecision:
        return TradeDecision(
            symbol=symbol,
            side=OrderSide.HOLD,
            reason=DecisionReason.RISK_BLOCK,
            signal_score=0.0,
            notional=0.0,
            timestamp=now,
            blocked=True,
            details={"risk_reasons": ["data_or_execution_error"], "error": str(exc)},
        )

    @staticmethod
    def _blocked_order_throttle_decision(decision: TradeDecision) -> TradeDecision:
        return TradeDecision(
            symbol=decision.symbol,
            side=OrderSide.HOLD,
            reason=DecisionReason.RISK_BLOCK,
            signal_score=decision.signal_score,
            notional=0.0,
            timestamp=decision.timestamp,
            blocked=True,
            details={
                **decision.details,
                "risk_reasons": [*decision.details.get("risk_reasons", []), "order_rate_limit"],
            },
        )

    @staticmethod
    def _blocked_circuit_breaker_decision(symbol: str, now: datetime) -> TradeDecision:
        return TradeDecision(
            symbol=symbol,
            side=OrderSide.HOLD,
            reason=DecisionReason.KILL_SWITCH,
            signal_score=0.0,
            notional=0.0,
            timestamp=now,
            blocked=True,
            details={"risk_reasons": ["error_circuit_breaker"]},
        )
