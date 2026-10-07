from __future__ import annotations

from dataclasses import replace

from bot.models import Bar, Portfolio, Position, Quote, Signal
from bot.risk import RiskManager
from bot.storage import InMemoryState
from bot.trading_loop import PaperTradingBot, TradingLoopConfig


class StubStrategy:
    def __init__(self, score: float) -> None:
        self.score_value = score

    def score(self, symbol, bars_by_timeframe, quote):
        frame = bars_by_timeframe["15Min"]
        return Signal(symbol, self.score_value, {"stub": self.score_value}, frame["timestamp"].iloc[-1])


class FakeDataClient:
    def __init__(self, bars, quote: Quote, truncate_to: int | None = None) -> None:
        self.bars = bars
        self.quote = quote
        self.truncate_to = truncate_to

    def historical_bars(self, symbol, timeframe, start, end=None, limit=10_000):
        frame = self.bars.tail(self.truncate_to) if self.truncate_to else self.bars
        return [
            Bar(
                symbol=symbol,
                timestamp=row.timestamp,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            for row in frame.itertuples()
        ]

    def latest_quote(self, symbol):
        return replace(self.quote, symbol=symbol)


class FakeExecutor:
    def __init__(self, portfolio: Portfolio) -> None:
        self.portfolio = portfolio
        self.orders = []

    def get_portfolio(self):
        return self.portfolio

    def submit_order(self, request):
        self.orders.append(request)
        return {"status": "accepted"}


def test_cycle_once_submits_buy_order_when_signal_and_risk_allow(
    trending_bars, normal_quote, fresh_portfolio, now
):
    state = InMemoryState()
    executor = FakeExecutor(fresh_portfolio)
    bot = PaperTradingBot(
        data_client=FakeDataClient(trending_bars, normal_quote),
        executor=executor,
        strategy=StubStrategy(0.8),
        risk_manager=RiskManager(),
        state=state,
        config=TradingLoopConfig(symbols=("BTC/USD",), min_bars=40),
    )

    decisions = bot.cycle_once(now)

    assert decisions[0].side == "buy"
    assert executor.orders[0].side == "buy"
    assert executor.orders[0].notional == 1_000.0
    snapshot = state.snapshot()
    assert snapshot["metrics"]["orders_submitted"] == 1
    assert snapshot["metrics"]["orders_acknowledged"] == 1
    assert snapshot["metrics"]["last_order_status"] == "accepted"
    assert "last_order_ack_latency_ms" in snapshot["metrics"]
    assert decisions[0].details["trace"]["strategy"] == "StubStrategy"
    assert decisions[0].details["trace"]["bar_counts"]["15Min"] == 40
    assert decisions[0].details["execution"]["status"] == "accepted"


def test_cycle_once_submits_sell_order_when_exit_signal_fires(
    trending_bars, normal_quote, fresh_portfolio, now
):
    fresh_portfolio.positions["BTC/USD"] = Position("BTC/USD", qty=0.5, avg_entry_price=90.0)
    executor = FakeExecutor(fresh_portfolio)
    bot = PaperTradingBot(
        data_client=FakeDataClient(trending_bars, normal_quote),
        executor=executor,
        strategy=StubStrategy(0.0),
        risk_manager=RiskManager(),
        config=TradingLoopConfig(symbols=("BTC/USD",), min_bars=40),
    )

    decisions = bot.cycle_once(now)

    assert decisions[0].side == "sell"
    assert executor.orders[0].side == "sell"
    assert executor.orders[0].qty == 0.5


def test_cycle_once_blocks_when_market_data_is_incomplete(
    trending_bars, normal_quote, fresh_portfolio, now
):
    executor = FakeExecutor(fresh_portfolio)
    bot = PaperTradingBot(
        data_client=FakeDataClient(trending_bars, normal_quote, truncate_to=5),
        executor=executor,
        strategy=StubStrategy(0.8),
        risk_manager=RiskManager(),
        config=TradingLoopConfig(symbols=("BTC/USD",), min_bars=40),
    )

    decisions = bot.cycle_once(now)

    assert decisions[0].blocked
    assert decisions[0].side == "hold"
    assert "data_or_execution_error" in decisions[0].details["risk_reasons"]
    assert bot.state.snapshot()["metrics"]["data_or_execution_errors"] == 1
    assert executor.orders == []


def test_cycle_once_throttles_orders_after_cycle_limit(
    trending_bars, normal_quote, fresh_portfolio, now
):
    fresh_portfolio.positions["ETH/USD"] = Position("ETH/USD")
    executor = FakeExecutor(fresh_portfolio)
    bot = PaperTradingBot(
        data_client=FakeDataClient(trending_bars, normal_quote),
        executor=executor,
        strategy=StubStrategy(0.8),
        risk_manager=RiskManager(),
        config=TradingLoopConfig(
            symbols=("BTC/USD", "ETH/USD"),
            min_bars=40,
            max_orders_per_cycle=1,
        ),
    )

    decisions = bot.cycle_once(now)

    assert decisions[0].side == "buy"
    assert decisions[1].blocked
    assert "order_rate_limit" in decisions[1].details["risk_reasons"]
    assert len(executor.orders) == 1


def test_repeated_error_cycles_open_circuit_breaker(
    trending_bars, normal_quote, fresh_portfolio, now
):
    executor = FakeExecutor(fresh_portfolio)
    bot = PaperTradingBot(
        data_client=FakeDataClient(trending_bars, normal_quote, truncate_to=5),
        executor=executor,
        strategy=StubStrategy(0.8),
        risk_manager=RiskManager(),
        config=TradingLoopConfig(
            symbols=("BTC/USD",),
            min_bars=40,
            max_consecutive_error_cycles=2,
        ),
    )

    bot.cycle_once(now)
    bot.cycle_once(now)
    decisions = bot.cycle_once(now)

    assert decisions[0].reason == "kill_switch"
    assert "error_circuit_breaker" in decisions[0].details["risk_reasons"]
    assert executor.orders == []
