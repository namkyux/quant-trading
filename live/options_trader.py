"""
Options Trader — Automated options strategies.

Strategies:
1. Momentum Calls: Buy calls on hot stocks from scanner (leveraged momentum)
2. Earnings Straddles: Buy ATM straddles before earnings (bet on big move)
3. Protective Puts: Buy puts as insurance on existing stock positions
4. Covered Calls: Sell calls against stock positions for income

Uses the hot stock scanner (volume anomalies, Reddit buzz, insider filings)
to dynamically find momentum call candidates instead of a hardcoded list.

Run via: python live/run.py --type options
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

import pandas as pd

from config import (
    MAX_DRAWDOWN_PCT, UNIVERSE_SOURCE,
    SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME,
)
from live.broker_factory import get_broker, get_options_broker
from live.risk_manager import RiskManager
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.scanner import run_full_scan
from utils.trade_log import log_trade
from utils.display import (
    C, display_banner, display_account, display_positions,
    display_scan_header, display_trade, display_hot_stocks, subheader,
    display_position_action, display_daily_summary,
    display_no_signals, pct_color, pnl_color, score_color, header, divider,
)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"options_{datetime.now():%Y%m%d}.log")),
    ],
)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("options_trader")

# --- Configuration ---
SCAN_INTERVAL_MINUTES = 15
HOT_SCAN_MINUTES = 60          # run full hot stock scan every 60 min
MAX_OPTIONS_POSITIONS = 5
MAX_COST_PER_TRADE = 500       # max $500 per option trade (controls risk)
DAILY_LOSS_LIMIT_PCT = 0.05
STOP_LOSS_PCT = 0.50           # 50% loss on an option = exit (options are volatile)
TAKE_PROFIT_PCT = 1.00         # 100% gain = take profit (double your money)
MIN_DAYS_TO_EXPIRY = 14        # don't buy options expiring in < 2 weeks
MAX_DAYS_TO_EXPIRY = 45        # don't buy options expiring in > 45 days
MIN_STRADDLE_VOL_RATIO = 2.0   # min volume ratio to trigger earnings straddle
STOP_COOLDOWN_HOURS = 4        # don't re-enter same underlying after stop loss


@dataclass
class OptionSignal:
    underlying: str
    strategy: str           # "momentum_call", "earnings_straddle", "protective_put"
    score: float
    contract_symbol: str
    contract_type: str      # "call" or "put"
    strike: float
    expiration: str
    estimated_cost: float   # per contract
    reason: str


class OptionsTrader:
    """Automated options trading system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.broker = None  # created in start()
        self.options = None
        self.risk_mgr = RiskManager(
            max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_position_pct=0.10,  # tighter for options
        )
        self.start_equity = 0.0
        self.scan_count = 0
        self.hot_tickers: dict[str, float] = {}
        self.universe: list[str] = []
        self._minutes_since_hot = HOT_SCAN_MINUTES
        self._stop_cooldowns: dict[str, datetime] = {}  # underlying -> earliest re-entry time

    def start(self):
        """Main loop — runs during market hours."""
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        self.broker = get_broker()
        self.options = get_options_broker()

        display_banner()

        print(f"  {C.YELLOW}{C.BOLD}OPTIONS MODE{C.RESET}")
        mode_str = f"{C.YELLOW}{C.BOLD}SIMULATE{C.RESET}" if self.dry_run else f"{C.GREEN}{C.BOLD}PAPER{C.RESET}"
        print(f"  {C.DIM}Mode:{C.RESET}             {mode_str}")
        print(f"  {C.DIM}Scan interval:{C.RESET}    every {C.BOLD}{SCAN_INTERVAL_MINUTES} min{C.RESET}")
        print(f"  {C.DIM}Max per trade:{C.RESET}    {C.BOLD}${MAX_COST_PER_TRADE}{C.RESET}")
        print(f"  {C.DIM}Max positions:{C.RESET}    {C.BOLD}{MAX_OPTIONS_POSITIONS}{C.RESET}")
        print(f"  {C.DIM}Stop loss:{C.RESET}        {C.RED}{STOP_LOSS_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Take profit:{C.RESET}      {C.GREEN}{TAKE_PROFIT_PCT:.0%}{C.RESET}")
        print(f"  {C.DIM}Expiry range:{C.RESET}     {MIN_DAYS_TO_EXPIRY}-{MAX_DAYS_TO_EXPIRY} days")
        print()

        # Load stock universe for scanner
        universe_df = get_universe(UNIVERSE_SOURCE)
        criteria = ScreenCriteria(min_price=SCREEN_MIN_PRICE, min_avg_volume=SCREEN_MIN_AVG_VOLUME)
        self.universe = screen(universe_df, criteria, verbose=False)
        print(f"  {C.DIM}Universe:{C.RESET}        {C.BOLD}{len(self.universe)} stocks{C.RESET}")
        print()

        account = self.broker.get_account()
        self.start_equity = account.equity
        self.risk_mgr.update_equity(account.equity)

        display_account(
            account.equity, account.cash, account.buying_power,
            len(account.positions), peak=self.risk_mgr.peak_equity,
        )

        while True:
            try:
                if not self.broker.is_market_open():
                    print(f"  {C.DIM}Market closed. Waiting...{C.RESET}")
                    time.sleep(60)
                    continue

                self.scan_count += 1
                display_scan_header(self.scan_count, SCAN_INTERVAL_MINUTES, 0)

                # Risk check
                account = self.broker.get_account()
                daily_pnl = (account.equity - self.start_equity) / self.start_equity
                display_account(
                    account.equity, account.cash, account.buying_power,
                    len(account.positions), daily_pnl=account.equity - self.start_equity,
                    peak=self.risk_mgr.peak_equity,
                )

                if daily_pnl < -DAILY_LOSS_LIMIT_PCT:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} DAILY LOSS LIMIT {C.RESET}")
                    break

                risk = self.risk_mgr.update_equity(account.equity)
                if not risk.passed:
                    print(f"\n  {C.BG_RED}{C.WHITE}{C.BOLD} KILL SWITCH {C.RESET} {C.RED}{risk.reason}{C.RESET}")
                    break

                # Hot stock scanner (runs every HOT_SCAN_MINUTES)
                self._minutes_since_hot += SCAN_INTERVAL_MINUTES
                if self._minutes_since_hot >= HOT_SCAN_MINUTES:
                    self._minutes_since_hot = 0
                    print(subheader("Hot Stock Scanner (Options)"))
                    try:
                        hot_stocks = run_full_scan(
                            self.universe,
                            include_social=True,
                            include_insider=True,
                        )
                        if hot_stocks:
                            self.hot_tickers = {h.symbol: h.heat_score for h in hot_stocks[:15]}
                            display_hot_stocks(hot_stocks, top_n=10)
                        else:
                            self.hot_tickers = {}
                            print(f"  {C.DIM}No hot stocks detected.{C.RESET}")
                    except Exception as e:
                        logger.error(f"Hot scan failed: {e}")
                        print(f"  {C.RED}Hot scan error: {e}{C.RESET}")

                # Manage existing option positions
                print(subheader("Options Positions"))
                self._manage_positions(account)

                # Scan for new option plays
                option_positions = [p for p in account.positions if len(p.symbol) > 10]
                open_slots = MAX_OPTIONS_POSITIONS - len(option_positions)
                if open_slots > 0:
                    print(subheader(f"Options Scanner ({open_slots} slots)"))
                    self._scan_and_enter(account, open_slots)
                else:
                    print(f"\n  {C.DIM}All {MAX_OPTIONS_POSITIONS} option slots filled.{C.RESET}")

                print(f"\n  {C.DIM}Next scan in {SCAN_INTERVAL_MINUTES}m{C.RESET}")
                time.sleep(SCAN_INTERVAL_MINUTES * 60)

            except KeyboardInterrupt:
                print(f"\n  {C.YELLOW}Shutting down...{C.RESET}")
                break
            except Exception as e:
                print(f"\n  {C.RED}Error: {e}{C.RESET}")
                logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)

        self._end_of_day_summary()

    def _scan_and_enter(self, account, open_slots: int):
        """Scan for option trading opportunities."""
        signals = self._generate_signals(account)

        if not signals:
            display_no_signals()
            return

        # Purge expired cooldowns
        now = datetime.now()
        self._stop_cooldowns = {s: t for s, t in self._stop_cooldowns.items() if t > now}

        # Filter out underlyings in cooldown (recently stopped out)
        before = len(signals)
        signals = [s for s in signals if now >= self._stop_cooldowns.get(s.underlying, datetime.min)]

        # Filter out underlyings we already hold options on
        held_underlyings = set()
        for p in account.positions:
            if len(p.symbol) > 10:
                held_underlyings.add(self._extract_underlying(p.symbol))
        signals = [s for s in signals if s.underlying not in held_underlyings]

        if before != len(signals):
            filtered = before - len(signals)
            print(f"  {C.DIM}Filtered {filtered} signals (cooldown/dedup){C.RESET}")

        if not signals:
            display_no_signals()
            return

        print(f"\n  {C.BOLD}{len(signals)} option signals:{C.RESET}")
        for s in signals[:open_slots + 3]:
            strat_color = C.GREEN if "call" in s.strategy else C.RED if "put" in s.strategy else C.YELLOW
            print(f"  {score_color(s.score)} {strat_color}{C.BOLD}{s.strategy:<20}{C.RESET} "
                  f"{C.WHITE}{C.BOLD}{s.underlying:<6}{C.RESET} "
                  f"${s.strike:>7.0f} {s.contract_type:<4} "
                  f"exp={s.expiration} "
                  f"~${s.estimated_cost:>6.0f} "
                  f"{C.DIM}{s.reason}{C.RESET}")

        print()

        for signal in signals[:open_slots]:
            cost = signal.estimated_cost * 100  # options are per 100 shares

            if cost > MAX_COST_PER_TRADE:
                print(f"  {C.YELLOW}Skipping {signal.underlying} — cost ${cost:.0f} > max ${MAX_COST_PER_TRADE}{C.RESET}")
                continue

            if cost > account.buying_power * 0.20:
                print(f"  {C.YELLOW}Skipping {signal.underlying} — insufficient buying power{C.RESET}")
                continue

            if self.dry_run:
                display_trade("buy", signal.contract_symbol, cost, signal.score, f"DRY RUN {signal.strategy}")
            else:
                try:
                    self.options.buy_option(signal.contract_symbol, qty=1)
                    display_trade("buy", signal.contract_symbol, cost, signal.score, signal.strategy)
                    log_trade(signal.contract_symbol, "buy", cost, asset_type="option",
                              score=signal.score, reason=signal.strategy)
                    logger.info(f"BOUGHT {signal.contract_symbol} (${cost:.0f})")
                except Exception as e:
                    print(f"  {C.RED}Failed: {signal.contract_symbol} — {e}{C.RESET}")
                    logger.error(f"Failed: {signal.contract_symbol} — {e}")

    def _generate_signals(self, account) -> list[OptionSignal]:
        """Generate option trading signals from existing stock positions and scanner."""
        signals = []

        # Strategy 1: Momentum calls on hot stocks
        # Use the stock day trader's universe to find momentum picks
        signals.extend(self._scan_momentum_calls())

        # Strategy 2: Earnings straddles on stocks with upcoming earnings + unusual volume
        signals.extend(self._scan_earnings_straddles())

        # Strategy 3: Protective puts on existing large positions
        signals.extend(self._scan_protective_puts(account))

        # Strategy 4: Covered calls on existing positions
        signals.extend(self._scan_covered_calls(account))

        signals.sort(key=lambda s: -s.score)
        return signals

    def _scan_momentum_calls(self) -> list[OptionSignal]:
        """Buy calls on hot stocks from the scanner + momentum confirmation."""
        import yfinance as yf

        # Use hot stocks from scanner, fall back to mega-cap defaults
        if self.hot_tickers:
            momentum_picks = list(self.hot_tickers.keys())[:15]
            logger.info(f"Momentum calls: scanning {len(momentum_picks)} hot stocks")
        else:
            momentum_picks = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "AMD"]
            logger.info("Momentum calls: no hot stocks, using defaults")

        signals = []

        for symbol in momentum_picks:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1mo")
                if len(hist) < 5:
                    continue

                current_price = hist["Close"].iloc[-1]
                mom_5d = hist["Close"].iloc[-1] / hist["Close"].iloc[-5] - 1
                mom_21d = hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1

                # Only buy calls on stocks with positive momentum
                if mom_5d <= 0 or mom_21d <= 0:
                    continue

                # Find a slightly OTM call (5% above current price)
                target_strike = round(current_price * 1.05, -1)
                contract = self.options.get_nearest_call(
                    symbol, target_strike,
                    min_days=MIN_DAYS_TO_EXPIRY, max_days=MAX_DAYS_TO_EXPIRY,
                )
                if not contract:
                    continue

                quote = self.options.get_quote(contract.symbol)
                if not quote or quote.ask <= 0:
                    continue

                # Base score from momentum
                score = mom_5d * 5.0 + mom_21d * 3.0
                # Boost score if the stock is hot from scanner
                heat = self.hot_tickers.get(symbol, 0)
                if heat > 0:
                    score += heat * 0.5

                reason_parts = [f"5d={mom_5d:+.1%}", f"21d={mom_21d:+.1%}"]
                if heat > 0:
                    reason_parts.append(f"heat={heat:.1f}")

                signals.append(OptionSignal(
                    underlying=symbol,
                    strategy="momentum_call",
                    score=score,
                    contract_symbol=contract.symbol,
                    contract_type="call",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    estimated_cost=quote.ask,
                    reason=" ".join(reason_parts),
                ))

            except Exception as e:
                logger.debug(f"Momentum call scan failed for {symbol}: {e}")
                continue

        return signals

    def _scan_earnings_straddles(self) -> list[OptionSignal]:
        """
        Buy straddles on stocks with upcoming earnings + unusual pre-earnings volume.

        A straddle = buy a call + buy a put at the same strike (ATM).
        Profits from a big move in either direction — perfect for earnings.
        We look for stocks where the market is already pricing in a move
        (high volume) but hasn't fully moved yet.
        """
        import yfinance as yf

        # Check hot stocks + a curated list of high-vol earnings movers
        candidates = list(self.hot_tickers.keys())[:20] if self.hot_tickers else []
        # Always check mega-caps that frequently have big earnings moves
        for sym in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX", "AMD", "CRM"]:
            if sym not in candidates:
                candidates.append(sym)

        signals = []

        for symbol in candidates:
            try:
                ticker = yf.Ticker(symbol)

                # Check if earnings are within the next 14 days
                cal = ticker.calendar
                if cal is None or cal.empty:
                    continue

                earnings_date = None
                if "Earnings Date" in cal.index:
                    raw = cal.loc["Earnings Date"]
                    if hasattr(raw, "iloc"):
                        earnings_date = pd.Timestamp(raw.iloc[0])
                    else:
                        earnings_date = pd.Timestamp(raw)
                elif isinstance(cal, pd.DataFrame) and len(cal.columns) > 0:
                    # Some yfinance versions return columns as dates
                    earnings_date = pd.Timestamp(cal.columns[0])

                if earnings_date is None:
                    continue

                now = pd.Timestamp.now()
                days_to_earnings = (earnings_date - now).days
                if days_to_earnings < 1 or days_to_earnings > 14:
                    continue

                # Check for unusual pre-earnings volume
                hist = ticker.history(period="1mo")
                if len(hist) < 10:
                    continue

                current_price = hist["Close"].iloc[-1]
                vol_recent = hist["Volume"].iloc[-3:].mean()
                vol_avg = hist["Volume"].iloc[:-3].mean()
                vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 0

                if vol_ratio < MIN_STRADDLE_VOL_RATIO:
                    continue

                # Find ATM call and put
                target_strike = round(current_price, -1)  # nearest round number
                call = self.options.get_nearest_call(
                    symbol, target_strike,
                    min_days=days_to_earnings, max_days=max(days_to_earnings + 7, MIN_DAYS_TO_EXPIRY),
                )
                put = self.options.get_nearest_put(
                    symbol, target_strike,
                    min_days=days_to_earnings, max_days=max(days_to_earnings + 7, MIN_DAYS_TO_EXPIRY),
                )
                if not call or not put:
                    continue

                call_quote = self.options.get_quote(call.symbol)
                put_quote = self.options.get_quote(put.symbol)
                if not call_quote or not put_quote:
                    continue
                if call_quote.ask <= 0 or put_quote.ask <= 0:
                    continue

                total_cost = call_quote.ask + put_quote.ask
                # Score: higher volume anomaly + closer earnings = better
                score = vol_ratio * 0.5 + (14 - days_to_earnings) * 0.1
                heat = self.hot_tickers.get(symbol, 0)
                if heat > 0:
                    score += heat * 0.3

                # Add the call leg
                signals.append(OptionSignal(
                    underlying=symbol,
                    strategy="earnings_straddle",
                    score=score,
                    contract_symbol=call.symbol,
                    contract_type="call",
                    strike=call.strike,
                    expiration=call.expiration,
                    estimated_cost=call_quote.ask,
                    reason=f"earnings in {days_to_earnings}d vol={vol_ratio:.1f}x straddle=${total_cost:.2f}",
                ))
                # Add the put leg
                signals.append(OptionSignal(
                    underlying=symbol,
                    strategy="earnings_straddle",
                    score=score,
                    contract_symbol=put.symbol,
                    contract_type="put",
                    strike=put.strike,
                    expiration=put.expiration,
                    estimated_cost=put_quote.ask,
                    reason=f"earnings in {days_to_earnings}d vol={vol_ratio:.1f}x straddle=${total_cost:.2f}",
                ))

            except Exception as e:
                logger.debug(f"Earnings straddle scan failed for {symbol}: {e}")
                continue

        return signals

    def _scan_protective_puts(self, account) -> list[OptionSignal]:
        """Buy puts to protect large stock positions."""
        signals = []

        for pos in account.positions:
            # Only protect stock positions > $5K
            if "/" in pos.symbol or len(pos.symbol) > 10:
                continue
            if pos.market_value < 5000:
                continue

            try:
                # Find a put ~5% below current price
                target_strike = round(pos.current_price * 0.95, -1)
                contract = self.options.get_nearest_put(
                    pos.symbol, target_strike,
                    min_days=MIN_DAYS_TO_EXPIRY, max_days=MAX_DAYS_TO_EXPIRY,
                )
                if not contract:
                    continue

                quote = self.options.get_quote(contract.symbol)
                if not quote or quote.ask <= 0:
                    continue

                # Score based on position size and current loss
                score = 0.5 + (pos.market_value / 50000)  # bigger positions = more urgent
                if pos.unrealized_pl_pct > 0.05:
                    score += 0.3  # protect gains

                signals.append(OptionSignal(
                    underlying=pos.symbol,
                    strategy="protective_put",
                    score=score,
                    contract_symbol=contract.symbol,
                    contract_type="put",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    estimated_cost=quote.ask,
                    reason=f"protecting ${pos.market_value:,.0f} ({pos.unrealized_pl_pct:+.1%})",
                ))

            except Exception as e:
                logger.debug(f"Protective put scan failed for {pos.symbol}: {e}")
                continue

        return signals

    def _scan_covered_calls(self, account) -> list[OptionSignal]:
        """Sell calls against existing stock positions for income."""
        signals = []

        for pos in account.positions:
            if "/" in pos.symbol or len(pos.symbol) > 10:
                continue
            if pos.qty < 100:  # need at least 100 shares for covered call
                continue

            try:
                # Find a call ~5% above current price
                target_strike = round(pos.current_price * 1.05, -1)
                contract = self.options.get_nearest_call(
                    pos.symbol, target_strike,
                    min_days=MIN_DAYS_TO_EXPIRY, max_days=MAX_DAYS_TO_EXPIRY,
                )
                if not contract:
                    continue

                quote = self.options.get_quote(contract.symbol)
                if not quote or quote.bid <= 0:
                    continue

                # Score: higher premium = better
                premium_pct = quote.bid / pos.current_price
                score = premium_pct * 100

                signals.append(OptionSignal(
                    underlying=pos.symbol,
                    strategy="covered_call",
                    score=score,
                    contract_symbol=contract.symbol,
                    contract_type="call",
                    strike=contract.strike,
                    expiration=contract.expiration,
                    estimated_cost=quote.bid,  # this is income, not cost
                    reason=f"premium ${quote.bid:.2f} on {int(pos.qty)} shares",
                ))

            except Exception as e:
                logger.debug(f"Covered call scan failed for {pos.symbol}: {e}")
                continue

        return signals

    @staticmethod
    def _extract_underlying(option_symbol: str) -> str:
        """Extract underlying ticker from OCC option symbol (e.g., 'AAPL260315C00170000' -> 'AAPL')."""
        for i, ch in enumerate(option_symbol):
            if ch.isdigit():
                return option_symbol[:i]
        return option_symbol[:4]

    def _manage_positions(self, account):
        """Check option positions for stop loss / take profit."""
        option_positions = [p for p in account.positions if len(p.symbol) > 10]

        if not option_positions:
            print(f"  {C.DIM}No option positions{C.RESET}")
            return

        for pos in option_positions:
            pnl_pct = pos.unrealized_pl_pct

            if pnl_pct < -STOP_LOSS_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "stop_loss")
                # Cooldown: block this underlying from re-entry
                underlying = self._extract_underlying(pos.symbol)
                cooldown_until = datetime.now() + timedelta(hours=STOP_COOLDOWN_HOURS)
                self._stop_cooldowns[underlying] = cooldown_until
                print(f"    {C.YELLOW}Cooldown: {underlying} blocked until {cooldown_until:%H:%M}{C.RESET}")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="option",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="stop_loss")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            elif pnl_pct > TAKE_PROFIT_PCT:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "take_profit")
                if not self.dry_run:
                    try:
                        self.broker.close_position(pos.symbol)
                        log_trade(pos.symbol, "sell", pos.market_value, asset_type="option",
                                  pnl=pos.unrealized_pl, pnl_pct=pnl_pct, reason="take_profit")
                    except Exception as e:
                        print(f"    {C.RED}Failed: {e}{C.RESET}")

            else:
                display_position_action(pos.symbol, pnl_pct, pos.unrealized_pl, "hold")

    def _end_of_day_summary(self):
        """Show summary."""
        try:
            account = self.broker.get_account()
            option_positions = [p for p in account.positions if len(p.symbol) > 10]
            display_daily_summary(
                self.start_equity, account.equity,
                self.scan_count, len(option_positions),
            )
        except Exception as e:
            print(f"  {C.RED}Summary error: {e}{C.RESET}")
