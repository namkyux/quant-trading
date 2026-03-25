"""
Automated Trader — The main loop that runs the trading system.

This is the brain. It:
1. Connects to broker
2. Pulls latest market data
3. Generates target portfolio (using momentum strategy)
4. Compares target vs current holdings
5. Executes trades (with risk checks)
6. Logs everything

Runs on a schedule — every trading day at a configured time.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import (
    UNIVERSE_SOURCE, MOMENTUM_LOOKBACK, TOP_N,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
    MAX_DRAWDOWN_PCT, MAX_POSITION_PCT,
)
from live.broker_factory import get_broker
from live.risk_manager import RiskManager
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from strategies.aggressive_momentum import make_aggressive_momentum_strategy

# --- Logging ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"trader_{datetime.now():%Y%m%d}.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("trader")


class AutoTrader:
    """Automated trading system."""

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: if True, calculate trades but don't execute them
        """
        self.dry_run = dry_run
        self.broker = get_broker()
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=MAX_POSITION_PCT,
        )
        self.trade_log = []

    def run_cycle(self) -> dict:
        """
        Run one full trading cycle. Returns a summary dict.

        This is the main method — call it on each rebalance day.
        """
        logger.info("=" * 60)
        logger.info("STARTING TRADING CYCLE")
        logger.info("=" * 60)

        summary = {"timestamp": datetime.now().isoformat(), "trades": [], "errors": []}

        try:
            # 1. Get account state
            account = self.broker.get_account()
            logger.info(f"Account — Equity: ${account.equity:,.2f}, Cash: ${account.cash:,.2f}")
            logger.info(f"Positions: {len(account.positions)}")

            # 2. Risk check
            risk_check = self.risk_mgr.update_equity(account.equity)
            logger.info(f"Risk: {self.risk_mgr.status}")
            if not risk_check.passed:
                logger.critical(f"RISK CHECK FAILED: {risk_check.reason}")
                if not self.dry_run:
                    logger.critical("Closing all positions due to kill switch!")
                    self.broker.close_all_positions()
                summary["killed"] = True
                summary["kill_reason"] = risk_check.reason
                return summary

            # 3. Generate target portfolio
            target_weights = self._generate_signals()
            logger.info(f"Target portfolio: {len(target_weights)} positions")
            for sym, w in sorted(target_weights.items(), key=lambda x: -x[1]):
                logger.info(f"  {sym}: {w:.1%}")

            # 4. Apply risk limits to weights
            target_weights = self.risk_mgr.check_weights(target_weights, account.equity)

            # 5. Calculate required trades
            trades = self._calculate_trades(target_weights, account)

            if not trades:
                logger.info("No trades needed — portfolio is on target.")
                summary["trades"] = []
                return summary

            logger.info(f"Trades to execute: {len(trades)}")
            for t in trades:
                logger.info(f"  {t['side'].upper()} {t['symbol']}: ${abs(t['notional']):,.2f}")

            # 6. Execute trades
            if self.dry_run:
                logger.info("DRY RUN — trades not executed")
                summary["dry_run"] = True
            else:
                executed = self._execute_trades(trades, account.equity)
                summary["trades"] = executed

            # 7. Log final state
            if not self.dry_run:
                final_account = self.broker.get_account()
                logger.info(f"Post-trade — Equity: ${final_account.equity:,.2f}, "
                           f"Cash: ${final_account.cash:,.2f}, "
                           f"Positions: {len(final_account.positions)}")

            summary["target_weights"] = target_weights
            summary["num_trades"] = len(trades)

        except Exception as e:
            logger.error(f"Error in trading cycle: {e}", exc_info=True)
            summary["errors"].append(str(e))

        # Save log
        self._save_log(summary)
        logger.info("TRADING CYCLE COMPLETE")
        return summary

    def _generate_signals(self) -> dict[str, float]:
        """Generate target portfolio weights from the momentum strategy."""
        logger.info("Generating signals...")

        # Get universe
        universe_df = get_universe(UNIVERSE_SOURCE)
        criteria = ScreenCriteria(
            min_price=SCREEN_MIN_PRICE,
            min_avg_volume=SCREEN_MIN_AVG_VOLUME,
        )
        symbols = screen(universe_df, criteria, verbose=False)

        # Fetch recent price data (need lookback + buffer)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=MOMENTUM_LOOKBACK * 2)).strftime("%Y-%m-%d")

        logger.info(f"Downloading prices for {len(symbols)} stocks...")
        data = yf.download(symbols, start=start_date, end=end_date, auto_adjust=True, progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]]
            prices.columns = symbols

        prices = prices.dropna(how="all")

        # Fetch SPY for trend filter
        spy_data = yf.download("SPY", start=start_date, end=end_date, auto_adjust=True, progress=False)
        if isinstance(spy_data.columns, pd.MultiIndex):
            spy_prices = spy_data["Close"].squeeze()
        else:
            spy_prices = spy_data["Close"]

        # Generate weights — no trend filter for active trading
        # (stop losses + kill switch handle downside protection)
        strategy = make_aggressive_momentum_strategy(
            top_n=TOP_N,
            market_prices=None,  # disabled — rely on stop loss / kill switch
            trend_sma=50,
        )

        target_weights = strategy(prices.index[-1], prices)
        return target_weights

    def _calculate_trades(
        self,
        target_weights: dict[str, float],
        account,
    ) -> list[dict]:
        """Calculate the trades needed to move from current to target portfolio."""
        trades = []
        current_positions = self.broker.get_position_map()
        equity = account.equity

        # Target position values
        target_values = {sym: equity * w for sym, w in target_weights.items()}

        # Sells first (to free up cash)
        for sym, pos in current_positions.items():
            if sym not in target_values:
                # Sell entire position
                trades.append({
                    "symbol": sym,
                    "side": "sell",
                    "notional": -pos.market_value,
                    "reason": "not in target",
                })
            else:
                # Rebalance: check if we need to sell some
                diff = target_values[sym] - pos.market_value
                if diff < -50:  # only trade if difference > $50
                    trades.append({
                        "symbol": sym,
                        "side": "sell",
                        "notional": diff,
                        "reason": "rebalance down",
                    })

        # Buys
        for sym, target_val in target_values.items():
            if sym in current_positions:
                diff = target_val - current_positions[sym].market_value
                if diff > 50:  # only trade if difference > $50
                    trades.append({
                        "symbol": sym,
                        "side": "buy",
                        "notional": diff,
                        "reason": "rebalance up",
                    })
            else:
                # New position
                if target_val > 50:
                    trades.append({
                        "symbol": sym,
                        "side": "buy",
                        "notional": target_val,
                        "reason": "new position",
                    })

        # Sort: sells first, then buys
        trades.sort(key=lambda t: (0 if t["side"] == "sell" else 1, t["symbol"]))
        return trades

    def _execute_trades(self, trades: list[dict], equity: float) -> list[dict]:
        """Execute trades via broker with risk checks."""
        executed = []

        for trade in trades:
            symbol = trade["symbol"]
            notional = trade["notional"]

            # Risk check each trade
            risk = self.risk_mgr.check_trade(symbol, notional, equity)
            if not risk.passed:
                logger.warning(f"Skipping {symbol}: {risk.reason}")
                continue

            try:
                if trade["side"] == "sell" and trade["reason"] == "not in target":
                    result = self.broker.close_position(symbol)
                else:
                    result = self.broker.submit_market_order(
                        symbol=symbol,
                        notional=abs(notional),
                        side=trade["side"],
                    )
                trade["status"] = "executed"
                trade["order_id"] = result.get("id", "unknown")
                executed.append(trade)

            except Exception as e:
                logger.error(f"Failed to execute {trade['side']} {symbol}: {e}")
                trade["status"] = "failed"
                trade["error"] = str(e)
                executed.append(trade)

        return executed

    def _save_log(self, summary: dict) -> None:
        """Save trade cycle log to file."""
        log_path = os.path.join(LOG_DIR, f"cycle_{datetime.now():%Y%m%d_%H%M%S}.json")
        with open(log_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Cycle log saved to {log_path}")
