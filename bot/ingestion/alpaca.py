from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from bot.models import Bar, Quote


class AlpacaDataClient:
    """Small HTTP client for Alpaca crypto market data."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        data_base_url: str = "https://data.alpaca.markets",
        client: httpx.Client | None = None,
    ) -> None:
        self.data_base_url = data_base_url.rstrip("/")
        self.client = client or httpx.Client(
            base_url=self.data_base_url,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            timeout=15,
        )

    def historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        limit: int = 10_000,
    ) -> list[Bar]:
        params: dict[str, Any] = {
            "symbols": symbol,
            "timeframe": timeframe,
            "start": start.isoformat(),
            "limit": limit,
        }
        if end is not None:
            params["end"] = end.isoformat()

        response = self.client.get("/v1beta3/crypto/us/bars", params=params)
        response.raise_for_status()
        payload = response.json()
        raw_bars = payload.get("bars", {}).get(symbol, [])
        return [self._bar_from_payload(symbol, item) for item in raw_bars]

    def latest_quote(self, symbol: str) -> Quote:
        response = self.client.get("/v1beta3/crypto/us/latest/quotes", params={"symbols": symbol})
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("quotes", {}).get(symbol)
        if raw is None:
            raise ValueError(f"Alpaca returned no quote for {symbol}")
        return self._quote_from_payload(symbol, raw)

    @staticmethod
    def _bar_from_payload(symbol: str, payload: dict[str, Any]) -> Bar:
        return Bar(
            symbol=symbol,
            timestamp=_parse_timestamp(payload["t"]),
            open=float(payload["o"]),
            high=float(payload["h"]),
            low=float(payload["l"]),
            close=float(payload["c"]),
            volume=float(payload.get("v", 0.0)),
        )

    @staticmethod
    def _quote_from_payload(symbol: str, payload: dict[str, Any]) -> Quote:
        return Quote(
            symbol=symbol,
            bid=float(payload["bp"]),
            ask=float(payload["ap"]),
            bid_size=float(payload.get("bs", 0.0)),
            ask_size=float(payload.get("as", 0.0)),
            timestamp=_parse_timestamp(payload["t"]),
        )


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
