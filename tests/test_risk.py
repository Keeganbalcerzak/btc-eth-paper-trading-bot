from __future__ import annotations

from datetime import timedelta

import pytest

from bot.models import Position, Signal
from bot.risk import RiskConfig, RiskManager


def test_entry_blocked_when_feed_is_stale(fresh_portfolio, normal_quote, now):
    stale_quote = normal_quote.__class__(
        symbol=normal_quote.symbol,
        bid=normal_quote.bid,
        ask=normal_quote.ask,
        bid_size=normal_quote.bid_size,
        ask_size=normal_quote.ask_size,
        timestamp=now - timedelta(minutes=10),
    )
    signal = Signal("BTC/USD", 0.8, {}, now)

    decision = RiskManager().make_decision(fresh_portfolio, signal, stale_quote, now)

    assert decision.blocked
    assert "feed_stale" in decision.details["risk_reasons"]


def test_entry_blocked_when_spread_is_too_wide(fresh_portfolio, now):
    quote = normal_wide_quote(now)
    signal = Signal("BTC/USD", 0.8, {}, now)

    decision = RiskManager().make_decision(fresh_portfolio, signal, quote, now)

    assert decision.blocked
    assert "spread_too_wide" in decision.details["risk_reasons"]


def test_drawdown_trips_kill_switch(fresh_portfolio, normal_quote, now):
    fresh_portfolio.equity = 9_400.0
    signal = Signal("BTC/USD", 0.8, {}, now)

    decision = RiskManager().make_decision(fresh_portfolio, signal, normal_quote, now)

    assert decision.blocked
    assert decision.reason == "kill_switch"
    assert "total_drawdown_limit" in decision.details["risk_reasons"]


def test_position_sizing_uses_conservative_cap(fresh_portfolio, normal_quote, now):
    signal = Signal("BTC/USD", 0.8, {}, now)

    decision = RiskManager().make_decision(fresh_portfolio, signal, normal_quote, now)

    assert not decision.blocked
    assert decision.notional == 1_000.0


def test_position_sizing_shrinks_when_atr_stop_is_wider(fresh_portfolio, normal_quote, now):
    signal = Signal("BTC/USD", 0.8, {}, now)

    decision = RiskManager(RiskConfig(stop_loss_atr=3.0)).make_decision(
        fresh_portfolio,
        signal,
        normal_quote,
        now,
        atr_value=3.0,
    )

    assert not decision.blocked
    assert decision.notional < 1_000.0
    assert decision.notional == pytest.approx(277.9166666666667)


def test_stop_loss_exits_existing_position(fresh_portfolio, normal_quote, now):
    fresh_portfolio.positions["BTC/USD"] = Position("BTC/USD", qty=1.0, avg_entry_price=110.0)
    signal = Signal("BTC/USD", 0.5, {}, now)

    decision = RiskManager(RiskConfig(stop_loss_pct=0.02)).make_decision(
        fresh_portfolio, signal, normal_quote, now
    )

    assert not decision.blocked
    assert decision.side == "sell"
    assert "stop_loss_triggered" in decision.details["risk_reasons"]


def test_atr_stop_exits_existing_position(fresh_portfolio, now):
    from bot.models import Quote

    fresh_portfolio.positions["BTC/USD"] = Position("BTC/USD", qty=1.0, avg_entry_price=110.0)
    quote = Quote("BTC/USD", bid=103.9, ask=104.1, bid_size=1, ask_size=1, timestamp=now)
    signal = Signal("BTC/USD", 0.5, {}, now)

    decision = RiskManager(RiskConfig(stop_loss_pct=0.50, stop_loss_atr=3.0)).make_decision(
        fresh_portfolio,
        signal,
        quote,
        now,
        atr_value=2.0,
    )

    assert decision.side == "sell"
    assert "atr_stop_triggered" in decision.details["risk_reasons"]


def normal_wide_quote(now):
    from bot.models import Quote

    return Quote("BTC/USD", bid=95.0, ask=105.0, bid_size=1, ask_size=1, timestamp=now)
