"""
Day Trader — Active intraday trading system.

Unlike the weekly rebalancer, this system:
- Runs continuously during market hours
- Scans for opportunities every N minutes
- Enters and exits positions within the same day or holds short-term
- Uses multiple signals: momentum, breakouts, volume spikes
- Manages a portfolio of 3-5 positions at a time

Architecture:
  1. Scanner: finds stocks with unusual activity (volume, price moves)
  2. Signal: scores candidates on momentum + breakout + volume
  3. Portfolio: manages entries, exits, and position sizing
  4. Risk: enforces stop losses and daily loss limits
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    UNIVERSE_SOURCE, MAX_DRAWDOWN_PCT, MAX_POSITION_PCT, TOP_N,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
)
from live.broker import AlpacaBroker
from live.risk_manager import RiskManager
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.scanner import run_full_scan, print_hot_stocks

# --- Logging ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"daytrader_{datetime.now():%Y%m%d}.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day_trader")


# --- Configuration ---
SCAN_INTERVAL_MINUTES = 15    # scan for opportunities every 15 min
MAX_POSITIONS = 5             # max concurrent positions
DAILY_LOSS_LIMIT_PCT = 0.05   # stop trading if down 5% in a day
STOP_LOSS_PCT = 0.05          # 5% trailing stop per position
TAKE_PROFIT_PCT = 0.10        # take profits at 10% gain
MIN_SCORE = 0.5               # minimum score to enter a trade


@dataclass
class TradeSignal:
    symbol: str
    score: float
    momentum_5d: float
    momentum_21d: float
    volume_ratio: float
    near_high: bool
    action: str  # "buy", "sell", "hold"


class DayTrader:
    """Active intraday trading system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.broker = AlpacaBroker()
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=MAX_POSITION_PCT,
        )
        self.day_start_equity = 0.0
        self.universe = []
        self.scan_count = 0
        self.hot_tickers = {}  # symbol -> heat_score from scanner

    def start(self):
        """Main loop — runs during market hours."""
        logger.info("=" * 60)
        logger.info("DAY TRADER STARTING")
        logger.info(f"  Scan interval: {SCAN_INTERVAL_MINUTES} min")
        logger.info(f"  Max positions: {MAX_POSITIONS}")
        logger.info(f"  Stop loss: {STOP_LOSS_PCT:.0%} | Take profit: {TAKE_PROFIT_PCT:.0%}")
        logger.info(f"  Daily loss limit: {DAILY_LOSS_LIMIT_PCT:.0%}")
        logger.info(f"  Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info("=" * 60)

        # Load universe once at start of day
        self._load_universe()

        # Record start-of-day equity
        account = self.broker.get_account()
        self.day_start_equity = account.equity
        self.risk_mgr.update_equity(account.equity)
        logger.info(f"Start equity: ${account.equity:,.2f}")

        while True:
            try:
                if not self.broker.is_market_open():
                    logger.info("Market is closed. Waiting...")
                    time.sleep(60)
                    continue

                self.scan_count += 1
                logger.info(f"\n--- Scan #{self.scan_count} at {datetime.now():%H:%M:%S} ---")

                # Check daily loss limit
                account = self.broker.get_account()
                daily_pnl = (account.equity - self.day_start_equity) / self.day_start_equity
                logger.info(f"Day P&L: {daily_pnl:+.2%} (${account.equity - self.day_start_equity:+,.2f})")

                if daily_pnl < -DAILY_LOSS_LIMIT_PCT:
                    logger.critical(f"DAILY LOSS LIMIT HIT ({daily_pnl:.1%}). Stopping for today.")
                    if not self.dry_run:
                        self.broker.close_all_positions()
                    break

                # Check kill switch
                risk = self.risk_mgr.update_equity(account.equity)
                if not risk.passed:
                    logger.critical(f"KILL SWITCH: {risk.reason}")
                    if not self.dry_run:
                        self.broker.close_all_positions()
                    break

                # 1. Check existing positions for exits
                self._manage_positions(account)

                # 2. Run hot stock scanner (every 4th scan to save API calls)
                if self.scan_count % 4 == 1:
                    logger.info("Running hot stock scanner...")
                    hot_stocks = run_full_scan(
                        self.universe,
                        include_social=True,
                        include_insider=True,
                        include_short_squeeze=False,
                    )
                    if hot_stocks:
                        # Boost hot stocks in our signal scoring
                        self.hot_tickers = {h.symbol: h.heat_score for h in hot_stocks[:10]}
                        print_hot_stocks(hot_stocks, top_n=10)
                    else:
                        self.hot_tickers = {}

                # 3. Scan for new entries (incorporates hot stocks)
                current_positions = len(account.positions)
                if current_positions < MAX_POSITIONS:
                    self._scan_and_enter(account, MAX_POSITIONS - current_positions)

                logger.info(f"Positions: {len(self.broker.get_positions())}/{MAX_POSITIONS} | "
                           f"Cash: ${account.cash:,.2f}")

                # Sleep until next scan
                logger.info(f"Next scan in {SCAN_INTERVAL_MINUTES} minutes...")
                time.sleep(SCAN_INTERVAL_MINUTES * 60)

            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in scan loop: {e}", exc_info=True)
                time.sleep(60)

        self._end_of_day_summary()

    def _load_universe(self):
        """Load and screen the stock universe."""
        logger.info("Loading stock universe...")
        universe_df = get_universe(UNIVERSE_SOURCE)
        criteria = ScreenCriteria(
            min_price=SCREEN_MIN_PRICE,
            min_avg_volume=SCREEN_MIN_AVG_VOLUME,
        )
        self.universe = screen(universe_df, criteria, verbose=False)
        logger.info(f"Universe: {len(self.universe)} stocks")

    def _scan_and_enter(self, account, open_slots: int):
        """Scan for entry opportunities and open new positions."""
        signals = self._generate_signals()

        # Filter to actionable buy signals
        buys = [s for s in signals if s.action == "buy" and s.score >= MIN_SCORE]
        buys.sort(key=lambda s: -s.score)

        # Don't buy stocks we already hold
        held = {p.symbol for p in account.positions}
        buys = [s for s in buys if s.symbol not in held]

        if not buys:
            logger.info("No buy signals found.")
            return

        # Take the top opportunities (up to open slots)
        for signal in buys[:open_slots]:
            position_value = account.equity * MAX_POSITION_PCT
            position_value = min(position_value, account.cash * 0.95)  # keep some cash buffer

            if position_value < 100:
                logger.info("Insufficient cash for new position.")
                break

            logger.info(f"SIGNAL: {signal.symbol} score={signal.score:.2f} "
                       f"mom5d={signal.momentum_5d:+.1%} mom21d={signal.momentum_21d:+.1%} "
                       f"vol={signal.volume_ratio:.1f}x {'BREAKOUT' if signal.near_high else ''}")

            if self.dry_run:
                logger.info(f"  DRY RUN: would BUY ${position_value:,.0f} of {signal.symbol}")
            else:
                try:
                    self.broker.submit_market_order(
                        symbol=signal.symbol,
                        notional=position_value,
                        side="buy",
                    )
                    logger.info(f"  BOUGHT ${position_value:,.0f} of {signal.symbol}")
                except Exception as e:
                    logger.error(f"  Failed to buy {signal.symbol}: {e}")

    def _manage_positions(self, account):
        """Check existing positions for stop loss / take profit exits."""
        for pos in account.positions:
            pnl_pct = pos.unrealized_pl_pct

            # Stop loss
            if pnl_pct < -STOP_LOSS_PCT:
                logger.warning(f"STOP LOSS: {pos.symbol} at {pnl_pct:+.1%} "
                              f"(${pos.unrealized_pl:+,.2f})")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                    except Exception as e:
                        logger.error(f"Failed to close {pos.symbol}: {e}")
                else:
                    logger.info(f"  DRY RUN: would close {pos.symbol}")

            # Take profit
            elif pnl_pct > TAKE_PROFIT_PCT:
                logger.info(f"TAKE PROFIT: {pos.symbol} at {pnl_pct:+.1%} "
                           f"(${pos.unrealized_pl:+,.2f})")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                    except Exception as e:
                        logger.error(f"Failed to close {pos.symbol}: {e}")
                else:
                    logger.info(f"  DRY RUN: would close {pos.symbol}")

            else:
                logger.info(f"  HOLD: {pos.symbol} {pnl_pct:+.1%} (${pos.unrealized_pl:+,.2f})")

    def _generate_signals(self) -> list[TradeSignal]:
        """Score all stocks in the universe and return ranked signals."""
        # Download recent data
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        data = yf.download(self.universe, start=start, end=end, auto_adjust=True, progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
            volume = data["Volume"]
        else:
            close = data[["Close"]]
            close.columns = self.universe
            volume = data[["Volume"]]
            volume.columns = self.universe

        if len(close) < 22:
            return []

        signals = []

        for symbol in close.columns:
            try:
                prices = close[symbol].dropna()
                vols = volume[symbol].dropna()

                if len(prices) < 22:
                    continue

                # Momentum scores
                mom_5d = prices.iloc[-1] / prices.iloc[-5] - 1 if len(prices) >= 5 else 0
                mom_21d = prices.iloc[-1] / prices.iloc[-21] - 1 if len(prices) >= 21 else 0

                # Volume ratio (recent vs average)
                vol_recent = vols.iloc[-3:].mean() if len(vols) >= 3 else 0
                vol_avg = vols.iloc[-20:].mean() if len(vols) >= 20 else 1
                vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1.0

                # Near 20-day high?
                high_20d = prices.iloc[-20:].max()
                near_high = prices.iloc[-1] >= high_20d * 0.98

                # Composite score
                score = 0.0
                score += mom_5d * 3.0      # heavy weight on short-term momentum
                score += mom_21d * 2.0     # medium weight on monthly trend
                if near_high:
                    score += 0.3           # breakout bonus
                if vol_ratio > 1.5:
                    score += 0.2           # volume confirmation
                if vol_ratio > 2.0:
                    score += 0.1           # extra volume bonus

                # Volatility penalty
                daily_ret = prices.pct_change().dropna()
                ann_vol = daily_ret.std() * np.sqrt(252)
                if ann_vol > 0.80:
                    score -= 0.3
                if ann_vol > 1.20:
                    score -= 0.5

                # Hot stock boost from scanner
                if symbol in self.hot_tickers:
                    heat = self.hot_tickers[symbol]
                    score += heat * 0.3  # 30% of heat score as bonus
                    near_high = True  # flag it

                # Determine action — aggressive: only need score + short-term momentum
                is_hot = symbol in self.hot_tickers
                if score >= MIN_SCORE and (mom_5d > 0 or is_hot):
                    action = "buy"
                else:
                    action = "hold"

                signals.append(TradeSignal(
                    symbol=symbol,
                    score=score,
                    momentum_5d=mom_5d,
                    momentum_21d=mom_21d,
                    volume_ratio=vol_ratio,
                    near_high=near_high,
                    action=action,
                ))

            except Exception:
                continue

        # Sort by score descending
        signals.sort(key=lambda s: -s.score)
        return signals

    def _end_of_day_summary(self):
        """Print end-of-day summary."""
        try:
            account = self.broker.get_account()
            daily_pnl = account.equity - self.day_start_equity
            daily_pct = daily_pnl / self.day_start_equity if self.day_start_equity > 0 else 0

            logger.info("\n" + "=" * 60)
            logger.info("  END OF DAY SUMMARY")
            logger.info("=" * 60)
            logger.info(f"  Start equity:  ${self.day_start_equity:>12,.2f}")
            logger.info(f"  End equity:    ${account.equity:>12,.2f}")
            logger.info(f"  Day P&L:       ${daily_pnl:>+12,.2f} ({daily_pct:+.2%})")
            logger.info(f"  Scans today:   {self.scan_count}")
            logger.info(f"  Positions:     {len(account.positions)}")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
