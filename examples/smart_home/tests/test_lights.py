import os
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from fastmcp import Client

os.environ.setdefault("HUE_BRIDGE_IP", "test-bridge")
os.environ.setdefault("HUE_BRIDGE_USERNAME", "test-user")

from phue.exceptions import PhueException
from smart_home.hub import hub_mcp
from smart_home.lights import server


@pytest.fixture
def bridge(monkeypatch):
    bridge = MagicMock()
    bridge.get_light.return_value = {
        "1": {
            "name": "lamp",
            "state": {"on": True, "bri": 127, "reachable": True},
            "capabilities": {"control": {"ct": {"min": 153, "max": 500}}},
        },
        "2": {"name": "lamp", "state": {"on": False}},
    }
    bridge.get_group.return_value = {
        "1": {"name": "office", "lights": ["1"]},
        "2": {"name": "bedroom", "lights": ["2"]},
    }
    bridge.get_scene.return_value = {
        "a": {"name": "Relax", "group": "1"},
        "b": {"name": "Relax", "group": "2"},
    }
    bridge.set_light.return_value = [[{"success": {"/lights/1/state/on": True}}]]
    bridge.set_group.return_value = [{"success": {"/groups/1/action/on": True}}]
    monkeypatch.setattr(server, "get_bridge", lambda: bridge)
    return bridge


@pytest.mark.asyncio
async def test_discovery_and_changes_over_mcp(bridge):
    async with Client(hub_mcp) as client:
        result = await client.call_tool("hue_read_lights")
        assert result.data["1"]["state"]["reachable"] is True
        assert result.data["1"]["capabilities"]["control"]["ct"]["min"] == 153
        await client.call_tool(
            "hue_set_light",
            {
                "target": "1",
                "state": {
                    "on": True,
                    "brightness": 50,
                    "color_temperature": 2500,
                    "transition": 1.5,
                },
            },
        )
        bridge.set_light.assert_called_once_with(
            1, {"on": True, "bri": 127, "ct": 400, "transitiontime": 15}
        )
        await client.call_tool(
            "hue_activate_scene", {"group": "office", "scene": "Relax"}
        )
        bridge.set_group.assert_called_once_with(1, {"scene": "a"})


@pytest.mark.asyncio
async def test_ambiguous_name_never_writes(bridge):
    async with Client(hub_mcp) as client:
        result = await client.call_tool(
            "hue_set_light",
            {"target": "lamp", "state": {"on": True}},
            raise_on_error=False,
        )
        assert result.is_error
        bridge.set_light.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_room_scene_never_writes(bridge):
    async with Client(hub_mcp) as client:
        result = await client.call_tool(
            "hue_activate_scene",
            {"group": "office", "scene": "b"},
            raise_on_error=False,
        )
        assert result.is_error
        bridge.set_group.assert_not_called()


@pytest.mark.asyncio
async def test_sdk_failure_is_mcp_error(bridge):
    bridge.set_light.side_effect = PhueException(201, "light unavailable")
    async with Client(hub_mcp) as client:
        result = await client.call_tool(
            "hue_set_light",
            {"target": "1", "state": {"on": True}},
            raise_on_error=False,
        )
        assert result.is_error


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"transition": 1},
        {"brightness": 101},
        {"xy": [0.9, 0.9]},
        {"xy": [0.2, 0.3], "color_temperature": 3000},
        {"typo": True},
    ],
)
def test_invalid_states_rejected(state):
    with pytest.raises(ValidationError):
        server.LightState.model_validate(state)


def test_color_degrees_and_percent():
    state = server.LightState(hue=120, saturation=50)
    assert state.to_hue() == {"hue": 21845, "sat": 127}
    assert server.LightState(hue=360).to_hue() == {"hue": 0}
    with pytest.raises(ValidationError):
        server.LightState(hue=120, xy=(0.2, 0.3))
