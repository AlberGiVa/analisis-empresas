"""Guard: the test suite must never reach the internet (pytest-socket blocks it)."""

import socket

import pytest
from pytest_socket import SocketConnectBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_connections_to_external_hosts_are_blocked() -> None:
    # 192.0.2.1 is reserved for documentation (TEST-NET-1): it is never a real server.
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
