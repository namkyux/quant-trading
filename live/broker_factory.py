"""
Broker Factory — Returns broker instances.

All trading goes through Interactive Brokers.
Uses auto-incrementing client IDs so multiple traders can connect simultaneously.
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_client_id_counter = 0
_client_id_lock = threading.Lock()


def _next_client_id() -> int:
    """Get a unique client ID for each connection."""
    global _client_id_counter
    with _client_id_lock:
        _client_id_counter += 1
        return _client_id_counter


def get_broker(client_id: int | None = None):
    """Get a stock/crypto broker."""
    from live.ib_broker import IBBroker
    cid = client_id if client_id is not None else _next_client_id()
    return IBBroker(client_id=cid)


def get_options_broker(ib_connection=None, client_id: int | None = None):
    """Get an options broker."""
    from live.ib_options_broker import IBOptionsBroker
    if ib_connection:
        return IBOptionsBroker(ib=ib_connection)
    cid = client_id if client_id is not None else _next_client_id()
    return IBOptionsBroker(client_id=cid)
