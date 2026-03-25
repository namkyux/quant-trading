"""
Futures Broker — IB futures trading wrapper.

Handles:
- Contract resolution (front month, micro contracts)
- Real-time pricing
- Order submission (market, limit, stop)
- Position management
- Margin monitoring

Micro contracts for small accounts ($10K):
  MES = Micro E-mini S&P 500    ($5/point,  CME)
  MNQ = Micro E-mini NASDAQ     ($2/point,  CME)
  MCL = Micro WTI Crude Oil     ($100/bbl,  NYMEX)
  MGC = Micro Gold              ($10/oz,    COMEX)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime
from dataclasses import dataclass

from ib_async import IB, Future, MarketOrder, LimitOrder, StopOrder

from config import (
    IB_HOST, IB_PAPER_PORT, IB_LIVE_PORT, IB_CLIENT_ID, IB_ACCOUNT,
    BROKER_MODE, FUTURES_SYMBOLS,
)

logger = logging.getLogger("futures_broker")


# Micro futures specs (for margin estimation and display)
FUTURES_SPECS = {
    "MES":  {"exchange": "CME",   "multiplier": 5,   "tick_size": 0.25, "name": "Micro S&P 500"},
    "MNQ":  {"exchange": "CME",   "multiplier": 2,   "tick_size": 0.25, "name": "Micro NASDAQ"},
    "MCL":  {"exchange": "NYMEX", "multiplier": 100,  "tick_size": 0.01, "name": "Micro Crude Oil"},
    "MGC":  {"exchange": "COMEX", "multiplier": 10,   "tick_size": 0.10, "name": "Micro Gold"},
    # Full-size (for reference / future use)
    "ES":   {"exchange": "CME",   "multiplier": 50,  "tick_size": 0.25, "name": "E-mini S&P 500"},
    "NQ":   {"exchange": "CME",   "multiplier": 20,  "tick_size": 0.25, "name": "E-mini NASDAQ"},
    "CL":   {"exchange": "NYMEX", "multiplier": 1000, "tick_size": 0.01, "name": "WTI Crude Oil"},
    "GC":   {"exchange": "COMEX", "multiplier": 100,  "tick_size": 0.10, "name": "Gold"},
}


@dataclass
class FuturesContract:
    symbol: str           # "MES"
    local_symbol: str     # "MESH6" (month code + year)
    exchange: str         # "CME"
    multiplier: float
    tick_size: float
    expiration: str       # "20260320"
    con_id: int = 0


@dataclass
class FuturesPosition:
    symbol: str
    local_symbol: str
    qty: int              # positive = long, negative = short
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_pl_pct: float
    multiplier: float
    market_value: float


@dataclass
class MarginInfo:
    net_liquidation: float
    available_funds: float
    excess_liquidity: float
    initial_margin: float
    maintenance_margin: float
    buying_power: float


class FuturesBroker:
    """Interactive Brokers futures trading client."""

    def __init__(
        self,
        ib: IB | None = None,
        host: str = IB_HOST,
        port: int | None = None,
        client_id: int = IB_CLIENT_ID,
        account: str = IB_ACCOUNT,
    ):
        if ib is not None:
            self.ib = ib
            self._owns_connection = False
        else:
            self.ib = IB()
            port = port or (IB_PAPER_PORT if BROKER_MODE == "paper" else IB_LIVE_PORT)
            self.ib.connect(host, port, clientId=client_id + 2)  # +2 to avoid clashes
            self._owns_connection = True

        self.account = account or self.ib.managedAccounts()[0]
        self._contract_cache: dict[str, FuturesContract] = {}
        self._ib_contract_cache: dict[str, object] = {}
        # Request delayed data if live market data isn't subscribed
        self.ib.reqMarketDataType(3)  # 3 = delayed, 1 = live

    def _ensure_connected(self):
        if not self.ib.isConnected():
            logger.warning("IB disconnected — reconnecting...")
            import time
            time.sleep(2)
            port = IB_PAPER_PORT if BROKER_MODE == "paper" else IB_LIVE_PORT
            self.ib.connect(IB_HOST, port, clientId=IB_CLIENT_ID + 2)

    # --- Contract Resolution ---

    def get_front_month(self, symbol: str) -> FuturesContract:
        """
        Get the front-month (nearest expiry) futures contract.

        Uses IB contract details to find the active front month.
        """
        if symbol in self._contract_cache:
            return self._contract_cache[symbol]

        spec = FUTURES_SPECS.get(symbol)
        if not spec:
            raise ValueError(f"Unknown futures symbol: {symbol}. Known: {list(FUTURES_SPECS.keys())}")

        # Create a generic contract and let IB resolve to front month
        contract = Future(symbol, exchange=spec["exchange"])
        details_list = self.ib.reqContractDetails(contract)

        if not details_list:
            raise ValueError(f"No contracts found for {symbol} on {spec['exchange']}")

        # Sort by expiration, pick the nearest one that's still active
        today = datetime.now().strftime("%Y%m%d")
        active = [d for d in details_list if d.contract.lastTradeDateOrContractMonth >= today]
        if not active:
            raise ValueError(f"No active contracts for {symbol}")

        active.sort(key=lambda d: d.contract.lastTradeDateOrContractMonth)
        front = active[0]

        # Qualify the contract
        ib_contract = front.contract
        self.ib.qualifyContracts(ib_contract)
        self._ib_contract_cache[symbol] = ib_contract

        result = FuturesContract(
            symbol=symbol,
            local_symbol=ib_contract.localSymbol,
            exchange=spec["exchange"],
            multiplier=spec["multiplier"],
            tick_size=spec["tick_size"],
            expiration=ib_contract.lastTradeDateOrContractMonth,
            con_id=ib_contract.conId,
        )
        self._contract_cache[symbol] = result
        logger.info(f"Resolved {symbol} → {result.local_symbol} (exp={result.expiration})")
        return result

    def _get_ib_contract(self, symbol: str):
        """Get the qualified IB Future contract object."""
        if symbol not in self._ib_contract_cache:
            self.get_front_month(symbol)
        return self._ib_contract_cache[symbol]

    # --- Pricing ---

    def get_price(self, symbol: str) -> float:
        """Get real-time price for a futures contract."""
        self._ensure_connected()
        contract = self._get_ib_contract(symbol)
        tickers = self.ib.reqTickers(contract)
        if tickers:
            price = tickers[0].marketPrice()
            if price and price == price:  # not NaN
                return float(price)
            # Fall back to last/close
            last = tickers[0].last
            if last and last == last:
                return float(last)
        raise ValueError(f"Could not get price for {symbol}")

    def get_prices(self, symbols: list[str] | None = None) -> dict[str, float]:
        """Get prices for multiple futures symbols."""
        symbols = symbols or FUTURES_SYMBOLS
        prices = {}
        for sym in symbols:
            try:
                prices[sym] = self.get_price(sym)
            except Exception as e:
                logger.debug(f"Price fetch failed for {sym}: {e}")
        return prices

    # --- Positions ---

    def get_positions(self) -> list[FuturesPosition]:
        """Get all open futures positions."""
        self._ensure_connected()
        all_positions = self.ib.positions(self.account)
        futures_positions = []

        for p in all_positions:
            if p.contract.secType != "FUT":
                continue

            symbol = p.contract.symbol
            spec = FUTURES_SPECS.get(symbol, {})
            multiplier = spec.get("multiplier", float(p.contract.multiplier or 1))
            qty = int(p.position)
            avg_cost = float(p.avgCost) / multiplier  # IB reports avgCost as cost per contract

            try:
                current_price = self.get_price(symbol)
            except Exception:
                current_price = avg_cost

            unrealized_pl = (current_price - avg_cost) * qty * multiplier
            unrealized_pl_pct = (current_price / avg_cost - 1) if avg_cost > 0 else 0
            market_value = abs(qty) * current_price * multiplier

            futures_positions.append(FuturesPosition(
                symbol=symbol,
                local_symbol=p.contract.localSymbol,
                qty=qty,
                avg_entry_price=avg_cost,
                current_price=current_price,
                unrealized_pl=unrealized_pl,
                unrealized_pl_pct=unrealized_pl_pct,
                multiplier=multiplier,
                market_value=market_value,
            ))

        return futures_positions

    # --- Orders ---

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str = "buy",
        order_type: str = "market",
        limit_price: float = 0,
        stop_price: float = 0,
    ) -> dict:
        """
        Submit a futures order.

        Args:
            symbol: futures root (e.g., "MES")
            qty: number of contracts
            side: "buy" (long) or "sell" (short)
            order_type: "market", "limit", or "stop"
        """
        self._ensure_connected()
        contract = self._get_ib_contract(symbol)
        action = "BUY" if side == "buy" else "SELL"

        if order_type == "limit":
            order = LimitOrder(action, abs(qty), limit_price)
        elif order_type == "stop":
            order = StopOrder(action, abs(qty), stop_price)
        else:
            order = MarketOrder(action, abs(qty))

        logger.info(f"Futures order: {action} {abs(qty)} {symbol} ({order_type})")
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1)

        result = {
            "id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "symbol": symbol,
            "side": side,
            "qty": abs(qty),
        }
        logger.info(f"Order: {result['id']} — {result['status']}")
        return result

    def close_position(self, symbol: str) -> dict:
        """Close a futures position by submitting the opposite order."""
        positions = {p.symbol: p for p in self.get_positions()}
        pos = positions.get(symbol)
        if not pos:
            raise ValueError(f"No futures position for {symbol}")

        side = "sell" if pos.qty > 0 else "buy"
        return self.submit_order(symbol, abs(pos.qty), side)

    def close_all_positions(self) -> None:
        """Emergency: close all futures positions."""
        logger.warning("CLOSING ALL FUTURES POSITIONS")
        for pos in self.get_positions():
            try:
                self.close_position(pos.symbol)
            except Exception as e:
                logger.error(f"Failed to close {pos.symbol}: {e}")

    # --- Margin ---

    def get_margin_info(self) -> MarginInfo:
        """Get current margin status."""
        self._ensure_connected()
        summary = self.ib.accountSummary(self.account)
        values = {item.tag: float(item.value) for item in summary if item.currency == "USD"}

        return MarginInfo(
            net_liquidation=values.get("NetLiquidation", 0),
            available_funds=values.get("AvailableFunds", 0),
            excess_liquidity=values.get("ExcessLiquidity", 0),
            initial_margin=values.get("InitMarginReq", 0),
            maintenance_margin=values.get("MaintMarginReq", 0),
            buying_power=values.get("BuyingPower", 0),
        )

    # --- Market Hours ---

    def is_market_open(self, symbol: str = "MES") -> bool:
        """
        Check if futures market is open.

        Futures trade nearly 24h: Sun 6 PM ET - Fri 5 PM ET,
        with daily break 5:00-6:00 PM ET.
        """
        now = datetime.now()
        weekday = now.weekday()  # 0=Mon, 6=Sun
        hour = now.hour
        minute = now.minute

        # Saturday: always closed
        if weekday == 5:
            return False

        # Sunday: open after 6 PM ET
        if weekday == 6:
            return hour >= 18

        # Mon-Fri: closed during 5:00-6:00 PM ET daily maintenance
        if hour == 17:
            return False

        # Friday: closes at 5 PM ET
        if weekday == 4 and hour >= 17:
            return False

        return True
