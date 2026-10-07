# Future Roadmap: US Equities Ensemble on LEAN

The active v1 bot is BTC/ETH paper trading through Alpaca. Perplexity's US
equities research is useful, but it should be a separate v2 track because it
needs a different universe, data model, regulatory surface, and deployment
stack.

## Candidate Stack

- QuantConnect LEAN for research, survivorship-bias-aware equities data,
  backtesting, paper trading, and later live deployment.
- Universe: liquid US stocks and ETFs filtered by dollar volume.
- Resolution: daily bars for swing signals, minute bars for intraday signals.

## Candidate Strategy Buckets

- Cross-sectional mean reversion: rank liquid names by volatility-adjusted
  short-term return or moving-average z-score.
- Cross-sectional momentum: rank 3-12 month returns, optionally skipping the
  most recent month.
- Intraday gap/VWAP reversion: fade extreme gaps and VWAP deviations when
  liquidity is acceptable.
- Pairs/stat-arb: trade rolling spread z-scores for stable, liquid pairs.

## Risk And Execution Requirements

- Sector, gross exposure, and net exposure limits.
- Order-rate throttles and error-loop circuit breakers.
- Pattern day trader and broker margin constraints.
- Paper-trading burn-in before any live capital.

Keep this as a separate implementation line from the BTC/ETH bot unless the
project explicitly expands beyond crypto.
