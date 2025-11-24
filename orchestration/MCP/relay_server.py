"""Lightweight relay server shim."""
from __future__ import annotations

from custody.custodian_ledger import log_event


class RelayServer:
    def __init__(self, name: str = "relay-server") -> None:
        self.name = name
        self.running = False

    def start(self) -> None:
        if not self.running:
            self.running = True
            log_event("RELAY_SERVER_START", {"name": self.name})

    def stop(self) -> None:
        if self.running:
            self.running = False
            log_event("RELAY_SERVER_STOP", {"name": self.name})
