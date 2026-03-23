"""Trend filter — market regime detection to avoid trading in downtrends."""

import pandas as pd
import yfinance as yf

from utils.data import fetch_prices


def is_uptrend(
    market_prices: pd.Series,
    date_idx: int,
    sma_period: int = 200,
) -> bool:
    """
    Check if the market is in an uptrend.

    Rule: price is above its N-day simple moving average.
    When the market is below the SMA, we go to cash (or reduce exposure).
    """
    if date_idx < sma_period:
        return True  # not enough data, assume uptrend

    window = market_prices.iloc[date_idx - sma_period + 1 : date_idx + 1]
    sma = window.mean()
    current_price = market_prices.iloc[date_idx]

    return current_price > sma


def get_market_index(start: str, end: str, symbol: str = "SPY") -> pd.Series:
    """Fetch the market index prices for trend filtering."""
    prices = fetch_prices([symbol], start=start, end=end)
    if symbol in prices.columns:
        return prices[symbol]
    return prices.iloc[:, 0]
