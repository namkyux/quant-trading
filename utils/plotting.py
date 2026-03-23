"""Plotting utilities for backtests."""

import matplotlib.pyplot as plt
import pandas as pd

from utils.metrics import total_return, cagr, sharpe_ratio, max_drawdown

# Color palette for multiple strategies
COLORS = [
    "#2196F3", "#F44336", "#4CAF50", "#FF9800", "#9C27B0",
    "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5",
]


def plot_equity_curve(
    equity_curve: pd.Series,
    strategy_name: str = "Strategy",
    save_path: str | None = None,
) -> None:
    """Plot a single equity curve with drawdown shading."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), height_ratios=[3, 1], sharex=True)

    ax1.plot(equity_curve.index, equity_curve.values, linewidth=1.5, color=COLORS[0])
    ax1.set_title(f"{strategy_name} — Equity Curve", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Portfolio Value ($)")
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    ax2.fill_between(drawdown.index, drawdown.values, 0, color="#F44336", alpha=0.4)
    ax2.set_ylabel("Drawdown")
    ax2.set_xlabel("Date")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Chart saved to {save_path}")
    plt.show()


def plot_comparison(
    curves: dict[str, pd.Series],
    title: str = "Strategy Comparison",
    save_path: str | None = None,
) -> None:
    """
    Plot multiple equity curves on the same chart for comparison.

    Args:
        curves: dict of {name: equity_curve}
        title: chart title
        save_path: optional path to save the chart
    """
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(14, 10), height_ratios=[3, 1, 1], sharex=True
    )

    # --- Equity curves ---
    for i, (name, curve) in enumerate(curves.items()):
        color = COLORS[i % len(COLORS)]
        ax1.plot(curve.index, curve.values, linewidth=1.5, color=color, label=name)

    ax1.set_title(title, fontsize=14, fontweight="bold")
    ax1.set_ylabel("Portfolio Value ($)")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # --- Drawdowns ---
    for i, (name, curve) in enumerate(curves.items()):
        color = COLORS[i % len(COLORS)]
        peak = curve.cummax()
        dd = (curve - peak) / peak
        ax2.plot(dd.index, dd.values, linewidth=1, color=color, alpha=0.7, label=name)

    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.3)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    # --- Rolling 1-year return ---
    for i, (name, curve) in enumerate(curves.items()):
        color = COLORS[i % len(COLORS)]
        rolling_ret = curve.pct_change(252).dropna()
        ax3.plot(rolling_ret.index, rolling_ret.values, linewidth=1, color=color, alpha=0.7, label=name)

    ax3.axhline(y=0, color="black", linewidth=0.5, linestyle="--")
    ax3.set_ylabel("Rolling 1Y Return")
    ax3.set_xlabel("Date")
    ax3.grid(True, alpha=0.3)
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Chart saved to {save_path}")
    plt.show()


def print_comparison_table(curves: dict[str, pd.Series]) -> None:
    """Print a side-by-side comparison table of all strategies/benchmarks."""
    print(f"\n{'='*80}")
    print(f"  {'Strategy/Benchmark':<30} {'Return':>10} {'CAGR':>8} {'Sharpe':>8} {'Max DD':>10} {'Final $':>12}")
    print(f"{'='*80}")

    for name, curve in curves.items():
        print(
            f"  {name:<30} "
            f"{total_return(curve):>9.2%} "
            f"{cagr(curve):>7.2%} "
            f"{sharpe_ratio(curve):>7.2f} "
            f"{max_drawdown(curve):>9.2%} "
            f"${curve.iloc[-1]:>11,.0f}"
        )

    print(f"{'='*80}\n")
