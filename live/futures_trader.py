"""
Futures Trader — Automated futures trading system.

Strategies:
1. Trend Following: ride momentum on micro futures (MES, MNQ, MCL, MGC)
2. Mean Reversion: fade extreme moves during quiet sessions
3. Supports both LONG and SHORT positions (key advantage over stocks)

Uses micro contracts sized for $10K accounts.
No PDT rule — can day trade freely with any account size.

Run via: python live/run.py --type futures
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    MAX_DRAWDOWN_PCT, FUTURES_SYMBOLS, FUTURES_STOP_LOSS_PCT,
    FUTURES_TAKE_PROFIT_PCT, FUTURES_MAX_CONTRACTS, FUTURES_SCAN_MINUTES,
    FUTURES_MAX_POSITIONS, FUTURES_DAILY_LOSS_LIMIT,
)
from live.futures_broker import FuturesBroker, FuturesPosition, FUTURES_SPECS
from live.broker_factory import _next_client_id
from live.risk_manager import RiskManager
from utils.trade_log import log_trade
from utils.display import (
    C, display_banner, subheader, divider,
    pct_color, pnl_color, score_color, header,
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"futures_{datetime.now():%Y%m%d}.log")),
    ],
)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logger = logging.getLogger("futures_trader")

# yfinance tickers that proxy for micro contracts
YF_PROXY = {
    "MES": "ES=F",
    "MNQ": "NQ=F",
    "MCL": "CL=F",
    "MGC": "GC=F",
}

POSITION_CHECK_MINUTES = 3
MIN_SCORE = 0.15  # lowered: hourly signals are naturally weaker


@dataclass
class FuturesSignal:
    symbol: str
    score: float
    direction: str           # "long" or "short"
    momentum_short: float    # 5-bar momentum
    momentum_long: float     # 21-bar momentum
    volume_ratio: float
    trend_aligned: bool
    reason: str
    rsi: float = 50.0
    atr_stop_pct: float = 0.02  # ATR-based dynamic stop


class FuturesTrader:
    """Automated futures trading system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.futures = None  # created in start() to bind to the right thread
        self._client_id = _next_client_id()
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=0.50,  # futures are margin-based, different sizing
        )
        self.start_equity = 0.0
        self.scan_count = 0
        self._position_stops: dict[str, float] = {}  # symbol -> ATR-based stop pct

    def start(self):
        """Main loop."""
        # Create event loop and broker in this thread (ib_async binds to creating thread)
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.futures = FuturesBroker(client_id=self._client_id)

        display_banner()

        print(f"  {C.MAGENTA}{C.BOLD}FUTURES MODE{C.RESET}")
        mode_str = f"{C.YELLOW}{C.BOLD}SIMULATE{C.RESET}" if self.dry_run else f"{C.GREEN}{C.BOLD}PAPER{C.RESET}"
        print(f"  {C.DIM}Mode:{C.RESET}            {mode_str}")
        print(f"  {C.DIM}Contracts:{C.RESET}       {C.BOLD}{', '.join(FUTURES_SYMBOLS)}{C.RESET}")
        print(f"  {C.DIM}Scan interval:{C.RESET}   every {C.BOLD}{FUTURES_SCAN_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Max contracts:{C.RESET}   {C.BOLD}{FUTURES_MAX_CONTRACTS} per symbol{C.RESET}")
        print(f"  {C.DIM}Max positions:{C.RESET}   {C.BOLD}{FUTURES_MAX_POSITIONS}{C.RESET}")
        print(f"  {C.DIM}Stop loss:{C.RESET}       {C.RED}{FUTURES_STOP_LOSS_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Take profit:{C.RESET}     {C.GREEN}{FUTURES_TAKE_PROFIT_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Daily loss cap:{C.RESET}  {C.RED}${FUTURES_DAILY_LOSS_LIMIT}{C.RESET}")
        print()

        # Resolve front-month contracts
        print(subheader("Resolving Contracts"))
        for sym in FUTURES_SYMBOLS:
            try:
                contract = self.futures.get_front_month(sym)
                spec = FUTURES_SPECS.get(sym, {})
                print(f"  {C.GREEN}✓{C.RESET} {C.BOLD}{sym:<5}{C.RESET} → {contract.local_symbol:<8} "
                      f"exp={contract.expiration}  "
                      f"${spec.get('multiplier', '?')}/pt  "
                      f"{C.DIM}{spec.get('name', '')}{C.RESET}")
            except Exception as e:
                print(f"  {C.RED}✗{C.RESET} {C.BOLD}{sym:<5}{C.RESET} — {e}")

        # Get initial account state
        margin = self.futures.get_margin_info()
        self.start_equity = margin.net_liquidation
        self.risk_mgr.update_equity(margin.net_liquidation)

        print(subheader("Account"))
        self._display_margin(margin)

        # Main loop
        minutes_since_scan = FUTURES_SCAN_MINUTES  # trigger immediately
        while True:
            try:
                if not self.futures.is_market_open():
                    print(f"  {C.DIM}Futures market closed. Waiting...{C.RESET}")
                    time.sleep(60)
                    continue

                minutes_since_scan += POSITION_CHECK_MINUTES

                # Check margin and positions every cycle
                margin = self.futures.get_margin_info()
                daily_pnl = margin.net_liquidation - self.start_equity

                # Daily loss limit (dollar-based for futures)
                if daily_pnl < -FUTURES_DAILY_LOSS_LIMIT:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} DAILY LOSS LIMIT ${abs(daily_pnl):.0f} {C.RESET}")
                    break

                # Drawdown kill switch
                risk = self.risk_mgr.update_equity(margin.net_liquidation)
                if not risk.passed:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} KILL SWITCH {C.RESET} {C.RED}{risk.reason}{C.RESET}")
                    if not self.dry_run:
                        self.futures.close_all_positions()
                    break

                # Manage existing positions (every cycle)
                positions = self.futures.get_positions()
                if positions:
                    print(subheader("Futures Positions"))
                    self._manage_positions(positions)

                # Scan for new trades
                if minutes_since_scan >= FUTURES_SCAN_MINUTES:
                    minutes_since_scan = 0
                    self.scan_count += 1

                    print(subheader(f"Futures Scan #{self.scan_count}"))
                    self._display_margin(margin)

                    open_slots = FUTURES_MAX_POSITIONS - len(positions)
                    if open_slots > 0:
                        self._scan_and_enter(margin, positions, open_slots)
                    else:
                        print(f"  {C.DIM}All {FUTURES_MAX_POSITIONS} slots filled.{C.RESET}")

                print(f"\n  {C.DIM}Next check in {POSITION_CHECK_MINUTES}m{C.RESET}")
                time.sleep(POSITION_CHECK_MINUTES * 60)

            except KeyboardInterrupt:
                print(f"\n  {C.YELLOW}Shutting down...{C.RESET}")
                break
            except Exception as e:
                print(f"\n  {C.RED}Error: {e}{C.RESET}")
                logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

        self._end_of_day_summary()

    def _display_margin(self, margin):
        """Show margin status."""
        margin_used_pct = margin.initial_margin / margin.net_liquidation if margin.net_liquidation > 0 else 0
        color = C.GREEN if margin_used_pct < 0.30 else C.YELLOW if margin_used_pct < 0.60 else C.RED
        daily_pnl = margin.net_liquidation - self.start_equity

        print(f"  {C.DIM}Net Liq:{C.RESET}     {C.BOLD}${margin.net_liquidation:>12,.2f}{C.RESET}")
        print(f"  {C.DIM}Available:{C.RESET}   ${margin.available_funds:>12,.2f}")
        print(f"  {C.DIM}Margin Used:{C.RESET} {color}${margin.initial_margin:>12,.2f}{C.RESET} ({color}{margin_used_pct:.0%}{C.RESET})")
        print(f"  {C.DIM}Day P&L:{C.RESET}     {pnl_color(daily_pnl, '+12,.2f')}")
        print(divider())

    def _generate_signals(self) -> list[FuturesSignal]:
        """Generate trading signals using yfinance data on futures proxies."""
        signals = []

        for symbol in FUTURES_SYMBOLS:
            yf_ticker = YF_PROXY.get(symbol)
            if not yf_ticker:
                continue

            try:
                # Get hourly data for intraday signals
                data = yf.download(yf_ticker, period="5d", interval="1h", progress=False)
                if len(data) < 21:
                    continue

                close = data["Close"].squeeze()
                volume = data["Volume"].squeeze()
                high = data["High"].squeeze() if "High" in data.columns else close
                low = data["Low"].squeeze() if "Low" in data.columns else close

                # Momentum
                mom_5 = close.iloc[-1] / close.iloc[-5] - 1
                mom_21 = close.iloc[-1] / close.iloc[-21] - 1

                # Volume ratio (recent vs average)
                vol_recent = volume.iloc[-3:].mean()
                vol_avg = volume.iloc[:-3].mean()
                vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1.0

                # RSI (14-period on hourly bars)
                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss_s = (-delta.clip(upper=0)).rolling(14).mean()
                rs = float(gain.iloc[-1]) / float(loss_s.iloc[-1]) if float(loss_s.iloc[-1]) > 0 else 100
                rsi = 100 - (100 / (1 + rs))

                # ATR (14-period) for dynamic stop sizing
                tr = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs(),
                ], axis=1).max(axis=1)
                atr_14 = float(tr.rolling(14).mean().iloc[-1])
                price = float(close.iloc[-1])
                atr_pct = atr_14 / price if price > 0 else 0.02

                # Trend alignment: short and long momentum same direction
                trend_aligned = (mom_5 > 0 and mom_21 > 0) or (mom_5 < 0 and mom_21 < 0)

                # Simple moving averages
                sma_8 = close.iloc[-8:].mean()
                sma_21 = close.iloc[-21:].mean()

                # --- Strategy 1: Trend Following ---
                if abs(mom_5) > 0.005 and trend_aligned:
                    direction = "long" if mom_5 > 0 else "short"

                    # RSI filter: don't go long overbought, don't short oversold
                    if direction == "long" and rsi > 70:
                        pass  # skip
                    elif direction == "short" and rsi < 30:
                        pass  # skip
                    elif direction == "long" and price > sma_8 > sma_21:
                        score = abs(mom_5) * 10 + abs(mom_21) * 5
                        if vol_ratio > 1.5:
                            score += vol_ratio * 0.3
                        stop = max(atr_pct * 1.5, 0.005)  # 1.5x ATR, floor 0.5%
                        signals.append(FuturesSignal(
                            symbol=symbol, score=score, direction=direction,
                            momentum_short=mom_5, momentum_long=mom_21,
                            volume_ratio=vol_ratio, trend_aligned=True,
                            reason=f"trend_long 5h={mom_5:+.2%} 21h={mom_21:+.2%} RSI={rsi:.0f}",
                            rsi=rsi, atr_stop_pct=stop,
                        ))
                    elif direction == "short" and price < sma_8 < sma_21:
                        score = abs(mom_5) * 10 + abs(mom_21) * 5
                        if vol_ratio > 1.5:
                            score += vol_ratio * 0.3
                        stop = max(atr_pct * 1.5, 0.005)
                        signals.append(FuturesSignal(
                            symbol=symbol, score=score, direction=direction,
                            momentum_short=mom_5, momentum_long=mom_21,
                            volume_ratio=vol_ratio, trend_aligned=True,
                            reason=f"trend_short 5h={mom_5:+.2%} 21h={mom_21:+.2%} RSI={rsi:.0f}",
                            rsi=rsi, atr_stop_pct=stop,
                        ))

                # --- Strategy 2: Mean Reversion ---
                # Extreme short-term move against the longer trend = fade it
                if abs(mom_5) > 0.02 and not trend_aligned:
                    direction = "long" if mom_5 < 0 and mom_21 > 0 else "short" if mom_5 > 0 and mom_21 < 0 else None
                    if direction:
                        score = abs(mom_5) * 5
                        # RSI confirms mean reversion
                        if direction == "long" and rsi < 30:
                            score += 0.1  # oversold bounce
                        elif direction == "short" and rsi > 70:
                            score += 0.1  # overbought fade
                        stop = max(atr_pct * 2.0, 0.008)  # wider stop for mean reversion
                        signals.append(FuturesSignal(
                            symbol=symbol, score=score, direction=direction,
                            momentum_short=mom_5, momentum_long=mom_21,
                            volume_ratio=vol_ratio, trend_aligned=False,
                            reason=f"mean_revert 5h={mom_5:+.2%} 21h={mom_21:+.2%} RSI={rsi:.0f}",
                            rsi=rsi, atr_stop_pct=stop,
                        ))

            except Exception as e:
                logger.debug(f"Signal generation failed for {symbol}: {e}")
                continue

        signals.sort(key=lambda s: -s.score)
        return signals

    def _scan_and_enter(self, margin, positions: list[FuturesPosition], open_slots: int):
        """Scan for signals and enter new positions."""
        signals = self._generate_signals()

        if not signals:
            print(f"  {C.DIM}No futures signals.{C.RESET}")
            return

        # Show all signals
        print(f"\n  {C.BOLD}{len(signals)} signals:{C.RESET}")
        for s in signals:
            dir_color = C.GREEN if s.direction == "long" else C.RED
            aligned = f"{C.GREEN}aligned{C.RESET}" if s.trend_aligned else f"{C.YELLOW}counter{C.RESET}"
            spec = FUTURES_SPECS.get(s.symbol, {})
            print(f"  {score_color(s.score)} {C.BOLD}{s.symbol:<5}{C.RESET} "
                  f"{dir_color}{C.BOLD}{s.direction:<6}{C.RESET} "
                  f"5h={pct_color(s.momentum_short, '+5.2%')} "
                  f"21h={pct_color(s.momentum_long, '+5.2%')} "
                  f"vol={C.CYAN}{s.volume_ratio:.1f}x{C.RESET} "
                  f"{aligned} "
                  f"{C.DIM}{spec.get('name', '')}{C.RESET}")

        print()

        # Filter: already have a position in this symbol?
        held_symbols = {p.symbol for p in positions}

        for signal in signals[:open_slots]:
            if signal.score < MIN_SCORE:
                continue
            if signal.symbol in held_symbols:
                print(f"  {C.DIM}Skipping {signal.symbol} — already holding{C.RESET}")
                continue

            # Margin check: need at least 50% excess after this trade
            if margin.excess_liquidity < margin.net_liquidation * 0.30:
                print(f"  {C.YELLOW}Margin too tight — stopping entries{C.RESET}")
                break

            side = "buy" if signal.direction == "long" else "sell"
            qty = 1  # always 1 micro contract per signal

            if self.dry_run:
                dir_color = C.GREEN if signal.direction == "long" else C.RED
                print(f"  {dir_color}{C.BOLD}{signal.direction.upper():<5}{C.RESET} "
                      f"{C.BOLD}{signal.symbol}{C.RESET} x{qty}  "
                      f"{score_color(signal.score)}  "
                      f"stop={signal.atr_stop_pct:.1%}  "
                      f"{C.DIM}DRY RUN {signal.reason}{C.RESET}")
                self._position_stops[signal.symbol] = signal.atr_stop_pct
            else:
                try:
                    self.futures.submit_order(signal.symbol, qty, side)
                    self._position_stops[signal.symbol] = signal.atr_stop_pct
                    dir_color = C.GREEN if signal.direction == "long" else C.RED
                    print(f"  {dir_color}{C.BOLD}{signal.direction.upper():<5}{C.RESET} "
                          f"{C.BOLD}{signal.symbol}{C.RESET} x{qty}  "
                          f"{score_color(signal.score)}  "
                          f"stop={signal.atr_stop_pct:.1%}  "
                          f"{C.DIM}{signal.reason}{C.RESET}")
                    log_trade(signal.symbol, side, 0, asset_type="futures",
                              score=signal.score, reason=signal.reason)
                    logger.info(f"ENTERED {signal.direction} {signal.symbol} x{qty}")
                except Exception as e:
                    print(f"  {C.RED}Failed: {signal.symbol} — {e}{C.RESET}")
                    logger.error(f"Failed: {signal.symbol} — {e}")

    def _manage_positions(self, positions: list[FuturesPosition]):
        """Check futures positions for stop loss / take profit (ATR-based)."""
        for pos in positions:
            pnl_pct = pos.unrealized_pl_pct
            direction = "LONG" if pos.qty > 0 else "SHORT"
            dir_color = C.GREEN if pos.qty > 0 else C.RED

            # Use ATR-based stop if available, otherwise fall back to config
            stop_pct = self._position_stops.get(pos.symbol, FUTURES_STOP_LOSS_PCT)

            if pnl_pct < -stop_pct:
                print(f"  {C.RED}✗ STOP{C.RESET}  {dir_color}{direction:<5}{C.RESET} "
                      f"{C.BOLD}{pos.symbol:<5}{C.RESET} "
                      f"{pct_color(pnl_pct, '+.1%')} ({pnl_color(pos.unrealized_pl)})")
                if not self.dry_run:
                    try:
                        self.futures.close_position(pos.symbol)
                        log_trade(pos.symbol, "close", 0, asset_type="futures",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="stop_loss")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            elif pnl_pct > FUTURES_TAKE_PROFIT_PCT:
                print(f"  {C.GREEN}✓ TAKE{C.RESET}  {dir_color}{direction:<5}{C.RESET} "
                      f"{C.BOLD}{pos.symbol:<5}{C.RESET} "
                      f"{pct_color(pnl_pct, '+.1%')} ({pnl_color(pos.unrealized_pl)})")
                if not self.dry_run:
                    try:
                        self.futures.close_position(pos.symbol)
                        log_trade(pos.symbol, "close", 0, asset_type="futures",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="take_profit")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            else:
                print(f"  {C.CYAN}● HOLD{C.RESET}  {dir_color}{direction:<5}{C.RESET} "
                      f"{C.BOLD}{pos.symbol:<5}{C.RESET} "
                      f"{pct_color(pnl_pct, '+.1%')} ({pnl_color(pos.unrealized_pl)})")

    def _end_of_day_summary(self):
        """Show end of session summary."""
        try:
            margin = self.futures.get_margin_info()
            positions = self.futures.get_positions()
            pnl = margin.net_liquidation - self.start_equity
            pct = pnl / self.start_equity if self.start_equity > 0 else 0

            print(header("FUTURES SESSION SUMMARY", color=C.MAGENTA))
            print(f"  Start      ${self.start_equity:>12,.2f}")
            print(f"  End        ${margin.net_liquidation:>12,.2f}")
            print(f"  P&L        {pnl_color(pnl, '+12,.2f')}  ({pct_color(pct)})")
            print(f"  Scans      {self.scan_count}")
            print(f"  Open       {len(positions)} positions")
            print(divider())
        except Exception as e:
            print(f"  {C.RED}Summary error: {e}{C.RESET}")
