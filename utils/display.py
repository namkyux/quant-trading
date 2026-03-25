"""Pretty terminal output with colors and formatting."""

from datetime import datetime


# --- ANSI Color Codes ---
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Backgrounds
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"


# --- Symbols ---
UP = f"{C.GREEN}▲{C.RESET}"
DOWN = f"{C.RED}▼{C.RESET}"
BULLET = f"{C.CYAN}●{C.RESET}"
FIRE = f"{C.RED}{C.BOLD}■{C.RESET}"
CHECK = f"{C.GREEN}✓{C.RESET}"
CROSS = f"{C.RED}✗{C.RESET}"
WARN = f"{C.YELLOW}⚠{C.RESET}"
SKULL = f"{C.RED}{C.BOLD}☠{C.RESET}"
MONEY = f"{C.GREEN}${C.RESET}"
CLOCK = f"{C.CYAN}◷{C.RESET}"
CHART = f"{C.BLUE}▁▂▃▅▆▇{C.RESET}"


def pnl_color(value: float, fmt: str = "+,.2f") -> str:
    """Color a P&L value green/red."""
    if value > 0:
        return f"{C.GREEN}{value:{fmt}}{C.RESET}"
    elif value < 0:
        return f"{C.RED}{value:{fmt}}{C.RESET}"
    return f"{C.GRAY}{value:{fmt}}{C.RESET}"


def pct_color(value: float, fmt: str = "+.2%") -> str:
    """Color a percentage green/red."""
    if value > 0:
        return f"{C.GREEN}{value:{fmt}}{C.RESET}"
    elif value < 0:
        return f"{C.RED}{value:{fmt}}{C.RESET}"
    return f"{C.GRAY}{value:{fmt}}{C.RESET}"


def score_color(score: float) -> str:
    """Color a score by intensity."""
    if score >= 1.5:
        return f"{C.RED}{C.BOLD}{score:.2f}{C.RESET}"
    elif score >= 1.0:
        return f"{C.YELLOW}{score:.2f}{C.RESET}"
    elif score >= 0.5:
        return f"{C.GREEN}{score:.2f}{C.RESET}"
    return f"{C.GRAY}{score:.2f}{C.RESET}"


def heat_bar(score: float, max_score: float = 5.0, width: int = 10) -> str:
    """Visual heat bar."""
    filled = int(min(score / max_score, 1.0) * width)
    if score >= 2.0:
        color = C.RED
    elif score >= 1.0:
        color = C.YELLOW
    else:
        color = C.GREEN
    bar = f"{color}{'█' * filled}{C.GRAY}{'░' * (width - filled)}{C.RESET}"
    return bar


def divider(char: str = "─", width: int = 80, color: str = C.GRAY) -> str:
    return f"{color}{char * width}{C.RESET}"


def header(title: str, width: int = 80, color: str = C.CYAN) -> str:
    """Fancy header box."""
    top = f"{color}╔{'═' * (width - 2)}╗{C.RESET}"
    mid = f"{color}║{C.RESET} {C.BOLD}{C.WHITE}{title:^{width - 4}}{C.RESET} {color}║{C.RESET}"
    bot = f"{color}╚{'═' * (width - 2)}╝{C.RESET}"
    return f"\n{top}\n{mid}\n{bot}"


def subheader(title: str, width: int = 80, color: str = C.BLUE) -> str:
    """Lighter section header."""
    line = f"{color}{'─' * 3} {C.BOLD}{title}{C.RESET} {color}{'─' * (width - len(title) - 5)}{C.RESET}"
    return f"\n{line}"


def timestamp() -> str:
    """Colored timestamp."""
    now = datetime.now()
    return f"{C.GRAY}{now:%H:%M:%S}{C.RESET}"


# --- Pre-built displays ---

def display_banner():
    """Show startup banner."""
    print(f"""
{C.CYAN}{C.BOLD}
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║     ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗      ║
    ║    ██╔═══██╗██║   ██║██╔══██╗████╗  ██║      ║
    ║    ██║   ██║██║   ██║███████║██╔██╗ ██║      ║
    ║    ██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║      ║
    ║    ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║      ║
    ║     ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝      ║
    ║          T R A D I N G   S Y S T E M          ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
{C.RESET}""")


