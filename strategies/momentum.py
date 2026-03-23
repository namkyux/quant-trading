"""
Momentum Strategy — N-day price momentum on S&P 500 stocks.

How it works:
1. Rank stocks by their N-day return (lookback period).
2. Go equal-weight long the top K stocks.
3. Rebalance every M trading days.
4. Optional: trend filter — only invest when market is above 200-day SMA.

Run: python strategies/momentum.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
)
from utils.pipeline import run_pipeline
from utils.screener import ScreenCriteria
from utils.trend_filter import get_market_index, is_uptrend


def make_momentum_strategy(
    lookback: int = MOMENTUM_LOOKBACK,
    top_n: int = TOP_N,
    market_prices: pd.Series | None = None,
    trend_sma: int = 200,
):
    """
    Factory that returns a momentum strategy function.

    If market_prices is provided, applies a trend filter:
    go to cash when the market is below its SMA.
    """
    def strategy_fn(date: pd.Timestamp, prices: pd.DataFrame) -> dict[str, float]:
        if len(prices) < lookback:
            return {}

        # Trend filter: if market is in downtrend, go to cash
        if market_prices is not None:
            # Find the index position of this date in market_prices
            if date in market_prices.index:
                date_idx = market_prices.index.get_loc(date)
                if not is_uptrend(market_prices, date_idx, sma_period=trend_sma):
                    return {}  # all cash

        # N-day return
        current = prices.iloc[-1]
        past = prices.iloc[-lookback]
        returns = (current / past - 1).dropna()

        # Pick top N
        top_symbols = returns.nlargest(top_n).index.tolist()
        weight = 1.0 / top_n

        return {s: weight for s in top_symbols}

    return strategy_fn


def run_backtest(
    source: str = UNIVERSE_SOURCE,
    start: str = "2019-01-01",
    end: str = "2025-12-31",
    lookback: int = MOMENTUM_LOOKBACK,
    top_n: int = TOP_N,
    rebalance_freq: int = REBALANCE_FREQ,
    use_trend_filter: bool = False,
    trend_sma: int = 200,
) -> pd.Series:
    """Run the momentum strategy backtest."""
    market_prices = None
    if use_trend_filter:
        market_prices = get_market_index(start, end)

    strategy_fn = make_momentum_strategy(
        lookback=lookback,
        top_n=top_n,
        market_prices=market_prices,
        trend_sma=trend_sma,
    )

    suffix = f"{lookback}-day"
    if use_trend_filter:
        suffix += f" + {trend_sma}SMA filter"

    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    equity = run_pipeline(
        strategy_fn=strategy_fn,
        strategy_name=f"Momentum ({suffix})",
        source=source,
        criteria=criteria,
        start=start,
        end=end,
        rebalance_freq=rebalance_freq,
        lookback=lookback,
    )

    return equity


if __name__ == "__main__":
    run_backtest()
