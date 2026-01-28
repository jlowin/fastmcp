"""Google GenAI sampling handler with tool support for FastMCP 3.0."""

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

try:
    from google.genai import Client as GoogleGenaiClient
    from google.genai.types import (
        Candidate,
        Content,
        FunctionCall,
        FunctionCallingConfig,
        FunctionCallingConfigMode,
        FunctionDeclaration,
        FunctionResponse,
        GenerateContentConfig,
        GenerateContentResponse,
        ModelContent,
        Part,
        ThinkingConfig,
        ToolConfig,
        UserContent,
    )
    from google.genai.types import Tool as GoogleTool
except ImportError as e:
    raise ImportError(
        "The `google-genai` package is not installed. "
        "Install it with `pip install fastmcp[google-genai]` or add `google-genai` "
        "to your dependencies."
    ) from e

from mcp import ClientSession, ServerSession
from mcp.shared.context import LifespanContextT, RequestContext
from mcp.types import (
    AudioContent,
    CreateMessageResult,
    CreateMessageResultWithTools,
    ImageContent,
    ModelPreferences,
    SamplingMessage,
    SamplingMessageContentBlock,
    StopReason,
    TextContent,
    ToolChoice,
    ToolResultContent,
    ToolUseContent,
)
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import Tool as MCPTool

__all__ = ["GoogleGenaiSamplingHandler"]


class GoogleGenaiSamplingHandler:
    """Sampling handler that uses the Google GenAI API with tool support.

    Example:
        ```python
        from google.genai import Client
        from fastmcp import FastMCP
        from fastmcp.client.sampling.handlers.google_genai import (
            GoogleGenaiSamplingHandler,
        )

        handler = GoogleGenaiSamplingHandler(
            default_model="gemini-2.0-flash",
            client=Client(),
        )

        server = FastMCP(sampling_handler=handler)
        ```
    """

    def __init__(
        self,
        default_model: str,
        client: GoogleGenaiClient | None = None,
        thinking_budget: int | None = None,
    ) -> None:
        self.client: GoogleGenaiClient = client or GoogleGenaiClient()
        self.default_model: str = default_model
        self.thinking_budget: int | None = thinking_budget

    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: RequestContext[ServerSession, LifespanContextT]
        | RequestContext[ClientSession, LifespanContextT],
    ) -> CreateMessageResult | CreateMessageResultWithTools:
        contents: list[Content] = _convert_messages_to_google_genai_content(messages)

        # Convert MCP tools to Google GenAI format
        google_tools: list[GoogleTool] | None = None
        tool_config: ToolConfig | None = None

        if params.tools:
            google_tools = [
                _convert_tool_to_google_genai(tool) for tool in params.tools
            ]
            tool_config = _convert_tool_choice_to_google_genai(params.toolChoice)

        # Select the model based on preferences
        selected_model = self._get_model(model_preferences=params.modelPreferences)

        # Configure thinking if a budget is specified
        thinking_config = (
            ThinkingConfig(thinking_budget=self.thinking_budget)
            if self.thinking_budget is not None
            else None
        )

        response: GenerateContentResponse = (
            await self.client.aio.models.generate_content(
                model=selected_model,
                contents=contents,
                config=GenerateContentConfig(
                    system_instruction=params.systemPrompt,
                    temperature=params.temperature,
                    max_output_tokens=params.maxTokens,
                    stop_sequences=params.stopSequences,
                    thinking_config=thinking_config,
                    tools=google_tools,  # ty: ignore[invalid-argument-type]
                    tool_config=tool_config,
                ),
            )
        )

        # Return appropriate result type based on whether tools were provided
        if params.tools:
            return _response_to_result_with_tools(response, selected_model)
        return _response_to_create_message_result(response, selected_model)

    def _get_model(self, model_preferences: ModelPreferences | None) -> str:
        if model_preferences and model_preferences.hints:
            for hint in model_preferences.hints:
                if hint.name:
                    return hint.name
        return self.default_model


