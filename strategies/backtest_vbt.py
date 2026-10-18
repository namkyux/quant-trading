"""
Vectorbt Backtesting — Fast momentum backtest + parameter sweep.

Run:
  python strategies/backtest_vbt.py                # Single backtest
  python strategies/backtest_vbt.py --sweep        # Parameter sweep (all combos)
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME, INITIAL_CAPITAL,
)
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.data import fetch_prices
from utils.backtest_vbt import (
    backtest_momentum, backtest_momentum_sweep,
    print_vbt_report, plot_vbt_results,
)


START = "2019-01-01"
END = "2025-12-31"


def run_single():
    """Run a single momentum backtest with vectorbt."""
    print("Loading universe and data...")
    universe_df = get_universe(UNIVERSE_SOURCE)
    criteria = ScreenCriteria(min_price=SCREEN_MIN_PRICE, min_avg_volume=SCREEN_MIN_AVG_VOLUME)
    symbols = screen(universe_df, criteria)
    prices = fetch_prices(symbols, start=START, end=END)

    # Drop stocks with insufficient history
    min_rows = len(prices) * 0.8
    prices = prices[prices.columns[prices.count() >= min_rows]]
    print(f"Universe: {len(prices.columns)} stocks, {len(prices)} days")

    print(f"\nRunning momentum backtest (lookback={MOMENTUM_LOOKBACK}, top_n={TOP_N}, rebal={REBALANCE_FREQ})...")
    pf = backtest_momentum(
        prices,
        lookback=MOMENTUM_LOOKBACK,
        top_n=TOP_N,
        rebalance_every=REBALANCE_FREQ,
    )

    print_vbt_report(pf, name=f"Momentum ({MOMENTUM_LOOKBACK}d, top {TOP_N})")

    backtests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests")
    os.makedirs(backtests_dir, exist_ok=True)
    plot_vbt_results(pf, name=f"Momentum ({MOMENTUM_LOOKBACK}d)",
                     save_path=os.path.join(backtests_dir, "vbt_momentum.html"))


def run_sweep():
    """Run parameter sweep with vectorbt."""
    print("Loading universe and data...")
    universe_df = get_universe(UNIVERSE_SOURCE)
    criteria = ScreenCriteria(min_price=SCREEN_MIN_PRICE, min_avg_volume=SCREEN_MIN_AVG_VOLUME)
    symbols = screen(universe_df, criteria)
    prices = fetch_prices(symbols, start=START, end=END)

    min_rows = len(prices) * 0.8
    prices = prices[prices.columns[prices.count() >= min_rows]]
    print(f"Universe: {len(prices.columns)} stocks, {len(prices)} days")

    lookbacks = [63, 126, 189, 252]
    top_ns = [3, 5, 10, 20]
    rebal_freqs = [5, 21, 63]
    total = len(lookbacks) * len(top_ns) * len(rebal_freqs)

    print(f"\nRunning {total} parameter combinations...")
    print(f"  Lookbacks:  {lookbacks}")
    print(f"  Top N:      {top_ns}")
    print(f"  Rebalance:  {rebal_freqs}")

    df = backtest_momentum_sweep(prices, lookbacks, top_ns, rebal_freqs)

    # Sort by Sharpe
    df_sorted = df.sort_values("sharpe", ascending=False)

    print(f"\n{'='*95}")
    print(f"  TOP 10 COMBINATIONS (by Sharpe)")
    print(f"{'='*95}")
    print(f"  {'LB':>4} {'TopN':>5} {'Rebal':>6} {'Return':>9} {'Sharpe':>8} {'Sortino':>8} "
          f"{'MaxDD':>8} {'WinRate':>8} {'Trades':>7}")
    print(f"  {'-'*75}")

    for _, row in df_sorted.head(10).iterrows():
        if "error" in row and pd.notna(row.get("error")):
            continue
        print(f"  {int(row['lookback']):>4} {int(row['top_n']):>5} {int(row['rebalance_freq']):>6} "
              f"{row['total_return']:>8.1%} {row['sharpe']:>7.2f} {row['sortino']:>7.2f} "
              f"{row['max_dd']:>7.1%} {row['win_rate']:>7.1%} {row['num_trades']:>7.0f}")

    print(f"\n{'='*95}")
    print(f"  WORST 5")
    print(f"{'='*95}")
    for _, row in df_sorted.tail(5).iterrows():
        if "error" in row and pd.notna(row.get("error")):
            continue
        print(f"  {int(row['lookback']):>4} {int(row['top_n']):>5} {int(row['rebalance_freq']):>6} "
              f"{row['total_return']:>8.1%} {row['sharpe']:>7.2f} {row['sortino']:>7.2f} "
              f"{row['max_dd']:>7.1%} {row['win_rate']:>7.1%} {row['num_trades']:>7.0f}")

    # Save results
    results_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests", "vbt_sweep_results.csv")
    df_sorted.to_csv(results_path, index=False)
    print(f"\n  Full results saved to {results_path}")

    # Best combo
    best = df_sorted.iloc[0]
    print(f"\n  Best: Lookback={int(best['lookback'])}, Top N={int(best['top_n'])}, "
          f"Rebalance={int(best['rebalance_freq'])}d")
    print(f"  -> Sharpe={best['sharpe']:.2f}, Sortino={best['sortino']:.2f}, "
          f"Return={best['total_return']:.1%}, MaxDD={best['max_dd']:.1%}")
    print(f"{'='*95}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true", help="Run parameter sweep")
    args = parser.parse_args()

    if args.sweep:
        run_sweep()
    else:
        run_single()
