"""
IB Broker — Interactive Brokers API wrapper via ib_async.

Drop-in replacement for AlpacaBroker. Same interface (get_account, get_positions,
submit_market_order, close_position, etc.) so all existing traders work unchanged.

Connects to TWS or IB Gateway on localhost.
  - Paper: port 4002 (Gateway) or 7497 (TWS)
  - Live:  port 4001 (Gateway) or 7496 (TWS)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from dataclasses import dataclass

from ib_async import IB, Stock, Crypto, MarketOrder, util

from config import IB_HOST, IB_PAPER_PORT, IB_LIVE_PORT, IB_CLIENT_ID, IB_ACCOUNT, BROKER_MODE
from live.broker import Position, AccountInfo

logger = logging.getLogger("ib_broker")


class IBBroker:
    """Interactive Brokers client — matches AlpacaBroker interface."""

    def __init__(
        self,
        host: str = IB_HOST,
        port: int | None = None,
        client_id: int = IB_CLIENT_ID,
        account: str = IB_ACCOUNT,
    ):
        self.host = host
        self.port = port or (IB_PAPER_PORT if BROKER_MODE == "paper" else IB_LIVE_PORT)
        self.client_id = client_id
        self.account = account
        self.ib = IB()
        self._contract_cache: dict[str, object] = {}
        self._connect()

    def _connect(self):
        """Connect to TWS / IB Gateway."""
        logger.info(f"Connecting to IB at {self.host}:{self.port} (clientId={self.client_id})")
        self.ib.connect(self.host, self.port, clientId=self.client_id)
        acct = self.account or self.ib.managedAccounts()[0]
        self.account = acct
        logger.info(f"Connected to IB — account: {acct}")

    def _ensure_connected(self):
        """Reconnect if disconnected (IB resets daily ~11:45 PM ET)."""
        if not self.ib.isConnected():
            logger.warning("IB disconnected — reconnecting...")
            time.sleep(2)
            self._connect()

    def _resolve_contract(self, symbol: str):
        """Resolve a symbol to a qualified IB Contract. Caches results."""
        if symbol in self._contract_cache:
            return self._contract_cache[symbol]

        # Detect crypto (BTC/USD, ETH/USD, etc.)
        if "/" in symbol:
            base = symbol.split("/")[0]
            contract = Crypto(base, "SMART", "USD")
        else:
            contract = Stock(symbol, "SMART", "USD")

        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            raise ValueError(f"Could not qualify contract for {symbol}")

        self._contract_cache[symbol] = qualified[0]
        return qualified[0]

    def _get_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        contract = self._resolve_contract(symbol)
        tickers = self.ib.reqTickers(contract)
        if tickers and tickers[0].marketPrice():
            price = tickers[0].marketPrice()
            if price != price:  # NaN check
                # Fall back to last price or close
                price = tickers[0].last or tickers[0].close
            return float(price)
        raise ValueError(f"Could not get price for {symbol}")

    # --- Account ---

    def get_account(self) -> AccountInfo:
        """Get account equity, cash, and positions."""
        self._ensure_connected()

        summary = self.ib.accountSummary(self.account)
        values = {item.tag: float(item.value) for item in summary if item.currency == "USD"}

        equity = values.get("NetLiquidation", 0)
        cash = values.get("TotalCashValue", 0)
        buying_power = values.get("BuyingPower", 0)

        positions = self.get_positions()

        return AccountInfo(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            positions=positions,
        )

    def get_positions(self) -> list[Position]:
        """Get all open positions."""
        self._ensure_connected()

        ib_positions = self.ib.positions(self.account)
        positions = []

        for p in ib_positions:
            symbol = p.contract.localSymbol or p.contract.symbol
            # For crypto, format as BASE/USD
            if p.contract.secType == "CRYPTO":
                symbol = f"{p.contract.symbol}/USD"

            qty = float(p.position)
            avg_cost = float(p.avgCost)

            # Get current price
            try:
                current_price = self._get_price(symbol)
            except Exception:
                # If we can't get price, estimate from avg cost
                current_price = avg_cost

            # For options/futures, avgCost is per unit already
            market_value = abs(qty) * current_price
            unrealized_pl = (current_price - avg_cost) * qty
            unrealized_pl_pct = (current_price / avg_cost - 1) if avg_cost > 0 else 0

            positions.append(Position(
                symbol=symbol,
                qty=qty,
                market_value=market_value,
                avg_entry_price=avg_cost,
                current_price=current_price,
                unrealized_pl=unrealized_pl,
                unrealized_pl_pct=unrealized_pl_pct,
            ))

        return positions

    def get_position_map(self) -> dict[str, Position]:
        """Get positions as a dict keyed by symbol."""
        return {p.symbol: p for p in self.get_positions()}

    # --- Trading ---

    def submit_market_order(
        self,
        symbol: str,
        notional: float | None = None,
        qty: float | None = None,
        side: str = "buy",
    ) -> dict:
        """
        Submit a market order.

        IB does not support notional orders natively, so we convert
        dollar amounts to share quantities.
        """
        self._ensure_connected()
        contract = self._resolve_contract(symbol)

        if notional is not None and qty is None:
            price = self._get_price(symbol)
            qty = int(abs(notional) / price)
            if qty < 1:
                qty = 1

        if qty is None or qty == 0:
            raise ValueError("Must specify either notional or qty")

        action = "BUY" if side == "buy" else "SELL"
        order = MarketOrder(action, abs(qty))

        logger.info(f"Submitting order: {action} {abs(qty)} {symbol}")
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1)  # brief wait for order to submit

        result = {
            "id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "symbol": symbol,
            "side": side,
            "qty": abs(qty),
        }
        logger.info(f"Order submitted: {result['id']} — status: {result['status']}")
        return result

    def close_position(self, symbol: str) -> dict:
        """Close an entire position."""
        self._ensure_connected()
        logger.info(f"Closing position: {symbol}")

        positions = {p.symbol: p for p in self.get_positions()}
        pos = positions.get(symbol)
        if not pos:
            raise ValueError(f"No position found for {symbol}")

        side = "sell" if pos.qty > 0 else "buy"
        return self.submit_market_order(symbol, qty=abs(pos.qty), side=side)

    def close_all_positions(self) -> None:
        """Emergency: close all positions."""
        self._ensure_connected()
        logger.warning("CLOSING ALL POSITIONS")
        for pos in self.get_positions():
            try:
                self.close_position(pos.symbol)
            except Exception as e:
                logger.error(f"Failed to close {pos.symbol}: {e}")

    def is_market_open(self) -> bool:
        """Check if the US stock market is currently open."""
        self._ensure_connected()
        # Request market hours via a known stock contract
        try:
            spy = self._resolve_contract("SPY")
            details = self.ib.reqContractDetails(spy)
            if details:
                hours = details[0].tradingHours
                # Trading hours format: "20260324:0930-20260324:1600;..."
                # If current time is within a range, market is open
                from datetime import datetime
                now = datetime.now()
                today = now.strftime("%Y%m%d")
                for segment in hours.split(";"):
                    if today in segment and "CLOSED" not in segment:
                        parts = segment.split("-")
                        if len(parts) == 2:
                            open_time = parts[0].split(":")[-1]
                            close_time = parts[1].split(":")[-1]
                            current = now.strftime("%H%M")
                            if open_time <= current <= close_time:
                                return True
            return False
        except Exception:
            # Fallback: check by time
            from datetime import datetime
            now = datetime.now()
            # Mon-Fri, 9:30 AM - 4:00 PM ET
            if now.weekday() < 5:
                market_open = now.replace(hour=9, minute=30, second=0)
                market_close = now.replace(hour=16, minute=0, second=0)
                return market_open <= now <= market_close
            return False

    def disconnect(self):
        """Cleanly disconnect from IB."""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB")
