"""Quick script to check current positions and account status."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live.broker_factory import get_broker


def main():
    broker = get_broker()
    account = broker.get_account()

    print(f"\n{'='*50}")
    print(f"  ACCOUNT STATUS")
    print(f"{'='*50}")
    print(f"  Equity:       ${account.equity:>12,.2f}")
    print(f"  Cash:         ${account.cash:>12,.2f}")
    print(f"  Buying Power: ${account.buying_power:>12,.2f}")
    print(f"  Positions:    {len(account.positions)}")

    if account.positions:
        total_pl = sum(p.unrealized_pl for p in account.positions)
        print(f"\n  {'Symbol':<8} {'Qty':>8} {'Value':>12} {'P&L':>10} {'P&L %':>8}")
        print(f"  {'-'*48}")
        for p in sorted(account.positions, key=lambda x: -x.market_value):
            print(f"  {p.symbol:<8} {p.qty:>8.2f} ${p.market_value:>11,.2f} "
                  f"${p.unrealized_pl:>9,.2f} {p.unrealized_pl_pct:>7.1%}")
        print(f"  {'-'*48}")
        print(f"  {'Total P&L':<8} {'':>8} {'':>12} ${total_pl:>9,.2f}")

    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
