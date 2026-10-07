# Future Roadmap: Institutional Architecture Ideas

The active v1 bot is a conservative BTC/ETH Alpaca paper-trading system. The
Gemini architecture notes are useful, but most of them belong to a later phase
after weeks of paper-trading evidence proves the basic strategy has an edge.

## Ideas Captured For Later

- Persistent operator gateway: OpenClaw or a similar supervisor could expose
  status, emergency stop, and reporting through chat tools.
- Streaming ingestion: Redpanda can buffer raw WebSocket events before storage
  or replay.
- Time-series analytics: QuestDB can support tick/quote storage and ASOF JOIN
  research if the bot moves from bar-level trading to tick-level microstructure.
- Research engines: VectorBT can speed up parameter sweeps, while Backtrader or
  NautilusTrader can support deeper event-driven simulation.
- Advanced modeling: HMM-style regime detection, triple-barrier labeling, and
  meta-labeling can help filter candidate signals before they are promoted to
  live paper trading.
- Execution specialization: Rust or venue-specific services may matter only if
  the strategy proves latency-sensitive; this is not required for the v1 Alpaca
  paper loop.

## Adopted In This Repo

- Offline Gaussian-mixture regime detection in `bot.research.regime`.
- Offline triple-barrier labeling in `bot.research.labeling`.
- No LLM or agent framework is allowed to make direct order decisions.

## Deferred Until Evidence Warrants It

- Redpanda, QuestDB, Kubernetes, NautilusTrader, Hyperliquid, and Rust execution
  services.
- HFT or co-location assumptions.
- LightGBM/XGBoost meta-labeling that changes live position sizing.

Promote these only after paper trading produces enough decisions to evaluate
out-of-sample hit rate, drawdown behavior, and slippage.
