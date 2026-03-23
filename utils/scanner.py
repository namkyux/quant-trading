"""
Hot Stock Scanner — Detect stocks before they move.

Signals:
1. Volume anomaly: unusual volume vs 20-day average
2. Price acceleration: sudden momentum shift
3. Insider buying: SEC Form 4 filings (via SEC EDGAR RSS)
4. Social buzz: Reddit mentions trending up
5. Short squeeze setup: high short interest + rising price
6. Earnings estimate revisions: analyst upgrades

Each signal returns a score. Combined score = "heat" level.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import re
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("scanner")


@dataclass
class HotStock:
    symbol: str
    name: str
    heat_score: float           # combined score (higher = hotter)
    price: float
    change_1d: float            # 1-day return
    change_5d: float            # 5-day return
    volume_ratio: float         # today's vol / 20d avg vol
    signals: list[str]          # which signals fired
    details: dict = field(default_factory=dict)


# ============================================================
# Signal 1: Volume Anomaly Detection
# ============================================================

def scan_volume_anomalies(
    symbols: list[str],
    min_ratio: float = 2.0,
) -> dict[str, float]:
    """
    Find stocks with unusual volume (>2x their 20-day average).

    Volume precedes price — institutional buying shows up in volume
    before the price moves.
    """
    logger.info(f"Scanning {len(symbols)} stocks for volume anomalies...")

    data = yf.download(symbols, period="1mo", auto_adjust=True, progress=False)

    if isinstance(data.columns, pd.MultiIndex):
        volume = data["Volume"]
        close = data["Close"]
    else:
        volume = data[["Volume"]]
        volume.columns = symbols
        close = data[["Close"]]
        close.columns = symbols

    # Recent volume vs average
    vol_recent = volume.iloc[-3:].mean()   # last 3 days avg
    vol_avg = volume.iloc[:-3].mean()      # prior period avg

    ratio = (vol_recent / vol_avg).dropna()
    anomalies = ratio[ratio >= min_ratio].sort_values(ascending=False)

    logger.info(f"  Found {len(anomalies)} volume anomalies (>{min_ratio}x)")
    return anomalies.to_dict()


# ============================================================
# Signal 2: Price Acceleration (Momentum Shift)
# ============================================================

def scan_price_acceleration(
    symbols: list[str],
    min_accel: float = 0.5,
) -> dict[str, float]:
    """
    Find stocks where momentum is accelerating.

    Acceleration = 5-day return is much stronger than 20-day trend.
    This catches stocks that are just starting to move.
    """
    data = yf.download(symbols, period="1mo", auto_adjust=True, progress=False)

    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
    else:
        close = data[["Close"]]
        close.columns = symbols

    if len(close) < 21:
        return {}

    ret_5d = (close.iloc[-1] / close.iloc[-5] - 1).dropna()
    ret_20d = (close.iloc[-1] / close.iloc[-20] - 1).dropna()

    # Acceleration = short-term momentum stronger than long-term
    # Positive = momentum is increasing
    accel = (ret_5d - ret_20d / 4).dropna()  # normalize 20d to 5d scale
    hot = accel[accel >= min_accel].sort_values(ascending=False)

    return hot.to_dict()


# ============================================================
# Signal 3: Insider Buying (SEC EDGAR)
# ============================================================

def scan_insider_buying() -> dict[str, dict]:
    """
    Check recent SEC Form 4 filings for insider purchases.

    Uses SEC EDGAR RSS feed (free, no API key needed).
    Insiders buying = they know something we don't.
    """
    logger.info("Checking SEC insider filings...")

    url = "https://efts.sec.gov/LATEST/search-index?q=%22Purchase%22&dateRange=custom&startdt={}&enddt={}&forms=4".format(
        (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d"),
    )

    # Use EDGAR full-text search RSS
    rss_url = "https://efts.sec.gov/LATEST/search-index?q=%22open+market+purchase%22&forms=4&dateRange=custom&startdt={}&enddt={}&_format=atom".format(
        (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d"),
    )

    try:
        import feedparser
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "QuantTrading research@example.com"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            feed_data = resp.read().decode("utf-8")

        feed = feedparser.parse(feed_data)

        # Extract ticker symbols from filing titles
        ticker_pattern = re.compile(r'\(([A-Z]{1,5})\)')
        insider_buys = Counter()

        for entry in feed.entries[:100]:
            title = entry.get("title", "")
            matches = ticker_pattern.findall(title)
            for ticker in matches:
                insider_buys[ticker] += 1

        logger.info(f"  Found insider buying in {len(insider_buys)} stocks")
        return dict(insider_buys.most_common(20))

    except Exception as e:
        logger.warning(f"  Failed to fetch insider data: {e}")
        return {}


# ============================================================
# Signal 4: Reddit Social Buzz
# ============================================================

def scan_reddit_buzz(top_n: int = 20) -> dict[str, int]:
    """
    Scan Reddit for trending stock tickers.

    Checks r/wallstreetbets and r/stocks for most-mentioned tickers.
    Uses Reddit's public JSON API (no authentication needed for read).
    """
    logger.info("Scanning Reddit for social buzz...")

    subreddits = ["wallstreetbets", "stocks", "investing"]
    ticker_pattern = re.compile(r'\b([A-Z]{2,5})\b')

    # Common words that look like tickers but aren't
    blacklist = {
        "THE", "FOR", "AND", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN", "HER",
        "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "ITS", "LET", "MAY",
        "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "DID", "GET", "HIM", "HAD",
        "SAY", "SHE", "TOO", "USE", "CEO", "IPO", "ETF", "ATH", "DD", "WSB",
        "IMO", "YOLO", "HODL", "SEC", "GDP", "CPI", "FED", "NYSE", "NASDAQ",
        "USA", "USD", "EUR", "EDIT", "TLDR", "FOMO", "LMAO", "THIS", "THAT",
        "WITH", "HAVE", "FROM", "BEEN", "SOME", "WHAT", "WHEN", "YOUR", "JUST",
        "LIKE", "WILL", "THEY", "THAN", "THEM", "THEN", "ALSO", "INTO", "OVER",
        "SUCH", "TAKE", "YEAR", "VERY", "MUCH", "EACH", "MAKE", "CALL", "LONG",
        "HIGH", "KEEP", "EVEN", "NEXT", "ONLY", "COME", "MADE", "FIND", "HERE",
        "MANY", "WELL", "BACK", "LAST", "GOOD", "MOST", "SELL", "PUMP", "DUMP",
        "PUTS", "HOLD", "CASH", "GAIN", "LOSS", "BULL", "BEAR", "MOON", "RISK",
        "PLAY", "MOVE", "FREE", "WEEK", "OPEN", "HUGE", "BEST", "EVER", "STILL",
        "DOWN", "NEED", "SURE", "REAL", "MORE", "DOES", "KNOW",
    }

    all_tickers = Counter()

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
            req = urllib.request.Request(url, headers={
                "User-Agent": "QuantTrading/1.0 (research bot)"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for post in data.get("data", {}).get("children", []):
                text = post["data"].get("title", "") + " " + post["data"].get("selftext", "")
                tickers = ticker_pattern.findall(text)
                for t in tickers:
                    if t not in blacklist and len(t) >= 2:
                        all_tickers[t] += 1

        except Exception as e:
            logger.warning(f"  Failed to fetch r/{sub}: {e}")

    # Filter to likely real tickers (mentioned 2+ times)
    trending = {t: c for t, c in all_tickers.most_common(50) if c >= 2}
    logger.info(f"  Found {len(trending)} trending tickers on Reddit")
    return dict(list(trending.items())[:top_n])


# ============================================================
# Signal 5: Short Squeeze Candidates
# ============================================================

def scan_short_squeeze(symbols: list[str]) -> dict[str, dict]:
    """
    Find short squeeze candidates.

    Criteria: high short interest + price rising + volume increasing.
    Uses yfinance for short data (when available).
    """
    logger.info("Scanning for short squeeze candidates...")

    candidates = {}
    # Check in batches to avoid overwhelming yfinance
    for symbol in symbols[:100]:  # limit to top 100 by volume
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            short_pct = info.get("shortPercentOfFloat", 0) or 0
            if short_pct < 0.10:  # need at least 10% short interest
                continue

            # Check if price is rising (potential squeeze)
            hist = ticker.history(period="5d")
            if len(hist) < 2:
                continue

            price_change = (hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1

            if price_change > 0:  # price is rising with high short interest
                candidates[symbol] = {
                    "short_pct": short_pct,
                    "price_change_5d": price_change,
                    "score": short_pct * (1 + price_change) * 10,
                }

        except Exception:
            continue

    logger.info(f"  Found {len(candidates)} short squeeze candidates")
    return candidates


# ============================================================
# Combined Hot Stock Scanner
# ============================================================

def run_full_scan(
    symbols: list[str],
    include_social: bool = True,
    include_insider: bool = True,
    include_short_squeeze: bool = False,  # slow, off by default
) -> list[HotStock]:
    """
    Run all scanners and combine into a ranked list of hot stocks.

    Returns a list of HotStock objects sorted by heat_score.
    """
    logger.info("=" * 60)
    logger.info("FULL HOT STOCK SCAN")
    logger.info(f"Universe: {len(symbols)} stocks")
    logger.info("=" * 60)

    # Collect all signals
    volume_signals = scan_volume_anomalies(symbols)
    accel_signals = scan_price_acceleration(symbols)

    insider_signals = {}
    if include_insider:
        insider_signals = scan_insider_buying()

    social_signals = {}
    if include_social:
        social_signals = scan_reddit_buzz()

    squeeze_signals = {}
    if include_short_squeeze:
        squeeze_signals = scan_short_squeeze(symbols)

    # Get current prices and returns for all flagged stocks
    all_flagged = set()
    all_flagged.update(volume_signals.keys())
    all_flagged.update(accel_signals.keys())
    all_flagged.update(insider_signals.keys())
    all_flagged.update(social_signals.keys())
    all_flagged.update(squeeze_signals.keys())

    if not all_flagged:
        logger.info("No hot stocks found.")
        return []

    # Fetch price data for flagged stocks
    flagged_list = [s for s in all_flagged if s in symbols]
    if not flagged_list:
        # Social/insider might flag stocks not in our universe — try them anyway
        flagged_list = list(all_flagged)[:50]

    price_data = yf.download(flagged_list, period="1mo", auto_adjust=True, progress=False)
    if isinstance(price_data.columns, pd.MultiIndex):
        close = price_data["Close"]
    else:
        close = price_data[["Close"]]
        close.columns = flagged_list

    # Build hot stock list
    hot_stocks = []

    for symbol in all_flagged:
        signals = []
        heat = 0.0
        details = {}

        # Volume signal
        if symbol in volume_signals:
            vol_ratio = volume_signals[symbol]
            heat += min(vol_ratio / 2, 3.0)  # cap at 3 points
            signals.append(f"VOL {vol_ratio:.1f}x")
            details["volume_ratio"] = vol_ratio
        else:
            details["volume_ratio"] = 1.0

        # Price acceleration
        if symbol in accel_signals:
            accel = accel_signals[symbol]
            heat += min(accel * 2, 3.0)
            signals.append(f"ACCEL +{accel:.0%}")

        # Insider buying
        if symbol in insider_signals:
            count = insider_signals[symbol]
            heat += min(count, 3.0)
            signals.append(f"INSIDER x{count}")
            details["insider_filings"] = count

        # Social buzz
        if symbol in social_signals:
            mentions = social_signals[symbol]
            heat += min(mentions / 3, 2.0)  # cap at 2 points
            signals.append(f"REDDIT x{mentions}")
            details["reddit_mentions"] = mentions

        # Short squeeze
        if symbol in squeeze_signals:
            sq = squeeze_signals[symbol]
            heat += sq["score"]
            signals.append(f"SQUEEZE {sq['short_pct']:.0%} short")
            details["short_pct"] = sq["short_pct"]

        # Get price info
        price = 0.0
        change_1d = 0.0
        change_5d = 0.0
        if symbol in close.columns:
            col = close[symbol].dropna()
            if len(col) >= 2:
                price = col.iloc[-1]
                change_1d = col.iloc[-1] / col.iloc[-2] - 1 if len(col) >= 2 else 0
                change_5d = col.iloc[-1] / col.iloc[-5] - 1 if len(col) >= 5 else 0

        # Get name
        name = symbol
        try:
            name = yf.Ticker(symbol).info.get("shortName", symbol)
        except Exception:
            pass

        hot_stocks.append(HotStock(
            symbol=symbol,
            name=name,
            heat_score=heat,
            price=price,
            change_1d=change_1d,
            change_5d=change_5d,
            volume_ratio=details.get("volume_ratio", 1.0),
            signals=signals,
            details=details,
        ))

    # Sort by heat score
    hot_stocks.sort(key=lambda h: -h.heat_score)
    return hot_stocks


def print_hot_stocks(hot_stocks: list[HotStock], top_n: int = 15):
    """Pretty print the hot stocks list."""
    print(f"\n{'='*85}")
    print(f"  HOT STOCKS — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*85}")
    print(f"  {'#':<3} {'Symbol':<7} {'Price':>8} {'1D':>7} {'5D':>7} {'Vol':>5} {'Heat':>5}  Signals")
    print(f"  {'-'*78}")

    for i, h in enumerate(hot_stocks[:top_n], 1):
        signals_str = " | ".join(h.signals)
        print(
            f"  {i:<3} {h.symbol:<7} "
            f"${h.price:>7.2f} "
            f"{h.change_1d:>+6.1%} "
            f"{h.change_5d:>+6.1%} "
            f"{h.volume_ratio:>4.1f}x "
            f"{h.heat_score:>5.1f}  "
            f"{signals_str}"
        )

    print(f"{'='*85}\n")
