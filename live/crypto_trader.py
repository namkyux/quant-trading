"""
Crypto Day Trader — 24/7 automated crypto trading.

Unlike stocks, crypto markets never close. This system:
- Runs 24/7 (no market hours check)
- Trades BTC, ETH, SOL, DOGE and more via Interactive Brokers
- Uses momentum + social sentiment signals
- Wider stop losses (8%) for higher volatility
- Scans Reddit for crypto buzz

Run: python live/crypto_trader.py
     python live/crypto_trader.py --dry-run
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
import requests

import yfinance as yf

from config import (
    CRYPTO_SYMBOLS, CRYPTO_STOP_LOSS_PCT, CRYPTO_TAKE_PROFIT_PCT,
    CRYPTO_MAX_POSITION_PCT, CRYPTO_SCAN_MINUTES,
    MAX_DRAWDOWN_PCT,
)
from live.broker_factory import get_broker
from live.risk_manager import RiskManager
from utils.display import (
    C, display_banner, display_account, display_positions,
    display_scan_header, display_trade, display_signal,
    display_position_action, display_risk_status,
    display_daily_summary, display_no_signals,
    subheader, pct_color, pnl_color, header, divider, heat_bar,
    score_color, FIRE,
)
from utils.trade_log import log_trade

# --- Logging ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"crypto_{datetime.now():%Y%m%d}.log")),
    ],
)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("crypto_trader")

# --- Configuration ---
POSITION_CHECK_MINUTES = 3     # check stops every 3 min (crypto moves fast)
SIGNAL_SCAN_MINUTES = 10       # generate signals every 10 min
SOCIAL_SCAN_MINUTES = 30       # Reddit scan every 30 min
MAX_POSITIONS = 5
DAILY_LOSS_LIMIT_PCT = 0.08    # 8% daily loss limit (crypto is wild)
MIN_SCORE = 0.4


@dataclass
class CryptoSignal:
    symbol: str
    score: float
    momentum_1h: float
    momentum_24h: float
    momentum_7d: float
    volume_ratio: float
    social_buzz: int
    action: str


class CryptoTrader:
    """24/7 crypto trading system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.broker = None  # created in start()
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=CRYPTO_MAX_POSITION_PCT,
        )
        self.start_equity = 0.0
        self.scan_count = 0
        self.social_buzz = {}

    def start(self):
        """Main loop — runs 24/7."""
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.broker = get_broker()

        display_banner()

        print(f"  {C.MAGENTA}{C.BOLD}CRYPTO MODE — 24/7{C.RESET}")
        mode_str = f"{C.YELLOW}{C.BOLD}DRY RUN{C.RESET}" if self.dry_run else f"{C.GREEN}{C.BOLD}LIVE{C.RESET}"
        print(f"  {C.DIM}Mode:{C.RESET}           {mode_str}")
        print(f"  {C.DIM}Position check:{C.RESET}  every {C.BOLD}{POSITION_CHECK_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Signal scan:{C.RESET}     every {C.BOLD}{SIGNAL_SCAN_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Social scan:{C.RESET}     every {C.BOLD}{SOCIAL_SCAN_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Stop loss:{C.RESET}       {C.RED}{CRYPTO_STOP_LOSS_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Take profit:{C.RESET}     {C.GREEN}{CRYPTO_TAKE_PROFIT_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Coins:{C.RESET}           {C.BOLD}{len(CRYPTO_SYMBOLS)}{C.RESET}")
        print()

        # Show universe
        print(subheader("Crypto Universe"))
        for i in range(0, len(CRYPTO_SYMBOLS), 4):
            row = CRYPTO_SYMBOLS[i:i+4]
            print(f"  {C.CYAN}{'  '.join(f'{s:<10}' for s in row)}{C.RESET}")
        print()

        # Get initial account state
        account = self.broker.get_account()
        self.start_equity = account.equity
        self.risk_mgr.update_equity(account.equity)

        display_account(
            account.equity, account.cash, account.buying_power,
            len(account.positions), peak=self.risk_mgr.peak_equity,
        )

        minutes_since_signal = SIGNAL_SCAN_MINUTES  # trigger on first loop
        minutes_since_social = SOCIAL_SCAN_MINUTES

        while True:
            try:
                self.scan_count += 1
                next_signal = SIGNAL_SCAN_MINUTES - minutes_since_signal
                next_social = SOCIAL_SCAN_MINUTES - minutes_since_social
                display_scan_header(self.scan_count, next_signal, next_social)

                # === EVERY 3 MIN: Risk + positions ===
                account = self.broker.get_account()
                daily_pnl_val = account.equity - self.start_equity
                daily_pnl_pct = daily_pnl_val / self.start_equity if self.start_equity else 0

                display_account(
                    account.equity, account.cash, account.buying_power,
                    len(account.positions), daily_pnl=daily_pnl_val,
                    peak=self.risk_mgr.peak_equity,
                )
                logger.info(f"Check #{self.scan_count} | Equity: ${account.equity:,.2f} | P&L: {daily_pnl_pct:+.2%}")

                if daily_pnl_pct < -DAILY_LOSS_LIMIT_PCT:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} DAILY LOSS LIMIT {C.RESET} {C.RED}{daily_pnl_pct:.1%}{C.RESET}")
                    logger.critical(f"DAILY LOSS LIMIT: {daily_pnl_pct:.1%}")
                    if not self.dry_run:
                        self._close_all_crypto()
                    break

                risk = self.risk_mgr.update_equity(account.equity)
                if not risk.passed:
                    display_risk_status(risk.reason, killed=True)
                    logger.critical(f"KILL SWITCH: {risk.reason}")
                    if not self.dry_run:
                        self._close_all_crypto()
                    break

                # Check positions
                print(subheader("Positions"))
                self._manage_positions(account)

                # === EVERY 30 MIN: Social scan ===
                if minutes_since_social >= SOCIAL_SCAN_MINUTES:
                    minutes_since_social = 0
                    print(subheader("Crypto Social Scan"))
                    self._scan_social()

                # === EVERY 10 MIN: Signal scan ===
                if minutes_since_signal >= SIGNAL_SCAN_MINUTES:
                    minutes_since_signal = 0
                    crypto_positions = [p for p in account.positions
                                       if "/" in p.symbol or p.symbol.endswith("USD")]
                    open_slots = MAX_POSITIONS - len(crypto_positions)
                    if open_slots > 0:
                        print(subheader(f"Crypto Signals ({open_slots} slots open)"))
                        self._scan_and_enter(account, open_slots)
                    else:
                        print(f"\n  {C.DIM}All {MAX_POSITIONS} crypto slots filled.{C.RESET}")

                # Next check
                next_signal = SIGNAL_SCAN_MINUTES - minutes_since_signal
                next_social = SOCIAL_SCAN_MINUTES - minutes_since_social
                print(f"\n  {C.DIM}Next check in {POSITION_CHECK_MINUTES}m "
                      f"| signals in {next_signal}m "
                      f"| social in {next_social}m{C.RESET}")

                time.sleep(POSITION_CHECK_MINUTES * 60)
                minutes_since_signal += POSITION_CHECK_MINUTES
                minutes_since_social += POSITION_CHECK_MINUTES

            except KeyboardInterrupt:
                print(f"\n  {C.YELLOW}Shutting down...{C.RESET}")
                break
            except Exception as e:
                print(f"\n  {C.RED}Error: {e}{C.RESET}")
                logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

        self._end_of_day_summary()

    def _get_crypto_prices(self) -> dict[str, dict]:
        """Fetch current crypto prices and bars via yfinance."""
        results = {}

        for symbol in CRYPTO_SYMBOLS:
            try:
                # Convert BTC/USD -> BTC-USD for yfinance
                yf_symbol = symbol.replace("/", "-")
                data = yf.download(yf_symbol, period="7d", interval="1h", progress=False)
                if len(data) < 24:
                    continue

                closes = data["Close"].squeeze().dropna()
                volumes = data["Volume"].squeeze().dropna()
                current_price = float(closes.iloc[-1])

                # Momentum calculations
                mom_1h = float(closes.iloc[-1] / closes.iloc[-2] - 1) if len(closes) >= 2 else 0
                mom_24h = float(closes.iloc[-1] / closes.iloc[-24] - 1) if len(closes) >= 24 else 0
                mom_7d = float(closes.iloc[-1] / closes.iloc[0] - 1) if len(closes) >= 48 else 0

                # Volume ratio (last 6h avg vs 7d avg)
                vol_recent = float(np.mean(volumes.iloc[-6:])) if len(volumes) >= 6 else 0
                vol_avg = float(np.mean(volumes)) if len(volumes) > 0 else 1
                vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 1.0

                results[symbol] = {
                    "price": current_price,
                    "mom_1h": mom_1h,
                    "mom_24h": mom_24h,
                    "mom_7d": mom_7d,
                    "vol_ratio": vol_ratio,
                    "high_7d": float(closes.max()),
                }

            except Exception as e:
                logger.debug(f"Failed to fetch {symbol}: {e}")
                continue

        return results

    def _generate_signals(self) -> list[CryptoSignal]:
        """Generate crypto trading signals."""
        print(f"  {C.DIM}Fetching prices for {len(CRYPTO_SYMBOLS)} coins...{C.RESET}")
        prices = self._get_crypto_prices()

        signals = []
        for symbol, data in prices.items():
            score = 0.0

            # Momentum scoring
            score += data["mom_1h"] * 5.0      # heavy on short-term
            score += data["mom_24h"] * 3.0     # 24h trend
            score += data["mom_7d"] * 2.0      # weekly trend

            # Volume confirmation
            if data["vol_ratio"] > 1.5:
                score += 0.2
            if data["vol_ratio"] > 2.0:
                score += 0.2

            # Near 7-day high (breakout)
            near_high = data["price"] >= data["high_7d"] * 0.97
            if near_high:
                score += 0.3

            # Social buzz boost
            buzz = self.social_buzz.get(symbol.split("/")[0], 0)
            if buzz >= 3:
                score += min(buzz / 5, 1.0)

            # Determine action
            if score >= MIN_SCORE and data["mom_1h"] > 0 and data["mom_24h"] > -0.05:
                action = "buy"
            else:
                action = "hold"

            signals.append(CryptoSignal(
                symbol=symbol,
                score=score,
                momentum_1h=data["mom_1h"],
                momentum_24h=data["mom_24h"],
                momentum_7d=data["mom_7d"],
                volume_ratio=data["vol_ratio"],
                social_buzz=buzz,
                action=action,
            ))

        signals.sort(key=lambda s: -s.score)
        return signals

    def _scan_and_enter(self, account, open_slots: int):
        """Scan and enter new crypto positions."""
        signals = self._generate_signals()
        buys = [s for s in signals if s.action == "buy"]

        # Skip coins we already hold
        held = {p.symbol for p in account.positions}
        buys = [s for s in buys if s.symbol not in held]

        if not buys:
            display_no_signals()
            return

        print(f"\n  {C.BOLD}{len(buys)} buy signals:{C.RESET}")
        for s in buys[:open_slots + 3]:
            buzz_tag = f" {C.MAGENTA}BUZZ x{s.social_buzz}{C.RESET}" if s.social_buzz >= 3 else ""
            print(f"  {score_color(s.score)} {C.BOLD}{C.WHITE}{s.symbol:<10}{C.RESET} "
                  f"1h={pct_color(s.momentum_1h, '+5.1%')} "
                  f"24h={pct_color(s.momentum_24h, '+5.1%')} "
                  f"7d={pct_color(s.momentum_7d, '+5.1%')} "
                  f"vol={C.CYAN}{s.volume_ratio:.1f}x{C.RESET}"
                  f"{buzz_tag}")

        print()

        for signal in buys[:open_slots]:
            # Use buying power (accounts for margin), split among open slots
            available = max(account.buying_power, 0) * 0.90
            max_per_position = account.equity * CRYPTO_MAX_POSITION_PCT
            position_value = min(max_per_position, available / max(open_slots, 1))

            if position_value < 10:  # minimum crypto order
                print(f"  {C.YELLOW}Insufficient buying power (${account.buying_power:,.0f} available, $10 min per order).{C.RESET}")
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
                    log_trade(signal.symbol, "buy", position_value, asset_type="crypto",
                              score=signal.score, reason="momentum signal")
                    logger.info(f"BOUGHT ${position_value:,.0f} of {signal.symbol}")
                except Exception as e:
                    print(f"  {C.RED}Failed to buy {signal.symbol}: {e}{C.RESET}")
                    log_trade(signal.symbol, "buy", position_value, asset_type="crypto",
                              score=signal.score, reason=str(e), status="failed")

    def _manage_positions(self, account):
        """Check crypto positions for stop loss / take profit."""
        crypto_positions = [p for p in account.positions
                          if "/" in p.symbol or p.symbol.endswith("USD")]

        if not crypto_positions:
            print(f"  {C.DIM}No crypto positions{C.RESET}")
            return

        for pos in crypto_positions:
            pnl_pct = pos.unrealized_pl_pct

            if pnl_pct < -CRYPTO_STOP_LOSS_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "stop_loss")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol.replace("/", "%2F"))
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="crypto",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="stop_loss")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            elif pnl_pct > CRYPTO_TAKE_PROFIT_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "take_profit")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol.replace("/", "%2F"))
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="crypto",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="take_profit")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            else:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "hold")

    def _scan_social(self):
        """Scan Reddit for crypto buzz."""
        import re
        import urllib.request

        crypto_tickers = {s.split("/")[0] for s in CRYPTO_SYMBOLS}
        # Add common names
        name_map = {
            "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL",
            "DOGECOIN": "DOGE", "CARDANO": "ADA", "CHAINLINK": "LINK",
            "POLKADOT": "DOT", "AVALANCHE": "AVAX", "LITECOIN": "LTC",
        }

        subreddits = ["cryptocurrency", "CryptoMarkets", "bitcoin", "ethereum", "solana"]
        mentions = {}

        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "QuantTrading/1.0 (crypto scanner)"
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for post in data.get("data", {}).get("children", []):
                    text = (post["data"].get("title", "") + " " +
                            post["data"].get("selftext", "")).upper()

                    for ticker in crypto_tickers:
                        if ticker in text:
                            mentions[ticker] = mentions.get(ticker, 0) + 1

                    for name, ticker in name_map.items():
                        if name in text:
                            mentions[ticker] = mentions.get(ticker, 0) + 1

            except Exception as e:
                logger.debug(f"Failed to scan r/{sub}: {e}")

        self.social_buzz = mentions

        if mentions:
            sorted_buzz = sorted(mentions.items(), key=lambda x: -x[1])
            print(f"  {C.MAGENTA}Reddit buzz:{C.RESET}")
            for ticker, count in sorted_buzz[:8]:
                bar = heat_bar(count, max_score=20, width=8)
                print(f"    {C.BOLD}{ticker:<6}{C.RESET} {C.MAGENTA}x{count:<3}{C.RESET} {bar}")
        else:
            print(f"  {C.DIM}No significant crypto buzz detected.{C.RESET}")

    def _close_all_crypto(self):
        """Close all crypto positions."""
        positions = self.broker.get_positions()
        for p in positions:
            if "/" in p.symbol or p.symbol.endswith("USD"):
                try:
                    self.broker.close_position(p.symbol.replace("/", "%2F"))
                except Exception:
                    pass

    def _end_of_day_summary(self):
        """Show summary."""
        try:
            account = self.broker.get_account()
            crypto_positions = [p for p in account.positions
                              if "/" in p.symbol or p.symbol.endswith("USD")]
            display_daily_summary(
                self.start_equity, account.equity,
                self.scan_count, len(crypto_positions),
            )
            if crypto_positions:
                display_positions(crypto_positions)
        except Exception as e:
            print(f"  {C.RED}Summary error: {e}{C.RESET}")
