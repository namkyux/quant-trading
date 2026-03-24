"""
Broker Factory — Returns the right broker based on config.

Usage:
    from live.broker_factory import get_broker, get_options_broker
    broker = get_broker()             # reads BROKER env var
    options = get_options_broker()    # same
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BROKER, BROKER_MODE


def get_broker(broker_type: str | None = None, mode: str | None = None):
    """Get a stock/crypto broker instance."""
    broker_type = broker_type or BROKER
    mode = mode or BROKER_MODE

    if broker_type == "ib":
        from live.ib_broker import IBBroker
        return IBBroker()
    else:
        from live.broker import AlpacaBroker
        return AlpacaBroker()


def get_options_broker(broker_type: str | None = None, mode: str | None = None, ib_connection=None):
    """Get an options broker instance."""
    broker_type = broker_type or BROKER
    mode = mode or BROKER_MODE

    if broker_type == "ib":
        from live.ib_options_broker import IBOptionsBroker
        return IBOptionsBroker(ib=ib_connection)
    else:
        from live.options_broker import OptionsBroker
        return OptionsBroker()
