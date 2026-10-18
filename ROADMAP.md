# Roadmap

## Current State

Working automated trading system with stocks (S&P 500) and crypto (33 coins) via Interactive Brokers, plus options and futures traders. Custom backtesting engine, hot stock scanner (volume + Reddit + SEC insider), aggressive momentum strategy, and pretty terminal UI.

## Short Term

- [ ] Replace custom backtesting engine with `vectorbt` or `backtesting.py` for faster, more rigorous backtesting
- [ ] Add Telegram notifications for trade alerts (buy/sell/stop loss/kill switch)
- [ ] Add retry logic and error recovery for network failures and API outages
- [ ] Add unit tests for critical paths (risk manager, signal generation, order execution)

## Medium Term

- [ ] Integrate Freqtrade for crypto trading — battle-tested across 50+ exchanges, Hyperopt strategy optimization, FreqUI web dashboard, Telegram bot control
- [ ] Replace yfinance with a paid data provider (Polygon, Databento, or IB's market data API) for reliability
- [ ] Add limit orders and smarter execution (TWAP, iceberg) to reduce slippage
- [ ] Build a web dashboard (replace terminal-only UI) so positions can be monitored from phone
- [ ] Add walk-forward optimization to avoid overfitting strategies to historical data

## Long Term

- [ ] Integrate with QuantConnect LEAN for institutional-grade multi-asset backtesting (stocks, options, futures, crypto)
- [ ] Add options trading strategies (covered calls, iron condors for income generation)
- [ ] Add NautilusTrader as the core engine for tick-level backtesting and deterministic event-driven architecture
- [ ] ML-powered signal generation (integrate PyBroker or custom models)
- [ ] Multi-account support (paper + live with confirmation gates)
- [ ] Deploy to cloud (AWS/GCP) for 24/7 uptime without keeping a laptop running

## Unique Edge (Keep and Expand)

The hot stock scanner (Reddit + SEC insider filings + volume anomalies) is unique — none of the major open source bots have this. Future expansions:

- [ ] Add Twitter/X sentiment scanning
- [ ] Add options flow detection (unusual options activity)
- [ ] Add earnings estimate revision tracking
- [ ] Add dark pool volume monitoring
- [ ] Real-time news headline sentiment (NLP)
- [ ] Expand Reddit scanning to more subreddits and add historical trend detection (is buzz increasing or decreasing?)
