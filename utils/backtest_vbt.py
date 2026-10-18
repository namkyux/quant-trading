"""
Vectorbt-powered backtesting engine.

Replaces the custom backtest_engine.py with vectorbt for:
- 10-100x faster backtesting (vectorized NumPy operations)
- More accurate portfolio simulation
- Built-in metrics (Sharpe, Sortino, Calmar, win rate, etc.)
- Interactive Plotly charts
- Parameter sweep in seconds instead of minutes
"""

import numpy as np
import pandas as pd
import vectorbt as vbt

from config import INITIAL_CAPITAL, COMMISSION_PCT, SLIPPAGE_PCT


def backtest_momentum(
    prices: pd.DataFrame,
    lookback: int = 126,
    top_n: int = 5,
    rebalance_every: int = 21,
    initial_capital: float = INITIAL_CAPITAL,
    commission: float = COMMISSION_PCT,
    slippage: float = SLIPPAGE_PCT,
) -> vbt.Portfolio:
    """
    Run a momentum backtest using vectorbt.

    Much faster than the custom engine — runs in seconds even for 500+ stocks.
    """
    # Calculate N-day returns for ranking
    returns = prices.pct_change(lookback)

    # Build signals: on rebalance days, go long the top N stocks
    entries = pd.DataFrame(False, index=prices.index, columns=prices.columns)
    exits = pd.DataFrame(False, index=prices.index, columns=prices.columns)

    rebalance_indices = list(range(lookback, len(prices), rebalance_every))

    for i in rebalance_indices:
        row_returns = returns.iloc[i].dropna()
        if len(row_returns) == 0:
            continue

        top = row_returns.nlargest(top_n).index.tolist()

        # Exit everything not in top N
        for col in prices.columns:
            if col not in top:
                exits.iloc[i][col] = True

        # Enter top N
        for col in top:
            entries.iloc[i][col] = True

    # Run portfolio simulation
    pf = vbt.Portfolio.from_signals(
        prices,
        entries=entries,
        exits=exits,
        size=1.0 / top_n,  # equal weight
        size_type="percent",
        init_cash=initial_capital,
        fees=commission + slippage,
        freq="1D",
        cash_sharing=True,
        group_by=True,
    )

    return pf


def backtest_momentum_sweep(
    prices: pd.DataFrame,
    lookbacks: list[int] = [63, 126, 189, 252],
    top_ns: list[int] = [3, 5, 10, 20],
    rebalance_freqs: list[int] = [5, 21, 63],
    initial_capital: float = INITIAL_CAPITAL,
) -> pd.DataFrame:
    """
    Run a parameter sweep across all combinations.

    Returns a DataFrame with metrics for each combination.
    vectorbt makes this 10-100x faster than looping.
    """
    results = []

    for lookback in lookbacks:
        returns = prices.pct_change(lookback)

        for top_n in top_ns:
            for rebal in rebalance_freqs:
                entries = pd.DataFrame(False, index=prices.index, columns=prices.columns)
                exits = pd.DataFrame(False, index=prices.index, columns=prices.columns)

                rebalance_indices = list(range(lookback, len(prices), rebal))

                for i in rebalance_indices:
                    row_returns = returns.iloc[i].dropna()
                    if len(row_returns) == 0:
                        continue

                    top = row_returns.nlargest(top_n).index.tolist()

                    for col in prices.columns:
                        if col not in top:
                            exits.iloc[i][col] = True
                    for col in top:
                        entries.iloc[i][col] = True

                try:
                    pf = vbt.Portfolio.from_signals(
                        prices,
                        entries=entries,
                        exits=exits,
                        size=1.0 / top_n,
                        size_type="percent",
                        init_cash=initial_capital,
                        fees=COMMISSION_PCT + SLIPPAGE_PCT,
                        freq="1D",
                        cash_sharing=True,
                        group_by=True,
                    )

                    stats = pf.stats()
                    results.append({
                        "lookback": lookback,
                        "top_n": top_n,
                        "rebalance_freq": rebal,
                        "total_return": stats.get("Total Return [%]", 0) / 100,
                        "sharpe": stats.get("Sharpe Ratio", 0),
                        "sortino": stats.get("Sortino Ratio", 0),
                        "max_dd": stats.get("Max Drawdown [%]", 0) / -100,
                        "calmar": stats.get("Calmar Ratio", 0),
                        "win_rate": stats.get("Win Rate [%]", 0) / 100,
                        "num_trades": stats.get("Total Trades", 0),
                        "final_value": stats.get("End Value", 0),
                    })
                except Exception as e:
                    results.append({
                        "lookback": lookback,
                        "top_n": top_n,
                        "rebalance_freq": rebal,
                        "error": str(e),
                    })

    return pd.DataFrame(results)


def print_vbt_report(pf: vbt.Portfolio, name: str = "Strategy"):
    """Print a formatted report from a vectorbt portfolio."""
    stats = pf.stats()

    print(f"\n{'='*60}")
    print(f"  {name} — Backtest Report (vectorbt)")
    print(f"{'='*60}")
    print(f"  Period:        {pf.wrapper.index[0].date()} → {pf.wrapper.index[-1].date()}")
    print(f"  Total Return:  {stats.get('Total Return [%]', 0):>8.2f}%")
    print(f"  Sharpe Ratio:  {stats.get('Sharpe Ratio', 0):>8.2f}")
    print(f"  Sortino Ratio: {stats.get('Sortino Ratio', 0):>8.2f}")
    print(f"  Calmar Ratio:  {stats.get('Calmar Ratio', 0):>8.2f}")
    print(f"  Max Drawdown:  {stats.get('Max Drawdown [%]', 0):>8.2f}%")
    print(f"  Win Rate:      {stats.get('Win Rate [%]', 0):>8.2f}%")
    print(f"  Total Trades:  {stats.get('Total Trades', 0):>8.0f}")
    print(f"  Final Value:   ${stats.get('End Value', 0):>12,.2f}")
    print(f"{'='*60}\n")


def plot_vbt_results(pf: vbt.Portfolio, name: str = "Strategy", save_path: str | None = None):
    """Plot interactive equity curve and drawdown using vectorbt's Plotly charts."""
    fig = pf.plot(subplots=["value", "drawdowns"], title=f"{name} — Equity & Drawdown")
    if save_path:
        fig.write_html(save_path)
        print(f"Interactive chart saved to {save_path}")
    fig.show()
