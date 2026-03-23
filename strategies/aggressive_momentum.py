"""
Aggressive Momentum Strategy — Short-term momentum with breakout acceleration.

How it works:
1. Score stocks on multiple timeframes (5d, 10d, 21d momentum).
2. Boost score for stocks breaking out to new 20-day highs on high volume.
3. Penalize stocks with high recent volatility (avoid pump-and-dumps).
4. Concentrated bets: top 3 stocks, rebalance daily.
5. 50-day SMA trend filter — go to cash fast if market turns.

This trades more frequently and takes bigger positions than vanilla momentum.
Higher returns potential, but also higher risk.

Run: python strategies/aggressive_momentum.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N, REBALANCE_FREQ,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
)
from utils.pipeline import run_pipeline
from utils.screener import ScreenCriteria
from utils.trend_filter import get_market_index, is_uptrend


def compute_composite_momentum(prices: pd.DataFrame, date_idx: int) -> pd.Series:
    """
    Multi-timeframe momentum score.

    Combines:
    - 5-day return (40% weight) — captures short-term acceleration
    - 10-day return (30% weight) — medium-term trend
    - 21-day return (30% weight) — monthly trend confirmation
    """
    current = prices.iloc[date_idx]

    scores = pd.Series(0.0, index=prices.columns)
    weights_and_periods = [(0.4, 5), (0.3, 10), (0.3, 21)]

    for weight, period in weights_and_periods:
        if date_idx < period:
            continue
        past = prices.iloc[date_idx - period]
        ret = (current / past - 1).fillna(0)
        scores += weight * ret

    return scores


def compute_breakout_bonus(prices: pd.DataFrame, date_idx: int, period: int = 20) -> pd.Series:
    """
    Bonus score for stocks breaking out to new N-day highs.

    Stocks at or near their 20-day high get a boost.
    """
    if date_idx < period:
        return pd.Series(0.0, index=prices.columns)

    window = prices.iloc[date_idx - period + 1 : date_idx + 1]
    high = window.max()
    current = prices.iloc[date_idx]

    # How close to the 20-day high (1.0 = at the high)
    pct_of_high = (current / high).fillna(0)

    # Only give bonus if within 2% of high
    bonus = pd.Series(0.0, index=prices.columns)
    bonus[pct_of_high > 0.98] = 0.3  # 30% score bonus for breakouts
    return bonus


def compute_volume_confirmation(
    prices: pd.DataFrame,
    volumes: pd.DataFrame | None,
    date_idx: int,
) -> pd.Series:
    """
    Volume confirmation — boost stocks with above-average recent volume.

    High volume on up moves = institutional buying = stronger signal.
    """
    if volumes is None or date_idx < 20:
        return pd.Series(0.0, index=prices.columns)

    recent_vol = volumes.iloc[date_idx - 4 : date_idx + 1].mean()  # 5-day avg
    avg_vol = volumes.iloc[date_idx - 19 : date_idx + 1].mean()    # 20-day avg

    vol_ratio = (recent_vol / avg_vol).fillna(1.0)

    bonus = pd.Series(0.0, index=prices.columns)
    bonus[vol_ratio > 1.5] = 0.2   # 20% bonus for high volume
    bonus[vol_ratio > 2.0] = 0.3   # 30% bonus for very high volume
    return bonus


def compute_volatility_penalty(prices: pd.DataFrame, date_idx: int, period: int = 20) -> pd.Series:
    """
    Penalize extremely volatile stocks to avoid pump-and-dumps.

    We want momentum, not chaos.
    """
    if date_idx < period:
        return pd.Series(0.0, index=prices.columns)

    window = prices.iloc[date_idx - period + 1 : date_idx + 1]
    daily_returns = window.pct_change().dropna()
    vol = daily_returns.std() * np.sqrt(252)  # annualized volatility

    penalty = pd.Series(0.0, index=prices.columns)
    # Penalize stocks with >80% annualized vol
    penalty[vol > 0.80] = -0.2
    penalty[vol > 1.20] = -0.5
    return penalty


def make_aggressive_momentum_strategy(
    top_n: int = TOP_N,
    market_prices: pd.Series | None = None,
    trend_sma: int = 50,  # faster SMA for aggressive trading
    min_lookback: int = 30,
):
    """
    Factory for the aggressive momentum strategy.

    Combines multi-timeframe momentum + breakout detection + volume
    confirmation - volatility penalty.
    """
    def strategy_fn(date: pd.Timestamp, prices: pd.DataFrame) -> dict[str, float]:
        if len(prices) < min_lookback:
            return {}

        date_idx = len(prices) - 1

        # Trend filter — faster 50-day SMA
        if market_prices is not None:
            if date in market_prices.index:
                mkt_idx = market_prices.index.get_loc(date)
                if not is_uptrend(market_prices, mkt_idx, sma_period=trend_sma):
                    return {}  # cash when market is trending down

        # Compute composite score
        momentum = compute_composite_momentum(prices, date_idx)
        breakout = compute_breakout_bonus(prices, date_idx)
        vol_penalty = compute_volatility_penalty(prices, date_idx)

        # Combined score
        score = momentum + breakout + vol_penalty

        # Filter: only consider stocks with positive momentum
        score = score[score > 0].dropna()

        if len(score) == 0:
            return {}

        # Pick top N
        top_symbols = score.nlargest(top_n).index.tolist()
        weight = 1.0 / len(top_symbols)

        return {s: weight for s in top_symbols}

    return strategy_fn


def run_backtest(
    source: str = UNIVERSE_SOURCE,
    start: str = "2019-01-01",
    end: str = "2025-12-31",
    top_n: int = TOP_N,
    rebalance_freq: int = REBALANCE_FREQ,
    trend_sma: int = 50,
) -> pd.Series:
    """Run the aggressive momentum strategy backtest."""
    market_prices = get_market_index(start, end)

    strategy_fn = make_aggressive_momentum_strategy(
        top_n=top_n,
        market_prices=market_prices,
        trend_sma=trend_sma,
    )

    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )

    equity = run_pipeline(
        strategy_fn=strategy_fn,
        strategy_name=f"Aggressive Momentum (top {top_n}, daily)",
        source=source,
        criteria=criteria,
        start=start,
        end=end,
        rebalance_freq=rebalance_freq,
        lookback=30,
    )

    return equity


if __name__ == "__main__":
    run_backtest()
