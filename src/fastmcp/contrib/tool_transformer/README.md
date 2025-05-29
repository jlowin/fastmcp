# Tool Transformer

This module provides the [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) function and related utilities to modify existing FastMCP tools and add them to a server. It allows for intercepting tool calls, altering their behavior by changing parameters, adding new parameters for hooks, and executing custom logic before or after the original tool execution. The [`transform_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:133) function is also available for transforming a tool without adding it to a server.

This is a community-contributed module and is located in the `contrib` directory. Please refer to the main [FastMCP Contrib Modules README](../../contrib/README.md) for general information about contrib modules and their guarantees.

## Purpose

The Tool Transformer is useful for scenarios where you need to:
- Modify arguments of an existing tool (e.g., setting constant values, providing new defaults, changing descriptions).
- Add new parameters that are not passed to the original tool but are available to custom hook functions.
- Execute custom logic before a tool call (e.g., logging, input validation, conditional logic via `pre_call_hook`).
- Process the response from a tool before returning it (e.g., filtering, transforming, logging via `post_call_hook`).
- Load tool transformation configurations from YAML files.

## Installation

Since this is a contrib module, it is included with the FastMCP library. No separate installation is required.

## Core Concepts

### `proxy_tool` Function
The primary way to use this module to transform a tool and add it to a server is through the [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) function. This function takes an existing `FastMCPTool` instance and an `FastMCP` server instance to which the new, transformed tool will be added. It allows you to specify a new name, description, parameter overrides, hook parameters, and pre/post call hooks.

### `transform_tool` Function
The [`transform_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:133) function is used to transform a tool without adding it to a server. It takes an existing `FastMCPTool` instance and allows you to specify a new name, description, parameter overrides, hook parameters, and pre/post call hooks.

### Parameter Overrides
You can modify existing parameters of a tool using the [`ToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:16) class and its subclasses (e.g., [`StringToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:150), [`IntToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:134), [`BooleanToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:158)). This allows you to:
- Change a parameter's description.
- Set a `constant` value for a parameter, which will always be used.
- Provide a new `default` value.
- Make an optional parameter `required` (note: you cannot make an already required parameter optional).

