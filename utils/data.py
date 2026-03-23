"""Market data fetching and caching via yfinance."""

import hashlib
import os

import pandas as pd
import yfinance as yf

from config import DATA_DIR


def fetch_prices(symbols: list[str], start: str, end: str, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch adjusted close prices for a list of symbols.

    Returns a DataFrame with dates as index and symbols as columns.
    Caches data locally to avoid re-downloading.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    symbols_hash = hashlib.md5("_".join(sorted(symbols)).encode()).hexdigest()[:12]
    cache_key = f"prices_{symbols_hash}_{start}_{end}.parquet"
    cache_path = os.path.join(DATA_DIR, cache_key)

    if use_cache and os.path.exists(cache_path):
        print(f"Loading cached data from {cache_path}")
        return pd.read_parquet(cache_path)

    print(f"Downloading data for {len(symbols)} symbols from {start} to {end}...")
    data = yf.download(symbols, start=start, end=end, auto_adjust=True)

    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data[["Close"]]
        prices.columns = symbols

    prices = prices.dropna(how="all")

    prices.to_parquet(cache_path)
    print(f"Cached data to {cache_path}")

    return prices
