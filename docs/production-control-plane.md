# Production Control Plane Notes

The Deep Research PDF emphasizes that an automated trading bot should be treated
as an operational system, not a passive script. The active v1 implements the
controls that fit BTC/ETH Alpaca paper trading and defers the HFT/institutional
parts until paper evidence justifies them.

## Adopted In V1

- Pre-trade risk checks: stale data, spread limits, drawdown brakes, max
  position sizing, ATR-aware sizing, and ATR/fixed stop exits.
- Message controls: max orders per cycle plus repeated-error circuit breaker.
- Decision tracing: every non-error decision records bot version, strategy,
  risk manager, bar counts, latest bar timestamps, quote spread/age, ATR,
  portfolio values, and position state.
- Execution observability: submitted paper orders record broker status and
  acknowledgement latency in API metrics.
- Reconciliation: the bot refreshes account and position state from Alpaca at
  the start of every cycle before making new decisions.

## Deferred Until Needed

- Direct market access, FIX, TT, direct futures routing, or exchange colocation.
- HFT market making and queue-position strategies.
- Options, news, event-driven, and text-sentiment sleeves.
- Redpanda/QuestDB raw tick replay infrastructure.
- Rust execution microservices or FPGA acceleration.

## Live-Paper Acceptance Gate

Before live capital, the bot still needs:

- A real Alpaca paper account smoke run.
- A 24-hour paper soak with no uncaught exceptions.
- Review of decision traces, order acknowledgement latency, blocked orders, and
  slippage/fill behavior.
- Manual confirmation that every live-money credential remains absent from v1.
