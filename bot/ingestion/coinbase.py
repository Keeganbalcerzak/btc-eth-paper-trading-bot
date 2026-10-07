from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import websockets


@dataclass(frozen=True)
class CoinbaseTicker:
    product_id: str
    price: float
    best_bid: float | None
    best_ask: float | None


class CoinbaseBackupStream:
    """Data-only Coinbase websocket fallback; never executes orders."""

    endpoint = "wss://advanced-trade-ws.coinbase.com"

    def __init__(self, product_ids: tuple[str, ...] = ("BTC-USD", "ETH-USD")) -> None:
        self.product_ids = product_ids

    async def ticker_messages(self) -> AsyncIterator[CoinbaseTicker]:
        subscribe = {
            "type": "subscribe",
            "product_ids": list(self.product_ids),
            "channel": "ticker",
        }
        async with websockets.connect(self.endpoint, ping_interval=20) as websocket:
            await websocket.send(json.dumps(subscribe))
            while True:
                message = json.loads(await websocket.recv())
                for event in message.get("events", []):
                    for ticker in event.get("tickers", []):
                        if "price" not in ticker:
                            continue
                        yield CoinbaseTicker(
                            product_id=ticker["product_id"],
                            price=float(ticker["price"]),
                            best_bid=_maybe_float(ticker.get("best_bid")),
                            best_ask=_maybe_float(ticker.get("best_ask")),
                        )
                await asyncio.sleep(0)


def _maybe_float(value: str | float | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
