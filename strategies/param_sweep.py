"""
Parameter Sweep — Test momentum strategy across different parameter combinations.

Finds robust parameters that work across different settings,
not just one lucky combination.

Run: python strategies/param_sweep.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from config import (
    UNIVERSE_SOURCE, SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME, INITIAL_CAPITAL,
)
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.data import fetch_prices
from utils.backtest_engine import BacktestEngine
from utils.metrics import total_return, cagr, sharpe_ratio, max_drawdown
from utils.trend_filter import get_market_index, is_uptrend
from strategies.momentum import make_momentum_strategy


# Parameter grid
LOOKBACKS = [63, 126, 189, 252]     # 3mo, 6mo, 9mo, 12mo
TOP_NS = [3, 5, 10, 20]              # number of stocks to hold
REBALANCE_FREQS = [5, 21, 63]        # weekly, monthly, quarterly
USE_TREND_FILTER = [False, True]

START = "2019-01-01"
END = "2025-12-31"


def main():
    # Fetch data once
    print("Setting up universe and data (one-time)...")

    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    universe_df = get_universe(UNIVERSE_SOURCE)
    symbols = screen(universe_df, criteria)
    prices = fetch_prices(symbols, start=START, end=END)

    # Drop columns with too many NaNs
    min_rows = len(prices) * 0.8
    valid_cols = prices.columns[prices.count() >= min_rows]
    prices = prices[valid_cols]

    market_prices = get_market_index(START, END)

    print(f"Universe: {len(prices.columns)} stocks, {len(prices)} trading days")
    print(f"\nRunning parameter sweep...")
    print(f"  Lookbacks: {LOOKBACKS}")
    print(f"  Top N: {TOP_NS}")
    print(f"  Rebalance freq: {REBALANCE_FREQS}")
    print(f"  Trend filter: {USE_TREND_FILTER}")
    total_combos = len(LOOKBACKS) * len(TOP_NS) * len(REBALANCE_FREQS) * len(USE_TREND_FILTER)
    print(f"  Total combinations: {total_combos}\n")

    results = []
    combo_num = 0

    for lookback in LOOKBACKS:
        for top_n in TOP_NS:
            for rebal in REBALANCE_FREQS:
                for use_trend in USE_TREND_FILTER:
                    combo_num += 1
                    label = f"L={lookback} N={top_n} R={rebal} TF={'Y' if use_trend else 'N'}"

                    strategy_fn = make_momentum_strategy(
                        lookback=lookback,
                        top_n=top_n,
                        market_prices=market_prices if use_trend else None,
                        trend_sma=200,
                    )

                    rebalance_days = list(range(lookback, len(prices), rebal))

                    engine = BacktestEngine(prices, initial_capital=INITIAL_CAPITAL)
                    equity = engine.run(strategy_fn, rebalance_days=rebalance_days)

                    results.append({
                        "lookback": lookback,
                        "top_n": top_n,
                        "rebalance_freq": rebal,
                        "trend_filter": use_trend,
                        "total_return": total_return(equity),
                        "cagr": cagr(equity),
                        "sharpe": sharpe_ratio(equity),
                        "max_dd": max_drawdown(equity),
                        "final_value": equity.iloc[-1],
                    })

                    if combo_num % 10 == 0 or combo_num == total_combos:
                        print(f"  [{combo_num}/{total_combos}] {label} -> "
                              f"Sharpe={results[-1]['sharpe']:.2f}, "
                              f"CAGR={results[-1]['cagr']:.1%}, "
                              f"MaxDD={results[-1]['max_dd']:.1%}")

    df = pd.DataFrame(results)

    # Sort by Sharpe ratio (risk-adjusted returns matter most)
    df_sorted = df.sort_values("sharpe", ascending=False)

    print(f"\n{'='*90}")
    print(f"  TOP 10 PARAMETER COMBINATIONS (by Sharpe Ratio)")
    print(f"{'='*90}")
    print(f"  {'Lookback':>8} {'Top N':>6} {'Rebal':>6} {'Trend':>6} {'Return':>9} {'CAGR':>8} {'Sharpe':>8} {'Max DD':>9}")
    print(f"  {'-'*72}")

    for _, row in df_sorted.head(10).iterrows():
        print(
            f"  {int(row['lookback']):>8} "
            f"{int(row['top_n']):>6} "
            f"{int(row['rebalance_freq']):>6} "
            f"{'Yes' if row['trend_filter'] else 'No':>6} "
            f"{row['total_return']:>8.1%} "
            f"{row['cagr']:>7.1%} "
            f"{row['sharpe']:>7.2f} "
            f"{row['max_dd']:>8.1%}"
        )

    print(f"\n{'='*90}")
    print(f"  WORST 5 COMBINATIONS")
    print(f"{'='*90}")
    print(f"  {'Lookback':>8} {'Top N':>6} {'Rebal':>6} {'Trend':>6} {'Return':>9} {'CAGR':>8} {'Sharpe':>8} {'Max DD':>9}")
    print(f"  {'-'*72}")

    for _, row in df_sorted.tail(5).iterrows():
        print(
            f"  {int(row['lookback']):>8} "
            f"{int(row['top_n']):>6} "
            f"{int(row['rebalance_freq']):>6} "
            f"{'Yes' if row['trend_filter'] else 'No':>6} "
            f"{row['total_return']:>8.1%} "
            f"{row['cagr']:>7.1%} "
            f"{row['sharpe']:>7.2f} "
            f"{row['max_dd']:>8.1%}"
        )

    # Key insights
    print(f"\n{'='*90}")
    print(f"  KEY INSIGHTS")
    print(f"{'='*90}")

    avg_with_trend = df[df["trend_filter"]]["sharpe"].mean()
    avg_without_trend = df[~df["trend_filter"]]["sharpe"].mean()
    avg_dd_with = df[df["trend_filter"]]["max_dd"].mean()
    avg_dd_without = df[~df["trend_filter"]]["max_dd"].mean()

    print(f"  Avg Sharpe WITH trend filter:    {avg_with_trend:.2f}")
    print(f"  Avg Sharpe WITHOUT trend filter: {avg_without_trend:.2f}")
    print(f"  Avg Max DD WITH trend filter:    {avg_dd_with:.1%}")
    print(f"  Avg Max DD WITHOUT trend filter: {avg_dd_without:.1%}")

    best = df_sorted.iloc[0]
    print(f"\n  Best overall: Lookback={int(best['lookback'])}, Top N={int(best['top_n'])}, "
          f"Rebalance={int(best['rebalance_freq'])}d, "
          f"Trend Filter={'Yes' if best['trend_filter'] else 'No'}")
    print(f"  -> Sharpe={best['sharpe']:.2f}, CAGR={best['cagr']:.1%}, Max DD={best['max_dd']:.1%}")

    # Save results
    results_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests", "param_sweep_results.csv")
    df_sorted.to_csv(results_path, index=False)
    print(f"\n  Full results saved to {results_path}")
    print(f"{'='*90}\n")


if __name__ == "__main__":
    main()
