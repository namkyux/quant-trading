"""Analysis pipeline — source, screen, fetch, backtest, report."""

import os

import pandas as pd

from config import INITIAL_CAPITAL
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.data import fetch_prices
from utils.backtest_engine import BacktestEngine
from utils.metrics import print_report
from utils.plotting import plot_equity_curve


def run_pipeline(
    strategy_fn,
    strategy_name: str = "Strategy",
    source: str = "sp500",
    criteria: ScreenCriteria | None = None,
    start: str = "2019-01-01",
    end: str = "2025-12-31",
    rebalance_days: list[int] | None = None,
    rebalance_freq: int | None = None,
    lookback: int = 0,
    initial_capital: float = INITIAL_CAPITAL,
    save_chart: bool = True,
) -> pd.Series:
    """
    Full simulation pipeline:
      1. Source universe (from Wikipedia)
      2. Screen stocks (price, volume, sector filters)
      3. Fetch historical prices
      4. Run backtest
      5. Print report + plot equity curve

    Args:
        strategy_fn: callable(date, prices_so_far) -> dict[symbol, weight]
        strategy_name: name for reports/charts
        source: universe source ("sp500", "nasdaq100", "sp400")
        criteria: screening criteria (None = defaults)
        start/end: backtest date range
        rebalance_days: explicit list of rebalance indices, OR
        rebalance_freq: rebalance every N trading days (used with lookback)
        lookback: skip this many initial days before first rebalance
        initial_capital: starting capital
        save_chart: whether to save equity curve chart

    Returns:
        Equity curve as pd.Series
    """
    # 1. Source universe
    print(f"\n{'='*50}")
    print(f"  Pipeline: {strategy_name}")
    print(f"{'='*50}")
    print(f"\n[1/4] Sourcing universe: {source}")
    universe_df = get_universe(source)
    print(f"  Total constituents: {len(universe_df)}")

    # 2. Screen
    print(f"\n[2/4] Screening stocks...")
    symbols = screen(universe_df, criteria)

    if not symbols:
        print("  No stocks passed screening. Aborting.")
        return pd.Series(dtype=float)

    # 3. Fetch prices
    print(f"\n[3/4] Fetching price data for {len(symbols)} stocks ({start} to {end})...")
    prices = fetch_prices(symbols, start=start, end=end)

    # Drop columns with too many NaNs (stocks that didn't exist for full period)
    min_rows = len(prices) * 0.8
    valid_cols = prices.columns[prices.count() >= min_rows]
    dropped = len(prices.columns) - len(valid_cols)
    if dropped > 0:
        print(f"  Dropped {dropped} stocks with insufficient history")
        prices = prices[valid_cols]

    print(f"  Final universe: {len(prices.columns)} stocks, {len(prices)} trading days")

    # 4. Run backtest
    print(f"\n[4/4] Running backtest...")

    if rebalance_days is None and rebalance_freq is not None:
        rebalance_days = list(range(lookback, len(prices), rebalance_freq))

    engine = BacktestEngine(prices, initial_capital=initial_capital)
    equity = engine.run(strategy_fn, rebalance_days=rebalance_days)

    # Report
    print_report(equity, strategy_name=strategy_name)

    # Chart
    if save_chart:
        backtests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests")
        os.makedirs(backtests_dir, exist_ok=True)
        chart_name = strategy_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        save_path = os.path.join(backtests_dir, f"{chart_name}_equity.png")
        plot_equity_curve(equity, strategy_name=strategy_name, save_path=save_path)

    return equity
