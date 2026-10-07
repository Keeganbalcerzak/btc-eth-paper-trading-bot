from __future__ import annotations

import httpx
import pytest

from bot.execution import AlpacaPaperExecutor
from bot.models import OrderRequest, OrderSide


def test_executor_rejects_live_trading_url():
    with pytest.raises(ValueError, match="live trading is disabled"):
        AlpacaPaperExecutor(
            api_key="key",
            api_secret="secret",
            trading_base_url="https://api.alpaca.markets",
            paper=False,
        )


def test_executor_submits_paper_order_with_idempotent_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "id": "order-1",
                "client_order_id": "paper-fixed",
                "symbol": "BTC/USD",
                "side": "buy",
                "status": "accepted",
            },
        )

    client = httpx.Client(
        base_url="https://paper-api.alpaca.markets",
        transport=httpx.MockTransport(handler),
    )
    executor = AlpacaPaperExecutor("key", "secret", client=client)

    result = executor.submit_order(
        OrderRequest("BTC/USD", OrderSide.BUY, notional=25.0, client_order_id="paper-fixed")
    )

    assert result.status == "accepted"
    assert result.client_order_id == "paper-fixed"
    assert '"notional":"25.0"' in captured["json"].replace(" ", "")


def test_executor_reads_portfolio_and_crypto_positions():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"cash": "9000", "equity": "10000", "last_equity": "9950"})
        if request.url.path == "/v2/positions":
            return httpx.Response(
                200,
                json=[
                    {"symbol": "BTCUSD", "qty": "0.1", "avg_entry_price": "60000"},
                    {"symbol": "AAPL", "qty": "1", "avg_entry_price": "100"},
                ],
            )
        return httpx.Response(404)

    client = httpx.Client(
        base_url="https://paper-api.alpaca.markets",
        transport=httpx.MockTransport(handler),
    )
    executor = AlpacaPaperExecutor("key", "secret", client=client)

    portfolio = executor.get_portfolio()

    assert portfolio.cash == 9_000
    assert portfolio.equity == 10_000
    assert portfolio.day_start_equity == 9_950
    assert portfolio.positions["BTC/USD"].qty == 0.1
    assert "AAPL" not in portfolio.positions