def display_account(equity, cash, buying_power, positions, daily_pnl=None, peak=None):
    """Pretty account status display."""
    print(header("ACCOUNT STATUS"))
    print(f"  {MONEY} Equity       {C.BOLD}{C.WHITE}${equity:>12,.2f}{C.RESET}")
    print(f"  {BULLET} Cash         ${cash:>12,.2f}")
    print(f"  {BULLET} Buying Power ${buying_power:>12,.2f}")
    if daily_pnl is not None:
        arrow = UP if daily_pnl >= 0 else DOWN
        print(f"  {arrow} Day P&L      {pnl_color(daily_pnl, '+12,.2f')}  ({pct_color(daily_pnl / equity if equity else 0)})")
    if peak:
        print(f"  {WARN} Kill switch  ${peak * 0.80:>12,.2f} {C.DIM}(20% from ${peak:,.0f} peak){C.RESET}")
    print(f"  {BULLET} Positions    {C.BOLD}{positions}{C.RESET}")
    print(divider())


def _load_trade_reasons() -> dict[str, str]:
    """Load the most recent buy reason for each symbol from the trade log."""
    import os
    import csv
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "live", "logs", "trades.csv")
    reasons = {}
    try:
        with open(log_path, "r") as f:
            for row in csv.DictReader(f):
                if row.get("side") == "buy" and row.get("symbol"):
                    reasons[row["symbol"]] = row.get("reason", "")
    except (FileNotFoundError, KeyError):
        pass
    return reasons


def _strategy_tag(reason: str) -> str:
    """Color-code a strategy reason into a short tag."""
    r = reason.lower()
    if "momentum" in r and "hot" in r:
        return f"{C.RED}{C.BOLD}momentum+HOT{C.RESET}"
    elif "momentum" in r:
        return f"{C.GREEN}momentum{C.RESET}"
    elif "covered_call" in r:
        return f"{C.CYAN}covered call{C.RESET}"
    elif "protective_put" in r:
        return f"{C.YELLOW}protective put{C.RESET}"
    elif "earnings_straddle" in r:
        return f"{C.MAGENTA}earnings straddle{C.RESET}"
    elif "trend_long" in r:
        return f"{C.GREEN}trend long{C.RESET}"
    elif "trend_short" in r:
        return f"{C.RED}trend short{C.RESET}"
    elif "mean_revert" in r:
        return f"{C.YELLOW}mean revert{C.RESET}"
    elif "stop_loss" in r:
        return f"{C.RED}stop loss{C.RESET}"
    elif "take_profit" in r:
        return f"{C.GREEN}take profit{C.RESET}"
    elif reason:
        return f"{C.DIM}{reason}{C.RESET}"
    return ""


def display_positions(positions):
    """Pretty position table with strategy info from trade log."""
    if not positions:
        print(f"  {C.DIM}No open positions{C.RESET}")
        return

    # Load strategy reasons from trade log
    reasons = _load_trade_reasons()

    # Dynamic symbol width — options symbols can be 18+ chars
    W_SYM = max(10, max(len(p.symbol) for p in positions) + 2)
    W_QTY = 10
    W_VAL = 12
    W_AVG = 12
    W_PNL = 12
    W_PCT = 8
    W_TOTAL = W_SYM + W_QTY + W_VAL + W_AVG + W_PNL + W_PCT + 6

    print(f"  {C.BOLD}{'Symbol':<{W_SYM}}{'Qty':>{W_QTY}}{'Value':>{W_VAL}}{'Avg':>{W_AVG}}{'P&L':>{W_PNL}}{'P&L %':>{W_PCT}}  Strategy{C.RESET}")
    print(f"  {C.GRAY}{'─' * (W_TOTAL + 20)}{C.RESET}")

    total_pl = 0
    for p in sorted(positions, key=lambda x: -x.market_value):
        # Format qty
        if abs(p.qty) >= 1_000_000:
            qty_raw = f"{p.qty / 1_000_000:.2f}M"
        elif abs(p.qty) >= 1_000:
            qty_raw = f"{p.qty / 1_000:.2f}K"
        elif abs(p.qty) >= 1:
            qty_raw = f"{p.qty:.2f}"
        else:
            qty_raw = f"{p.qty:.6f}"
        qty_str = f"{qty_raw:>{W_QTY}}"

        val_str = f"${p.market_value:>{W_VAL - 1},.2f}"
        avg_str = f"${p.avg_entry_price:>{W_AVG - 1},.2f}"

        # Format P&L with sign, pad to fixed width, then colorize
        pl_raw = f"{p.unrealized_pl:>+{W_PNL - 1},.2f}"
        pct_raw = f"{p.unrealized_pl_pct:>+6.1%}"

        if p.unrealized_pl >= 0:
            pl_str = f"{C.GREEN}{pl_raw}{C.RESET}"
            pct_str = f"{C.GREEN}{pct_raw}{C.RESET}"
        else:
            pl_str = f"{C.RED}{pl_raw}{C.RESET}"
            pct_str = f"{C.RED}{pct_raw}{C.RESET}"

        # Strategy tag from trade log
        reason = reasons.get(p.symbol, "")
        tag = _strategy_tag(reason)

        bar = heat_bar(abs(p.unrealized_pl_pct) * 10, max_score=5.0, width=8)
        print(f"  {C.BOLD}{C.WHITE}{p.symbol:<{W_SYM}}{C.RESET}{qty_str} {val_str} {avg_str} {pl_str} {pct_str}  {bar} {tag}")
        total_pl += p.unrealized_pl

    print(f"  {C.GRAY}{'─' * (W_TOTAL + 20)}{C.RESET}")
    total_raw = f"{total_pl:>+{W_PNL - 1},.2f}"
    total_color = C.GREEN if total_pl >= 0 else C.RED
    pad = W_SYM + W_QTY + W_VAL + W_AVG + 3
    print(f"  {'Total P&L':<{W_SYM}}{'':{pad - W_SYM}}{total_color}{total_raw}{C.RESET}")


