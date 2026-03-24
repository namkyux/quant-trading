"""
Quant Trading System

Usage:
  python live/run.py                                  # Run all on paper (default)
  python live/run.py --type stocks                    # Stocks only
  python live/run.py --type crypto                    # Crypto only (24/7)
  python live/run.py --type options                   # Options only
  python live/run.py --type futures                   # Futures only (IB required)
  python live/run.py --type all                       # Everything
  python live/run.py --broker ib                      # Use Interactive Brokers
  python live/run.py --broker alpaca                  # Use Alpaca (default)
  python live/run.py --display account                # Show account & positions
  python live/run.py --scan all                       # Scan stocks + crypto
  python live/run.py --type stocks --simulate         # Simulate stocks (no orders)
"""

import sys
import os
import argparse
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Quant Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python live/run.py                                Run all on paper
  python live/run.py --type stocks                  Stocks only
  python live/run.py --type crypto                  Crypto only (24/7)
  python live/run.py --type stocks --simulate       Simulate stocks
  python live/run.py --display account              Show account & positions
  python live/run.py --scan all                     Full scanner
  python live/run.py --scan crypto                  Crypto scanner + Reddit
        """,
    )

    parser.add_argument(
        "--type", choices=["stocks", "crypto", "options", "futures", "all"], default="all",
        help="What to trade: stocks, crypto, options, futures, or all (default: all)",
    )
    parser.add_argument(
        "--broker", choices=["alpaca", "ib"], default=None,
        help="Override broker: alpaca or ib (default: from BROKER env var)",
    )
    parser.add_argument(
        "--account", choices=["paper"], default="paper",
        help="Which account to use (default: paper)",
    )
    parser.add_argument(
        "--display", choices=["account", "trades"],
        help="Display info: account (live portfolio) or trades (trade history)",
    )
    parser.add_argument(
        "--scan", choices=["stocks", "crypto", "all"], nargs="?", const="all",
        help="Run scanner and exit: stocks, crypto, or all (default: all)",
    )
    parser.add_argument(
        "--simulate", action="store_true",
        help="Simulate trades without placing orders",
    )

    args = parser.parse_args()

    # Override broker if specified via CLI
    if args.broker:
        import config
        config.BROKER = args.broker

    # --- Display ---
    if args.display == "account":
        _show_account()
        return
    if args.display == "trades":
        from utils.trade_log import print_trade_history
        print_trade_history(limit=50)
        return

    # --- Scan ---
    if args.scan is not None:
        _run_scan(args.scan)
        return

    # --- Trade ---
    simulate = args.simulate

    if args.type == "all":
        _run_all(simulate)
    elif args.type == "stocks":
        _run_stocks(simulate)
    elif args.type == "crypto":
        _run_crypto(simulate)
    elif args.type == "options":
        _run_options(simulate)
    elif args.type == "futures":
        _run_futures(simulate)


def _show_account():
    import time
    from live.broker_factory import get_broker
    from utils.display import (
        display_live_account, display_positions, C, subheader, divider, timestamp,
    )

    broker = get_broker()

    # Get initial equity to track daily P&L
    initial = broker.get_account()
    start_equity = initial.equity

    print(f"\n  {C.DIM}Live account viewer — refreshes every 5 seconds. Ctrl+C to exit.{C.RESET}")

    while True:
        try:
            account = broker.get_account()
            daily_pnl = account.equity - start_equity

            # Clear screen
            print("\033[2J\033[H", end="")

            display_live_account(
                account.equity, account.cash, account.buying_power,
                len(account.positions), daily_pnl=daily_pnl,
                peak=account.equity if account.equity >= start_equity else start_equity,
            )

            # Categorize positions: options have long symbols (>10 chars)
            stock_positions = []
            crypto_positions = []
            option_positions = []

            for p in account.positions:
                if len(p.symbol) > 10:
                    option_positions.append(p)
                elif "/" in p.symbol or p.symbol.endswith("USD"):
                    crypto_positions.append(p)
                else:
                    stock_positions.append(p)

            if stock_positions:
                print(subheader("Stock Positions"))
                display_positions(stock_positions)
            if crypto_positions:
                print(subheader("Crypto Positions"))
                display_positions(crypto_positions)
            if option_positions:
                print(subheader("Options Positions"))
                display_positions(option_positions)
            if not stock_positions and not crypto_positions and not option_positions:
                print(f"  {C.DIM}No open positions{C.RESET}")

            print(f"\n  {C.DIM}Last updated: {timestamp()} │ Refreshing every 5s │ Ctrl+C to exit{C.RESET}")

            time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}Exiting account viewer.{C.RESET}\n")
            break
        except Exception as e:
            print(f"\n  {C.RED}Error: {e}{C.RESET}")
            time.sleep(5)


def _run_scan(target: str):
    from utils.display import C

    if target in ("stocks", "all"):
        print(f"\n  {C.BOLD}Scanning stocks...{C.RESET}")
        _scan_stocks()

    if target in ("crypto", "all"):
        print(f"\n  {C.BOLD}Scanning crypto...{C.RESET}")
        _scan_crypto()


def _scan_stocks():
    from config import UNIVERSE_SOURCE, SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME
    from utils.universe import get_universe
    from utils.screener import screen, ScreenCriteria
    from utils.scanner import run_full_scan
    from utils.display import display_hot_stocks

    universe_df = get_universe(UNIVERSE_SOURCE)
    criteria = ScreenCriteria(min_price=SCREEN_MIN_PRICE, min_avg_volume=SCREEN_MIN_AVG_VOLUME)
    symbols = screen(universe_df, criteria, verbose=False)

    hot_stocks = run_full_scan(symbols, include_social=True, include_insider=True)
    display_hot_stocks(hot_stocks, top_n=20)


def _scan_crypto():
    from live.crypto_trader import CryptoTrader
    from utils.display import subheader, C, pct_color, score_color

    trader = CryptoTrader(dry_run=True)

    print(subheader("Crypto Prices"))
    prices = trader._get_crypto_prices()

    print(f"  {C.BOLD}{'Symbol':<12} {'Price':>10} {'1h':>7} {'24h':>7} {'7d':>7} {'Vol':>5}{C.RESET}")
    print(f"  {C.GRAY}{'─' * 55}{C.RESET}")
    for sym in sorted(prices.keys(), key=lambda s: -prices[s]["price"]):
        d = prices[sym]
        print(f"  {C.WHITE}{C.BOLD}{sym:<12}{C.RESET} ${d['price']:>9,.2f} "
              f"{pct_color(d['mom_1h'], '+5.1%')} "
              f"{pct_color(d['mom_24h'], '+5.1%')} "
              f"{pct_color(d['mom_7d'], '+5.1%')} "
              f"{C.CYAN}{d['vol_ratio']:>4.1f}x{C.RESET}")

    print(subheader("Signals"))
    signals = trader._generate_signals()
    buys = [s for s in signals if s.action == "buy"]
    print(f"  {len(buys)}/{len(signals)} coins with buy signals\n")
    for s in signals[:15]:
        tag = f"{C.GREEN}{C.BOLD}BUY{C.RESET}" if s.action == "buy" else f"{C.DIM}---{C.RESET}"
        print(f"  {score_color(s.score)} {C.BOLD}{s.symbol:<10}{C.RESET} "
              f"1h={pct_color(s.momentum_1h, '+5.1%')} "
              f"24h={pct_color(s.momentum_24h, '+5.1%')} "
              f"7d={pct_color(s.momentum_7d, '+5.1%')} "
              f"{tag}")

    print(subheader("Reddit Buzz"))
    trader._scan_social()
    print()


def _run_all(simulate: bool):
    from live.day_trader import DayTrader
    from live.crypto_trader import CryptoTrader
    from live.options_trader import OptionsTrader
    from live.futures_trader import FuturesTrader
    from live.broker_factory import get_broker
    from config import BROKER
    from utils.display import C
    import time

    label = f"{C.YELLOW}SIMULATE{C.RESET}" if simulate else f"{C.GREEN}PAPER{C.RESET}"
    broker_label = f"{C.MAGENTA}{C.BOLD}{BROKER.upper()}{C.RESET}"
    print(f"\n  {C.BOLD}{C.CYAN}Starting ALL TRADERS{C.RESET} [{label}] broker={broker_label}\n")

    broker = get_broker()

    # Crypto always runs in background (24/7)
    crypto = CryptoTrader(dry_run=simulate)
    crypto_thread = threading.Thread(target=crypto.start, name="crypto", daemon=True)
    crypto_thread.start()

    # Options runs in background during market hours
    options = OptionsTrader(dry_run=simulate)
    options_thread = threading.Thread(target=options.start, name="options", daemon=True)
    options_thread.start()

    # Futures runs in background (nearly 24h on IB)
    if BROKER == "ib":
        futures = FuturesTrader(dry_run=simulate)
        futures_thread = threading.Thread(target=futures.start, name="futures", daemon=True)
        futures_thread.start()

    # Stocks in main thread
    stocks = DayTrader(dry_run=simulate)
    while True:
        try:
            if broker.is_market_open():
                print(f"\n  {C.GREEN}Market is open — starting stock trader{C.RESET}\n")
                stocks.start()
            else:
                print(f"\n  {C.DIM}Stock market closed — other traders running. "
                      f"Checking again in 5 min...{C.RESET}")
                time.sleep(300)
        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}Shutting down...{C.RESET}")
            break


def _run_stocks(simulate: bool):
    from live.day_trader import DayTrader
    from utils.display import C

    label = f"{C.YELLOW}SIMULATE{C.RESET}" if simulate else f"{C.GREEN}PAPER{C.RESET}"
    print(f"\n  {C.BOLD}{C.CYAN}Starting STOCKS{C.RESET} [{label}]\n")

    trader = DayTrader(dry_run=simulate)
    trader.start()


def _run_crypto(simulate: bool):
    from live.crypto_trader import CryptoTrader
    from utils.display import C

    label = f"{C.YELLOW}SIMULATE{C.RESET}" if simulate else f"{C.GREEN}PAPER{C.RESET}"
    print(f"\n  {C.BOLD}{C.CYAN}Starting CRYPTO 24/7{C.RESET} [{label}]\n")

    trader = CryptoTrader(dry_run=simulate)
    trader.start()


def _run_options(simulate: bool):
    from live.options_trader import OptionsTrader
    from utils.display import C

    label = f"{C.YELLOW}SIMULATE{C.RESET}" if simulate else f"{C.GREEN}PAPER{C.RESET}"
    print(f"\n  {C.BOLD}{C.CYAN}Starting OPTIONS{C.RESET} [{label}]\n")

    trader = OptionsTrader(dry_run=simulate)
    trader.start()


def _run_futures(simulate: bool):
    from live.futures_trader import FuturesTrader
    from utils.display import C

    label = f"{C.YELLOW}SIMULATE{C.RESET}" if simulate else f"{C.GREEN}PAPER{C.RESET}"
    print(f"\n  {C.BOLD}{C.CYAN}Starting FUTURES{C.RESET} [{label}]\n")

    trader = FuturesTrader(dry_run=simulate)
    trader.start()


if __name__ == "__main__":
    main()
