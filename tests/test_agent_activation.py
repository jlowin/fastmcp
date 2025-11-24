from agent_hub.activate import activate
from custody.custodian_ledger import get_last_events


def test_agent_activation():
    before = len(get_last_events(100))
    activate()
    after = len(get_last_events(100))
    assert after == before + 1
