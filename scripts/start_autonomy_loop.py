"""Start a single iteration of the autonomy loop."""
from __future__ import annotations

from custody.custodian_ledger import log_event
from telemetry.emit_heartbeat import generate_heartbeat


def run_cycle() -> dict:
    heartbeat = generate_heartbeat({"cycle": "autonomy"})
    log_event("AUTONOMY_LOOP", heartbeat)
    return heartbeat


if __name__ == "__main__":
    run_cycle()
