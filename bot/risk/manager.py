from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from bot.models import OrderSide, Portfolio, Position, Quote, Signal, TradeDecision


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float = 0.10
    account_risk_per_trade_pct: float = 0.0025
    daily_drawdown_pct: float = 0.01
    total_drawdown_pct: float = 0.05
    max_spread_bps: float = 35.0
    max_feed_age_seconds: int = 90
    entry_threshold: float = 0.35
    exit_threshold: float = 0.10
    stop_loss_pct: float = 0.02
    stop_loss_atr: float = 3.0
    min_order_notional: float = 10.0


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    side: OrderSide
    notional: float
    reasons: list[str] = field(default_factory=list)
    kill_switch: bool = False


class RiskManager:
    """Conservative long/cash risk gate."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def evaluate_entry(
        self,
        portfolio: Portfolio,
        position: Position,
        signal: Signal,
        quote: Quote,
        now: datetime | None = None,
        atr_value: float | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(UTC)
        global_block = self._global_blocks(portfolio)
        if global_block.kill_switch:
            return global_block

        reasons: list[str] = []
        if signal.score < self.config.entry_threshold:
            reasons.append("signal_below_entry_threshold")
        reasons.extend(self._market_blocks(quote, now))
        if position.is_open:
            reasons.append("position_already_open")

        max_position_notional = portfolio.equity * self.config.max_position_pct
        effective_stop_pct = self._effective_stop_pct(quote, atr_value)
        risk_notional = portfolio.equity * self.config.account_risk_per_trade_pct / effective_stop_pct
        target_notional = min(max_position_notional, risk_notional, portfolio.cash)

        if target_notional < self.config.min_order_notional:
            reasons.append("notional_below_minimum")

        return RiskDecision(
            allowed=not reasons,
            side=OrderSide.BUY if not reasons else OrderSide.HOLD,
            notional=max(target_notional, 0.0) if not reasons else 0.0,
            reasons=reasons,
        )

    def evaluate_exit(
        self,
        portfolio: Portfolio,
        position: Position,
        signal: Signal,
        quote: Quote,
        now: datetime | None = None,
        atr_value: float | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(UTC)
        global_block = self._global_blocks(portfolio)
        market_blocks = self._market_blocks(quote, now)

        if not position.is_open:
            return RiskDecision(False, OrderSide.HOLD, 0.0, ["no_open_position"])

        reasons: list[str] = []
        stop_loss = position.unrealized_pnl_pct(quote.mid) <= -self.config.stop_loss_pct
        atr_stop = (
            atr_value is not None
            and atr_value > 0
            and quote.mid <= position.avg_entry_price - (self.config.stop_loss_atr * atr_value)
        )
        if signal.score < self.config.exit_threshold:
            reasons.append("signal_below_exit_threshold")
        if stop_loss:
            reasons.append("stop_loss_triggered")
        if atr_stop:
            reasons.append("atr_stop_triggered")
        if market_blocks:
            reasons.extend(market_blocks)
        if global_block.kill_switch:
            reasons.extend(global_block.reasons)

        should_exit = bool(reasons)
        return RiskDecision(
            allowed=should_exit,
            side=OrderSide.SELL if should_exit else OrderSide.HOLD,
            notional=position.market_value(quote.mid) if should_exit else 0.0,
            reasons=reasons if should_exit else ["hold_position"],
            kill_switch=global_block.kill_switch,
        )

    def make_decision(
        self,
        portfolio: Portfolio,
        signal: Signal,
        quote: Quote,
        now: datetime | None = None,
        atr_value: float | None = None,
    ) -> TradeDecision:
        now = now or datetime.now(UTC)
        position = portfolio.position_for(signal.symbol)
        exit_decision = self.evaluate_exit(portfolio, position, signal, quote, now, atr_value)
        if exit_decision.side == OrderSide.SELL:
            return TradeDecision(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                reason=self._reason_for(exit_decision),
                signal_score=signal.score,
                notional=exit_decision.notional,
                timestamp=now,
                blocked=False,
                details={"risk_reasons": exit_decision.reasons},
            )

        entry_decision = self.evaluate_entry(portfolio, position, signal, quote, now, atr_value)
        if entry_decision.allowed:
            return TradeDecision(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                reason=self._reason_for(entry_decision),
                signal_score=signal.score,
                notional=entry_decision.notional,
                timestamp=now,
                blocked=False,
                details={"risk_reasons": entry_decision.reasons},
            )

        return TradeDecision(
            symbol=signal.symbol,
            side=OrderSide.HOLD,
            reason=self._reason_for(entry_decision),
            signal_score=signal.score,
            notional=0.0,
            timestamp=now,
            blocked=True,
            details={"risk_reasons": entry_decision.reasons},
        )

    def _global_blocks(self, portfolio: Portfolio) -> RiskDecision:
        reasons: list[str] = []
        if portfolio.daily_drawdown_pct >= self.config.daily_drawdown_pct:
            reasons.append("daily_drawdown_limit")
        if portfolio.total_drawdown_pct >= self.config.total_drawdown_pct:
            reasons.append("total_drawdown_limit")
        return RiskDecision(
            allowed=not reasons,
            side=OrderSide.HOLD,
            notional=0.0,
            reasons=reasons,
            kill_switch=bool(reasons),
        )

    def _market_blocks(self, quote: Quote, now: datetime) -> list[str]:
        reasons: list[str] = []
        if quote.spread_bps > self.config.max_spread_bps:
            reasons.append("spread_too_wide")
        if quote.age_seconds(now) > self.config.max_feed_age_seconds:
            reasons.append("feed_stale")
        return reasons

    def _effective_stop_pct(self, quote: Quote, atr_value: float | None) -> float:
        atr_stop_pct = 0.0
        if atr_value is not None and atr_value > 0 and quote.mid > 0:
            atr_stop_pct = (self.config.stop_loss_atr * atr_value) / quote.mid
        return max(self.config.stop_loss_pct, atr_stop_pct, 0.0001)

    @staticmethod
    def _reason_for(decision: RiskDecision):
        from bot.models import DecisionReason

        if decision.kill_switch:
            return DecisionReason.KILL_SWITCH
        if not decision.allowed:
            return DecisionReason.RISK_BLOCK
        if decision.side == OrderSide.BUY:
            return DecisionReason.ENTRY
        if decision.side == OrderSide.SELL:
            return DecisionReason.EXIT
        return DecisionReason.HOLD
