from custody.custodian_ledger import get_last_events, log_event
from telemetry.emit_heartbeat import generate_heartbeat
from unittest.mock import patch

def test_heartbeat_write():
    with patch("custody.custodian_ledger.get_last_events") as mock_get_last_events, \
         patch("custody.custodian_ledger.log_event") as mock_log_event:
        # Simulate initial state: 5 events
        mock_get_last_events.return_value = [object()] * 5
        before = len(get_last_events(100))
        hb = generate_heartbeat()
        # After logging, simulate 6 events
        mock_get_last_events.return_value = [object()] * 6
        log_event("HEARTBEAT_EMIT", hb)
        after = len(get_last_events(100))
        assert after == before + 1
