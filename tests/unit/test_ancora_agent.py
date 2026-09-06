"""Unit tests for AncoraMind model factory and provider safeguards."""

from agno.models.message import Message
from agno.models.response import ModelResponse

from src.agent.ancora_agent import SafeOpenRouter, create_model


def test_create_model_uses_safe_openrouter_adapter():
    model = create_model(
        provider="openrouter",
        model_id="minimax/minimax-m3:free",
        api_key="test-key",
    )

    assert isinstance(model, SafeOpenRouter)


def test_safe_openrouter_drops_malformed_tool_calls_before_persistence(caplog):
    response = ModelResponse(
        tool_calls=[
            {},
            {"id": "id-only"},
            {"id": "missing-name", "type": "function", "function": {}},
            {
                "id": "valid-call",
                "type": "function",
                "function": {
                    "name": "propose_vehicle",
                    "arguments": '{"make":"Ford","model":"Mondeo"}',
                },
            },
        ]
    )
    model = SafeOpenRouter(id="minimax/minimax-m3:free", api_key="test-key")
    assistant_message = Message(role="assistant")

    populated = model._populate_assistant_message(assistant_message, response)

    assert populated.tool_calls == [
        {
            "id": "valid-call",
            "type": "function",
            "function": {
                "name": "propose_vehicle",
                "arguments": '{"make":"Ford","model":"Mondeo"}',
            },
        }
    ]
    assert "Dropped 3 malformed OpenRouter tool call(s)" in caplog.text
