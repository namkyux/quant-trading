import os
from dotenv import load_dotenv

load_dotenv()

# --- Universe ---
UNIVERSE_SOURCE = "sp500"  # "sp500", "nasdaq100", "sp400"

# Fallback / custom universe (used when UNIVERSE_SOURCE is overridden)
UNIVERSE_CUSTOM = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL",
    "META", "BRK-B", "UNH", "XOM", "JNJ",
    "JPM", "V", "PG", "MA", "HD",
    "CVX", "MRK", "ABBV", "LLY", "PEP",
]

# --- Screening Defaults ---
SCREEN_MIN_PRICE = 10.0          # higher floor — avoid junk
SCREEN_MIN_AVG_VOLUME = 1_000_000  # high liquidity only
SCREEN_MIN_MARKET_CAP = None
SCREEN_SECTORS = None
SCREEN_EXCLUDE_SECTORS = None

# --- Backtest Defaults ---
INITIAL_CAPITAL = 100_000
COMMISSION_PCT = 0.001
SLIPPAGE_PCT = 0.0005

# --- Momentum Strategy Defaults ---
MOMENTUM_LOOKBACK = 21   # ~1 month — short-term momentum
TOP_N = 3                # concentrated: top 3 only
REBALANCE_FREQ = 1       # daily rebalance

# --- Data ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# --- Live Trading ---
LIVE_INITIAL_CAPITAL = 10_000
LIVE_TARGET = 2_000_000
MAX_DRAWDOWN_PCT = 0.20          # tighter kill switch: 20% from peak
MAX_POSITION_PCT = 0.35          # allow concentrated bets
REBALANCE_TIME = "09:45"         # ET — 15 min after open
REBALANCE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]  # daily

# --- API Keys ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
