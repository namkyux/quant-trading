# Quant Trading System

Automated quantitative trading system that scans the entire S&P 500, detects hot stocks using multiple signals, and executes trades via the Alpaca API. Built for aggressive, systematic trading with full risk management.

## What It Does

1. **Scans 500+ stocks** every 15 minutes for momentum, volume anomalies, Reddit buzz, and insider buying
2. **Scores and ranks** candidates using multi-timeframe momentum + breakout detection + volume confirmation
3. **Executes trades** automatically on paper or live accounts via Alpaca
4. **Manages risk** with stop losses, daily loss limits, and a portfolio kill switch

## Quick Start

```bash
# 1. Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your Alpaca API keys to .env
#    Get free keys at https://alpaca.markets

# 3. Run the day trader (paper money)
python live/run.py --paper

# 4. Or just see what it would trade
python live/run.py --dry-run
```

## Commands

### Live Trading
```bash
python live/run.py --paper       # Run day trader on paper account (continuous)
python live/run.py --dry-run     # See what trades it would make (no execution)
python live/run.py --once        # Run one rebalance cycle and exit
python live/run.py --status      # Check account and positions
```

### Hot Stock Scanner
```bash
python live/scan.py              # Quick scan (volume + momentum)
python live/scan.py --full       # Full scan (+ Reddit + insider filings)
python live/scan.py --full --squeeze  # Include short squeeze candidates
```

### Backtesting
```bash
python strategies/momentum.py              # Vanilla momentum backtest
python strategies/aggressive_momentum.py   # Aggressive momentum backtest
python strategies/mean_reversion.py        # Mean reversion (RSI-based)
python strategies/sector_rotation.py       # Sector ETF rotation
python strategies/compare.py               # Compare strategies vs benchmarks
python strategies/param_sweep.py           # Test 96 parameter combinations
python strategies/combined.py              # Multi-strategy portfolio
```

## Architecture

```
quant-trading/
├── config.py                  # All settings: universe, strategy params, risk limits
├── .env                       # API keys (never committed)
│
├── strategies/                # Strategy definitions
│   ├── momentum.py            # Classic N-day momentum (126-day lookback)
│   ├── aggressive_momentum.py # Multi-timeframe momentum + breakout + volume
│   ├── mean_reversion.py      # RSI-based mean reversion
│   ├── sector_rotation.py     # Sector ETF rotation with safe havens
│   ├── combined.py            # Multi-strategy portfolio (40/30/30 split)
│   ├── compare.py             # Strategy vs benchmark comparison
│   └── param_sweep.py         # Parameter optimization (96 combinations)
│
├── live/                      # Live/paper trading
│   ├── run.py                 # Main entry point
│   ├── day_trader.py          # Continuous intraday trading loop
│   ├── trader.py              # Single-cycle rebalance trader
│   ├── broker.py              # Alpaca API wrapper
│   ├── risk_manager.py        # Kill switch, position limits, trade validation
│   ├── scan.py                # Hot stock scanner CLI
│   ├── paper_trade.py         # Scheduled paper trading
│   ├── check_positions.py     # Quick position check
│   └── logs/                  # Trade logs (JSON per cycle)
│
├── utils/                     # Shared infrastructure
│   ├── scanner.py             # Hot stock detection (volume, Reddit, insider, squeeze)
│   ├── universe.py            # Dynamic stock sourcing (S&P 500, NASDAQ-100, S&P 400)
│   ├── screener.py            # Stock screening (price, volume, sector filters)
│   ├── data.py                # Price data fetching + caching (yfinance)
│   ├── backtest_engine.py     # Custom backtesting engine (slippage, commissions)
│   ├── pipeline.py            # Source -> screen -> fetch -> backtest -> report
│   ├── benchmarks.py          # Buy-and-hold benchmarks (SPY, QQQ, 60/40, etc.)
│   ├── trend_filter.py        # Market regime detection (SMA-based)
│   ├── metrics.py             # Sharpe, CAGR, max drawdown, total return
│   └── plotting.py            # Equity curves, drawdowns, comparison charts
│
├── backtests/                 # Saved charts and results
├── data/                      # Cached market data (parquet)
└── notebooks/                 # Exploratory analysis
```

## How the Day Trader Works

```
Every 15 minutes during market hours:
│
├── Risk Checks
│   ├── Daily P&L check (stops at -5%)
│   └── Kill switch (liquidates at -20% from peak)
│
├── Position Management
│   ├── Stop loss: exit at -5%
│   └── Take profit: exit at +10%
│
├── Hot Stock Scanner (hourly)
│   ├── Volume anomalies (2x+ normal volume)
│   ├── Price acceleration (momentum shift)
│   ├── Reddit buzz (r/wallstreetbets, r/stocks, r/investing)
│   └── SEC insider buying filings
│
├── Signal Generation
│   ├── Multi-timeframe momentum (5d, 10d, 21d)
│   ├── Breakout detection (near 20-day highs)
│   ├── Volume confirmation
│   ├── Volatility penalty (avoid pump-and-dumps)
│   └── Hot stock score boost
│
└── Execution
    ├── Up to 5 concurrent positions
    ├── 35% max per position
    └── Market orders via Alpaca
```

## Risk Management

| Guard | Trigger | Action |
|---|---|---|
| Stop loss | Position down 5% | Close position |
| Take profit | Position up 10% | Close position |
| Daily loss limit | Account down 5% today | Stop trading for the day |
| Kill switch | Account down 20% from peak | Liquidate all positions |
| Position cap | Single stock > 35% | Block or scale down |

## Strategy Performance (Backtest 2019-2025)

| Strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|
| Momentum (vanilla) | 46.9% | 1.20 | -40.0% |
| Momentum + trend filter | 30.1% | 0.95 | -32.1% |
| Aggressive momentum | 74.9% | 1.44 | -47.3% |
| S&P 500 (benchmark) | 17.3% | 0.91 | -33.7% |

Note: Backtest results are subject to survivorship bias and may not reflect future performance.

## Configuration

All settings are in `config.py`:

```python
UNIVERSE_SOURCE = "sp500"       # "sp500", "nasdaq100", "sp400"
MOMENTUM_LOOKBACK = 21          # short-term momentum (trading days)
TOP_N = 3                       # concentrated: top 3 stocks
REBALANCE_FREQ = 1              # daily
MAX_DRAWDOWN_PCT = 0.20         # kill switch at 20%
MAX_POSITION_PCT = 0.35         # max 35% in one stock
SCREEN_MIN_PRICE = 10.0         # exclude cheap stocks
SCREEN_MIN_AVG_VOLUME = 1000000 # high liquidity only
```

## Stack

- **Python 3.11+**
- **Data:** yfinance, pandas, numpy
- **Visualization:** matplotlib, plotly
- **Brokerage:** Alpaca API (paper and live)
- **Stock Sourcing:** Wikipedia (S&P 500/NASDAQ-100/S&P 400 constituents)
- **Social Signals:** Reddit JSON API, SEC EDGAR RSS

## Setup

1. Clone the repo
2. Create virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Create a free Alpaca account at https://alpaca.markets
5. Copy your API keys to `.env`:
   ```
   ALPACA_API_KEY=your_key
   ALPACA_SECRET_KEY=your_secret
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```
6. Run: `python live/run.py --paper`
