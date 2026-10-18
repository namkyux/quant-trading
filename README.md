# Quant Trading System

Automated quantitative trading system for stocks and crypto. Scans 500+ stocks and 33 crypto coins, detects hot assets using momentum, volume anomalies, Reddit buzz, and insider buying, then executes trades through Interactive Brokers (IB Gateway/TWS) with full risk management. Crypto trades 24/7.

## What It Does

1. **Scans 500+ stocks and 33 crypto coins** for momentum, volume spikes, Reddit buzz, and insider buying
2. **Scores and ranks** candidates using multi-timeframe momentum + breakout detection + volume confirmation
3. **Executes trades** automatically on an Interactive Brokers paper account (stocks + crypto; options and futures have their own traders)
4. **Manages risk** with stop losses, take profits, daily loss limits, and a portfolio kill switch
5. **Runs 24/7** for crypto, market hours for stocks

## Quick Start

```bash
# 1. Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Start IB Gateway or TWS (paper account, API enabled) and copy the IB_* settings from Setup into .env

# 3. Run the full system (stocks + crypto on paper)
python live/run.py

# 4. Or simulate first (no orders placed)
python live/run.py --simulate
```

## Commands

```
python live/run.py [--type TYPE] [--account ACCOUNT] [--display DISPLAY] [--scan SCAN] [--simulate]
```

### Trading

| Command | What it does |
|---|---|
| `python live/run.py` | Run everything — stocks + crypto on paper |
| `python live/run.py --type stocks` | Stocks only (market hours) |
| `python live/run.py --type crypto` | Crypto only (24/7) |
| `python live/run.py --type all` | Stocks + crypto (default) |
| `python live/run.py --simulate` | Simulate all trades, no orders placed |
| `python live/run.py --type stocks --simulate` | Simulate stocks only |

### Account

| Command | What it does |
|---|---|
| `python live/run.py --display account` | Show equity, cash, positions, P&L |
| `python live/run.py --account paper` | Use paper account (default) |

### Scanner

| Command | What it does |
|---|---|
| `python live/run.py --scan` | Scan everything (stocks + crypto) |
| `python live/run.py --scan stocks` | Hot stock scanner (volume + Reddit + insider) |
| `python live/run.py --scan crypto` | Crypto scanner (prices + signals + Reddit buzz) |

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
│   ├── run.py                 # Main entry point (all commands)
│   ├── day_trader.py          # Stock day trader (market hours)
│   ├── crypto_trader.py       # Crypto trader (24/7)
│   ├── trader.py              # Single-cycle rebalance trader
│   ├── broker_factory.py      # Picks the broker (BROKER=ib)
│   ├── ib_broker.py           # Interactive Brokers wrapper (stocks + crypto, via ib_async)
│   ├── ib_options_broker.py   # IB options wrapper
│   ├── futures_broker.py      # IB futures wrapper (micro contracts)
│   ├── risk_manager.py        # Kill switch, position limits, trade validation
│   ├── scan.py                # Hot stock scanner CLI
│   └── logs/                  # Trade logs (JSON per cycle)
│
├── utils/                     # Shared infrastructure
│   ├── scanner.py             # Hot stock detection (volume, Reddit, insider, squeeze)
│   ├── display.py             # Pretty terminal output (colors, charts, tables)
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

## How It Works

### Stock Day Trader (market hours)

```
Every 5 min:   Check positions (stop loss / take profit)
               Risk checks (daily limit, kill switch)

Every 15 min:  Signal scan (momentum scoring for 500+ stocks)
               Open new positions if slots available

Every 60 min:  Hot stock scanner
               ├── Volume anomalies (2x+ normal volume)
               ├── Price acceleration (momentum shift)
               ├── Reddit buzz (r/wallstreetbets, r/stocks)
               └── SEC insider buying filings
```

### Crypto Trader (24/7)

