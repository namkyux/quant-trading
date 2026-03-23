"""Dynamic universe sourcing — pull index constituents from Wikipedia."""

import os
import urllib.request
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd

from config import DATA_DIR


def _clean_symbol(symbol: str) -> str:
    """Convert Wikipedia symbol format to yfinance format (e.g., BRK.B -> BRK-B)."""
    return symbol.replace(".", "-").strip()


def get_sp500(cache: bool = True) -> pd.DataFrame:
    """
    Fetch S&P 500 constituents from Wikipedia.

    Returns DataFrame with columns: symbol, name, sector, sub_industry
    """
    return _fetch_wiki_index(
        url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        table_index=0,
        col_map={"Symbol": "symbol", "Security": "name", "GICS Sector": "sector",
                 "GICS Sub-Industry": "sub_industry"},
        cache_name="sp500",
        cache=cache,
    )


def get_nasdaq100(cache: bool = True) -> pd.DataFrame:
    """Fetch NASDAQ-100 constituents from Wikipedia."""
    return _fetch_wiki_index(
        url="https://en.wikipedia.org/wiki/Nasdaq-100",
        table_index=4,
        col_map={"Ticker": "symbol", "Company": "name", "GICS Sector": "sector",
                 "GICS Sub-Industry": "sub_industry"},
        cache_name="nasdaq100",
        cache=cache,
    )


def get_sp400(cache: bool = True) -> pd.DataFrame:
    """Fetch S&P MidCap 400 constituents from Wikipedia."""
    return _fetch_wiki_index(
        url="https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        table_index=0,
        col_map={"Symbol": "symbol", "Security": "name", "GICS Sector": "sector",
                 "GICS Sub-Industry": "sub_industry"},
        cache_name="sp400",
        cache=cache,
    )


def get_universe(source: str = "sp500", cache: bool = True) -> pd.DataFrame:
    """
    Get a universe of stocks by source name.

    Args:
        source: "sp500", "nasdaq100", or "sp400"
        cache: whether to use cached data (7-day TTL)

    Returns:
        DataFrame with columns: symbol, name, sector, sub_industry
    """
    sources = {
        "sp500": get_sp500,
        "nasdaq100": get_nasdaq100,
        "sp400": get_sp400,
    }
    if source not in sources:
        raise ValueError(f"Unknown source '{source}'. Available: {list(sources.keys())}")

    return sources[source](cache=cache)


def _fetch_wiki_index(
    url: str,
    table_index: int,
    col_map: dict[str, str],
    cache_name: str,
    cache: bool = True,
) -> pd.DataFrame:
    """Shared logic for fetching an index from Wikipedia."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, f"universe_{cache_name}.parquet")

    # Check cache (7-day TTL)
    if cache and os.path.exists(cache_path):
        mod_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        if datetime.now() - mod_time < timedelta(days=7):
            print(f"Loading cached {cache_name} universe ({mod_time.date()})")
            return pd.read_parquet(cache_path)

    print(f"Fetching {cache_name} constituents from Wikipedia...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
    tables = pd.read_html(StringIO(html))
    df = tables[table_index]

    # Rename columns to standard names
    available_cols = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available_cols.keys())].rename(columns=available_cols)

    # Clean symbols
    df["symbol"] = df["symbol"].apply(_clean_symbol)

    # Drop duplicates
    df = df.drop_duplicates(subset="symbol").reset_index(drop=True)

    df.to_parquet(cache_path)
    print(f"Cached {len(df)} {cache_name} symbols to {cache_path}")

    return df