def display_scan_header(scan_num, next_signal, next_hot):
    """Pretty scan cycle header."""
    W = 80
    now = datetime.now()
    time_str = f"{now:%H:%M:%S}"

    # Build visible content (no ANSI) to calculate padding
    visible = f" * Scan #{scan_num}  {time_str}    signals: {next_signal}m | hot scan: {next_hot}m"
    pad = max(0, W - 2 - len(visible))  # -2 for the │ borders

    print(f"\n{C.BLUE}┌{'─' * (W - 2)}┐{C.RESET}")
    print(f"{C.BLUE}│{C.RESET} {CLOCK} {C.BOLD}Scan #{scan_num}{C.RESET}  "
          f"{C.GRAY}{time_str}{C.RESET}    "
          f"{C.DIM}signals: {next_signal}m | hot scan: {next_hot}m{C.RESET}"
          f"{' ' * pad}{C.BLUE}│{C.RESET}")
    print(f"{C.BLUE}└{'─' * (W - 2)}┘{C.RESET}")


def display_trade(side, symbol, amount, score=None, reason=""):
    """Pretty trade execution line."""
    if side == "buy":
        icon = f"{C.GREEN}{C.BOLD}BUY {C.RESET}"
    else:
        icon = f"{C.RED}{C.BOLD}SELL{C.RESET}"
    # 20 chars fits all OCC option symbols (e.g. VLO260410C00260000)
    w = 20 if len(symbol) > 8 else 8
    score_str = f"  {score_color(score)}" if score else ""
    reason_str = f"  {C.DIM}{reason}{C.RESET}" if reason else ""
    print(f"  {icon} {C.WHITE}{C.BOLD}{symbol:<{w}}{C.RESET} ${abs(amount):>10,.2f}{score_str}{reason_str}")


def display_signal(symbol, score, mom_5d, mom_21d, vol_ratio, is_breakout, is_hot):
    """Pretty signal line."""
    tags = []
    if is_breakout:
        tags.append(f"{C.YELLOW}BREAKOUT{C.RESET}")
    if is_hot:
        tags.append(f"{C.RED}{C.BOLD}HOT{C.RESET}")
    tags_str = " ".join(tags)
    print(f"  {score_color(score)} {C.BOLD}{C.WHITE}{symbol:<6}{C.RESET} "
          f"5d={pct_color(mom_5d, '+5.1%')} "
          f"21d={pct_color(mom_21d, '+5.1%')} "
          f"vol={C.CYAN}{vol_ratio:.1f}x{C.RESET} "
          f"{tags_str}")


