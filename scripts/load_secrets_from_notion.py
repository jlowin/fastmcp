"""Stub loader for Notion-hosted secrets."""
from __future__ import annotations

from custody.custodian_ledger import log_event


def load_secrets() -> dict:
    secrets = {"notion": "loaded"}
    log_event("NOTION_SECRETS_LOADED", secrets)
    return secrets


if __name__ == "__main__":
    load_secrets()
