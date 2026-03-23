"""Performance metrics for backtesting."""

import numpy as np
import pandas as pd


def total_return(equity_curve: pd.Series) -> float:
    """Total return as a decimal (e.g., 0.5 = 50%)."""
    return equity_curve.iloc[-1] / equity_curve.iloc[0] - 1


def cagr(equity_curve: pd.Series) -> float:
    """Compound annual growth rate."""
    n_days = (equity_curve.index[-1] - equity_curve.index[0]).days
    if n_days <= 0:
        return 0.0
    n_years = n_days / 365.25
    return (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / n_years) - 1


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum drawdown as a negative decimal (e.g., -0.2 = -20%)."""
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    return drawdown.min()


def sharpe_ratio(equity_curve: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily equity curve."""
    daily_returns = equity_curve.pct_change().dropna()
    if daily_returns.std() == 0:
        return 0.0
    excess = daily_returns.mean() - risk_free_rate / 252
    return excess / daily_returns.std() * np.sqrt(252)


def print_report(equity_curve: pd.Series, strategy_name: str = "Strategy") -> None:
    """Print a summary of backtest performance."""
    print(f"\n{'='*50}")
    print(f"  {strategy_name} — Backtest Report")
    print(f"{'='*50}")
    print(f"  Period:       {equity_curve.index[0].date()} → {equity_curve.index[-1].date()}")
    print(f"  Total Return: {total_return(equity_curve):>8.2%}")
    print(f"  CAGR:         {cagr(equity_curve):>8.2%}")
    print(f"  Sharpe Ratio: {sharpe_ratio(equity_curve):>8.2f}")
    print(f"  Max Drawdown: {max_drawdown(equity_curve):>8.2%}")
    print(f"  Final Value:  ${equity_curve.iloc[-1]:>12,.2f}")
    print(f"{'='*50}\n")
