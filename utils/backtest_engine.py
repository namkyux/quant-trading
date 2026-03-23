"""Simple event-driven backtesting engine."""

import pandas as pd
import numpy as np
from config import INITIAL_CAPITAL, COMMISSION_PCT, SLIPPAGE_PCT


class BacktestEngine:
    """
    A straightforward backtesting engine.

    A strategy provides target weights on rebalance days.
    The engine handles execution with commissions and slippage.
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        initial_capital: float = INITIAL_CAPITAL,
        commission_pct: float = COMMISSION_PCT,
        slippage_pct: float = SLIPPAGE_PCT,
    ):
        self.prices = prices
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

    def run(self, target_weights_fn, rebalance_days: list[int] | None = None) -> pd.Series:
        """
        Run the backtest.

        Args:
            target_weights_fn: callable(date, prices_up_to_date) -> dict[symbol, weight]
                Returns target portfolio weights on rebalance days.
                Weights should sum to <= 1.0 (remainder is cash).
            rebalance_days: list of integer indices into self.prices where we rebalance.
                If None, the strategy is called every day (not recommended).

        Returns:
            pd.Series: equity curve indexed by date.
        """
        dates = self.prices.index
        symbols = self.prices.columns.tolist()

        cash = self.initial_capital
        holdings = {s: 0 for s in symbols}  # shares held
        equity_history = []

        rebalance_set = set(rebalance_days) if rebalance_days is not None else set(range(len(dates)))

        for i, date in enumerate(dates):
            current_prices = self.prices.loc[date]

            # Portfolio value before any trades
            portfolio_value = cash + sum(
                holdings[s] * current_prices[s]
                for s in symbols
                if not np.isnan(current_prices[s])
            )

            # Rebalance if scheduled
            if i in rebalance_set:
                prices_so_far = self.prices.iloc[: i + 1]
                target_weights = target_weights_fn(date, prices_so_far)

                # Execute trades
                for symbol in symbols:
                    target_weight = target_weights.get(symbol, 0.0)
                    price = current_prices[symbol]
                    if np.isnan(price):
                        continue

                    target_value = portfolio_value * target_weight
                    current_value = holdings[symbol] * price
                    trade_value = target_value - current_value

                    if abs(trade_value) < 1.0:  # skip tiny trades
                        continue

                    # Apply slippage
                    if trade_value > 0:
                        exec_price = price * (1 + self.slippage_pct)
                    else:
                        exec_price = price * (1 - self.slippage_pct)

                    shares_traded = trade_value / exec_price
                    cost = abs(trade_value) * self.commission_pct

                    holdings[symbol] += shares_traded
                    cash -= shares_traded * exec_price + cost

            # Record end-of-day portfolio value
            eod_value = cash + sum(
                holdings[s] * current_prices[s]
                for s in symbols
                if not np.isnan(current_prices[s])
            )
            equity_history.append(eod_value)

        return pd.Series(equity_history, index=dates, name="equity")
