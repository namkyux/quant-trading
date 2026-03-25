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
from live.broker_factory import get_broker
from live.risk_manager import RiskManager
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.scanner import run_full_scan
from utils.trade_log import log_trade
from utils.display import (
    C, display_banner, display_account, display_positions,
    display_scan_header, display_trade, display_signal,
    display_hot_stocks, display_position_action, display_risk_status,
    display_daily_summary, display_market_closed, display_no_signals,
    subheader, pct_color, pnl_color, header,
)

# --- Logging ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"daytrader_{datetime.now():%Y%m%d}.log")),
    ],
)
# Suppress yfinance/urllib noise from terminal
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("day_trader")


# --- Configuration ---
POSITION_CHECK_MINUTES = 5    # check stop loss / take profit every 5 min
SIGNAL_SCAN_MINUTES = 15      # generate new trade signals every 15 min
HOT_SCAN_MINUTES = 60         # run hot stock scanner every 60 min
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
    rsi: float = 0.0


class DayTrader:
    """Active intraday trading system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.broker = None  # created in start()
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=MAX_POSITION_PCT,
        )
        self.day_start_equity = 0.0
        self.universe = []
        self.scan_count = 0
        self.hot_tickers = {}

    def start(self):
        """
        Main loop — runs during market hours with split intervals.
          - Every 5 min:  check positions (stop loss / take profit)
          - Every 15 min: generate new trade signals
          - Every 60 min: run hot stock scanner
        """
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.broker = get_broker()

        display_banner()

        mode_str = f"{C.YELLOW}{C.BOLD}DRY RUN{C.RESET}" if self.dry_run else f"{C.GREEN}{C.BOLD}LIVE{C.RESET}"
        print(f"  {C.DIM}Mode:{C.RESET}           {mode_str}")
        print(f"  {C.DIM}Position check:{C.RESET}  every {C.BOLD}{POSITION_CHECK_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Signal scan:{C.RESET}     every {C.BOLD}{SIGNAL_SCAN_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Hot stock scan:{C.RESET}  every {C.BOLD}{HOT_SCAN_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Max positions:{C.RESET}   {C.BOLD}{MAX_POSITIONS}{C.RESET}")
        print(f"  {C.DIM}Stop loss:{C.RESET}       {C.RED}{STOP_LOSS_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Take profit:{C.RESET}     {C.GREEN}{TAKE_PROFIT_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Daily limit:{C.RESET}     {C.RED}{DAILY_LOSS_LIMIT_PCT:.0%}{C.RESET}")
        print()

        logger.info("DAY TRADER STARTING")

        # Load universe once at start of day
        print(subheader("Loading Universe"))
        self._load_universe()
        print(f"  {C.GREEN}✓{C.RESET} {len(self.universe)} stocks loaded")

        # Record start-of-day equity
        account = self.broker.get_account()
        self.day_start_equity = account.equity
        self.risk_mgr.update_equity(account.equity)

        display_account(
            account.equity, account.cash, account.buying_power,
            len(account.positions), peak=self.risk_mgr.peak_equity,
        )
        if account.positions:
            display_positions(account.positions)

        # Track minutes elapsed for each interval
        minutes_since_signal = SIGNAL_SCAN_MINUTES   # trigger on first loop
        minutes_since_hot = HOT_SCAN_MINUTES          # trigger on first loop

        while True:
            try:
                if not self.broker.is_market_open():
                    display_market_closed()
                    time.sleep(60)
                    continue

                self.scan_count += 1
                next_signal = SIGNAL_SCAN_MINUTES - minutes_since_signal
                next_hot = HOT_SCAN_MINUTES - minutes_since_hot
                display_scan_header(self.scan_count, next_signal, next_hot)

                # === EVERY 5 MIN: Risk checks + position management ===
                account = self.broker.get_account()
                daily_pnl_val = account.equity - self.day_start_equity
                daily_pnl_pct = daily_pnl_val / self.day_start_equity if self.day_start_equity else 0

                display_account(
                    account.equity, account.cash, account.buying_power,
                    len(account.positions), daily_pnl=daily_pnl_val,
                    peak=self.risk_mgr.peak_equity,
                )
                logger.info(f"Check #{self.scan_count} | Equity: ${account.equity:,.2f} | Day P&L: {daily_pnl_pct:+.2%}")

                if daily_pnl_pct < -DAILY_LOSS_LIMIT_PCT:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} DAILY LOSS LIMIT HIT {C.RESET} {C.RED}{daily_pnl_pct:.1%}{C.RESET}")
                    print(f"  {C.RED}Closing all positions and stopping for today.{C.RESET}")
                    logger.critical(f"DAILY LOSS LIMIT HIT ({daily_pnl_pct:.1%})")
                    if not self.dry_run:
                        self.broker.close_all_positions()
                    break

                risk = self.risk_mgr.update_equity(account.equity)
                if not risk.passed:
                    display_risk_status(risk.reason, killed=True)
                    logger.critical(f"KILL SWITCH: {risk.reason}")
                    if not self.dry_run:
                        self.broker.close_all_positions()
                    break

                # Check stop loss / take profit on every tick
                print(subheader("Positions"))
                self._manage_positions(account)

                # === EVERY 60 MIN: Hot stock scanner ===
                if minutes_since_hot >= HOT_SCAN_MINUTES:
                    minutes_since_hot = 0
                    print(subheader("Hot Stock Scanner"))
                    try:
                        hot_stocks = run_full_scan(
                            self.universe,
                            include_social=True,
                            include_insider=True,
                            include_short_squeeze=False,
                        )
                        if hot_stocks:
                            self.hot_tickers = {h.symbol: h.heat_score for h in hot_stocks[:10]}
                            display_hot_stocks(hot_stocks, top_n=10)
                        else:
                            self.hot_tickers = {}
                            print(f"  {C.DIM}No hot stocks detected.{C.RESET}")
                    except Exception as e:
                        print(f"  {C.YELLOW}Scanner error: {e}{C.RESET}")
                        logger.warning(f"Hot scan failed: {e}")

                # === EVERY 15 MIN: Signal generation + new entries ===
                if minutes_since_signal >= SIGNAL_SCAN_MINUTES:
                    minutes_since_signal = 0
                    current_positions = len(account.positions)
                    if current_positions < MAX_POSITIONS:
                        print(subheader(f"Signal Scan ({MAX_POSITIONS - current_positions} slots open)"))
                        self._scan_and_enter(account, MAX_POSITIONS - current_positions)
                    else:
                        print(f"\n  {C.DIM}All {MAX_POSITIONS} slots filled — skipping signal scan.{C.RESET}")

                # Next check countdown
                next_signal = SIGNAL_SCAN_MINUTES - minutes_since_signal
                next_hot = HOT_SCAN_MINUTES - minutes_since_hot
                print(f"\n  {C.DIM}Next check in {POSITION_CHECK_MINUTES}m "
                      f"│ signals in {next_signal}m "
                      f"│ hot scan in {next_hot}m{C.RESET}")

                time.sleep(POSITION_CHECK_MINUTES * 60)
                minutes_since_signal += POSITION_CHECK_MINUTES
                minutes_since_hot += POSITION_CHECK_MINUTES

            except KeyboardInterrupt:
                print(f"\n  {C.YELLOW}Shutting down gracefully...{C.RESET}")
                break
            except Exception as e:
                print(f"\n  {C.RED}Error: {e}{C.RESET}")
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

    def _spy_above_sma(self, period: int = 50) -> bool:
        """Return True if SPY is above its N-day SMA (bullish regime)."""
        try:
            spy = yf.download("SPY", period=f"{period + 10}d", progress=False)
            if len(spy) < period:
                return True
            close = spy["Close"].squeeze()
            return float(close.iloc[-1]) > float(close.iloc[-period:].mean())
        except Exception:
            return True  # fail open

    def _scan_and_enter(self, account, open_slots: int):
        """Scan for entry opportunities and open new positions."""
        # Regime filter: only buy momentum when SPY is in uptrend
        if not self._spy_above_sma(50):
            print(f"  {C.YELLOW}SPY below 50-day SMA — bearish regime, skipping buys{C.RESET}")
            logger.info("Regime filter: SPY below 50-SMA, skipping entries")
            return

        print(f"  {C.DIM}Scanning {len(self.universe)} stocks...{C.RESET}")
        signals = self._generate_signals()

        # Filter to actionable buy signals
        buys = [s for s in signals if s.action == "buy" and s.score >= MIN_SCORE]
        buys.sort(key=lambda s: -s.score)

        # Don't buy stocks we already hold
        held = {p.symbol for p in account.positions}
        buys = [s for s in buys if s.symbol not in held]

        if not buys:
            display_no_signals()
            return

        # Show top signals
        print(f"\n  {C.BOLD}{len(buys)} buy signals found — top picks:{C.RESET}")
        for s in buys[:open_slots + 3]:
            is_hot = s.symbol in self.hot_tickers
            display_signal(s.symbol, s.score, s.momentum_5d, s.momentum_21d,
                          s.volume_ratio, s.near_high, is_hot)

        print()

        # Take the top opportunities (up to open slots)
        for signal in buys[:open_slots]:
            available = max(account.buying_power, 0) * 0.90
            max_per_position = account.equity * MAX_POSITION_PCT
            position_value = min(max_per_position, available / max(open_slots, 1))

            if position_value < 100:
                print(f"  {C.YELLOW}Insufficient buying power (${account.buying_power:,.0f} available).{C.RESET}")
                break

            if self.dry_run:
                display_trade("buy", signal.symbol, position_value, signal.score, "DRY RUN")
            else:
                try:
                    self.broker.submit_market_order(
                        symbol=signal.symbol,
                        notional=position_value,
                        side="buy",
                    )
                    display_trade("buy", signal.symbol, position_value, signal.score)
                    log_trade(signal.symbol, "buy", position_value, asset_type="stock",
                              score=signal.score, reason="momentum signal")
                    logger.info(f"BOUGHT ${position_value:,.0f} of {signal.symbol}")
                except Exception as e:
                    print(f"  {C.RED}Failed to buy {signal.symbol}: {e}{C.RESET}")
                    log_trade(signal.symbol, "buy", position_value, asset_type="stock",
                              score=signal.score, reason=str(e), status="failed")
                    logger.error(f"Failed to buy {signal.symbol}: {e}")

    def _manage_positions(self, account):
        """Check existing positions for stop loss / take profit exits."""
        if not account.positions:
            print(f"  {C.DIM}No open positions{C.RESET}")
            return

        for pos in account.positions:
            pnl_pct = pos.unrealized_pl_pct

            if pnl_pct < -STOP_LOSS_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "stop_loss")
                logger.warning(f"STOP LOSS: {pos.symbol} at {pnl_pct:+.1%}")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="stock",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="stop_loss")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")
                else:
                    print(f"    {C.YELLOW}{C.DIM}(dry run — not executed){C.RESET}")

            elif pnl_pct > TAKE_PROFIT_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "take_profit")
                logger.info(f"TAKE PROFIT: {pos.symbol} at {pnl_pct:+.1%}")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="stock",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="take_profit")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")
                else:
                    print(f"    {C.YELLOW}{C.DIM}(dry run — not executed){C.RESET}")

            else:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "hold")

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

                # RSI (14-period)
                delta = prices.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = float(gain.iloc[-1]) / float(loss.iloc[-1]) if float(loss.iloc[-1]) > 0 else 100
                rsi = 100 - (100 / (1 + rs))

                # RSI filter: penalize overbought, boost oversold-bouncing
                if rsi > 75:
                    score -= 0.4
                elif rsi < 40 and mom_5d > 0:
                    score += 0.2  # oversold bounce

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
                    score += heat * 0.3
                    near_high = True

                # Determine action: need score + short-term momentum + not overbought
                is_hot = symbol in self.hot_tickers
                if score >= MIN_SCORE and (mom_5d > 0 or is_hot) and rsi < 75:
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
                    rsi=rsi,
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
            display_daily_summary(
                self.day_start_equity,
                account.equity,
                self.scan_count,
                len(account.positions),
            )
            if account.positions:
                display_positions(account.positions)
            logger.info(f"END OF DAY | Equity: ${account.equity:,.2f} | P&L: ${account.equity - self.day_start_equity:+,.2f}")
        except Exception as e:
            print(f"  {C.RED}Failed to generate summary: {e}{C.RESET}")
