"""Hue V2 discovery, saved scenes, and native effects."""

from typing import Any, Literal

from mcp_types import ToolAnnotations
from phue import Bridge, LightState

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from smart_home.lights.hue_utils import get_bridge, hue_lifespan

lights_mcp = FastMCP(
    "Hue lights",
    lifespan=hue_lifespan,
    instructions="Discover rooms, lights and scenes before changing them. Prefer IDs; names must be exact and unique. Check each bulb's supported_effects before applying a native effect. Effects run on the bulb without a polling loop. Use no_effect to stop. Changes can partially succeed before an error; read back current state to verify.",
)
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def resolve(items: dict[str, Any], target: str) -> str:
    if target in items:
        return target
    matches = [key for key, item in items.items() if item["metadata"]["name"] == target]
    if len(matches) != 1:
        raise ToolError(
            f"Target {target!r} is {'ambiguous; use an ID' if matches else 'unknown; list available targets first'}"
        )
    return matches[0]


@lights_mcp.tool(annotations=READ)
async def read_lights(bridge: Bridge = Depends(get_bridge)) -> dict[str, Any]:
    """Read lights keyed by V2 UUID, with current state and supported native effects.

    Brightness is percent. Color temperature is reported as mirek; writes use
    temperature_kelvin. effects_v2.status reports the active effect. Connectivity
    belongs to the owning device. Missing connectivity means unknown.
    """
    connectivity = {
        item.model_dump().get("owner", {}).get("rid"): item.model_dump().get("status")
        for item in await bridge.resources()
        if item.type == "zigbee_connectivity"
    }
    return {
        light.id: {
            **light.model_dump(exclude_none=True),
            "supported_effects": light.supported_effects,
            "connectivity": connectivity.get(light.owner.rid if light.owner else None),
        }
        for light in await bridge.lights()
    }


@lights_mcp.tool(annotations=READ)
async def read_groups(bridge: Bridge = Depends(get_bridge)) -> dict[str, Any]:
    """Read rooms keyed by V2 UUID, including member light UUIDs and services.

    Native effects must target each member light individually. Other room-wide
    settings use the grouped_light service through set_group.
    """
    lights = await bridge.lights()
    return {
        room.id: {
            **room.model_dump(exclude_none=True),
            "lights": [
                light.id
                for light in lights
                if light.owner
                and light.owner.rid in {child.rid for child in room.children}
            ],
        }
        for room in await bridge.rooms()
    }


@lights_mcp.tool(annotations=READ)
async def read_scenes(bridge: Bridge = Depends(get_bridge)) -> dict[str, Any]:
    """Inspect saved scenes, including room references, palettes and per-light effects.

    Inspect actions to distinguish a static warm scene from native candle flicker.
    Scene names may repeat across rooms. IDs and group references disambiguate.
    """
    return {
        scene.id: scene.model_dump(exclude_none=True) for scene in await bridge.scenes()
    }


@lights_mcp.tool(annotations=WRITE)
async def set_light(
    target: str, state: LightState, bridge: Bridge = Depends(get_bridge)
) -> dict[str, Any]:
    """Change one light by UUID or unique exact name, including native candle/fire effects.

    Set effect to a name advertised by the bulb; no_effect stops it. effect_speed
    is 0–1. brightness is percent, temperature_kelvin is kelvin, and
    transition_seconds controls ordinary transitions, not effect speed.
    Brightness/effects do not implicitly turn on the light; include on=true if
    desired. Acceptance is not state verification: read_lights afterward.
    """
    lights = {light.id: light.model_dump() for light in await bridge.lights()}
    light_id = resolve(lights, target)
    accepted = await bridge.set_light(light_id, state)
    return {"light_id": light_id, "accepted": [item.model_dump() for item in accepted]}


@lights_mcp.tool(annotations=WRITE)
async def set_group(
    target: str, state: LightState, bridge: Bridge = Depends(get_bridge)
) -> dict[str, Any]:
    """Change a room by UUID or unique exact name using its grouped_light service.

    For native effects, set each member light individually after checking support.
    Mixed groups may only partially accept color settings. Read lights to verify.
    """
    rooms = {room.id: room.model_dump() for room in await bridge.rooms()}
    room_id = resolve(rooms, target)
    services = [
        s["rid"] for s in rooms[room_id]["services"] if s["rtype"] == "grouped_light"
    ]
    if len(services) != 1:
        raise ToolError("Room does not expose exactly one grouped_light service")
    accepted = await bridge.set_group(services[0], state)
    return {"group_id": room_id, "accepted": [item.model_dump() for item in accepted]}


@lights_mcp.tool(annotations=WRITE)
async def activate_scene(
    group: str,
    scene: str,
    action: Literal["active", "dynamic_palette", "static"] = "active",
    bridge: Bridge = Depends(get_bridge),
) -> dict[str, Any]:
    """Recall a saved scene within a room, including its native per-light effects.

    active recalls the saved look; dynamic_palette requests palette cycling where
    supported. Use read_scenes to inspect what will change before recalling.
    """
    rooms = {room.id: room.model_dump() for room in await bridge.rooms()}
    room_id = resolve(rooms, group)
    scenes = {
        item.id: item.model_dump()
        for item in await bridge.scenes()
        if item.group and item.group.rid == room_id
    }
    scene_id = resolve(scenes, scene)
    accepted = await bridge.recall_scene(scene_id, action=action)
    return {
        "group_id": room_id,
        "scene_id": scene_id,
        "accepted": [item.model_dump() for item in accepted],
    }
