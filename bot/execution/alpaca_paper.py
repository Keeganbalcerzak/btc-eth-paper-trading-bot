from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx

from bot.models import OrderRequest, OrderResult, OrderSide, Portfolio, Position


class AlpacaPaperExecutor:
    """Paper-only Alpaca order adapter."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        trading_base_url: str = "https://paper-api.alpaca.markets",
        paper: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        base_url = trading_base_url.rstrip("/")
        if not paper or "paper-api.alpaca.markets" not in base_url:
            raise ValueError("live trading is disabled; use Alpaca paper-api only")
        self.client = client or httpx.Client(
            base_url=base_url,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            timeout=15,
        )

    def submit_order(self, request: OrderRequest) -> OrderResult:
        if request.side not in (OrderSide.BUY, OrderSide.SELL):
            raise ValueError("only buy/sell orders can be submitted")
        if request.notional is None and request.qty is None:
            raise ValueError("order must include notional or qty")
        if request.notional is not None and request.notional <= 0:
            raise ValueError("notional must be positive")
        if request.qty is not None and request.qty <= 0:
            raise ValueError("qty must be positive")

        client_order_id = request.client_order_id or self.make_client_order_id(request)
        payload: dict[str, Any] = {
            "symbol": request.symbol,
            "side": request.side.value,
            "type": request.order_type,
            "time_in_force": request.time_in_force,
            "client_order_id": client_order_id,
        }
        if request.notional is not None:
            payload["notional"] = str(round(request.notional, 2))
        if request.qty is not None:
            payload["qty"] = str(request.qty)

        response = self.client.post("/v2/orders", json=payload)
        response.raise_for_status()
        raw = response.json()
        return OrderResult(
            id=str(raw.get("id", "")),
            client_order_id=str(raw.get("client_order_id", client_order_id)),
            symbol=str(raw.get("symbol", request.symbol)),
            side=OrderSide(str(raw.get("side", request.side.value))),
            status=str(raw.get("status", "unknown")),
            raw=raw,
        )

    def get_portfolio(self) -> Portfolio:
        account_response = self.client.get("/v2/account")
        account_response.raise_for_status()
        account = account_response.json()

        positions_response = self.client.get("/v2/positions")
        positions_response.raise_for_status()
        raw_positions = positions_response.json()
        positions: dict[str, Position] = {}
        for raw in raw_positions:
            symbol = _normalize_alpaca_symbol(str(raw.get("symbol", "")))
            if symbol not in {"BTC/USD", "ETH/USD"}:
                continue
            positions[symbol] = Position(
                symbol=symbol,
                qty=float(raw.get("qty", 0.0)),
                avg_entry_price=float(raw.get("avg_entry_price", 0.0)),
            )

        equity = float(account.get("equity", 0.0))
        day_start = float(account.get("last_equity", equity))
        return Portfolio(
            cash=float(account.get("cash", 0.0)),
            equity=equity,
            starting_equity=equity,
            day_start_equity=day_start,
            positions=positions,
        )

    @staticmethod
    def make_client_order_id(request: OrderRequest, now: datetime | None = None) -> str:
        bucket = (now or datetime.now(UTC)).replace(second=0, microsecond=0).isoformat()
        body = f"{request.symbol}|{request.side.value}|{request.notional}|{request.qty}|{bucket}"
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
        return f"paper-{digest}"


def _normalize_alpaca_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USD"):
        return f"{symbol[:-3]}/USD"
    return symbol
