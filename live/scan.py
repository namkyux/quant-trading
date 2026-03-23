"""
Hot Stock Scanner — Find stocks before they move.

Usage:
  # Quick scan (volume + momentum only, fastest)
  python live/scan.py

  # Full scan (includes Reddit + insider filings)
  python live/scan.py --full

  # Include short squeeze candidates (slower)
  python live/scan.py --full --squeeze
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import UNIVERSE_SOURCE, SCREEN_MIN_PRICE, SCREEN_MIN_AVG_VOLUME
from utils.universe import get_universe
from utils.screener import screen, ScreenCriteria
from utils.scanner import run_full_scan, print_hot_stocks


def main():
    parser = argparse.ArgumentParser(description="Hot Stock Scanner")
    parser.add_argument("--full", action="store_true", help="Include social + insider signals")
    parser.add_argument("--squeeze", action="store_true", help="Include short squeeze scan (slow)")
    parser.add_argument("--top", type=int, default=15, help="Number of results to show")
    args = parser.parse_args()

    # Load universe
    universe_df = get_universe(UNIVERSE_SOURCE)
    criteria = ScreenCriteria(
        min_price=SCREEN_MIN_PRICE,
        min_avg_volume=SCREEN_MIN_AVG_VOLUME,
    )
    symbols = screen(universe_df, criteria, verbose=False)

    # Run scan
    hot_stocks = run_full_scan(
        symbols,
        include_social=args.full,
        include_insider=args.full,
        include_short_squeeze=args.squeeze,
    )

    # Print results
    print_hot_stocks(hot_stocks, top_n=args.top)

    # Summary
    if hot_stocks:
        top = hot_stocks[0]
        print(f"  Hottest stock: {top.symbol} (heat={top.heat_score:.1f})")
        print(f"  Signals: {' | '.join(top.signals)}")
        print()


if __name__ == "__main__":
    main()
