"""Heartbeat telemetry utilities."""
from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone
from typing import Any


def generate_heartbeat(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a heartbeat payload with host and timestamp details."""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "status": "ok",
    }
    if metadata:
        payload.update(metadata)
    return payload
