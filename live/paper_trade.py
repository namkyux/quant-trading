"""
Paper Trading Entry Point

Run this to start automated paper trading.
The system will run one trading cycle immediately, then schedule
weekly rebalances on the configured day and time.

Usage:
  # Run one cycle now (dry run — no trades executed)
  python live/paper_trade.py --dry-run

  # Run one cycle now (execute on paper account)
  python live/paper_trade.py --once

  # Run on a schedule (keeps running, rebalances weekly)
  python live/paper_trade.py --schedule

Setup:
  1. Download and launch IB Gateway
  2. Log in with paper trading account
  3. Configure API settings (port 4002, enable socket clients)
"""

import sys
import os
import argparse
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from config import REBALANCE_TIME, REBALANCE_DAYS

logger = logging.getLogger("paper_trade")

DAY_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}


def should_run_today() -> bool:
    """Check if today is a scheduled rebalance day."""
    today = datetime.now().strftime("%a")[:3]
    return today in REBALANCE_DAYS


def wait_for_next_run():
    """Sleep until the next scheduled rebalance time."""
    now = datetime.now()
    hour, minute = map(int, REBALANCE_TIME.split(":"))

    # Next run time today
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if now >= target:
        # Already past today's time, schedule for tomorrow
        from datetime import timedelta
        target += timedelta(days=1)

    wait_seconds = (target - now).total_seconds()
    logger.info(f"Next run: {target.strftime('%Y-%m-%d %H:%M')} ({wait_seconds/3600:.1f} hours)")
    return wait_seconds


def main():
    parser = argparse.ArgumentParser(description="Paper Trading System")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Calculate trades but don't execute")
    group.add_argument("--once", action="store_true", help="Run one trading cycle and exit")
    group.add_argument("--schedule", action="store_true", help="Run on a weekly schedule")
    group.add_argument("--status", action="store_true", help="Show account status only")
    args = parser.parse_args()

    from live.trader import AutoTrader
    from live.broker_factory import get_broker

    if args.status:
        broker = get_broker()
        account = broker.get_account()
        print(f"\n{'='*50}")
        print(f"  PAPER TRADING ACCOUNT STATUS")
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

    if args.dry_run:
        print("\n*** DRY RUN MODE — No trades will be executed ***\n")
        trader = AutoTrader(dry_run=True)
        summary = trader.run_cycle()
        print(f"\nDry run complete. {summary.get('num_trades', 0)} trades would have been executed.")
        return

    if args.once:
        print("\n*** EXECUTING ONE TRADING CYCLE ***\n")
        trader = AutoTrader(dry_run=False)
        summary = trader.run_cycle()
        print(f"\nCycle complete. {len(summary.get('trades', []))} trades executed.")
        return

    if args.schedule:
        print(f"\n*** SCHEDULED MODE ***")
        print(f"  Rebalance days: {REBALANCE_DAYS}")
        print(f"  Rebalance time: {REBALANCE_TIME} ET")
        print(f"  Press Ctrl+C to stop\n")

        trader = AutoTrader(dry_run=False)

        while True:
            try:
                wait_seconds = wait_for_next_run()
                time.sleep(wait_seconds)

                if should_run_today():
                    if trader.broker.is_market_open():
                        logger.info("Market is open — running trading cycle")
                        summary = trader.run_cycle()
                        logger.info(f"Cycle complete: {len(summary.get('trades', []))} trades")
                    else:
                        logger.info("Market is closed — skipping")
                else:
                    logger.info(f"Not a rebalance day — skipping")

            except KeyboardInterrupt:
                print("\nShutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                time.sleep(60)  # wait a minute before retrying


if __name__ == "__main__":
    main()
