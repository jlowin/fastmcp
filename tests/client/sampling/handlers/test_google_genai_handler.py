from unittest.mock import MagicMock

import pytest

try:
    from google.genai import Client as GoogleGenaiClient  # type: ignore[import-untyped]
    from google.genai.types import (  # type: ignore[import-untyped]
        Candidate,
        FunctionCallingConfigMode,
        GenerateContentResponse,
        ModelContent,
        Part,
        UserContent,
    )
    from mcp.types import (
        CreateMessageResult,
        ModelHint,
        ModelPreferences,
        SamplingMessage,
        TextContent,
        ToolChoice,
    )

    from fastmcp.client.sampling.handlers.google_genai import (
        GoogleGenaiSamplingHandler,
        _convert_json_schema_to_google_schema,
        _convert_messages_to_google_genai_content,
        _convert_tool_choice_to_google_genai,
        _response_to_create_message_result,
    )

    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GOOGLE_GENAI_AVAILABLE, reason="google-genai not installed"
)


def test_convert_sampling_messages_to_google_genai_content():
    from mcp.types import SamplingMessage, TextContent

    msgs = _convert_messages_to_google_genai_content(
        messages=[
            SamplingMessage(
                role="user", content=TextContent(type="text", text="hello")
            ),
            SamplingMessage(
                role="assistant", content=TextContent(type="text", text="ok")
            ),
        ],
    )

    assert len(msgs) == 2
    assert isinstance(msgs[0], UserContent)
    assert isinstance(msgs[1], ModelContent)
    assert msgs[0].parts[0].text == "hello"
    assert msgs[1].parts[0].text == "ok"


def test_convert_to_google_genai_messages_raises_on_non_text():
    from mcp.types import SamplingMessage

    from fastmcp.utilities.types import Image

    with pytest.raises(ValueError):
        _convert_messages_to_google_genai_content(
            messages=[
                SamplingMessage(
                    role="user",
                    content=Image(data=b"abc").to_image_content(),
                )
            ],
        )


def test_get_model():
    mock_client = MagicMock(spec=GoogleGenaiClient)
    handler = GoogleGenaiSamplingHandler(
        default_model="fallback-model", client=mock_client
    )

    # Test with model hint
    prefs = ModelPreferences(hints=[ModelHint(name="gemini-2.0-flash-exp")])
    assert handler._get_model(prefs) == "gemini-2.0-flash-exp"

    # Test with None
    assert handler._get_model(None) == "fallback-model"

    # Test with empty hints
    prefs_empty = ModelPreferences(hints=[])
    assert handler._get_model(prefs_empty) == "fallback-model"


async def test_response_to_create_message_result():
    # Create a mock response
    mock_response = MagicMock(spec=GenerateContentResponse)
    mock_response.text = "HELPFUL CONTENT FROM GEMINI"

    result: CreateMessageResult = _response_to_create_message_result(
        response=mock_response, model="gemini-2.0-flash-exp"
    )
    assert result == CreateMessageResult(
        content=TextContent(type="text", text="HELPFUL CONTENT FROM GEMINI"),
        role="assistant",
        model="gemini-2.0-flash-exp",
    )


def test_convert_tool_choice_to_google_genai():
    # Test auto mode
    result = _convert_tool_choice_to_google_genai(ToolChoice(mode="auto"))
    assert result.function_calling_config.mode == FunctionCallingConfigMode.AUTO

    # Test required mode
    result = _convert_tool_choice_to_google_genai(ToolChoice(mode="required"))
    assert result.function_calling_config.mode == FunctionCallingConfigMode.ANY

    # Test none mode
    result = _convert_tool_choice_to_google_genai(ToolChoice(mode="none"))
    assert result.function_calling_config.mode == FunctionCallingConfigMode.NONE

    # Test None (defaults to auto)
    result = _convert_tool_choice_to_google_genai(None)
    assert result.function_calling_config.mode == FunctionCallingConfigMode.AUTO


def test_convert_json_schema_to_google_schema():
    # Test basic types
    assert _convert_json_schema_to_google_schema({"type": "string"}) == {
        "type": "STRING"
    }
    assert _convert_json_schema_to_google_schema({"type": "integer"}) == {
        "type": "INTEGER"
    }
    assert _convert_json_schema_to_google_schema({"type": "boolean"}) == {
        "type": "BOOLEAN"
    }

    # Test with description
    assert _convert_json_schema_to_google_schema(
        {"type": "string", "description": "A string field"}
    ) == {"type": "STRING", "description": "A string field"}

    # Test nullable type (anyOf with null)
    result = _convert_json_schema_to_google_schema(
        {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "Nullable"}
    )
    assert result == {"type": "STRING", "nullable": True, "description": "Nullable"}

    # Test array
    result = _convert_json_schema_to_google_schema(
        {"type": "array", "items": {"type": "string"}}
    )
    assert result == {"type": "ARRAY", "items": {"type": "STRING"}}

    # Test object
    result = _convert_json_schema_to_google_schema(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
    )
    assert result == {
        "type": "OBJECT",
        "properties": {"name": {"type": "STRING"}, "age": {"type": "INTEGER"}},
        "required": ["name"],
    }
