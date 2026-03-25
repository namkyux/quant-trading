"""
Broker Factory — Returns broker instances.

All trading goes through Interactive Brokers.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_broker():
    """Get the stock/crypto broker."""
    from live.ib_broker import IBBroker
    return IBBroker()


def get_options_broker(ib_connection=None):
    """Get the options broker."""
    from live.ib_options_broker import IBOptionsBroker
    return IBOptionsBroker(ib=ib_connection)
