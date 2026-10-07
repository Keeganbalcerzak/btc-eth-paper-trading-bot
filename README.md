# BTC/ETH Paper-Trading Bot

Conservative v1 automated paper-trading system for `BTC/USD` and `ETH/USD`.
It is intentionally long/cash only, deterministic, and guarded by risk checks.

This is not financial advice and does not guarantee profit. The code defaults to
paper trading and rejects non-paper Alpaca execution URLs.

## What It Does

- Watches BTC/ETH market data through Alpaca.
- Scores each symbol with a deterministic ensemble:
  - time-series momentum,
  - Donchian breakout,
  - MACD trend,
  - mean reversion,
  - quick reactivity,
  - volatility regime,
  - ADX trend/range regime weighting.
- Blocks trades when risk gates fail.
- Backtests with transaction fees, slippage, ATR stops, buy-and-hold comparison,
  and no future-bar leakage.
- Exposes a lightweight FastAPI dashboard and JSON endpoints.

## Quick Start

```powershell
cd btc_eth_paper_bot
copy .env.example .env
# Edit .env and add Alpaca paper keys.
docker compose up --build
```

Open `http://localhost:8000` for the status page.

Run one paper-trading cycle after adding Alpaca paper keys:

```powershell
.\.venv\Scripts\python.exe -m bot.runner trade --once
```

Run the continuous local worker:

```powershell
.\.venv\Scripts\python.exe -m bot.runner trade
```

With Docker Desktop running, the API and database start with:

```powershell
docker compose up --build
```

The continuous worker is opt-in:

```powershell
docker compose --profile worker up --build
```

To run the watcher inside the API process instead of a separate worker, set
`BOT_AUTOSTART=true`.

## Run Tests

```powershell
docker compose run --rm bot pytest
```

## Local Development Without Docker

The project is pinned to Python 3.12. Local Python 3.14 is intentionally not the
supported runtime because some scientific packages may lag new Python releases.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## Safety Defaults

- Paper trading only.
- Symbols fixed to `BTC/USD` and `ETH/USD`.
- Long/cash only.
- Max 10% paper equity per asset.
- Max 0.25% account risk per trade.
- Max 1% daily drawdown and 5% total drawdown before kill switch.
- ATR stop default: exit when price moves 3 ATRs against the entry.
- Entry threshold: ensemble score `>= 0.35`.
- Exit threshold: ensemble score `< 0.10`.

## API Endpoints

- `GET /health`
- `GET /metrics`
- `GET /signals`
- `GET /positions`
- `GET /decisions`

## Azure Deployment Notes

Azure is a later deployment target. Install and configure Azure CLI before
deployment:

```powershell
winget install Microsoft.AzureCLI
az login
```

Recommended services: Azure Container Apps, Azure Database for PostgreSQL,
Key Vault, and Application Insights.

## Future Equities Track

Perplexity's US-equities/QuantConnect recommendations are captured as a
separate roadmap in `docs/us-equities-lean-roadmap.md`. They are not mixed into
this BTC/ETH v1 because equities need different data, universe selection,
broker rules, and risk controls.

## Future Institutional Architecture Track

Gemini's heavier OpenClaw, Redpanda, QuestDB, HMM, triple-barrier, meta-labeling,
NautilusTrader, and Rust-execution recommendations are captured in
`docs/institutional-architecture-roadmap.md`. The useful research pieces adopted
now are offline-only regime detection and triple-barrier labeling under
`bot.research`.

## Production Control Plane

The Deep Research control-plane recommendations are captured in
`docs/production-control-plane.md`. The v1 bot now records replayable decision
traces and paper-order acknowledgement metrics while keeping the execution path
paper-only.
