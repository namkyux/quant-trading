"""
IB Options Broker — Interactive Brokers options API wrapper.

Drop-in replacement for OptionsBroker. Same interface (get_chain, get_quote,
buy_option, sell_option, etc.) so OptionsTrader works unchanged.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

from ib_async import IB, Option, Stock, MarketOrder, LimitOrder

from config import IB_HOST, IB_PAPER_PORT, IB_LIVE_PORT, IB_CLIENT_ID, BROKER_MODE
from live.options_broker import OptionContract, OptionQuote

logger = logging.getLogger("ib_options_broker")


class IBOptionsBroker:
    """Interactive Brokers options client — matches OptionsBroker interface."""

    def __init__(self, ib: IB | None = None, host: str = IB_HOST, port: int | None = None, client_id: int = IB_CLIENT_ID):
        """
        Args:
            ib: Shared IB connection (from IBBroker). If None, creates its own.
        """
        if ib is not None:
            self.ib = ib
            self._owns_connection = False
        else:
            self.ib = IB()
            port = port or (IB_PAPER_PORT if BROKER_MODE == "paper" else IB_LIVE_PORT)
            self.ib.connect(host, port, clientId=client_id + 1)  # +1 to avoid client ID clash
            self._owns_connection = True
        self._chain_cache: dict[str, dict] = {}

    def _get_chain_params(self, symbol: str) -> dict:
        """Get available strikes and expirations for a symbol."""
        if symbol in self._chain_cache:
            return self._chain_cache[symbol]

        stock = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(stock)
        chains = self.ib.reqSecDefOptParams(symbol, "", stock.secType, stock.conId)

        if not chains:
            return {}

        # Pick SMART exchange chain (most liquid)
        chain = None
        for c in chains:
            if c.exchange == "SMART":
                chain = c
                break
        if chain is None:
            chain = chains[0]

        result = {
            "exchange": chain.exchange,
            "expirations": sorted(chain.expirations),
            "strikes": sorted(chain.strikes),
        }
        self._chain_cache[symbol] = result
        return result

    # --- Option Chains ---

    def get_chain(
        self,
        symbol: str,
        option_type: str = "call",
        min_days: int = 7,
        max_days: int = 45,
        limit: int = 50,
    ) -> list[OptionContract]:
        """Get option chain for a stock."""
        params = self._get_chain_params(symbol)
        if not params:
            return []

        now = datetime.now()
        min_date = (now + timedelta(days=min_days)).strftime("%Y%m%d")
        max_date = (now + timedelta(days=max_days)).strftime("%Y%m%d")

        right = "C" if option_type == "call" else "P"

        # Filter expirations to the date range
        valid_exps = [e for e in params["expirations"] if min_date <= e <= max_date]
        if not valid_exps:
            return []

        contracts = []
        for exp in valid_exps[:3]:  # limit to 3 expirations to avoid flooding
            for strike in params["strikes"]:
                contracts.append(OptionContract(
                    symbol=f"{symbol}{exp}{right}{int(strike * 1000):08d}",
                    underlying=symbol,
                    type=option_type,
                    strike=strike,
                    expiration=f"{exp[:4]}-{exp[4:6]}-{exp[6:8]}",
                    style="american",
                    status="active",
                ))
                if len(contracts) >= limit:
                    return contracts

        return contracts

    def get_calls(self, symbol: str, **kwargs) -> list[OptionContract]:
        return self.get_chain(symbol, option_type="call", **kwargs)

    def get_puts(self, symbol: str, **kwargs) -> list[OptionContract]:
        return self.get_chain(symbol, option_type="put", **kwargs)

    def get_nearest_call(self, symbol: str, target_strike: float, min_days: int = 14, max_days: int = 45) -> OptionContract | None:
        calls = self.get_calls(symbol, min_days=min_days, max_days=max_days)
        if not calls:
            return None
        return min(calls, key=lambda c: abs(c.strike - target_strike))

    def get_nearest_put(self, symbol: str, target_strike: float, min_days: int = 14, max_days: int = 45) -> OptionContract | None:
        puts = self.get_puts(symbol, min_days=min_days, max_days=max_days)
        if not puts:
            return None
        return min(puts, key=lambda c: abs(c.strike - target_strike))

    # --- Quotes ---

    def _make_ib_option(self, contract: OptionContract):
        """Convert our OptionContract to an IB Option contract."""
        right = "C" if contract.type == "call" else "P"
        exp = contract.expiration.replace("-", "")
        opt = Option(contract.underlying, exp, contract.strike, right, "SMART")
        qualified = self.ib.qualifyContracts(opt)
        return qualified[0] if qualified else None

    def get_quote(self, option_symbol: str) -> OptionQuote | None:
        """
        Get latest quote for an option contract.

        Note: option_symbol is in OCC format. We need to parse it back.
        """
        try:
            # Parse OCC symbol: AAPL260330C00180000
            # underlying = letters, date = 6 digits, right = C/P, strike = 8 digits
            i = 0
            while i < len(option_symbol) and option_symbol[i].isalpha():
                i += 1
            underlying = option_symbol[:i]
            date_str = option_symbol[i:i + 6]
            right = option_symbol[i + 6]
            strike = int(option_symbol[i + 7:]) / 1000

            exp = f"20{date_str}"  # YYMMDD -> 20YYMMDD
            opt = Option(underlying, exp, strike, right, "SMART")
            qualified = self.ib.qualifyContracts(opt)
            if not qualified:
                return None

            tickers = self.ib.reqTickers(qualified[0])
            if not tickers:
                return None

            t = tickers[0]
            bid = float(t.bid) if t.bid and t.bid == t.bid else 0
            ask = float(t.ask) if t.ask and t.ask == t.ask else 0

            return OptionQuote(
                symbol=option_symbol,
                bid=bid,
                ask=ask,
                mid=(bid + ask) / 2 if bid and ask else 0,
                last=float(t.last) if t.last and t.last == t.last else 0,
                volume=int(t.volume) if t.volume and t.volume == t.volume else 0,
                open_interest=0,
                implied_vol=0,
            )
        except Exception as e:
            logger.debug(f"Failed to get quote for {option_symbol}: {e}")
            return None

    # --- Orders ---

    def _submit_option_order(self, option_symbol: str, qty: int, side: str, order_type: str = "market", limit_price: float = 0) -> dict:
        """Submit an option order."""
        # Parse the OCC symbol
        i = 0
        while i < len(option_symbol) and option_symbol[i].isalpha():
            i += 1
        underlying = option_symbol[:i]
        date_str = option_symbol[i:i + 6]
        right = option_symbol[i + 6]
        strike = int(option_symbol[i + 7:]) / 1000

        exp = f"20{date_str}"
        opt = Option(underlying, exp, strike, right, "SMART")
        qualified = self.ib.qualifyContracts(opt)
        if not qualified:
            raise ValueError(f"Could not qualify option: {option_symbol}")

        action = "BUY" if side == "buy" else "SELL"
        if order_type == "limit":
            order = LimitOrder(action, qty, limit_price)
        else:
            order = MarketOrder(action, qty)

        logger.info(f"{action} {qty}x {option_symbol} ({order_type})")
        trade = self.ib.placeOrder(qualified[0], order)
        self.ib.sleep(1)

        result = {
            "id": trade.order.orderId,
            "status": trade.orderStatus.status,
        }
        logger.info(f"Order: {result['id']} — {result['status']}")
        return result

    def buy_option(self, option_symbol: str, qty: int = 1) -> dict:
        return self._submit_option_order(option_symbol, qty, "buy")

    def sell_option(self, option_symbol: str, qty: int = 1) -> dict:
        return self._submit_option_order(option_symbol, qty, "sell")

    def buy_limit(self, option_symbol: str, qty: int, limit_price: float) -> dict:
        return self._submit_option_order(option_symbol, qty, "buy", "limit", limit_price)

    def sell_limit(self, option_symbol: str, qty: int, limit_price: float) -> dict:
        return self._submit_option_order(option_symbol, qty, "sell", "limit", limit_price)
