"""
Main entry point for the trading system.

Usage:
  # See what trades the system would make (no execution)
  python live/run.py --dry-run

  # Run the day trader on paper money
  python live/run.py --paper

  # Check account status
  python live/run.py --status

  # Run one rebalance cycle only
  python live/run.py --once

  # Run one cycle, dry run
  python live/run.py --once --dry-run
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Quant Trading System")
    parser.add_argument("--dry-run", action="store_true", help="Calculate trades but don't execute")
    parser.add_argument("--paper", action="store_true", help="Run day trader on paper account")
    parser.add_argument("--once", action="store_true", help="Run one rebalance cycle and exit")
    parser.add_argument("--status", action="store_true", help="Show account status")
    args = parser.parse_args()

    if args.status:
        from live.broker import AlpacaBroker
        broker = AlpacaBroker()
        account = broker.get_account()
        print(f"\n{'='*50}")
        print(f"  ACCOUNT STATUS")
        print(f"{'='*50}")
        print(f"  Equity:       ${account.equity:>12,.2f}")
        print(f"  Cash:         ${account.cash:>12,.2f}")
        print(f"  Buying Power: ${account.buying_power:>12,.2f}")
        print(f"  Positions:    {len(account.positions)}")
        if account.positions:
            print(f"\n  {'Symbol':<8} {'Qty':>8} {'Value':>12} {'P&L':>10} {'P&L %':>8}")
            print(f"  {'-'*48}")
            for p in sorted(account.positions, key=lambda x: -x.market_value):
                print(f"  {p.symbol:<8} {p.qty:>8.2f} ${p.market_value:>11,.2f} "
                      f"${p.unrealized_pl:>9,.2f} {p.unrealized_pl_pct:>7.1%}")
        print(f"{'='*50}\n")
        return

    if args.once:
        from live.trader import AutoTrader
        trader = AutoTrader(dry_run=args.dry_run)
        summary = trader.run_cycle()
        mode = "DRY RUN" if args.dry_run else "EXECUTED"
        print(f"\n{mode}: {summary.get('num_trades', 0)} trades.")
        return

    if args.paper or args.dry_run:
        from live.day_trader import DayTrader
        trader = DayTrader(dry_run=args.dry_run)
        trader.start()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
