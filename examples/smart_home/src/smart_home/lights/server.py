"""Hue discovery and control with observable state and explicit targets."""

from typing import Annotated, Any, Literal

from mcp_types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from smart_home.lights.hue_utils import get_bridge


class LightState(BaseModel):
    """Set only the properties you want to change; other properties stay unchanged."""

    model_config = ConfigDict(extra="forbid")
    on: bool | None = None
    brightness: (
        Annotated[
            float,
            Field(
                ge=0,
                le=100,
                description="Brightness percent; use on=false to turn off.",
            ),
        ]
        | None
    ) = None
    hue: float | None = Field(
        default=None,
        ge=0,
        le=360,
        description="Hue degrees: red 0, green 120, blue 240.",
    )
    saturation: float | None = Field(
        default=None, ge=0, le=100, description="Color saturation percent."
    )
    color_temperature: (
        Annotated[
            int,
            Field(
                ge=2000,
                le=6500,
                description="Color temperature in kelvin; check the light's capabilities.",
            ),
        ]
        | None
    ) = None
    xy: (
        Annotated[
            tuple[float, float],
            Field(
                description="CIE xy color coordinates; each coordinate must be between 0 and 1."
            ),
        ]
        | None
    ) = None
    effect: Literal["none", "colorloop"] | None = None
    transition: (
        Annotated[
            float, Field(ge=0, le=6553.5, description="Transition duration in seconds.")
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_state(self) -> "LightState":
        color_modes = sum(
            (
                self.xy is not None,
                self.color_temperature is not None,
                self.hue is not None or self.saturation is not None,
            )
        )
        if color_modes > 1:
            raise ValueError(
                "Choose one color mode: hue/saturation, xy, or color_temperature"
            )
        if self.xy is not None:
            if any(not 0 <= c <= 1 for c in self.xy) or sum(self.xy) > 1:
                raise ValueError("xy must be within the CIE chromaticity triangle")
        if not self.model_dump(exclude_none=True, exclude={"transition"}):
            raise ValueError("Provide at least one light property to change")
        return self

    def to_hue(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name in ("on", "effect"):
            value = getattr(self, name)
            if value is not None:
                values[name] = value
        if self.brightness is not None:
            values["bri"] = round(self.brightness * 254 / 100)
        if self.hue is not None:
            values["hue"] = round((self.hue % 360) * 65535 / 360)
        if self.saturation is not None:
            values["sat"] = round(self.saturation * 254 / 100)
        if self.color_temperature is not None:
            values["ct"] = round(1_000_000 / self.color_temperature)
        if self.xy is not None:
            values["xy"] = list(self.xy)
        if self.transition is not None:
            values["transitiontime"] = round(self.transition * 10)
        return values


lights_mcp = FastMCP(
    "Hue lights",
    instructions="Discover lights, groups and scenes before changing them. Prefer IDs; names must match exactly and be unique. Check reachability and capabilities. Changes to groups affect every member. Read state after a transition to verify the result. Hue writes can partially succeed before reporting an error.",
)
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def resolve(items: dict[str, Any], target: str) -> str:
    if target in items:
        return target
    matches = [key for key, item in items.items() if item.get("name") == target]
    if len(matches) != 1:
        raise ToolError(
            f"Target {target!r} is {'ambiguous; use an ID' if matches else 'unknown; list available targets first'}"
        )
    return matches[0]


@lights_mcp.tool(annotations=READ)
def read_lights() -> dict[str, Any]:
    """Read all lights keyed by stable bridge ID, including state, reachability, model and capabilities.

    State uses Hue units: bri 0–254, ct in mireds, xy coordinates. Write tools
    accept brightness percent, color temperature in kelvin and transition seconds.
    Capabilities vary by bulb; do not infer color support from the tool schema.
    """
    return get_bridge().get_light()


@lights_mcp.tool(annotations=READ)
def read_groups() -> dict[str, Any]:
    """Read rooms and groups keyed by ID, with member light IDs and aggregate state.

    A group named 'all' may contain only some lights; inspect membership.
    """
    return get_bridge().get_group()


@lights_mcp.tool(annotations=READ)
def read_scenes() -> dict[str, Any]:
    """Read scenes keyed by ID, including names, group IDs and member lights.

    Scene names can repeat across rooms. Use the scene ID when recalling one.
    """
    scenes = get_bridge().get_scene()
    return {
        key: {
            field: value
            for field, value in scene.items()
            if field in {"name", "group", "lights", "type", "recycle"}
        }
        for key, scene in scenes.items()
    }


@lights_mcp.tool(annotations=WRITE)
def set_light(target: str, state: LightState) -> dict[str, Any]:
    """Change one light by ID or unique exact name. Return the accepted Hue response.

    Setting brightness or color does not implicitly turn a light on. Include
    on=true when desired. A successful response acknowledges the command;
    read_lights after the transition verifies its resulting state.
    """
    bridge = get_bridge()
    light_id = resolve(bridge.get_light(), target)
    return {
        "light_id": light_id,
        "accepted": bridge.set_light(int(light_id), state.to_hue()),
    }


@lights_mcp.tool(annotations=WRITE)
def set_group(target: str, state: LightState) -> dict[str, Any]:
    """Change all members of one room/group by ID or unique exact name in one bridge command.

    Inspect member capabilities first; mixed groups may only partially accept
    color settings. Include on=true to turn lights on. Read lights to verify.
    """
    bridge = get_bridge()
    group_id = resolve(bridge.get_group(), target)
    return {
        "group_id": group_id,
        "accepted": bridge.set_group(int(group_id), state.to_hue()),
    }


@lights_mcp.tool(annotations=WRITE)
def activate_scene(group: str, scene: str) -> dict[str, Any]:
    """Recall a scene by ID or unique exact name within a room/group.

    The scene must belong to that group, or have all its lights within it.
    """
    bridge = get_bridge()
    groups = bridge.get_group()
    group_id = resolve(groups, group)
    scenes = {
        key: value
        for key, value in bridge.get_scene().items()
        if value.get("group") == group_id
        or (
            not value.get("group")
            and value.get("lights")
            and set(value["lights"]).issubset(groups[group_id]["lights"])
        )
    }
    scene_id = resolve(scenes, scene)
    return {
        "group_id": group_id,
        "scene_id": scene_id,
        "accepted": bridge.set_group(int(group_id), {"scene": scene_id}),
    }
