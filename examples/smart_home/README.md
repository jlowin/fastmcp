# smart home MCP

Control Philips Hue lights through FastMCP. An agent can inspect light state and
capabilities, discover rooms and scenes, change individual lights or whole rooms,
and read back the result. This example uses the local Hue bridge API through
[`phue2`](https://github.com/zzstoatzz/phue) 0.1. API failures raise exceptions,
including partial-success responses; the example exposes failures as MCP tool errors.

## Run

Create `.env` in this directory with your existing bridge credentials:

```dotenv
HUE_BRIDGE_IP=<bridge IP>
HUE_BRIDGE_USERNAME=<bridge application key>
```

Start the stdio server from this directory:

```bash
uv run smart-home
```

For an MCP client, configure `uv` with arguments `run --directory
/absolute/path/to/examples/smart_home smart-home`. Credentials stay in the local
environment; the server does not write a bridge configuration file.

## Agent workflow

Start with `hue_read_groups` and `hue_read_lights`. Discovery includes stable IDs,
room membership, reachability, current state and the capabilities reported by each
bulb. Names must match exactly and be unique; IDs avoid ambiguity. A room named
“all” is just a name, so inspect its membership.

To make one room warm and dim, call `hue_set_group` with its ID and a state:

```json
{
  "target": "1",
  "state": {
    "on": true,
    "brightness": 20,
    "color_temperature": 2700,
    "transition": 2
  }
}
```

Brightness is a percentage, temperature is kelvin and transitions are seconds.
Omitted properties stay unchanged. Brightness and color do not implicitly turn a
light on. Use hue degrees and saturation percent for a color-wheel setting, or `xy` for
CIE color coordinates instead of a temperature. Choose one color mode; consult bulb
capabilities before selecting a color. Discovery preserves Hue's native state
units (`bri` from 0–254, `ct` in mireds).

A successful write acknowledges the command. After a transition, use
`hue_read_lights` to verify actual state. Hue can partially apply a command before
returning an error; an error does not imply that nothing changed.

Use `hue_read_scenes` and `hue_activate_scene` to recall saved scenes. Scene names
are resolved within the specified room, so a “Relax” scene in another room cannot
be selected accidentally.

This refresh replaces the old name-only discovery and individual attribute tools
with three discovery tools and three control tools. Clients should rediscover the
server's tools after updating.

## Test

The regression tests use a simulated bridge and exercise the actual MCP client:

```bash
uv run pytest
```

For a live agent check, give Pi only this MCP server and disable built-in tools.
First ask it to inspect state without changing anything. For a write check, record
the original state of one reachable light, change a single property, read it back,
then restore and verify the original state. Keep the tool-call transcript to
separate an agent's claim from an observed result.

With Pi and `pi-mcp-adapter` installed, run the isolated harness from this directory:

```bash
uv run scripts/pi_harness.py --json
```

It supplies exactly this server, disables Pi's built-in tools and other extensions,
and defaults to a read-only prompt. Pass `--env-file /path/to/existing.env` if your
credentials are elsewhere. Pass a quoted prompt to exercise a particular workflow;
write requests operate real lights. `--json` records tool calls and results on stdout.
