"""
Sector Rotation Strategy — Rotate into the strongest sectors using ETFs.

How it works:
1. Track sector ETFs (XLK, XLF, XLE, XLV, etc.) + safe havens (TLT, GLD).
2. Rank by N-day momentum.
3. Go equal-weight into the top K sectors.
4. When all sectors are in a downtrend, rotate to bonds/gold (risk-off).

This is a macro-level strategy that complements stock-level momentum.

Run: python strategies/sector_rotation.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from config import INITIAL_CAPITAL
from utils.data import fetch_prices
from utils.backtest_engine import BacktestEngine
from utils.metrics import print_report
from utils.plotting import plot_equity_curve
from utils.trend_filter import is_uptrend


# Sector ETFs + safe havens
SECTOR_ETFS = {
    # Risk-on (sectors)
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

SAFE_HAVENS = {
    "TLT": "Long-Term Bonds",
    "GLD": "Gold",
}


def make_sector_rotation_strategy(
    lookback: int = 63,  # 3-month momentum for sectors
    top_k: int = 3,
    trend_sma: int = 200,
    use_safe_haven: bool = True,
):
    """
    Factory that returns a sector rotation strategy function.

    Rotates into top momentum sectors.
    Falls back to safe havens when the broad market is weak.
    """
    sector_symbols = list(SECTOR_ETFS.keys())
    safe_symbols = list(SAFE_HAVENS.keys())

    def strategy_fn(date: pd.Timestamp, prices: pd.DataFrame) -> dict[str, float]:
        if len(prices) < lookback:
            return {}

        # Compute momentum for sector ETFs
        current = prices.iloc[-1]
        past = prices.iloc[-lookback]
        returns = (current / past - 1).dropna()

        # Only rank sector ETFs (not safe havens)
        sector_returns = returns[[s for s in sector_symbols if s in returns.index]]

        if len(sector_returns) == 0:
            return {}

        # Check if broad market is in uptrend using SPY (if available)
        # Use average sector return as a proxy if SPY not in universe
        avg_sector_return = sector_returns.mean()

        if use_safe_haven and avg_sector_return < 0:
            # Risk-off: rotate to safe havens
            available_safe = [s for s in safe_symbols if s in returns.index]
            if available_safe:
                weight = 1.0 / len(available_safe)
                return {s: weight for s in available_safe}

        # Risk-on: pick top K sectors by momentum
        top_sectors = sector_returns.nlargest(top_k)

        # Only invest in sectors with positive momentum
        top_sectors = top_sectors[top_sectors > 0]

        if len(top_sectors) == 0:
            # All sectors negative, go to safe havens
            available_safe = [s for s in safe_symbols if s in returns.index]
            if available_safe:
                weight = 1.0 / len(available_safe)
                return {s: weight for s in available_safe}
            return {}

        weight = 1.0 / len(top_sectors)
        return {s: weight for s in top_sectors.index}

    return strategy_fn


def run_backtest(
    start: str = "2019-01-01",
    end: str = "2025-12-31",
    lookback: int = 63,
    top_k: int = 3,
    rebalance_freq: int = 21,
) -> pd.Series:
    """Run the sector rotation strategy backtest."""
    all_symbols = list(SECTOR_ETFS.keys()) + list(SAFE_HAVENS.keys())
    prices = fetch_prices(all_symbols, start=start, end=end)

    strategy_fn = make_sector_rotation_strategy(
        lookback=lookback,
        top_k=top_k,
    )

    rebalance_days = list(range(lookback, len(prices), rebalance_freq))

    engine = BacktestEngine(prices, initial_capital=INITIAL_CAPITAL)
    equity = engine.run(strategy_fn, rebalance_days=rebalance_days)

    print_report(equity, strategy_name=f"Sector Rotation (top {top_k})")

    backtests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtests")
    os.makedirs(backtests_dir, exist_ok=True)
    plot_equity_curve(
        equity,
        strategy_name=f"Sector Rotation (top {top_k})",
        save_path=os.path.join(backtests_dir, "sector_rotation_equity.png"),
    )

    return equity


if __name__ == "__main__":
    run_backtest()