### Extra Hook Parameters
New parameters can be defined using the [`ToolParameterTypes`](src/fastmcp/contrib/tool_transformer/models.py:186) (e.g., [`StringToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:150), [`IntToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:134), or [`BooleanToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:158)). These parameters are exposed by the transformed tool but are *not* passed to the underlying original tool. Instead, their values are passed to the `pre_call_hook` and `post_call_hook` functions, allowing for more flexible hook logic.

### Pre-call and Post-call Hooks
- **`pre_call_hook`**: A callable (async function) that is executed *before* the original tool is called. It receives the arguments intended for the original tool (which can be modified) and the values of any `hook_parameters`. See [`PreToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:197).
- **`post_call_hook`**: A callable (async function) that is executed *after* the original tool returns a response. It receives the response from the original tool, the arguments that were passed to it, and the values of any `hook_parameters`. See [`PostToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:206).

### Loading Overrides from YAML
The module also supports defining tool transformations in YAML or JSON files. The [`loader.py`](src/fastmcp/contrib/tool_transformer/loader.py) provides functions to load [`ToolOverride`](src/fastmcp/contrib/tool_transformer/models.py:219) objects from these files, such as [`overrides_from_yaml_file`](src/fastmcp/contrib/tool_transformer/loader.py:22) and [`overrides_from_json_file`](src/fastmcp/contrib/tool_transformer/loader.py:31).

## Usage

### Programmatic Transformation
To transform a single tool programmatically:
1. Obtain an instance of the tool you want to transform (e.g., from a `FastMCP` server).
2. Call the [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) function, providing the original tool, the target server, and any desired transformation options (name, description, parameter overrides, hook parameters, hooks, etc.).

Refer to [`example-overrides.py`](src/fastmcp/contrib/tool_transformer/example-overrides.py) for transforming parameters and [`example-hooks.py`](src/fastmcp/contrib/tool_transformer/example-hooks.py) for using pre-call hooks.

### YAML/JSON-based Transformation
To transform tools based on a YAML or JSON configuration:
1. Create a YAML or JSON file defining your tool overrides (see [`example-overrides-yaml.py`](src/fastmcp/contrib/tool_transformer/example-overrides-yaml.py) for structure).
2. Load this configuration using a function from [`loader.py`](src/fastmcp/contrib/tool_transformer/loader.py), such as [`overrides_from_yaml_file`](src/fastmcp/contrib/tool_transformer/loader.py:22). This will give you a dictionary mapping tool names to [`ToolOverride`](src/fastmcp/contrib/tool_transformer/models.py:219) objects.
3. Iterate through the tools you want to transform and call [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) for each, providing the original tool, the target server, and the corresponding [`ToolOverride`](src/fastmcp/contrib/tool_transformer/models.py:219) object.

Refer to [`example-overrides-yaml.py`](src/fastmcp/contrib/tool_transformer/example-overrides-yaml.py) for a practical demonstration.

## Key Components and Parameters

### `proxy_tool` and `transform_tool` Parameters:
Both [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) and [`transform_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:133) accept the following parameters:
- `tool`: The `FastMCPTool` instance to be transformed. (Required)
- `override`: A [`ToolOverride`](src/fastmcp/contrib/tool_transformer/models.py:219) object containing the overrides to apply. If provided, the individual override parameters below are ignored. (Optional)
- `name`: The new name for the transformed tool. If `None`, the original tool's name is used. (Optional)
- `description`: The new description for the transformed tool. If `None`, the original tool's description is used. (Optional)
- `parameter_overrides`: A list of [`ToolParameterTypes`](src/fastmcp/contrib/tool_transformer/models.py:186) objects defining overrides for existing parameters. (Optional)
- `hook_parameters`: A list of [`ToolParameterTypes`](src/fastmcp/contrib/tool_transformer/models.py:186) objects defining additional parameters for hooks. (Optional)
- `pre_call_hook`: An async callable matching [`PreToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:197). Executed before the original tool call. (Optional)
    - Receives: `tool_args: dict[str, Any]` (modifiable), `hook_args: dict[str, Any]`
- `post_call_hook`: An async callable matching [`PostToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:206). Executed after the original tool call. (Optional)
    - Receives: `response: list[TextContent | ImageContent | EmbeddedResource]`, `tool_args: dict[str, Any]`, `hook_args: dict[str, Any]`

Additionally, [`proxy_tool`](src/fastmcp/contrib/tool_transformer/tool_transformer.py:209) requires:
- `server`: The `FastMCP` server instance where the transformed tool will be added. (Required)

### Models
- [`ToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:16): A base class for defining tool parameters and their overrides. Subclasses like [`StringToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:150), [`IntToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:134), and [`BooleanToolParameter`](src/fastmcp/contrib/tool_transformer/models.py:158) are used for specific types. Key fields include:
    - `name`: Name of the parameter. (Required)
    - `description`: New description for the parameter. (Optional)
    - `required`: Boolean indicating if the parameter should be made required. Cannot make an already required parameter optional. (Optional)
    - `constant`: A constant value for the parameter. If set, this value always overrides any input. (Optional)
    - `default`: New default value for the parameter. (Optional)
- [`ToolOverride`](src/fastmcp/contrib/tool_transformer/models.py:219): A Pydantic model used to group transformation options for a single tool, particularly useful when loading configurations from YAML/JSON. Key fields include:
    - `name`: New name for the tool. (Optional)
    - `description`: New description for the tool. (Optional)
    - `parameter_overrides`: List of [`ToolParameterTypes`](src/fastmcp/contrib/tool_transformer/models.py:186) objects. (Optional)
    - `hook_parameters`: List of [`ToolParameterTypes`](src/fastmcp/contrib/tool_transformer/models.py:186) objects. (Optional)
    - `pre_call_hook`: An async callable matching [`PreToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:197). (Optional)
    - `post_call_hook`: An async callable matching [`PostToolCallHookProtocol`](src/fastmcp/contrib/tool_transformer/models.py:206). (Optional)

## Examples
- **Programmatic Transformation with Parameter Overrides:** See [`example-overrides.py`](src/fastmcp/contrib/tool_transformer/example-overrides.py)
- **Programmatic Transformation with Hooks:** See [`example-hooks.py`](src/fastmcp/contrib/tool_transformer/example-hooks.py)
- **YAML-based Transformation:** See [`example-overrides-yaml.py`](src/fastmcp/contrib/tool_transformer/example-overrides-yaml.py)