"""
Options Broker — Alpaca options API wrapper.

Handles:
- Fetching option chains (calls/puts for a symbol)
- Getting option quotes
- Submitting option orders
- Managing option positions
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass

import requests

from config import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL

logger = logging.getLogger("options_broker")


@dataclass
class OptionContract:
    symbol: str           # e.g., AAPL260330C00180000
    underlying: str       # e.g., AAPL
    type: str             # "call" or "put"
    strike: float         # strike price
    expiration: str       # e.g., 2026-03-30
    style: str            # "american"
    status: str           # "active"


@dataclass
class OptionQuote:
    symbol: str
    bid: float
    ask: float
    mid: float
    last: float
    volume: int
    open_interest: int
    implied_vol: float


class OptionsBroker:
    """Alpaca options trading client."""

    def __init__(
        self,
        api_key: str = ALPACA_API_KEY,
        secret_key: str = ALPACA_SECRET_KEY,
        base_url: str = ALPACA_BASE_URL,
    ):
        self.base_url = base_url.rstrip("/")
        self.data_url = "https://data.alpaca.markets"
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

    def _get(self, endpoint: str, base: str | None = None, params: dict | None = None) -> dict:
        url = (base or self.base_url) + endpoint
        resp = requests.get(url, headers=self.headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, data: dict) -> dict:
        url = self.base_url + endpoint
        resp = requests.post(url, json=data, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # --- Option Chains ---

    def get_chain(
        self,
        symbol: str,
        option_type: str = "call",
        min_days: int = 7,
        max_days: int = 45,
        limit: int = 50,
    ) -> list[OptionContract]:
        """
        Get option chain for a stock.

        Args:
            symbol: underlying stock (e.g., "AAPL")
            option_type: "call" or "put"
            min_days/max_days: expiration range from today
            limit: max contracts to return
        """
        now = datetime.now()
        exp_gte = (now + timedelta(days=min_days)).strftime("%Y-%m-%d")
        exp_lte = (now + timedelta(days=max_days)).strftime("%Y-%m-%d")

        params = {
            "underlying_symbols": symbol,
            "status": "active",
            "type": option_type,
            "expiration_date_gte": exp_gte,
            "expiration_date_lte": exp_lte,
            "limit": limit,
        }

        data = self._get("/v2/options/contracts", params=params)
        contracts = []

        for c in data.get("option_contracts", []):
            contracts.append(OptionContract(
                symbol=c["symbol"],
                underlying=c["underlying_symbol"],
                type=c["type"],
                strike=float(c["strike_price"]),
                expiration=c["expiration_date"],
                style=c["style"],
                status=c["status"],
            ))

        return contracts

    def get_calls(self, symbol: str, **kwargs) -> list[OptionContract]:
        """Get call options for a symbol."""
        return self.get_chain(symbol, option_type="call", **kwargs)

    def get_puts(self, symbol: str, **kwargs) -> list[OptionContract]:
        """Get put options for a symbol."""
        return self.get_chain(symbol, option_type="put", **kwargs)

    def get_nearest_call(self, symbol: str, target_strike: float, min_days: int = 14, max_days: int = 45) -> OptionContract | None:
        """Find the call option closest to a target strike price."""
        calls = self.get_calls(symbol, min_days=min_days, max_days=max_days)
        if not calls:
            return None
        return min(calls, key=lambda c: abs(c.strike - target_strike))

    def get_nearest_put(self, symbol: str, target_strike: float, min_days: int = 14, max_days: int = 45) -> OptionContract | None:
        """Find the put option closest to a target strike price."""
        puts = self.get_puts(symbol, min_days=min_days, max_days=max_days)
        if not puts:
            return None
        return min(puts, key=lambda c: abs(c.strike - target_strike))

    # --- Quotes ---

    def get_quote(self, option_symbol: str) -> OptionQuote | None:
        """Get latest quote for an option contract."""
        try:
            data = self._get(
                f"/v1beta1/options/quotes/latest?symbols={option_symbol}&feed=indicative",
                base=self.data_url,
            )
            quotes = data.get("quotes", {})
            q = quotes.get(option_symbol)
            if not q:
                return None

            bid = float(q.get("bp", 0))
            ask = float(q.get("ap", 0))
            return OptionQuote(
                symbol=option_symbol,
                bid=bid,
                ask=ask,
                mid=(bid + ask) / 2 if bid and ask else 0,
                last=0,
                volume=0,
                open_interest=0,
                implied_vol=0,
            )
        except Exception as e:
            logger.debug(f"Failed to get quote for {option_symbol}: {e}")
            return None

    # --- Orders ---

    def buy_option(self, option_symbol: str, qty: int = 1) -> dict:
        """Buy an option contract (market order)."""
        order = {
            "symbol": option_symbol,
            "qty": str(qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        logger.info(f"Buying {qty}x {option_symbol}")
        result = self._post("/v2/orders", order)
        logger.info(f"Order: {result.get('id')} — {result.get('status')}")
        return result

    def sell_option(self, option_symbol: str, qty: int = 1) -> dict:
        """Sell an option contract (market order)."""
        order = {
            "symbol": option_symbol,
            "qty": str(qty),
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
        }
        logger.info(f"Selling {qty}x {option_symbol}")
        result = self._post("/v2/orders", order)
        logger.info(f"Order: {result.get('id')} — {result.get('status')}")
        return result

    def buy_limit(self, option_symbol: str, qty: int, limit_price: float) -> dict:
        """Buy with a limit order (better fills for options)."""
        order = {
            "symbol": option_symbol,
            "qty": str(qty),
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": str(round(limit_price, 2)),
        }
        logger.info(f"Buying {qty}x {option_symbol} limit ${limit_price:.2f}")
        result = self._post("/v2/orders", order)
        return result

    def sell_limit(self, option_symbol: str, qty: int, limit_price: float) -> dict:
        """Sell with a limit order."""
        order = {
            "symbol": option_symbol,
            "qty": str(qty),
            "side": "sell",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": str(round(limit_price, 2)),
        }
        logger.info(f"Selling {qty}x {option_symbol} limit ${limit_price:.2f}")
        result = self._post("/v2/orders", order)
        return result
