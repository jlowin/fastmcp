"""Notion relay stub for diagnostics."""
from __future__ import annotations

from custody.custodian_ledger import log_event


class NotionRelay:
    """Pretend to send notifications to Notion."""

    def send(self, message: str) -> dict:
        payload = {"relay": "notion", "message": message}
        log_event("RELAY_NOTION", payload)
        return payload
