"""
Mean Reversion Strategy — Buy oversold quality stocks, sell when they recover.

How it works:
1. Compute RSI (Relative Strength Index) for each stock.
2. Buy stocks with RSI below oversold threshold (e.g., 30).
3. Equal-weight across selected stocks.
4. Rebalance regularly — exit when RSI normalizes.

This is the opposite of momentum: buy losers expecting a bounce.
Works best in choppy/sideways markets where momentum fails.

Run: python strategies/mean_reversion.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from config import (
    UNIVERSE_SOURCE, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
)
from utils.pipeline import run_pipeline
from utils.screener import ScreenCriteria


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI for a single price series."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(span=period, min_periods=period).mean()
    avg_loss = loss.ewm(span=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def make_mean_reversion_strategy(
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
    max_positions: int = 10,
    min_lookback: int = 50,
):
    """
    Factory that returns a mean reversion strategy function.

    Buys the most oversold stocks (lowest RSI below threshold).
    Goes to cash if nothing is oversold.
    """
    def strategy_fn(date: pd.Timestamp, prices: pd.DataFrame) -> dict[str, float]:
        if len(prices) < min_lookback:
            return {}

        # Compute RSI for all stocks
        rsi_values = {}
        for col in prices.columns:
            series = prices[col].dropna()
            if len(series) < rsi_period + 1:
                continue
            rsi = compute_rsi(series, period=rsi_period)
            if not np.isnan(rsi.iloc[-1]):
                rsi_values[col] = rsi.iloc[-1]

        if not rsi_values:
            return {}

        rsi_series = pd.Series(rsi_values)

        # Filter to oversold stocks
        oversold_stocks = rsi_series[rsi_series < oversold].sort_values()

        if len(oversold_stocks) == 0:
            return {}  # nothing oversold, stay in cash

        # Take the most oversold (up to max_positions)
        selected = oversold_stocks.head(max_positions)
        weight = 1.0 / len(selected)

        return {s: weight for s in selected.index}

    return strategy_fn


def run_backtest(
    source: str = UNIVERSE_SOURCE,
    start: str = "2019-01-01",
    end: str = "2025-12-31",
    rsi_period: int = 14,
    oversold: float = 30,
    max_positions: int = 10,
    rebalance_freq: int = 5,  # weekly default — mean reversion needs faster reaction
) -> pd.Series:
    """Run the mean reversion strategy backtest."""
    strategy_fn = make_mean_reversion_strategy(
        rsi_period=rsi_period,
        oversold=oversold,
        max_positions=max_positions,
    )

    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    equity = run_pipeline(
        strategy_fn=strategy_fn,
        strategy_name=f"Mean Reversion (RSI<{int(oversold)})",
        source=source,
        criteria=criteria,
        start=start,
        end=end,
        rebalance_freq=rebalance_freq,
        lookback=50,
    )

    return equity


if __name__ == "__main__":
    run_backtest()