```
Every 3 min:   Check positions (stop loss / take profit)
               Risk checks (daily limit, kill switch)

Every 10 min:  Signal scan (33 coins — momentum + volume)
               Open new positions if slots available

Every 30 min:  Reddit crypto scan
               ├── r/cryptocurrency, r/CryptoMarkets
               ├── r/bitcoin, r/ethereum, r/solana
               └── Social buzz scoring per coin
```

## Crypto Universe (33 coins)

| Category | Coins |
|---|---|
| Large cap | BTC, ETH, SOL, XRP, LTC, ADA, AVAX, DOT, LINK, BCH |
| DeFi | UNI, AAVE, CRV, GRT, LDO, SUSHI, FIL, RENDER, ONDO |
| Meme | DOGE, SHIB, PEPE, BONK, WIF, TRUMP |
| Layer 1/Infra | ARB, POL, XTZ, BAT |
| Other | YFI, SKY, PAXG, HYPE |

## Risk Management

### Stocks
| Guard | Trigger | Action |
|---|---|---|
| Stop loss | Position down 5% | Close position |
| Take profit | Position up 10% | Close position |
| Daily loss limit | Account down 5% today | Stop trading for the day |
| Kill switch | Account down 20% from peak | Liquidate all positions |
| Position cap | Single stock > 35% | Block or scale down |

### Crypto (wider limits for volatility)
| Guard | Trigger | Action |
|---|---|---|
| Stop loss | Position down 8% | Close position |
| Take profit | Position up 15% | Close position |
| Daily loss limit | Account down 8% today | Stop trading for the day |
| Kill switch | Account down 20% from peak | Liquidate all positions |
| Position cap | Single coin > 25% | Block or scale down |

## Strategy Performance (Backtest 2019-2025)

| Strategy | CAGR | Sharpe | Max DD |
|---|---|---|---|
| Aggressive momentum | 74.9% | 1.44 | -47.3% |
| Momentum (vanilla) | 46.9% | 1.20 | -40.0% |
| Momentum + trend filter | 30.1% | 0.95 | -32.1% |
| S&P 500 (benchmark) | 17.3% | 0.91 | -33.7% |

Note: Backtest results are subject to survivorship bias and may not reflect future performance.

## Configuration

All settings are in `config.py`:

```python
# Stocks
UNIVERSE_SOURCE = "sp500"           # "sp500", "nasdaq100", "sp400"
MOMENTUM_LOOKBACK = 21              # short-term momentum (trading days)
TOP_N = 3                           # concentrated: top 3 stocks
MAX_POSITION_PCT = 0.35             # max 35% in one stock

# Crypto
CRYPTO_SYMBOLS = ["BTC/USD", ...]   # 33 coins
CRYPTO_STOP_LOSS_PCT = 0.08         # 8% stop loss
CRYPTO_TAKE_PROFIT_PCT = 0.15       # 15% take profit
CRYPTO_MAX_POSITION_PCT = 0.25      # 25% max per coin

# Risk
MAX_DRAWDOWN_PCT = 0.20             # kill switch at 20% from peak
```

## Stack

- **Python 3.11+**
- **Data:** yfinance, pandas, numpy
- **Visualization:** matplotlib, plotly
- **Brokerage:** Interactive Brokers via `ib_async` (paper and live; stocks, crypto, options, futures)
- **Stock Sourcing:** Wikipedia (S&P 500/NASDAQ-100/S&P 400 constituents)
- **Social Signals:** Reddit JSON API, SEC EDGAR RSS
- **Terminal UI:** ANSI colors, formatted tables, heat bars

## Setup

1. Clone the repo
2. Create virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Open an Interactive Brokers account, then start IB Gateway or TWS with the API enabled (start on paper)
5. Put the connection settings in `.env` (all optional; defaults shown):
   ```
   IB_HOST=127.0.0.1
   IB_PAPER_PORT=4002
   IB_LIVE_PORT=4001
   IB_CLIENT_ID=1
   IB_ACCOUNT=          # blank = auto-detect
   BROKER_MODE=paper    # paper or live
   ```
6. Run: `python live/run.py`
