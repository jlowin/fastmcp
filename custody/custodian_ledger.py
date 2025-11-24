"""Simple SQLite-backed ledger for diagnostics and audit logging."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).with_name("ledger.db")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )


def log_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    payload = payload or {}
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO ledger (timestamp, event_type, payload) VALUES (?, ?, ?)",
            (datetime.now(tz=timezone.utc).isoformat(), event_type, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_events(n: int = 10) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_schema(conn)
        cursor = conn.execute(
            "SELECT timestamp, event_type, payload FROM ledger ORDER BY id DESC LIMIT ?",
            (n,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()
    events: list[dict[str, Any]] = []
    for timestamp, event_type, payload in rows:
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            payload_dict = {"malformed_payload": payload}
        events.append({"timestamp": timestamp, "event": event_type, "payload": payload_dict})
    return events
