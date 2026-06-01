"""Mock-driven end-to-end tests of each LLM provider's code path.

These verify that the asterix_patch.py functions:
1. Build the correct API request shape per provider (right model, no rejected
   params for reasoning models, no tool_choice for Ollama, etc.)
2. Translate responses back to a usable LLMResponse object.

No live API calls — we inject mocked SDK clients so the tests run offline.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from asterix.core.llm_manager import LLMMessage, llm_manager
import oscar.core.asterix_patch  # noqa: F401 — applies patches on import


# ─── helpers ──────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _basic_messages():
    return [
        LLMMessage(role="system", content="You are concise."),
        LLMMessage(role="user", content="Hi"),
    ]


def _basic_tools():
    return [{
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }]


# ─── OpenAI: reasoning-model parameter handling ───────────────────────


@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "o3", "o4-mini"])
def test_openai_reasoning_models_use_max_completion_tokens(model):
    """Reasoning/GPT-5.x models must NOT receive temperature/max_tokens."""
    captured_kwargs = {}

    def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    llm_manager._openai_client = fake_client

    result = _run(llm_manager._call_openai(_basic_messages(), model=model, max_tokens=500))

    assert captured_kwargs["model"] == model
    assert "max_completion_tokens" in captured_kwargs, "reasoning model must use max_completion_tokens"
    assert "max_tokens" not in captured_kwargs, "reasoning model must not receive max_tokens"
    assert "temperature" not in captured_kwargs, "reasoning model must not receive temperature"
    assert captured_kwargs["max_completion_tokens"] == 500
    assert result.provider == "openai"
    assert result.model == model
    assert result.content == "ok"


@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4.1"])
def test_openai_legacy_models_use_max_tokens_and_temperature(model):
    """Non-reasoning models keep the classic temperature + max_tokens shape."""
    captured = {}
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: (captured.update(kwargs) or SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        ))
    )))
    llm_manager._openai_client = fake_client

    _run(llm_manager._call_openai(_basic_messages(), model=model, temperature=0.4, max_tokens=200))

    assert captured["model"] == model
    assert captured["max_tokens"] == 200
    assert captured["temperature"] == 0.4
    assert "max_completion_tokens" not in captured


def test_openai_tool_call_translation():
    """tool_calls in OpenAI response must round-trip into LLMResponse.raw_response."""
    tool_call = SimpleNamespace(
        id="call_abc",
        function=SimpleNamespace(name="git_status", arguments='{"verbose":true}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="", tool_calls=[tool_call]),
            finish_reason="tool_calls",
        )],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: response
    )))
    llm_manager._openai_client = fake_client

    result = _run(llm_manager._call_openai(_basic_messages(), model="gpt-4o", tools=_basic_tools()))

    assert result.finish_reason == "tool_calls"
    raw_msg = result.raw_response["choices"][0]["message"]
    assert raw_msg["tool_calls"][0]["function"]["name"] == "git_status"
    assert json.loads(raw_msg["tool_calls"][0]["function"]["arguments"]) == {"verbose": True}


# ─── Anthropic: full request + response shape ─────────────────────────


def test_anthropic_request_uses_top_level_system_and_input_schema():
    """Verify we hit the messages.create() signature Anthropic actually expects."""
    captured = {}

    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Working on it"),
            SimpleNamespace(type="tool_use", id="toolu_1", name="git_status", input={"verbose": True}),
        ],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=20, output_tokens=10),
    )

    fake_client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kwargs: (captured.update(kwargs) or response)
    ))
    llm_manager._anthropic_client = fake_client

    result = _run(llm_manager._call_anthropic(
        _basic_messages(),
        model="claude-sonnet-4-6",
        tools=_basic_tools(),
        tool_choice="auto",
    ))

    # Top-level args
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["max_tokens"] == 1024  # default
    assert captured["system"] == "You are concise."
    assert captured["temperature"] == 0.1
    # No "system" role in messages
    assert all(m["role"] != "system" for m in captured["messages"])
    # Tools use Anthropic's input_schema, not OpenAI's "parameters"
    assert captured["tools"][0]["input_schema"]["type"] == "object"
    assert "function" not in captured["tools"][0], "must not nest under 'function' like OpenAI"
    # tool_choice translated to {"type": "auto"}
    assert captured["tool_choice"] == {"type": "auto"}
    # Response translation
    assert result.provider == "anthropic"
    assert result.content == "Working on it"
    assert result.finish_reason == "tool_calls"
    assert result.usage["total_tokens"] == 30
    raw_tc = result.raw_response["choices"][0]["message"]["tool_calls"]
    assert raw_tc[0]["function"]["name"] == "git_status"
    assert json.loads(raw_tc[0]["function"]["arguments"]) == {"verbose": True}


@pytest.mark.parametrize("oai_tool_choice", [
    {"type": "function", "function": {"name": "git_status"}},   # legacy nested
    {"type": "function", "name": "git_status"},                  # current flat
])
def test_anthropic_specific_tool_choice_accepts_both_openai_shapes(oai_tool_choice):
    """Both legacy and current OpenAI tool_choice formats should map to Anthropic."""
    captured = {}
    fake_client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kwargs: (captured.update(kwargs) or SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        ))
    ))
    llm_manager._anthropic_client = fake_client

    _run(llm_manager._call_anthropic(
        _basic_messages(),
        model="claude-haiku-4-5-20251001",
        tools=_basic_tools(),
        tool_choice=oai_tool_choice,
    ))

    assert captured["tool_choice"] == {"type": "tool", "name": "git_status"}


# ─── Ollama: no tool_choice ──────────────────────────────────────────


def test_ollama_request_omits_tool_choice():
    """Ollama's OpenAI-compat layer rejects tool_choice — we must not send it."""
    captured = {}

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="hi", tool_calls=None),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
    )
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: (captured.update(kwargs) or fake_response)
    )))
    llm_manager._ollama_client = fake_client

    _run(llm_manager._call_ollama(
        _basic_messages(),
        model="llama3.3",
        tools=_basic_tools(),
        tool_choice="auto",  # caller may pass this — we must drop it
    ))

    assert captured["model"] == "llama3.3"
    assert "tools" in captured
    assert "tool_choice" not in captured, "Ollama OpenAI-compat does not support tool_choice"
    assert captured["max_tokens"] == 1024
    assert captured["temperature"] == 0.1


