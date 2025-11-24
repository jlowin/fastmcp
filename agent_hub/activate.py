"""Activation entrypoints for the agent hub."""
from __future__ import annotations

from typing import Iterable, List

from custody.custodian_ledger import log_event
from telemetry.emit_heartbeat import generate_heartbeat


def activate(relays: Iterable[str] | None = None) -> dict:
    """Record an activation event with an optional relay list."""
    relay_list: List[str] = list(relays or [])
    heartbeat = generate_heartbeat()
    payload = {"heartbeat": heartbeat, "relays": relay_list}
    log_event("AGENT_ACTIVATED", payload)
    return payload
