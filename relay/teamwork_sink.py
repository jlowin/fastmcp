"""Teamwork sink stub."""
from __future__ import annotations

from custody.custodian_ledger import log_event


class TeamworkSink:
    def record(self, entry: dict) -> dict:
        payload = {"relay": "teamwork", "entry": entry}
        log_event("RELAY_TEAMWORK", payload)
        return payload
