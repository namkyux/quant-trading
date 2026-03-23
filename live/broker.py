"""
Broker interface — Alpaca API wrapper for paper and live trading.

Handles:
- Account info (cash, equity, positions)
- Fetching current prices
- Submitting orders (market orders for simplicity)
- Position management
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from dataclasses import dataclass

import requests

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

logger = logging.getLogger("broker")


@dataclass
class Position:
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_pl_pct: float


@dataclass
class AccountInfo:
    equity: float
    cash: float
    buying_power: float
    positions: list[Position]


class AlpacaBroker:
    """Alpaca API client for trading."""

    def __init__(
        self,
        api_key: str = ALPACA_API_KEY,
        secret_key: str = ALPACA_SECRET_KEY,
        base_url: str = ALPACA_BASE_URL,
    ):
        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca API keys not set. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env"
            )

        self.base_url = base_url.rstrip("/")
        self.data_url = "https://data.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._verify_connection()

    def _verify_connection(self):
        """Test the API connection."""
        resp = self._get("/v2/account")
        status = resp.get("status", "unknown")
        logger.info(f"Connected to Alpaca ({self.base_url}) — Account status: {status}")

    def _get(self, endpoint: str, base: str | None = None) -> dict:
        url = (base or self.base_url) + endpoint
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, data: dict) -> dict:
        url = self.base_url + endpoint
        resp = requests.post(url, json=data, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, endpoint: str) -> None:
        url = self.base_url + endpoint
        resp = requests.delete(url, headers=self.headers, timeout=10)
        resp.raise_for_status()

    # --- Account ---

    def get_account(self) -> AccountInfo:
        """Get account equity, cash, and positions."""
        acct = self._get("/v2/account")
        positions = self.get_positions()
        return AccountInfo(
            equity=float(acct["equity"]),
            cash=float(acct["cash"]),
            buying_power=float(acct["buying_power"]),
            positions=positions,
        )

    def get_positions(self) -> list[Position]:
        """Get all open positions."""
        raw = self._get("/v2/positions")
        positions = []
        for p in raw:
            positions.append(Position(
                symbol=p["symbol"],
                qty=float(p["qty"]),
                market_value=float(p["market_value"]),
                avg_entry_price=float(p["avg_entry_price"]),
                current_price=float(p["current_price"]),
                unrealized_pl=float(p["unrealized_pl"]),
                unrealized_pl_pct=float(p["unrealized_plpc"]),
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

        Args:
            symbol: ticker
            notional: dollar amount to buy/sell (fractional shares)
            qty: number of shares (use one of notional or qty)
            side: "buy" or "sell"
        """
        order = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }

        if notional is not None:
            order["notional"] = str(round(abs(notional), 2))
        elif qty is not None:
            order["qty"] = str(abs(qty))
        else:
            raise ValueError("Must specify either notional or qty")

        logger.info(f"Submitting order: {side.upper()} {symbol} "
                     f"{'$' + str(round(abs(notional), 2)) if notional else str(qty) + ' shares'}")

        result = self._post("/v2/orders", order)
        logger.info(f"Order submitted: {result.get('id', 'unknown')} — status: {result.get('status', 'unknown')}")
        return result

    def close_position(self, symbol: str) -> dict:
        """Close an entire position."""
        logger.info(f"Closing position: {symbol}")
        url = self.base_url + f"/v2/positions/{symbol}"
        resp = requests.delete(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def close_all_positions(self) -> None:
        """Emergency: close all positions."""
        logger.warning("CLOSING ALL POSITIONS")
        self._delete("/v2/positions")

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        clock = self._get("/v2/clock")
        return clock.get("is_open", False)
