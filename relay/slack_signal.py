"""Slack relay stub."""
from __future__ import annotations

from custody.custodian_ledger import log_event


class SlackSignalRelay:
    def send(self, channel: str, message: str) -> dict:
        payload = {"relay": "slack", "channel": channel, "message": message}
        log_event("RELAY_SLACK", payload)
        return payload
