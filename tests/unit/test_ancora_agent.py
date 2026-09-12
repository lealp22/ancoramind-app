"""Unit tests for AncoraMind model factory and provider safeguards."""

from agno.db.postgres import PostgresDb
from agno.db.sqlite import SqliteDb
from agno.models.base import MessageData
from agno.models.message import Message
from agno.models.openai import OpenAIChat
from agno.models.response import ModelResponse
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

from src.agent.ancora_agent import (
    SafeOpenRouter,
    create_ancora_agent,
    create_db,
    create_model,
    create_model_from_settings,
)
from src.config import Settings


def test_create_db_uses_dedicated_agno_runtime_schema():
    db = create_db("postgresql+psycopg://user:pass@localhost/database")

    assert isinstance(db, PostgresDb)
    assert db.db_schema == "agno_runtime"


def test_create_db_defaults_to_sqlite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    db = create_db()

    assert isinstance(db, SqliteDb)
    assert db.session_table_name == "ancoramind_sessions"


def test_create_model_uses_safe_openrouter_adapter():
    model = create_model(
        provider="openrouter",
        model_id="minimax/minimax-m3:free",
        api_key="test-key",
    )

    assert isinstance(model, SafeOpenRouter)


def test_create_model_from_settings_resolves_openrouter_api_key():
    settings = Settings(
        llm_provider="openrouter",
        llm_model="minimax/minimax-m3:free",
        openrouter_api_key="test-key",
    )

    model = create_model_from_settings(settings)

    assert isinstance(model, SafeOpenRouter)
    assert model.id == "minimax/minimax-m3:free"


def test_create_model_from_settings_resolves_openai_api_key():
    settings = Settings(
        llm_provider="openai",
        llm_model="gpt-5.4-mini",
        openai_api_key="test-key",
    )

    model = create_model_from_settings(settings)

    assert isinstance(model, OpenAIChat)
    assert model.id == "gpt-5.4-mini"


def test_create_ancora_agent_applies_tool_call_limit():
    agent = create_ancora_agent(
        model="openai:gpt-4o-mini",
        tools=[],
        instructions=[],
        tool_call_limit=5,
    )

    assert agent.tool_call_limit == 5


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


def test_safe_openrouter_normalizes_only_malformed_tool_calls_to_none(caplog):
    response = ModelResponse(
        content="¡Hola! ¿En qué puedo ayudarte?",
        tool_calls=[
            {},
            {"id": "id-only"},
            {"id": "missing-name", "type": "function", "function": {}},
        ],
    )
    model = SafeOpenRouter(id="minimax/minimax-m3:free", api_key="test-key")
    assistant_message = Message(role="assistant")

    populated = model._populate_assistant_message(assistant_message, response)

    assert populated.content == "¡Hola! ¿En qué puedo ayudarte?"
    assert response.tool_calls is None
    assert populated.tool_calls is None
    assert "Dropped 3 malformed OpenRouter tool call(s)" in caplog.text


def test_safe_openrouter_drops_malformed_streaming_tool_calls(caplog):
    stream_data = MessageData(
        response_tool_calls=[
            ChoiceDeltaToolCall(index=0, id="id-only"),
            ChoiceDeltaToolCall(
                index=1,
                id="valid-call",
                type="function",
                function=ChoiceDeltaToolCallFunction(
                    name="find_vehicle",
                    arguments='{"reference":"6789XYZ"}',
                ),
            ),
        ]
    )
    model = SafeOpenRouter(id="minimax/minimax-m3:free", api_key="test-key")
    assistant_message = Message(role="assistant")

    model._populate_assistant_message_from_stream_data(
        assistant_message,
        stream_data,
    )

    assert assistant_message.tool_calls == [
        {
            "id": "valid-call",
            "type": "function",
            "function": {
                "name": "find_vehicle",
                "arguments": '{"reference":"6789XYZ"}',
            },
        }
    ]
    assert "Dropped 1 malformed streaming OpenRouter tool call(s)" in caplog.text


def test_safe_openrouter_normalizes_only_malformed_streaming_tool_calls_to_none(caplog):
    stream_data = MessageData(
        response_content="¡Hola! ¿En qué puedo ayudarte?",
        response_tool_calls=[ChoiceDeltaToolCall(index=0, id="id-only")],
    )
    model = SafeOpenRouter(id="minimax/minimax-m3:free", api_key="test-key")
    assistant_message = Message(role="assistant")

    model._populate_assistant_message_from_stream_data(
        assistant_message,
        stream_data,
    )

    assert assistant_message.content == "¡Hola! ¿En qué puedo ayudarte?"
    assert assistant_message.tool_calls is None
    assert "Dropped 1 malformed streaming OpenRouter tool call(s)" in caplog.text


def test_safe_openrouter_stops_stream_loop_after_only_malformed_tool_calls(monkeypatch):
    model = SafeOpenRouter(id="minimax/minimax-m3:free", api_key="test-key")
    request_count = 0

    def fake_invoke_stream(**_kwargs):
        nonlocal request_count
        request_count += 1
        if request_count > 1:
            raise AssertionError("Agno started another model request without a valid tool call")
        yield ModelResponse(
            content="¡Hola! ¿En qué puedo ayudarte?",
            tool_calls=[ChoiceDeltaToolCall(index=0, id="id-only")],
        )

    monkeypatch.setattr(model, "invoke_stream", fake_invoke_stream)
    messages = [Message(role="user", content="Hola")]

    list(model.response_stream(messages=messages, tools=[]))

    assert request_count == 1
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "¡Hola! ¿En qué puedo ayudarte?"
    assert messages[-1].tool_calls is None
