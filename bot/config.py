from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


SUPPORTED_SYMBOLS = ("BTC/USD", "ETH/USD")


def _parse_symbols(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        symbols = tuple(part.strip() for part in value.split(",") if part.strip())
    else:
        symbols = tuple(value)
    unsupported = sorted(set(symbols) - set(SUPPORTED_SYMBOLS))
    if unsupported:
        raise ValueError(f"unsupported symbols: {unsupported}; allowed: {SUPPORTED_SYMBOLS}")
    return symbols


SymbolTuple = Annotated[tuple[str, ...], BeforeValidator(_parse_symbols)]


class Settings(BaseSettings):
    """Environment-backed runtime settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_api_secret: str = Field(default="", alias="ALPACA_API_SECRET")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")
    alpaca_trading_base_url: HttpUrl = Field(
        default="https://paper-api.alpaca.markets", alias="ALPACA_TRADING_BASE_URL"
    )
    alpaca_data_base_url: HttpUrl = Field(
        default="https://data.alpaca.markets", alias="ALPACA_DATA_BASE_URL"
    )

    bot_symbols: SymbolTuple = Field(default=SUPPORTED_SYMBOLS, alias="BOT_SYMBOLS")
    bot_timeframe: str = Field(default="15Min", alias="BOT_TIMEFRAME")
    bot_max_position_pct: float = Field(default=0.10, alias="BOT_MAX_POSITION_PCT", gt=0, le=1)
    bot_account_risk_per_trade_pct: float = Field(
        default=0.0025, alias="BOT_ACCOUNT_RISK_PER_TRADE_PCT", gt=0, le=1
    )
    bot_daily_drawdown_pct: float = Field(default=0.01, alias="BOT_DAILY_DRAWDOWN_PCT", gt=0, le=1)
    bot_total_drawdown_pct: float = Field(default=0.05, alias="BOT_TOTAL_DRAWDOWN_PCT", gt=0, le=1)
    bot_max_spread_bps: float = Field(default=35.0, alias="BOT_MAX_SPREAD_BPS", gt=0)
    bot_max_feed_age_seconds: int = Field(
        default=90, alias="BOT_MAX_FEED_AGE_SECONDS", gt=0
    )
    bot_stop_loss_atr: float = Field(default=3.0, alias="BOT_STOP_LOSS_ATR", gt=0)
    bot_max_orders_per_cycle: int = Field(default=2, alias="BOT_MAX_ORDERS_PER_CYCLE", ge=0)
    bot_max_consecutive_error_cycles: int = Field(
        default=3,
        alias="BOT_MAX_CONSECUTIVE_ERROR_CYCLES",
        gt=0,
    )
    bot_poll_seconds: int = Field(default=60, alias="BOT_POLL_SECONDS", gt=0)
    bot_backfill_days: int = Field(default=30, alias="BOT_BACKFILL_DAYS", gt=0)
    bot_min_bars: int = Field(default=80, alias="BOT_MIN_BARS", gt=20)
    bot_autostart: bool = Field(default=False, alias="BOT_AUTOSTART")
    database_url: str = Field(default="postgresql://bot:bot@db:5432/bot", alias="DATABASE_URL")

    def assert_paper_execution(self) -> None:
        base_url = str(self.alpaca_trading_base_url)
        if not self.alpaca_paper or "paper-api.alpaca.markets" not in base_url:
            raise ValueError("v1 only supports Alpaca paper trading; live execution is disabled")


@lru_cache
def get_settings() -> Settings:
    return Settings()
