"""
Strategy Comparison Runner

Runs momentum strategy (with and without trend filter) against
multiple benchmarks and produces a side-by-side comparison.

Run: python strategies/compare.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME, INITIAL_CAPITAL,
)
from utils.pipeline import run_pipeline
from utils.screener import ScreenCriteria
from utils.benchmarks import get_all_benchmarks
from utils.trend_filter import get_market_index
from utils.plotting import plot_comparison, print_comparison_table
from strategies.momentum import make_momentum_strategy


START = "2019-01-01"
END = "2025-12-31"


def main():
    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    results = {}

    # --- Strategy 1: Vanilla Momentum ---
    print("\n" + "=" * 60)
    print("  RUNNING: Vanilla Momentum")
    print("=" * 60)

    strategy_fn = make_momentum_strategy(
        lookback=MOMENTUM_LOOKBACK,
        top_n=TOP_N,
    )

    results["Momentum (vanilla)"] = run_pipeline(
        strategy_fn=strategy_fn,
        strategy_name="Momentum (vanilla)",
        source=UNIVERSE_SOURCE,
        criteria=criteria,
        start=START,
        end=END,
        rebalance_freq=REBALANCE_FREQ,
        lookback=MOMENTUM_LOOKBACK,
        save_chart=False,
    )

    # --- Strategy 2: Momentum + Trend Filter ---
    print("\n" + "=" * 60)
    print("  RUNNING: Momentum + 200-day SMA Trend Filter")
    print("=" * 60)

    market_prices = get_market_index(START, END)

    strategy_fn_filtered = make_momentum_strategy(
        lookback=MOMENTUM_LOOKBACK,
        top_n=TOP_N,
        market_prices=market_prices,
        trend_sma=200,
    )

    results["Momentum + trend filter"] = run_pipeline(
        strategy_fn=strategy_fn_filtered,
        strategy_name="Momentum + 200SMA filter",
        source=UNIVERSE_SOURCE,
        criteria=criteria,
        start=START,
        end=END,
        rebalance_freq=REBALANCE_FREQ,
        lookback=MOMENTUM_LOOKBACK,
        save_chart=False,
    )

    # --- Benchmarks ---
    print("\n" + "=" * 60)
    print("  FETCHING BENCHMARKS")
    print("=" * 60)

    benchmarks = get_all_benchmarks(START, END, INITIAL_CAPITAL)
    results.update(benchmarks)

    # --- Comparison ---
    print_comparison_table(results)

    backtests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests")
    os.makedirs(backtests_dir, exist_ok=True)
    save_path = os.path.join(backtests_dir, "strategy_comparison.png")

    plot_comparison(results, title="Momentum vs Benchmarks (2019-2025)", save_path=save_path)


if __name__ == "__main__":
    main()
