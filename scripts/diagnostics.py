"""Diagnostics helpers for quick repo health checks."""
from __future__ import annotations

import json

from custody.custodian_ledger import get_last_events


def diagnostics() -> dict:
    events = get_last_events(10)
    return {"last_10_events": events}


if __name__ == "__main__":
    print(json.dumps(diagnostics(), indent=2))