def _convert_tool_to_google_genai(tool: MCPTool) -> GoogleTool:
    """Convert an MCP Tool to Google GenAI format."""
    input_schema: dict[str, Any] = tool.inputSchema
    properties: dict[str, Any] = input_schema.get("properties", {})
    required: list[str] = input_schema.get("required", [])

    # Build parameters schema with Google's type format
    google_properties: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        google_properties[prop_name] = _convert_json_schema_to_google_schema(
            dict(prop_schema)
        )

    return GoogleTool(
        function_declarations=[
            FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters_json_schema={
                    "type": "OBJECT",
                    "properties": google_properties,
                    "required": required,
                },
            )
        ]
    )


def _convert_json_schema_to_google_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert JSON Schema to Google GenAI Schema format.

    Handles:
    - Basic types (string, integer, number, boolean, array, object)
    - Nullable types via anyOf with null type
    - Nested objects and arrays
    """
    result: dict[str, Any] = {}

    # Handle anyOf for nullable types (e.g., anyOf: [{type: string}, {type: null}])
    if "anyOf" in schema:
        any_of_types = schema["anyOf"]
        non_null_types = [t for t in any_of_types if t.get("type") != "null"]
        has_null = len(non_null_types) < len(any_of_types)

        if non_null_types:
            # Recursively convert the non-null type
            non_null_schema = non_null_types[0]
            result = _convert_json_schema_to_google_schema(non_null_schema)

        if has_null:
            result["nullable"] = True

        # Preserve description from parent schema
        if "description" in schema:
            result["description"] = schema["description"]

        return result

    schema_type = schema.get("type")

    # Handle type arrays (e.g., ["string", "null"]) for nullable types
    if isinstance(schema_type, list):
        non_null_types = [t for t in schema_type if t != "null"]
        has_null = len(non_null_types) < len(schema_type)
        schema_type = non_null_types[0] if non_null_types else None
        if has_null:
            result["nullable"] = True

    if isinstance(schema_type, str):
        type_map: dict[str, str] = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
        }
        result["type"] = type_map.get(schema_type, "STRING")

    if "description" in schema:
        result["description"] = schema["description"]

    if "enum" in schema:
        result["enum"] = schema["enum"]

    if "items" in schema:
        result["items"] = _convert_json_schema_to_google_schema(dict(schema["items"]))

    if "properties" in schema:
        result["properties"] = {
            str(k): _convert_json_schema_to_google_schema(dict(v))
            for k, v in dict(schema["properties"]).items()
        }

    if "required" in schema:
        result["required"] = schema["required"]

    return result


def _convert_tool_choice_to_google_genai(tool_choice: ToolChoice | None) -> ToolConfig:
    """Convert MCP ToolChoice to Google GenAI ToolConfig."""
    if tool_choice is None:
        return ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode=FunctionCallingConfigMode.AUTO
            )
        )

    if tool_choice.mode == "required":
        return ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode=FunctionCallingConfigMode.ANY
            )
        )
    if tool_choice.mode == "none":
        return ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode=FunctionCallingConfigMode.NONE
            )
        )

    # Default to AUTO for "auto" or any other value
    return ToolConfig(
        function_calling_config=FunctionCallingConfig(
            mode=FunctionCallingConfigMode.AUTO
        )
    )


def _sampling_content_to_google_genai_part(
    content: TextContent
    | ImageContent
    | AudioContent
    | ToolUseContent
    | ToolResultContent,
) -> Part:
    """Convert MCP content to Google GenAI Part."""
    if isinstance(content, TextContent):
        return Part(text=content.text)

    if isinstance(content, ToolUseContent):
        return Part(
            function_call=FunctionCall(
                name=content.name,
                args=content.input,
            ),
            thought_signature=b"skip_thought_signature_validator",
        )

    if isinstance(content, ToolResultContent):
        # Extract text from tool result content
        result_parts: list[str] = []
        if content.content:
            for item in content.content:
                if isinstance(item, TextContent):
                    result_parts.append(item.text)
                else:
                    msg = f"Unsupported tool result content type: {type(item).__name__}"
                    raise ValueError(msg)
        result_text = "".join(result_parts)

        # Extract function name from toolUseId
        # Our IDs are formatted as "{function_name}_{uuid8}", so extract the name.
        # Note: This is a limitation of MCP's ToolResultContent which only carries
        # toolUseId, while Google's FunctionResponse requires the function name.
        tool_use_id = content.toolUseId
        if "_" in tool_use_id:
            # Split and rejoin all but the last part (the UUID suffix)
            parts = tool_use_id.rsplit("_", 1)
            function_name = parts[0]
        else:
            # Fallback: use the full ID as the name
            function_name = tool_use_id

        return Part(
            function_response=FunctionResponse(
                name=function_name,
                response={"result": result_text},
            )
        )

    msg = f"Unsupported content type: {type(content)}"
    raise ValueError(msg)


def _convert_messages_to_google_genai_content(
    messages: Sequence[SamplingMessage],
) -> list[Content]:
    """Convert MCP messages to Google GenAI content."""
    google_messages: list[Content] = []

    for message in messages:
        content = message.content

        # Handle list content (tool calls + results)
        if isinstance(content, list):
            parts: list[Part] = []
            for item in content:
                parts.append(_sampling_content_to_google_genai_part(item))

            if message.role == "user":
                google_messages.append(UserContent(parts=parts))
            elif message.role == "assistant":
                google_messages.append(ModelContent(parts=parts))
            else:
                msg = f"Invalid message role: {message.role}"
                raise ValueError(msg)
            continue

        # Handle single content item
        part = _sampling_content_to_google_genai_part(content)

        if message.role == "user":
            google_messages.append(UserContent(parts=[part]))
        elif message.role == "assistant":
            google_messages.append(ModelContent(parts=[part]))
        else:
            msg = f"Invalid message role: {message.role}"
            raise ValueError(msg)

    return google_messages


def _get_candidate_from_response(response: GenerateContentResponse) -> Candidate:
    """Extract the first candidate from a response."""
    if response.candidates and response.candidates[0]:
        return response.candidates[0]
    msg = "No candidate in response from completion."
    raise ValueError(msg)


def _response_to_create_message_result(
    response: GenerateContentResponse,
    model: str,
) -> CreateMessageResult:
    """Convert Google GenAI response to CreateMessageResult (no tools)."""
    if not (text := response.text):
        candidate = _get_candidate_from_response(response)
        msg = f"No content in response: {candidate.finish_reason}"
        raise ValueError(msg)

    return CreateMessageResult(
        content=TextContent(type="text", text=text),
        role="assistant",
        model=model,
    )


def _response_to_result_with_tools(
    response: GenerateContentResponse,
    model: str,
) -> CreateMessageResultWithTools:
    """Convert Google GenAI response to CreateMessageResultWithTools."""
    candidate = _get_candidate_from_response(response)

    # Determine stop reason and check for function calls
    stop_reason: StopReason
    finish_reason = candidate.finish_reason
    has_function_calls = False

    if candidate.content and candidate.content.parts:
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                has_function_calls = True
                break

    if has_function_calls:
        stop_reason = "toolUse"
    elif finish_reason == "STOP":
        stop_reason = "endTurn"
    elif finish_reason == "MAX_TOKENS":
        stop_reason = "maxTokens"
    else:
        stop_reason = "endTurn"

    # Build content list
    content: list[SamplingMessageContentBlock] = []

    if candidate.content and candidate.content.parts:
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                content.append(TextContent(type="text", text=part.text))
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                fc_name: str = fc.name or "unknown"
                content.append(
                    ToolUseContent(
                        type="tool_use",
                        id=f"{fc_name}_{uuid4().hex[:8]}",  # Generate unique ID
                        name=fc_name,
                        input=dict(fc.args) if fc.args else {},
                    )
                )

    if not content:
        raise ValueError("No content in response from completion")

    return CreateMessageResultWithTools(
        content=content,
        role="assistant",
        model=model,
        stopReason=stop_reason,
    )
