"""
Combined Multi-Strategy Runner

Runs momentum, mean reversion, and sector rotation independently,
then combines them into a blended portfolio.

Allocation logic:
- Each strategy gets an equal capital allocation by default.
- Each runs independently with its own universe and rules.
- Combined equity = weighted sum of individual equity curves.

This diversifies across strategies that work in different regimes:
- Momentum: strong in trending bull markets
- Mean reversion: strong in choppy/sideways markets
- Sector rotation: adapts to macro regime shifts, defensive in downturns

Run: python strategies/combined.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME, INITIAL_CAPITAL,
)
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.data import fetch_prices
from utils.backtest_engine import BacktestEngine
from utils.benchmarks import get_all_benchmarks
from utils.trend_filter import get_market_index
from utils.metrics import print_report
from utils.plotting import plot_comparison, print_comparison_table
from strategies.momentum import make_momentum_strategy
from strategies.mean_reversion import make_mean_reversion_strategy
from strategies.sector_rotation import (
    make_sector_rotation_strategy, SECTOR_ETFS, SAFE_HAVENS,
)


START = "2019-01-01"
END = "2025-12-31"

# Strategy allocation weights (must sum to 1.0)
STRATEGY_WEIGHTS = {
    "momentum": 0.40,
    "mean_reversion": 0.30,
    "sector_rotation": 0.30,
}


def run_stock_strategy(name, strategy_fn, prices, rebalance_days, capital):
    """Run a stock-level strategy and return equity curve."""
    engine = BacktestEngine(prices, initial_capital=capital)
    equity = engine.run(strategy_fn, rebalance_days=rebalance_days)
    print_report(equity, strategy_name=name)
    return equity


def main():
    print(f"\n{'#'*60}")
    print(f"  MULTI-STRATEGY PORTFOLIO")
    print(f"  Allocation: Momentum {STRATEGY_WEIGHTS['momentum']:.0%} | "
          f"Mean Reversion {STRATEGY_WEIGHTS['mean_reversion']:.0%} | "
          f"Sector Rotation {STRATEGY_WEIGHTS['sector_rotation']:.0%}")
    print(f"{'#'*60}")

    # --- Shared setup for stock strategies ---
    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    print("\n[1/5] Sourcing and screening stock universe...")
    universe_df = get_universe(UNIVERSE_SOURCE)
    symbols = screen(universe_df, criteria)
    stock_prices = fetch_prices(symbols, start=START, end=END)

    # Clean up
    min_rows = len(stock_prices) * 0.8
    valid_cols = stock_prices.columns[stock_prices.count() >= min_rows]
    stock_prices = stock_prices[valid_cols]
    print(f"  Stock universe: {len(stock_prices.columns)} stocks, {len(stock_prices)} days")

    # Fetch market index for trend filter
    market_prices = get_market_index(START, END)

    results = {}

    # --- 1. Momentum (with trend filter — the "tradeable" config) ---
    print(f"\n[2/5] Running Momentum strategy...")
    mom_capital = INITIAL_CAPITAL * STRATEGY_WEIGHTS["momentum"]
    mom_strategy = make_momentum_strategy(
        lookback=MOMENTUM_LOOKBACK,
        top_n=TOP_N,
        market_prices=market_prices,
        trend_sma=200,
    )
    mom_rebalance = list(range(MOMENTUM_LOOKBACK, len(stock_prices), 5))  # weekly
    mom_equity = run_stock_strategy(
        "Momentum (trend-filtered)", mom_strategy, stock_prices, mom_rebalance, mom_capital,
    )
    results["Momentum"] = mom_equity

    # --- 2. Mean Reversion ---
    print(f"\n[3/5] Running Mean Reversion strategy...")
    mr_capital = INITIAL_CAPITAL * STRATEGY_WEIGHTS["mean_reversion"]
    mr_strategy = make_mean_reversion_strategy(
        rsi_period=14,
        oversold=30,
        max_positions=10,
    )
    mr_rebalance = list(range(50, len(stock_prices), 5))  # weekly
    mr_equity = run_stock_strategy(
        "Mean Reversion (RSI<30)", mr_strategy, stock_prices, mr_rebalance, mr_capital,
    )
    results["Mean Reversion"] = mr_equity

    # --- 3. Sector Rotation ---
    print(f"\n[4/5] Running Sector Rotation strategy...")
    sr_capital = INITIAL_CAPITAL * STRATEGY_WEIGHTS["sector_rotation"]
    all_etfs = list(SECTOR_ETFS.keys()) + list(SAFE_HAVENS.keys())
    etf_prices = fetch_prices(all_etfs, start=START, end=END)

    sr_strategy = make_sector_rotation_strategy(lookback=63, top_k=3)
    sr_rebalance = list(range(63, len(etf_prices), 21))

    sr_engine = BacktestEngine(etf_prices, initial_capital=sr_capital)
    sr_equity = sr_engine.run(sr_strategy, rebalance_days=sr_rebalance)
    print_report(sr_equity, strategy_name="Sector Rotation (top 3)")
    results["Sector Rotation"] = sr_equity

    # --- 4. Combined Portfolio ---
    print(f"\n[5/5] Building combined portfolio...")

    # Align all equity curves to the same dates
    combined_df = pd.DataFrame(results)
    combined_df = combined_df.dropna()

    # Combined = sum of all strategy equity curves
    combined_equity = combined_df.sum(axis=1)
    combined_equity.name = "Combined"
    results["COMBINED PORTFOLIO"] = combined_equity
    print_report(combined_equity, strategy_name="Combined Multi-Strategy")

    # --- Benchmarks ---
    print("\nFetching benchmarks...")
    benchmarks = get_all_benchmarks(START, END, INITIAL_CAPITAL)

    # Build final comparison (strategies + benchmarks)
    all_curves = {}
    all_curves["Combined Portfolio"] = combined_equity
    all_curves["  Momentum (40%)"] = mom_equity
    all_curves["  Mean Reversion (30%)"] = mr_equity
    all_curves["  Sector Rotation (30%)"] = sr_equity
    all_curves.update(benchmarks)

    print_comparison_table(all_curves)

    # Plot
    backtests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests")
    os.makedirs(backtests_dir, exist_ok=True)

    plot_comparison(
        all_curves,
        title="Multi-Strategy Portfolio vs Benchmarks (2019-2025)",
        save_path=os.path.join(backtests_dir, "combined_portfolio.png"),
    )


if __name__ == "__main__":
    main()
