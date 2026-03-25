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

# --- Crypto ---
CRYPTO_SYMBOLS = [
    # --- Large cap ---
    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "LTC/USD",
    "ADA/USD", "AVAX/USD", "DOT/USD", "LINK/USD", "BCH/USD",
    # --- Mid cap / DeFi ---
    "UNI/USD", "AAVE/USD", "CRV/USD", "GRT/USD", "LDO/USD",
    "SUSHI/USD", "FIL/USD", "RENDER/USD", "ONDO/USD",
    "COMP/USD", "MKR/USD", "SNX/USD", "ENS/USD", "LRC/USD",
    "DYDX/USD", "YFI/USD",
    # --- Meme / high volatility ---
    "DOGE/USD", "SHIB/USD", "PEPE/USD", "BONK/USD", "WIF/USD",
    "TRUMP/USD", "APE/USD",
    # --- Layer 1 / infra ---
    "ARB/USD", "POL/USD", "MATIC/USD", "ALGO/USD", "ATOM/USD",
    "NEAR/USD", "FTM/USD", "ICP/USD", "HBAR/USD", "XLM/USD",
    "EOS/USD", "XTZ/USD", "VET/USD", "THETA/USD", "IOTA/USD",
    "TRX/USD", "NEO/USD", "OP/USD", "IMX/USD", "ETC/USD",
    # --- Metaverse / gaming ---
    "MANA/USD", "SAND/USD", "AXS/USD",
    # --- Other ---
    "BAT/USD", "SKY/USD", "PAXG/USD", "HYPE/USD",
    "DASH/USD", "ZEC/USD",
]
CRYPTO_STOP_LOSS_PCT = 0.08      # wider: 8% (crypto is more volatile)
CRYPTO_TAKE_PROFIT_PCT = 0.15    # wider: 15%
CRYPTO_MAX_POSITION_PCT = 0.25   # smaller per position (more volatile)
CRYPTO_SCAN_MINUTES = 10         # scan more often (market never closes)

# --- Data ---
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# --- Live Trading ---
LIVE_INITIAL_CAPITAL = 10_000
LIVE_TARGET = 2_000_000
MAX_DRAWDOWN_PCT = 0.20
MAX_POSITION_PCT = 0.20   # 5 positions × 20% = 100% max (no margin)
REBALANCE_TIME = "09:45"
REBALANCE_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# --- Interactive Brokers ---
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PAPER_PORT = int(os.getenv("IB_PAPER_PORT", "4002"))
IB_LIVE_PORT = int(os.getenv("IB_LIVE_PORT", "4001"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))
IB_ACCOUNT = os.getenv("IB_ACCOUNT", "")  # auto-detect if blank

# --- Broker Selection ---
BROKER = os.getenv("BROKER", "ib")             # "ib"
BROKER_MODE = os.getenv("BROKER_MODE", "paper")  # "paper" or "live"

# --- Futures ---
FUTURES_SYMBOLS = ["MES", "MNQ", "MCL", "MGC"]
FUTURES_STOP_LOSS_PCT = 0.02         # tighter: 2% (leveraged)
FUTURES_TAKE_PROFIT_PCT = 0.04       # 4% take profit
FUTURES_MAX_CONTRACTS = 2            # max 2 contracts per symbol
FUTURES_SCAN_MINUTES = 5             # scan every 5 min (futures move fast)
FUTURES_MAX_POSITIONS = 4            # max 4 simultaneous positions
FUTURES_DAILY_LOSS_LIMIT = 500       # dollar-based (not %, due to leverage)
