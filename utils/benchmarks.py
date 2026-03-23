"""Benchmark generation — buy-and-hold strategies for comparison."""

import pandas as pd
import yfinance as yf

from config import INITIAL_CAPITAL
from utils.data import fetch_prices


# Standard benchmarks: ticker -> description
BENCHMARKS = {
    "SPY": "S&P 500",
    "QQQ": "NASDAQ-100",
    "IWM": "Russell 2000 (Small Cap)",
    "VTI": "Total US Market",
}

# 60/40 portfolio components
PORTFOLIO_60_40 = {"SPY": 0.6, "TLT": 0.4}


def buy_and_hold(symbol: str, start: str, end: str, initial_capital: float = INITIAL_CAPITAL) -> pd.Series:
    """Simulate buy-and-hold for a single ticker."""
    prices = fetch_prices([symbol], start=start, end=end)
    if symbol not in prices.columns:
        col = prices.columns[0]
    else:
        col = symbol
    series = prices[col].dropna()
    equity = series / series.iloc[0] * initial_capital
    equity.name = symbol
    return equity


def portfolio_buy_and_hold(
    weights: dict[str, float],
    start: str,
    end: str,
    initial_capital: float = INITIAL_CAPITAL,
    name: str = "60/40 Portfolio",
) -> pd.Series:
    """Simulate a static weighted portfolio (e.g., 60/40 SPY/TLT)."""
    symbols = list(weights.keys())
    prices = fetch_prices(symbols, start=start, end=end)

    # Normalize each to start at 1
    normalized = prices / prices.iloc[0]

    # Weighted sum
    portfolio = sum(normalized[s] * w for s, w in weights.items())
    equity = portfolio * initial_capital
    equity.name = name
    return equity.dropna()


def get_all_benchmarks(
    start: str, end: str, initial_capital: float = INITIAL_CAPITAL
) -> dict[str, pd.Series]:
    """Fetch all standard benchmarks + 60/40 portfolio."""
    results = {}

    for symbol, label in BENCHMARKS.items():
        try:
            results[label] = buy_and_hold(symbol, start, end, initial_capital)
        except Exception as e:
            print(f"  Warning: failed to fetch {symbol}: {e}")

    try:
        results["60/40 (SPY/TLT)"] = portfolio_buy_and_hold(
            PORTFOLIO_60_40, start, end, initial_capital
        )
    except Exception as e:
        print(f"  Warning: failed to build 60/40 portfolio: {e}")

    return results
