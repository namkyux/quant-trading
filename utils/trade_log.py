"""
Trade Logger — Persistent log of every trade in CSV + pretty terminal format.

Logs to: live/logs/trades.csv
Each row = one trade (buy or sell) with timestamp, symbol, side, amount, score, reason, etc.
"""

import os
import csv
from datetime import datetime
from dataclasses import dataclass

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs")
TRADE_LOG_PATH = os.path.join(LOG_DIR, "trades.csv")

FIELDS = [
    "timestamp", "type", "symbol", "side", "amount", "price", "qty",
    "score", "reason", "pnl", "pnl_pct", "status",
]


def _ensure_log():
    """Create the CSV file with headers if it doesn't exist."""
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(TRADE_LOG_PATH):
        with open(TRADE_LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def log_trade(
    symbol: str,
    side: str,
    amount: float,
    asset_type: str = "stock",
    price: float = 0.0,
    qty: float = 0.0,
    score: float = 0.0,
    reason: str = "",
    pnl: float = 0.0,
    pnl_pct: float = 0.0,
    status: str = "executed",
):
    """Log a trade to CSV."""
    _ensure_log()

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": asset_type,
        "symbol": symbol,
        "side": side,
        "amount": f"{abs(amount):.2f}",
        "price": f"{price:.2f}" if price else "",
        "qty": f"{qty:.4f}" if qty else "",
        "score": f"{score:.2f}" if score else "",
        "reason": reason,
        "pnl": f"{pnl:.2f}" if pnl else "",
        "pnl_pct": f"{pnl_pct:.2%}" if pnl_pct else "",
        "status": status,
    }

    with open(TRADE_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)


def get_trade_history(limit: int = 50) -> list[dict]:
    """Read recent trades from the log."""
    _ensure_log()

    trades = []
    with open(TRADE_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    return trades[-limit:]


def print_trade_history(limit: int = 30):
    """Pretty print trade history."""
    from utils.display import C, header, pnl_color, pct_color, divider

    trades = get_trade_history(limit)

    if not trades:
        print(f"\n  {C.DIM}No trades yet.{C.RESET}\n")
        return

    print(header("TRADE HISTORY", color=C.CYAN))
    print(f"  {C.BOLD}{'Time':<20} {'Type':<7} {'Side':<5} {'Symbol':<10} "
          f"{'Amount':>10} {'Score':>6} {'P&L':>10} {'Reason'}{C.RESET}")
    print(f"  {C.GRAY}{'─' * 85}{C.RESET}")

    for t in trades:
        # Color the side
        if t["side"] == "buy":
            side_str = f"{C.GREEN}{C.BOLD}BUY {C.RESET}"
        else:
            side_str = f"{C.RED}{C.BOLD}SELL{C.RESET}"

        # Color the type
        if t["type"] == "crypto":
            type_str = f"{C.MAGENTA}{t['type']:<7}{C.RESET}"
        else:
            type_str = f"{C.BLUE}{t['type']:<7}{C.RESET}"

        # Color P&L
        pnl_str = ""
        if t.get("pnl") and t["pnl"] != "0.00":
            pnl_val = float(t["pnl"])
            pnl_str = pnl_color(pnl_val, "+9,.2f")

        # Score
        score_str = ""
        if t.get("score") and t["score"] != "0.00":
            score_str = f"{C.YELLOW}{t['score']:>6}{C.RESET}"

        # Amount
        amt = float(t.get("amount", 0))

        # Reason
        reason = t.get("reason", "")
        if "stop_loss" in reason:
            reason_str = f"{C.RED}{reason}{C.RESET}"
        elif "take_profit" in reason:
            reason_str = f"{C.GREEN}{reason}{C.RESET}"
        else:
            reason_str = f"{C.DIM}{reason}{C.RESET}"

        print(f"  {C.DIM}{t['timestamp']:<20}{C.RESET} {type_str} {side_str} "
              f"{C.WHITE}{C.BOLD}{t['symbol']:<10}{C.RESET} "
              f"${amt:>9,.2f} {score_str} {pnl_str:>10} {reason_str}")

    print(f"  {C.GRAY}{'─' * 85}{C.RESET}")

    # Summary
    total_trades = len(trades)
    buys = sum(1 for t in trades if t["side"] == "buy")
    sells = sum(1 for t in trades if t["side"] == "sell")
    total_pnl = sum(float(t.get("pnl", 0) or 0) for t in trades if t["side"] == "sell")

    print(f"  {C.DIM}Total: {total_trades} trades ({buys} buys, {sells} sells) │ "
          f"Realized P&L: {pnl_color(total_pnl, '+,.2f')}{C.RESET}")
    print()