def test_ollama_tool_call_response_translation():
    """Ollama may return tool_calls in OpenAI shape — translate them through."""
    tool_call = SimpleNamespace(
        id="call_ol_1",
        function=SimpleNamespace(name="git_status", arguments='{}'),
    )
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="", tool_calls=[tool_call]),
            finish_reason="tool_calls",
        )],
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4),
    )
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: fake_response
    )))
    llm_manager._ollama_client = fake_client

    result = _run(llm_manager._call_ollama(_basic_messages(), model="qwen2.5-coder"))

    assert result.provider == "ollama"
    assert result.finish_reason == "tool_calls"
    raw_tc = result.raw_response["choices"][0]["message"]["tool_calls"]
    assert raw_tc[0]["function"]["name"] == "git_status"


# ─── Gemini: contents + tools shape ───────────────────────────────────


def test_gemini_request_sends_system_instruction_and_function_declarations(monkeypatch):
    """Translation helpers must split system→system_instruction and build tools properly."""
    captured = {}

    # Build a fake Gemini response with one function_call part.
    fake_part_text = SimpleNamespace(text=None, function_call=SimpleNamespace(
        name="git_status", args={"verbose": True}
    ))
    fake_response = SimpleNamespace(
        candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[fake_part_text])
        )],
        usage_metadata=SimpleNamespace(
            prompt_token_count=12, candidates_token_count=4, total_token_count=16,
        ),
    )

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return fake_response

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate))
    llm_manager._gemini_client = fake_client

    result = _run(llm_manager._call_gemini(
        _basic_messages(),
        model="gemini-3.5-flash",
        tools=_basic_tools(),
    ))

    assert captured["model"] == "gemini-3.5-flash"
    # The system message must be lifted into config.system_instruction.
    assert captured["config"].system_instruction == "You are concise."
    # Tools must be wrapped as [types.Tool(function_declarations=[...])]
    assert len(captured["config"].tools) == 1
    assert captured["config"].tools[0].function_declarations[0].name == "git_status"
    # contents must NOT contain a system entry — only the user message.
    assert all(c.role != "system" for c in captured["contents"])
    # Response translated
    assert result.provider == "gemini"
    assert result.model == "gemini-3.5-flash"
    assert result.finish_reason == "tool_calls"
    raw_tc = result.raw_response["choices"][0]["message"]["tool_calls"]
    assert raw_tc[0]["function"]["name"] == "git_status"
    assert json.loads(raw_tc[0]["function"]["arguments"]) == {"verbose": True}


# ─── complete() routing: provider+model resolution ────────────────────


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-5.4-mini"),
        ("anthropic", "claude-sonnet-4-6"),
        ("ollama", "llama3.3"),
        ("gemini", "gemini-3.5-flash"),
    ],
)
def test_complete_routes_to_correct_provider_call(provider, model, monkeypatch):
    """complete() with an explicit `provider` must dispatch to the matching _call_*."""
    called = {}

    async def fake_call(self, messages, model_arg, temperature=None, max_tokens=None, tools=None, tool_choice=None):
        called["provider"] = provider
        called["model"] = model_arg
        return SimpleNamespace(
            content="", model=model_arg, provider=provider,
            usage={"total_tokens": 0}, processing_time=0.01,
            finish_reason="stop", raw_response={},
        )

    # Patch all four targeted methods so any unintended dispatch raises clearly.
    for name in ("_call_openai", "_call_anthropic", "_call_ollama", "_call_gemini"):
        monkeypatch.setattr(type(llm_manager), name, fake_call, raising=True)

    _run(llm_manager.complete(messages="hi", provider=provider, model=model))
    assert called == {"provider": provider, "model": model}


def test_is_openai_reasoning_classifier():
    from oscar.core.asterix_patch import _is_openai_reasoning_model
    # Reasoning / GPT-5.x
    for m in ["gpt-5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5", "o3", "o3-mini", "o4-mini", "o1-mini"]:
        assert _is_openai_reasoning_model(m), f"{m} should be classified as reasoning"
    # Legacy
    for m in ["gpt-4o", "gpt-4.1", "gpt-3.5-turbo", "text-davinci-003"]:
        assert not _is_openai_reasoning_model(m), f"{m} should NOT be classified as reasoning"
