"""Simple orchestrator that routes commands and records them in the ledger."""
from __future__ import annotations

from typing import Any, Callable


class Orchestrator:
    def __init__(self, ledger: Any, relays: Any):
        self.ledger = ledger
        self.relays = relays

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.ledger.log_event(event_type, payload or {})

    def run_command(self, cmd: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.log("ORCH_COMMAND_RECEIVED", {"cmd": cmd})

        handler: Callable[[dict[str, Any]], Any] | None = getattr(self, f"cmd_{cmd}", None)
        if not handler:
            self.log("ORCH_COMMAND_UNKNOWN", {"cmd": cmd})
            return {"status": "unknown_command"}

        try:
            result = handler(payload or {})
            self.log("ORCH_COMMAND_SUCCESS", {"cmd": cmd})
            return {"status": "ok", "result": result}
        except Exception as exc:  # pragma: no cover - logged for diagnostics
            self.log("ORCH_COMMAND_FAILURE", {"cmd": cmd, "error": str(exc)})
            return {"status": "error", "error": str(exc)}

    def cmd_mvp_health_check(self, payload: dict[str, Any]):
        from telemetry.emit_heartbeat import generate_heartbeat

        res: dict[str, Any] = {
            "mcp": "unknown",
            "heartbeat": None,
            "ledger": "unknown",
        }

        res["mcp"] = "ok"

        hb = generate_heartbeat()
        self.log("ORCH_STEP_HEARTBEAT", hb)
        res["heartbeat"] = hb

        res["ledger"] = "ok"

        return res
