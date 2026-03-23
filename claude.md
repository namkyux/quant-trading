# Quant Trading Project

## About Me

- Comfortable Python developer
- Trading background: stocks/ETFs (buy & hold)
- Learning quant trading from the ground up
- Goal: build automated trading systems, eventually live auto-trading
- Target: $10K → $2M

## Project Goal

Build a full quant trading system:

1. Backtesting engine for strategy development
2. Paper trading via brokerage API
3. Live automated trading with risk guardrails

## Stack

- **Language:** Python 3.11+
- **Data:** `yfinance` for market data
- **Analysis:** `pandas`, `numpy`
- **Visualization:** `matplotlib`, `plotly`
- **Backtesting:** custom-built engine with slippage and commissions
- **Brokerage API:** Alpaca (paper → live)
- **Stock Sourcing:** Wikipedia (S&P 500, NASDAQ-100, S&P 400)
- **Social Signals:** Reddit JSON API, SEC EDGAR RSS
- **Dependencies:** `lxml`, `pyarrow`, `requests`, `praw`, `feedparser`

## Repo Structure

```
quant-trading/
├── CLAUDE.md
├── README.md
├── README_KR.md
├── config.py                  # All settings: universe, strategy params, risk limits
├── .env                       # API keys (never committed)
├── requirements.txt
│
├── strategies/                # Strategy definitions
│   ├── momentum.py            # Classic N-day momentum
│   ├── aggressive_momentum.py # Multi-timeframe + breakout + volume
│   ├── mean_reversion.py      # RSI-based mean reversion
│   ├── sector_rotation.py     # Sector ETF rotation
│   ├── combined.py            # Multi-strategy portfolio
│   ├── compare.py             # Strategy vs benchmark comparison
│   └── param_sweep.py         # Parameter optimization
│
├── live/                      # Live/paper trading
│   ├── run.py                 # Main entry point
│   ├── day_trader.py          # Continuous intraday trading loop
│   ├── trader.py              # Single-cycle rebalance trader
│   ├── broker.py              # Alpaca API wrapper
│   ├── risk_manager.py        # Kill switch, position limits
│   ├── scan.py                # Hot stock scanner CLI
│   ├── paper_trade.py         # Scheduled paper trading
│   └── check_positions.py     # Quick position check
│
├── utils/                     # Shared infrastructure
│   ├── scanner.py             # Hot stock detection
│   ├── universe.py            # Dynamic stock sourcing
│   ├── screener.py            # Stock screening
│   ├── data.py                # Price data + caching
│   ├── backtest_engine.py     # Custom backtesting engine
│   ├── pipeline.py            # Source → screen → fetch → backtest
│   ├── benchmarks.py          # Buy-and-hold benchmarks
│   ├── trend_filter.py        # Market regime detection
│   ├── metrics.py             # Performance metrics
│   └── plotting.py            # Charts and comparison plots
│
├── backtests/                 # Saved charts and results
├── data/                      # Cached market data (parquet)
└── notebooks/                 # Exploratory analysis
```

## Coding Conventions

- Keep strategies modular — each strategy is a self-contained class or function
- Never hardcode API keys — use `.env` + `python-dotenv`
- Every backtest should output: Sharpe ratio, max drawdown, total return, CAGR
- Always plot equity curve when running a backtest
- Write simple, readable code over clever code — this is a learning project

## Key Concepts to Reinforce

- **No lookahead bias** — never use future data in a signal calculation
- **Realistic backtesting** — account for slippage, commissions
- **Position sizing** — never go all-in; default to equal-weight or Kelly criterion
- **Risk first** — define max drawdown tolerance before optimizing returns

## Current Phase

🟢 Phase 2 — Paper trading live via Alpaca with aggressive momentum + hot stock scanner

## Strategies Tracker

| Strategy | Status | Sharpe | Max DD | Notes |
|---|---|---|---|---|
| Momentum (vanilla) | Done | 1.20 | -40.0% | 126-day lookback, top 5 |
| Momentum + trend filter | Done | 0.95 | -32.1% | 200-day SMA filter |
| Aggressive momentum | Done | 1.44 | -47.3% | Multi-timeframe, top 3, daily |
| Mean reversion (RSI) | Done | 0.21 | -62.5% | Needs improvement |
| Sector rotation | Done | 0.28 | -36.1% | Needs tuning |
| Combined portfolio | Done | 1.05 | -30.9% | 40/30/30 split |

## Live Trading Rules

- Max position size: 35% of portfolio
- Stop loss: 5% per position
- Take profit: 10% per position
- Daily loss limit: 5% — stops trading for the day
- Kill switch: 20% from peak — liquidates everything
- Never trade in first 15 min of market open (avoid spread spikes)
- Scan interval: every 15 minutes during market hours
- Hot stock scan: hourly (volume anomalies, Reddit buzz, insider filings)

## Commands

```bash
# --- Live Trading ---
python live/run.py --paper           # Run day trader (continuous)
python live/run.py --dry-run         # See what it would trade
python live/run.py --once            # One rebalance cycle
python live/run.py --once --dry-run  # One cycle, no execution
python live/run.py --status          # Check account + positions

# --- Hot Stock Scanner ---
python live/scan.py                  # Quick scan
python live/scan.py --full           # Full scan (+ Reddit + insider)
python live/scan.py --full --squeeze # Include short squeeze

# --- Backtesting ---
python strategies/momentum.py
python strategies/aggressive_momentum.py
python strategies/compare.py         # vs benchmarks
python strategies/param_sweep.py     # 96 param combos
python strategies/combined.py        # multi-strategy
```