def display_hot_stocks(hot_stocks, top_n=15):
    """Pretty hot stocks table."""
    print(header("HOT STOCKS", color=C.RED))

    # Header
    print(f"  {C.BOLD}{'#':<4}{'Symbol':<8}{'Price':>10}{'1D':>8}{'5D':>8}"
          f"{'Vol':>6}{'Heat':>6}  {'Bar':<12}Signals{C.RESET}")
    print(f"  {C.GRAY}{'─' * 80}{C.RESET}")

    for i, h in enumerate(hot_stocks[:top_n], 1):
        bar = heat_bar(h.heat_score)
        signals_str = f"{C.DIM} | {C.RESET}".join(
            [_color_signal(s) for s in h.signals]
        )

        # Format raw values first, then colorize
        price_str = f"${h.price:>8,.2f}" if h.price > 0 else f"{'—':>9}"
        chg1d_raw = f"{h.change_1d:>+6.1%}"
        chg5d_raw = f"{h.change_5d:>+6.1%}"
        vol_raw = f"{h.volume_ratio:>4.1f}x"
        heat_raw = f"{h.heat_score:>5.2f}"

        # Colorize
        chg1d = f"{C.GREEN}{chg1d_raw}{C.RESET}" if h.change_1d >= 0 else f"{C.RED}{chg1d_raw}{C.RESET}"
        chg5d = f"{C.GREEN}{chg5d_raw}{C.RESET}" if h.change_5d >= 0 else f"{C.RED}{chg5d_raw}{C.RESET}"
        vol = f"{C.CYAN}{vol_raw}{C.RESET}"
        heat = score_color(h.heat_score)

        print(
            f"  {C.BOLD}{i:<4}{C.RESET}"
            f"{C.WHITE}{C.BOLD}{h.symbol:<8}{C.RESET}"
            f"{price_str}  "
            f"{chg1d}  "
            f"{chg5d}  "
            f"{vol} "
            f"{heat}  "
            f"{bar} "
            f"{signals_str}"
        )

    print(divider())


def _color_signal(signal_str: str) -> str:
    """Color individual signal tags."""
    if "VOL" in signal_str:
        return f"{C.CYAN}{signal_str}{C.RESET}"
    elif "REDDIT" in signal_str:
        return f"{C.MAGENTA}{signal_str}{C.RESET}"
    elif "INSIDER" in signal_str:
        return f"{C.YELLOW}{signal_str}{C.RESET}"
    elif "SQUEEZE" in signal_str:
        return f"{C.RED}{C.BOLD}{signal_str}{C.RESET}"
    elif "ACCEL" in signal_str:
        return f"{C.GREEN}{signal_str}{C.RESET}"
    return signal_str


def display_position_action(symbol, pnl_pct, pnl_value, action):
    """Pretty position management line."""
    if action == "stop_loss":
        print(f"  {CROSS} {C.RED}STOP LOSS{C.RESET}  {C.BOLD}{symbol:<6}{C.RESET} "
              f"at {pct_color(pnl_pct, '+.1%')} ({pnl_color(pnl_value)})")
    elif action == "take_profit":
        print(f"  {CHECK} {C.GREEN}TAKE PROFIT{C.RESET} {C.BOLD}{symbol:<6}{C.RESET} "
              f"at {pct_color(pnl_pct, '+.1%')} ({pnl_color(pnl_value)})")
    elif action == "hold":
        print(f"  {BULLET} {C.DIM}HOLD{C.RESET}       {C.BOLD}{symbol:<6}{C.RESET} "
              f"{pct_color(pnl_pct, '+.1%')} ({pnl_color(pnl_value)})")


def display_risk_status(status, killed=False):
    """Pretty risk manager status."""
    if killed:
        print(f"  {SKULL} {C.BG_RED}{C.WHITE}{C.BOLD} KILLED {C.RESET} {C.RED}{status}{C.RESET}")
    else:
        print(f"  {CHECK} {C.DIM}Risk:{C.RESET} {status}")


def display_daily_summary(start_equity, end_equity, num_scans, num_positions):
    """Pretty end-of-day summary."""
    pnl = end_equity - start_equity
    pct = pnl / start_equity if start_equity > 0 else 0

    print(header("END OF DAY", color=C.YELLOW))
    print(f"  Start    ${start_equity:>12,.2f}")
    print(f"  End      ${end_equity:>12,.2f}")
    print(f"  P&L      {pnl_color(pnl, '+12,.2f')}  ({pct_color(pct)})")
    print(f"  Scans    {num_scans}")
    print(f"  Open     {num_positions} positions")
    print(divider())


def display_market_closed():
    """Pretty market closed message."""
    print(f"  {CLOCK} {C.DIM}Market closed. Waiting...{C.RESET}")


def display_no_signals():
    """Pretty no signals message."""
    print(f"  {C.DIM}No buy signals found.{C.RESET}")


