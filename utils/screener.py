"""Stock screener — filter a universe by price, volume, sector, and data quality."""

import os
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from config import DATA_DIR


@dataclass
class ScreenCriteria:
    """Screening criteria for filtering stocks."""
    min_price: float = 5.0               # exclude penny stocks
    max_price: float | None = None       # optional upper bound
    min_avg_volume: int = 500_000        # 20-day avg daily volume
    min_market_cap: float | None = None  # e.g., 1e9 for $1B+
    sectors: list[str] | None = None     # whitelist (None = all sectors)
    exclude_sectors: list[str] | None = None  # blacklist
    min_history_days: int = 252          # need at least 1 year of data


def screen(
    universe: pd.DataFrame,
    criteria: ScreenCriteria | None = None,
    verbose: bool = True,
) -> list[str]:
    """
    Filter a universe DataFrame down to stocks meeting all criteria.

    Args:
        universe: DataFrame with at least 'symbol' and 'sector' columns
                  (as returned by utils.universe.get_universe)
        criteria: screening criteria (defaults to ScreenCriteria())
        verbose: print progress

    Returns:
        List of ticker symbols that pass all filters.
    """
    if criteria is None:
        criteria = ScreenCriteria()

    df = universe.copy()
    initial_count = len(df)

    # --- Sector filter (free, no API call) ---
    if criteria.sectors is not None:
        df = df[df["sector"].isin(criteria.sectors)]
        if verbose:
            print(f"  Sector whitelist: {len(df)}/{initial_count} remain")

    if criteria.exclude_sectors is not None:
        df = df[~df["sector"].isin(criteria.exclude_sectors)]
        if verbose:
            print(f"  Sector blacklist: {len(df)}/{initial_count} remain")

    symbols = df["symbol"].tolist()
    if not symbols:
        return []

    # --- Price & Volume filter (bulk download, fast) ---
    if verbose:
        print(f"  Downloading 1-month data for {len(symbols)} symbols to filter by price/volume...")

    price_data = yf.download(symbols, period="1mo", auto_adjust=True, progress=False)

    if isinstance(price_data.columns, pd.MultiIndex):
        close = price_data["Close"]
        volume = price_data["Volume"]
    else:
        close = price_data[["Close"]]
        close.columns = symbols
        volume = price_data[["Volume"]]
        volume.columns = symbols

    last_price = close.iloc[-1]
    avg_volume = volume.mean()

    passing = set(symbols)

    # Min price
    if criteria.min_price is not None:
        fail = set(last_price[last_price < criteria.min_price].index)
        fail |= set(last_price[last_price.isna()].index)
        passing -= fail
        if verbose:
            print(f"  Min price (${criteria.min_price}): {len(passing)} remain")

    # Max price
    if criteria.max_price is not None:
        fail = set(last_price[last_price > criteria.max_price].index)
        passing -= fail
        if verbose:
            print(f"  Max price (${criteria.max_price}): {len(passing)} remain")

    # Min avg volume
    if criteria.min_avg_volume is not None:
        fail = set(avg_volume[avg_volume < criteria.min_avg_volume].index)
        fail |= set(avg_volume[avg_volume.isna()].index)
        passing -= fail
        if verbose:
            print(f"  Min avg volume ({criteria.min_avg_volume:,}): {len(passing)} remain")

    # --- Data sufficiency check ---
    # We check history length via the bulk price data timeframe
    # More thorough check happens when full backtest data is fetched
    too_few = set(close.columns[close.count() < close.count().max() * 0.8])
    passing -= too_few
    if verbose and too_few:
        print(f"  Data quality (>80% coverage): {len(passing)} remain")

    result = sorted(passing)
    if verbose:
        print(f"  ✓ Screening complete: {len(result)}/{initial_count} stocks passed")

    return result
