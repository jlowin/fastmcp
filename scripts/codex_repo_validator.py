"""Validate required MAOS file paths exist."""
from __future__ import annotations

import json
import os
from pathlib import Path

REQUIRED_PATHS = [
    "configs/global_config.yaml",
    "orchestration/MCP/relay_server.py",
    "memory/sql_store/sql_store.py",
    "memory/vector_store/vector_store.py",
    "custody/custodian_ledger.py",
    "scripts/load_secrets_from_notion.py",
    "scripts/start_autonomy_loop.py",
    "agent_hub/activate.py",
    "telemetry/emit_heartbeat.py",
    "relay/notion_relay.py",
    "relay/slack_signal.py",
    "relay/teamwork_sink.py",
]


def validate_paths(base_dir: str | os.PathLike[str] | None = None) -> dict:
    base = Path(base_dir or Path.cwd())
    missing = [p for p in REQUIRED_PATHS if not (base / p).exists()]
    return {"missing": missing, "status": "ok" if not missing else "fail"}


if __name__ == "__main__":
    print(json.dumps(validate_paths(), indent=2))