_BIG_FONT = {
    "0": [
        " ██████╗ ",
        "██╔═══██╗",
        "██║   ██║",
        "██║   ██║",
        "╚██████╔╝",
        " ╚═════╝ ",
    ],
    "1": [
        " ██╗",
        "███║",
        "╚██║",
        " ██║",
        " ██║",
        " ╚═╝",
    ],
    "2": [
        "██████╗ ",
        "╚════██╗",
        " █████╔╝",
        "██╔═══╝ ",
        "███████╗",
        "╚══════╝",
    ],
    "3": [
        "██████╗ ",
        "╚════██╗",
        " █████╔╝",
        " ╚═══██╗",
        "██████╔╝",
        "╚═════╝ ",
    ],
    "4": [
        "██╗  ██╗",
        "██║  ██║",
        "███████║",
        "╚════██║",
        "     ██║",
        "     ╚═╝",
    ],
    "5": [
        "███████╗",
        "██╔════╝",
        "███████╗",
        "╚════██║",
        "███████║",
        "╚══════╝",
    ],
    "6": [
        " ██████╗",
        "██╔════╝",
        "██████╗ ",
        "██╔══██╗",
        "╚█████╔╝",
        " ╚════╝ ",
    ],
    "7": [
        "███████╗",
        "╚════██║",
        "    ██╔╝",
        "   ██╔╝ ",
        "   ██║  ",
        "   ╚═╝  ",
    ],
    "8": [
        " █████╗ ",
        "██╔══██╗",
        "╚█████╔╝",
        "██╔══██╗",
        "╚█████╔╝",
        " ╚════╝ ",
    ],
    "9": [
        " █████╗ ",
        "██╔══██╗",
        "╚██████║",
        " ╚═══██║",
        " █████╔╝",
        " ╚════╝ ",
    ],
    "$": [
        "▄▄███▄▄·  ",
        "██╔════╝  ",
        "███████╗  ",
        "╚════██║  ",
        "███████║  ",
        "╚═▀▀▀══╝  ",
    ],
    ",": [
        "   ",
        "   ",
        "   ",
        "   ",
        "▐█╗",
        "▝╹ ",
    ],
    ".": [
        "  ",
        "  ",
        "  ",
        "  ",
        "██",
        "╚═",
    ],
    " ": [
        "  ",
        "  ",
        "  ",
        "  ",
        "  ",
        "  ",
    ],
}


def big_number(text: str, color: str = C.GREEN) -> str:
    """Render text as big block characters (6 lines tall)."""
    lines = [""] * 6
    for ch in str(text):
        glyph = _BIG_FONT.get(ch, ["    ", " ?? ", "    ", "    ", "    ", "    "])
        for i in range(6):
            lines[i] += glyph[i]
    return "\n".join(f"  {color}{C.BOLD}{line}{C.RESET}" for line in lines)


def display_live_account(equity, cash, buying_power, positions, daily_pnl=None, peak=None):
    """Big equity display for live account viewer."""
    eq_color = C.GREEN if (daily_pnl is None or daily_pnl >= 0) else C.RED
    equity_str = f"${equity:,.0f}"

    print(header("PORTFOLIO", color=C.CYAN))
    print()
    print(big_number(equity_str, color=eq_color))
    print()

    # P&L line
    if daily_pnl is not None:
        pnl_pct = daily_pnl / (equity - daily_pnl) if (equity - daily_pnl) > 0 else 0
        arrow = "▲" if daily_pnl >= 0 else "▼"
        pnl_color_code = C.GREEN if daily_pnl >= 0 else C.RED
        print(f"    {pnl_color_code}{C.BOLD}{arrow} ${abs(daily_pnl):,.2f} ({pnl_pct:+.2%}) today{C.RESET}")
        print()

    # Details in a clean grid
    print(f"    {C.CYAN}┌──────────────┬─────────────────┐{C.RESET}")
    print(f"    {C.CYAN}│{C.RESET} {C.DIM}Cash{C.RESET}         {C.CYAN}│{C.RESET} ${cash:>14,.2f} {C.CYAN}│{C.RESET}")
    print(f"    {C.CYAN}│{C.RESET} {C.DIM}Buying Power{C.RESET} {C.CYAN}│{C.RESET} ${buying_power:>14,.2f} {C.CYAN}│{C.RESET}")
    print(f"    {C.CYAN}│{C.RESET} {C.DIM}Positions{C.RESET}    {C.CYAN}│{C.RESET} {positions:>15} {C.CYAN}│{C.RESET}")
    if peak and peak > 0:
        kill_at = peak * 0.80
        print(f"    {C.CYAN}├──────────────┼─────────────────┤{C.RESET}")
        print(f"    {C.CYAN}│{C.RESET} {C.DIM}Peak{C.RESET}         {C.CYAN}│{C.RESET} ${peak:>14,.2f} {C.CYAN}│{C.RESET}")
        print(f"    {C.CYAN}│{C.RESET} {C.RED}Kill Switch{C.RESET}  {C.CYAN}│{C.RESET} {C.RED}${kill_at:>14,.2f}{C.RESET} {C.CYAN}│{C.RESET}")
    print(f"    {C.CYAN}└──────────────┴─────────────────┘{C.RESET}")
    print()
