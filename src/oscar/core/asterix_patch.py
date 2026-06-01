"""
Asterix v0.2.1 Runtime Patch — Multi-provider LLM support for OSCAR

Monkey-patches Asterix to:
- Route the existing ``gemini`` provider through Vertex AI (ADC) by default,
  with any catalog model id (gemini-2.5-flash / pro / flash-lite / 2.0-flash).
- Add ``anthropic`` (Claude opus/sonnet/haiku 4.x) as a first-class provider.
- Add ``ollama`` (local llama3.x / qwen-coder / deepseek-coder) via the
  OpenAI-compatible endpoint at ``http://localhost:11434/v1``.
- Honour OSCAR's primary/fallback provider+model selection from settings.

Asterix natively supports ``groq``, ``openai`` and (since 0.2.1) ``gemini``.
We override the gemini path to prefer Vertex AI ADC over an API key when both
are present, and we add the two new providers via the same monkey-patch surface.

Patched symbols:
- ``LLMConfig.__post_init__``
- ``LLMProviderManager.__init__``
- ``LLMProviderManager._ensure_clients_initialized``
- ``LLMProviderManager._call_gemini``
- ``LLMProviderManager._call_anthropic`` (new)
- ``LLMProviderManager._call_ollama`` (new)
- ``LLMProviderManager.complete``
- ``LLMProviderManager._select_provider``
- ``LLMProviderManager.get_performance_metrics``
- the ``llm_manager`` singleton's per-provider tracking dicts

If you upgrade ``asterix-agent``, audit each patched symbol against the new
version before bumping the pin.
"""

from __future__ import annotations

import json
import os
import time
import logging
from typing import List, Optional, Any, Dict, Union

from google.genai import Client as GeminiClient, types as genai_types

from asterix.core.config import LLMConfig
from asterix.core.llm_manager import (
    LLMProviderManager,
    LLMResponse,
    LLMMessage,
    LLMError,
)

from oscar.config.providers import (
    PROVIDERS,
    selected_provider,
    selected_model,
    selected_fallback_provider,
    selected_fallback_model,
)

logger = logging.getLogger(__name__)

_patched = False

ALL_PROVIDERS = ["groq", "openai", "gemini", "anthropic", "ollama"]

# Vertex AI project config — reads from env, falls back to the historical default
_VERTEX_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("VERTEX_PROJECT", "oscar-490517"))
_VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("VERTEX_LOCATION", "us-central1"))

_OLLAMA_BASE_URL = os.getenv("OSCAR_OLLAMA_BASE_URL", "http://localhost:11434/v1")

# OpenAI models that REJECT temperature/top_p/max_tokens and require
# max_completion_tokens (per OpenAI's reasoning-model docs). Matched as
# substrings so "o3", "o3-mini", "o4-mini", "gpt-5.5-something" all hit.
_OPENAI_REASONING_PREFIXES = (
    "o1", "o3", "o4",
    "gpt-5", "gpt-5.4", "gpt-5.5",
)


def _is_openai_reasoning_model(model: str) -> bool:
    name = (model or "").lower()
    return any(name == p or name.startswith(p + "-") or name.startswith(p + ".") for p in _OPENAI_REASONING_PREFIXES)


# ---------------------------------------------------------------------------
# Gemini message translation helpers
# ---------------------------------------------------------------------------

def _gemini_translate_messages(messages):
    """Translate OpenAI-format messages to Gemini Contents + system_instruction."""
    system_instruction = None
    contents = []

    for msg in messages:
        if not isinstance(msg, dict):
            msg = {"role": msg.role, "content": msg.content}

        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            system_instruction = content
            continue

        if role == "user":
            contents.append(
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=content)],
                )
            )
            continue

        if role == "assistant":
            parts = []
            if content:
                parts.append(genai_types.Part.from_text(text=content))
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                parts.append(genai_types.Part.from_function_call(name=name, args=args))
            if parts:
                contents.append(genai_types.Content(role="model", parts=parts))
            continue

        if role == "tool":
            fn_name = msg.get("name", "unknown")
            part = genai_types.Part.from_function_response(
                name=fn_name, response={"result": content}
            )
            if (
                contents
                and contents[-1].role == "user"
                and contents[-1].parts
                and any(
                    getattr(p, "function_response", None) is not None
                    for p in contents[-1].parts
                )
            ):
                contents[-1].parts.append(part)
            else:
                contents.append(genai_types.Content(role="user", parts=[part]))
            continue

    return system_instruction, contents


def _gemini_translate_tools(tools):
    if not tools:
        return None
    declarations = []
    for tool_def in tools:
        fn = tool_def.get("function", {})
        declarations.append(
            genai_types.FunctionDeclaration(
                name=fn.get("name", ""),
                description=fn.get("description", ""),
                parameters=fn.get("parameters"),
            )
        )
    if not declarations:
        return None
    return genai_types.Tool(function_declarations=declarations)


def _gemini_translate_response(response, processing_time, model_id):
    text_parts = []
    function_calls = []
    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if getattr(part, "text", None) is not None:
                    text_parts.append(part.text)
                if getattr(part, "function_call", None) is not None:
                    function_calls.append(part.function_call)

    content = "\n".join(text_parts) if text_parts else ""
    has_tool_calls = len(function_calls) > 0
    finish_reason = "tool_calls" if has_tool_calls else "stop"

    tool_calls = None
    if has_tool_calls:
        tool_calls = []
        for i, fc in enumerate(function_calls):
            tool_calls.append({
                "id": f"call_{fc.name}_{int(time.time() * 1000)}_{i}",
                "type": "function",
                "function": {
                    "name": fc.name,
                    "arguments": json.dumps(dict(fc.args) if fc.args else {}),
                },
            })

    message_dict = {"content": content}
    if tool_calls:
        message_dict["tool_calls"] = tool_calls

    raw_response = {
        "choices": [
            {"message": message_dict, "finish_reason": finish_reason}
        ]
    }

    usage_meta = getattr(response, "usage_metadata", None)
    usage = {
        "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0) or 0,
        "completion_tokens": getattr(usage_meta, "candidates_token_count", 0) or 0,
        "total_tokens": getattr(usage_meta, "total_token_count", 0) or 0,
    }

    return LLMResponse(
        content=content,
        model=model_id,
        provider="gemini",
        usage=usage,
        processing_time=processing_time,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------

def _anthropic_translate_messages(messages):
    """Translate OpenAI-format messages to Anthropic format.

    Returns (system_str | None, anthropic_messages: list).
    """
    system_text = None
    out: List[dict] = []

    # Track open tool_use ids so we know how to attach tool_result blocks.
    pending_tool_use_by_name: Dict[str, str] = {}

    for msg in messages:
        if not isinstance(msg, dict):
            msg = {"role": getattr(msg, "role", "user"), "content": getattr(msg, "content", "") or ""}

        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            # Anthropic uses a top-level "system" arg, not a system message.
            system_text = (system_text + "\n" + content) if system_text else content
            continue

        if role == "user":
            out.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            blocks: List[dict] = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tu_id = tc.get("id") or f"toolu_{int(time.time() * 1000)}_{name}"
                blocks.append({
                    "type": "tool_use",
                    "id": tu_id,
                    "name": name,
                    "input": args,
                })
                pending_tool_use_by_name[name] = tu_id
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            tool_name = msg.get("name") or ""
            tool_call_id = msg.get("tool_call_id") or pending_tool_use_by_name.get(tool_name, "")
            block = {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content if isinstance(content, str) else json.dumps(content),
            }
            # Merge consecutive tool_results into one user message.
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

    return system_text, out


def _anthropic_translate_tools(tools):
    if not tools:
        return None
    result = []
    for tool_def in tools:
        fn = tool_def.get("function", {})
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", "") or "",
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return result


def _anthropic_translate_response(response, processing_time, model_id):
    text_parts: List[str] = []
    tool_calls_payload: List[dict] = []

    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(getattr(block, "text", "") or "")
        elif block_type == "tool_use":
            tool_calls_payload.append({
                "id": getattr(block, "id", "") or f"toolu_{int(time.time() * 1000)}",
                "type": "function",
                "function": {
                    "name": getattr(block, "name", "") or "",
                    "arguments": json.dumps(dict(getattr(block, "input", {}) or {})),
                },
            })

    content = "\n".join(text_parts) if text_parts else ""
    has_tool_calls = bool(tool_calls_payload)
    finish_reason = "tool_calls" if has_tool_calls else (getattr(response, "stop_reason", None) or "stop")

    message_dict = {"content": content}
    if has_tool_calls:
        message_dict["tool_calls"] = tool_calls_payload

    raw_response = {
        "choices": [
            {"message": message_dict, "finish_reason": finish_reason}
        ]
    }

    usage = getattr(response, "usage", None)
    usage_dict = {
        "prompt_tokens": getattr(usage, "input_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0),
    }

    return LLMResponse(
        content=content,
        model=model_id,
        provider="anthropic",
        usage=usage_dict,
        processing_time=processing_time,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def apply_patches() -> None:
    """Apply all multi-provider patches to Asterix v0.2.1. Idempotent."""
    global _patched
    if _patched:
        return

    # ------------------------------------------------------------------
    # 1. Patch LLMConfig.__post_init__ to allow all supported providers
    # ------------------------------------------------------------------
    def patched_post_init(self):
        if self.provider not in ALL_PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("Max tokens must be positive")

    LLMConfig.__post_init__ = patched_post_init

    # ------------------------------------------------------------------
    # 2. Patch LLMProviderManager.__init__ for full provider tracking
    # ------------------------------------------------------------------
    _original_init = LLMProviderManager.__init__

    def patched_init(self):
        _original_init(self)
        self._gemini_client = None
        self._anthropic_client = None
        self._ollama_client = None
        for provider in ALL_PROVIDERS:
            self._operation_count[provider] = self._operation_count.get(provider, 0)
            self._total_processing_time[provider] = self._total_processing_time.get(provider, 0.0)
            self._total_tokens[provider] = self._total_tokens.get(provider, 0)
            self._error_count[provider] = self._error_count.get(provider, 0)
            self._provider_failures[provider] = self._provider_failures.get(provider, 0)

        # Honour OSCAR's selected primary/fallback providers.
        self._primary_provider = selected_provider()
        fallback = selected_fallback_provider()
        if fallback == self._primary_provider:
            # Fall back to the historical defaults when the user didn't pick a
            # distinct fallback — otherwise a single provider failure can't recover.
            for candidate in ("gemini", "groq", "openai"):
                if candidate != self._primary_provider:
                    fallback = candidate
                    break
        self._fallback_provider = fallback

    LLMProviderManager.__init__ = patched_init

    # ------------------------------------------------------------------
    # 3. Patch _ensure_clients_initialized to lazy-init all providers
    # ------------------------------------------------------------------
    _original_ensure = LLMProviderManager._ensure_clients_initialized

    async def patched_ensure_clients_initialized(self):
        await _original_ensure(self)

        # Gemini — prefer Vertex AI ADC, fall back to an explicit API key.
        if self._gemini_client is None:
            try:
                if os.getenv("GOOGLE_CLOUD_PROJECT") or _VERTEX_PROJECT:
                    self._gemini_client = GeminiClient(
                        vertexai=True,
                        project=_VERTEX_PROJECT,
                        location=_VERTEX_LOCATION,
                    )
                elif os.getenv("GEMINI_API_KEY"):
                    self._gemini_client = GeminiClient(api_key=os.getenv("GEMINI_API_KEY"))
            except Exception as e:  # pragma: no cover — surfaced at call-time
                logger.warning("Failed to initialise Gemini client: %s", e)

        # Anthropic
        if self._anthropic_client is None and os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # local import keeps it optional
                self._anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            except Exception as e:
                logger.warning("Failed to initialise Anthropic client: %s", e)

        # Ollama — uses the OpenAI SDK against a local server.
        if self._ollama_client is None:
            try:
                import openai
                self._ollama_client = openai.OpenAI(
                    base_url=_OLLAMA_BASE_URL,
                    api_key="ollama",  # ignored by the server but required by the SDK
                )
            except Exception as e:
                logger.warning("Failed to initialise Ollama client: %s", e)

    LLMProviderManager._ensure_clients_initialized = patched_ensure_clients_initialized

    # ------------------------------------------------------------------
    # 4. Add _call_gemini (overrides Asterix's native version so that any
    #    catalog model id flows through Vertex AI cleanly)
    # ------------------------------------------------------------------
    async def _call_gemini(
        self,
        messages: List[LLMMessage],
        model: str = "gemini-2.5-flash",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
    ) -> LLMResponse:
        if not self._gemini_client:
            raise LLMError("Gemini client not initialized (set GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY)")

        start_time = time.time()
        try:
            system_instruction, gemini_contents = _gemini_translate_messages(messages)
            gemini_tool = _gemini_translate_tools(tools)

            config = genai_types.GenerateContentConfig(
                temperature=temperature or 0.1,
                max_output_tokens=max_tokens or 1000,
            )
            if system_instruction:
                config.system_instruction = system_instruction
            if gemini_tool:
                config.tools = [gemini_tool]

            response = self._gemini_client.models.generate_content(
                model=model,
                contents=gemini_contents,
                config=config,
            )

            processing_time = time.time() - start_time
            result = _gemini_translate_response(response, processing_time, model)

            self._operation_count["gemini"] += 1
            self._total_processing_time["gemini"] += processing_time
            self._total_tokens["gemini"] += result.usage["total_tokens"]
            self._provider_failures["gemini"] = 0

            logger.info(
                "Gemini completion (%s): %s tokens in %.3fs",
                model, result.usage["total_tokens"], processing_time,
            )
            return result
        except Exception as e:
            self._error_count["gemini"] += 1
            self._provider_failures["gemini"] += 1
            logger.error("Gemini API error: %s", e)
            raise LLMError(f"Gemini error: {e}")

    LLMProviderManager._call_gemini = _call_gemini

    # ------------------------------------------------------------------
    # 5. Add _call_anthropic
    # ------------------------------------------------------------------
    async def _call_anthropic(
        self,
        messages: List[LLMMessage],
        model: str = "claude-sonnet-4-6",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
    ) -> LLMResponse:
        if not self._anthropic_client:
            raise LLMError("Anthropic client not initialized (set ANTHROPIC_API_KEY)")

        start_time = time.time()
        try:
            system_text, anthropic_messages = _anthropic_translate_messages(messages)
            anthropic_tools = _anthropic_translate_tools(tools)

            kwargs = {
                "model": model,
                "messages": anthropic_messages,
                "max_tokens": max_tokens or 1024,
                "temperature": temperature or 0.1,
            }
            if system_text:
                kwargs["system"] = system_text
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
                # Map OpenAI-style tool_choice values to Anthropic's shape.
                if isinstance(tool_choice, str):
                    if tool_choice in {"auto", "any"}:
                        kwargs["tool_choice"] = {"type": tool_choice}
                    elif tool_choice == "none":
                        # Anthropic doesn't surface a 'none' choice; just omit tools.
                        kwargs.pop("tools", None)
                elif isinstance(tool_choice, dict):
                    # Accept both OpenAI tool_choice shapes:
                    #   {"type":"function","function":{"name":"x"}}  (legacy)
                    #   {"type":"function","name":"x"}                (current docs)
                    nested = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
                    name = nested.get("name") or tool_choice.get("name")
                    if name:
                        kwargs["tool_choice"] = {"type": "tool", "name": name}

            response = self._anthropic_client.messages.create(**kwargs)
            processing_time = time.time() - start_time
            result = _anthropic_translate_response(response, processing_time, model)

            self._operation_count["anthropic"] += 1
            self._total_processing_time["anthropic"] += processing_time
            self._total_tokens["anthropic"] += result.usage["total_tokens"]
            self._provider_failures["anthropic"] = 0

            logger.info(
                "Anthropic completion (%s): %s tokens in %.3fs",
                model, result.usage["total_tokens"], processing_time,
            )
            return result
        except Exception as e:
            self._error_count["anthropic"] += 1
            self._provider_failures["anthropic"] += 1
            logger.error("Anthropic API error: %s", e)
            raise LLMError(f"Anthropic error: {e}")

    LLMProviderManager._call_anthropic = _call_anthropic

    # ------------------------------------------------------------------
    # 5b. Override _call_openai so that GPT-5.x / o3 / o4-mini work
    # ------------------------------------------------------------------
    # Asterix's native _call_openai only knows about a small subset of
    # reasoning models (gpt-5-mini, o1-mini, o1-preview). It would send
    # `temperature` and `max_tokens` to gpt-5/gpt-5.4/gpt-5.5/o3/o4-mini
    # which all reject those parameters. We replace it with a version
    # that consults _is_openai_reasoning_model().
    async def _call_openai(
        self,
        messages: List[LLMMessage],
        model: str = "gpt-5.4-mini",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
    ) -> LLMResponse:
        if not self._openai_client:
            raise LLMError("OpenAI client not initialized (set OPENAI_API_KEY)")

        start_time = time.time()
        try:
            openai_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    openai_messages.append(msg)
                else:
                    openai_messages.append({"role": msg.role, "content": msg.content})

            api_params: Dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
                "stream": False,
            }

            if _is_openai_reasoning_model(model):
                # Reasoning models: max_completion_tokens only, no temperature.
                api_params["max_completion_tokens"] = max_tokens or 1024
            else:
                api_params["temperature"] = temperature if temperature is not None else 0.1
                api_params["max_tokens"] = max_tokens or 1024

            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = tool_choice or "auto"

            response = self._openai_client.chat.completions.create(**api_params)
            processing_time = time.time() - start_time

            choice = response.choices[0].message
            content = choice.content or ""
            finish_reason = response.choices[0].finish_reason or "stop"

            tool_calls = None
            raw_tool_calls = getattr(choice, "tool_calls", None) or []
            if raw_tool_calls:
                tool_calls = []
                for tc in raw_tool_calls:
                    fn = getattr(tc, "function", None)
                    if fn is None:
                        continue
                    arguments = getattr(fn, "arguments", "{}")
                    tool_calls.append({
                        "id": getattr(tc, "id", "") or f"call_{int(time.time() * 1000)}",
                        "type": "function",
                        "function": {
                            "name": getattr(fn, "name", "") or "",
                            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
                        },
                    })
                finish_reason = "tool_calls"

            message_dict = {"content": content}
            if tool_calls:
                message_dict["tool_calls"] = tool_calls
            raw_response = {
                "choices": [
                    {"message": message_dict, "finish_reason": finish_reason}
                ]
            }

            usage_obj = response.usage if hasattr(response, "usage") and response.usage else None
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
            }

            result = LLMResponse(
                content=content,
                model=model,
                provider="openai",
                usage=usage,
                processing_time=processing_time,
                finish_reason=finish_reason,
                raw_response=raw_response,
            )

            self._operation_count["openai"] += 1
            self._total_processing_time["openai"] += processing_time
            self._total_tokens["openai"] += usage["total_tokens"]
            self._provider_failures["openai"] = 0

            logger.info(
                "OpenAI completion (%s): %s tokens in %.3fs",
                model, usage["total_tokens"], processing_time,
            )
            return result
        except Exception as e:
            self._error_count["openai"] += 1
            self._provider_failures["openai"] += 1
            logger.error("OpenAI API error: %s", e)
            raise LLMError(f"OpenAI error: {e}")

    LLMProviderManager._call_openai = _call_openai

    # ------------------------------------------------------------------
    # 6. Add _call_ollama (OpenAI-compatible)
    # ------------------------------------------------------------------
    async def _call_ollama(
        self,
        messages: List[LLMMessage],
        model: str = "llama3.3",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
    ) -> LLMResponse:
        if not self._ollama_client:
            raise LLMError("Ollama client not initialized")

        start_time = time.time()
        try:
            openai_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    openai_messages.append(msg)
                else:
                    openai_messages.append({"role": msg.role, "content": msg.content})

            api_params: Dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
                "temperature": temperature or 0.1,
                "max_tokens": max_tokens or 1024,
                "stream": False,
            }
            if tools:
                api_params["tools"] = tools
                # Ollama's OpenAI-compatible layer does NOT support tool_choice
                # (per docs.ollama.com/api/openai-compatibility). Omit it.

            response = self._ollama_client.chat.completions.create(**api_params)
            processing_time = time.time() - start_time

            choice = response.choices[0].message
            content = choice.content or ""
            finish_reason = response.choices[0].finish_reason or "stop"

            tool_calls = None
            raw_tool_calls = getattr(choice, "tool_calls", None) or []
            if raw_tool_calls:
                tool_calls = []
                for tc in raw_tool_calls:
                    fn = getattr(tc, "function", None)
                    if fn is None:
                        continue
                    arguments = getattr(fn, "arguments", "{}")
                    tool_calls.append({
                        "id": getattr(tc, "id", "") or f"call_{int(time.time() * 1000)}",
                        "type": "function",
                        "function": {
                            "name": getattr(fn, "name", "") or "",
                            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
                        },
                    })
                finish_reason = "tool_calls"

            message_dict = {"content": content}
            if tool_calls:
                message_dict["tool_calls"] = tool_calls
            raw_response = {
                "choices": [
                    {"message": message_dict, "finish_reason": finish_reason}
                ]
            }

            usage_obj = response.usage if hasattr(response, "usage") and response.usage else None
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
            }

            result = LLMResponse(
                content=content,
                model=model,
                provider="ollama",
                usage=usage,
                processing_time=processing_time,
                finish_reason=finish_reason,
                raw_response=raw_response,
            )

            self._operation_count["ollama"] += 1
            self._total_processing_time["ollama"] += processing_time
            self._total_tokens["ollama"] += usage["total_tokens"]
            self._provider_failures["ollama"] = 0

            logger.info(
                "Ollama completion (%s): %s tokens in %.3fs",
                model, usage["total_tokens"], processing_time,
            )
            return result
        except Exception as e:
            self._error_count["ollama"] += 1
            self._provider_failures["ollama"] += 1
            logger.error("Ollama API error: %s", e)
            raise LLMError(f"Ollama error: {e}")

    LLMProviderManager._call_ollama = _call_ollama

    # ------------------------------------------------------------------
    # 7. Patch complete() to route all providers + apply OSCAR's selected model
    # ------------------------------------------------------------------
    async def patched_complete(
        self,
        messages: Union[str, List[LLMMessage]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        retry_on_failure: bool = True,
    ) -> LLMResponse:
        if isinstance(messages, str):
            messages = [LLMMessage(role="user", content=messages)]
        if not messages:
            raise LLMError("No messages provided for completion")

        await self._ensure_clients_initialized()
        selected = await self._select_provider(provider)

        # If caller didn't supply a model, use the model the user selected for
        # this provider (so a Claude run actually picks the configured Claude
        # model rather than a hard-coded default).
        if not model:
            if selected == selected_provider():
                model = selected_model()
            elif selected == selected_fallback_provider():
                model = selected_fallback_model()
            else:
                model = PROVIDERS[selected].default_model if selected in PROVIDERS else None

        try:
            if selected == "gemini":
                return await self._call_gemini(
                    messages, model or "gemini-2.5-flash",
                    temperature, max_tokens, tools, tool_choice,
                )
            elif selected == "groq":
                return await self._call_groq(
                    messages, model or "llama-3.3-70b-versatile",
                    temperature, max_tokens, tools, tool_choice,
                )
            elif selected == "openai":
                return await self._call_openai(
                    messages, model or "gpt-5-mini",
                    temperature, max_tokens, tools, tool_choice,
                )
            elif selected == "anthropic":
                return await self._call_anthropic(
                    messages, model or "claude-sonnet-4-6",
                    temperature, max_tokens, tools, tool_choice,
                )
            elif selected == "ollama":
                return await self._call_ollama(
                    messages, model or "llama3.3",
                    temperature, max_tokens, tools, tool_choice,
                )
            else:
                raise LLMError(f"Unknown provider: {selected}")
        except LLMError:
            if (
                retry_on_failure
                and not provider
                and selected != self._fallback_provider
            ):
                logger.warning(
                    "Provider %s failed, trying fallback %s",
                    selected, self._fallback_provider,
                )
                return await patched_complete(
                    self,
                    messages,
                    provider=self._fallback_provider,
                    model=None,  # let the routing pick the fallback's model
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    retry_on_failure=False,
                )
            raise

    LLMProviderManager.complete = patched_complete

    # ------------------------------------------------------------------
    # 8. Patch _select_provider so failure resets include every provider
    # ------------------------------------------------------------------
    async def patched_select_provider(self, force_provider=None):
        if force_provider:
            return force_provider
        if self._provider_failures.get(self._primary_provider, 0) < self._max_failures:
            return self._primary_provider
        if self._provider_failures.get(self._fallback_provider, 0) < self._max_failures:
            logger.warning(
                "Primary provider %s has failed too many times, using fallback",
                self._primary_provider,
            )
            return self._fallback_provider
        logger.warning("All tracked providers have failed; resetting failure counts")
        for p in ALL_PROVIDERS:
            self._provider_failures[p] = 0
        return self._primary_provider

    LLMProviderManager._select_provider = patched_select_provider

    # ------------------------------------------------------------------
    # 9. Patch get_performance_metrics to include all providers
    # ------------------------------------------------------------------
    def patched_get_performance_metrics(self):
        metrics = {
            "primary_provider": self._primary_provider,
            "fallback_provider": self._fallback_provider,
            "provider_health": getattr(self, "_provider_health", {}),
            "provider_failures": dict(self._provider_failures),
            "providers": {},
        }
        for provider in ALL_PROVIDERS:
            operation_count = self._operation_count.get(provider, 0)
            avg_time = (
                self._total_processing_time.get(provider, 0.0) / operation_count
                if operation_count > 0
                else 0
            )
            error_count = self._error_count.get(provider, 0)
            metrics["providers"][provider] = {
                "operation_count": operation_count,
                "error_count": error_count,
                "total_tokens": self._total_tokens.get(provider, 0),
                "total_processing_time_ms": round(
                    self._total_processing_time.get(provider, 0.0) * 1000, 2
                ),
                "average_processing_time_ms": round(avg_time * 1000, 2),
                "failure_count": self._provider_failures.get(provider, 0),
                "success_rate": (
                    round((operation_count - error_count) / operation_count * 100, 2)
                    if operation_count > 0
                    else 0
                ),
            }
        return metrics

    LLMProviderManager.get_performance_metrics = patched_get_performance_metrics

    # ------------------------------------------------------------------
    # 10. Patch the existing singleton (already constructed before us)
    # ------------------------------------------------------------------
    from asterix.core.llm_manager import llm_manager as _singleton

    if not hasattr(_singleton, "_gemini_client"):
        _singleton._gemini_client = None
    if not hasattr(_singleton, "_anthropic_client"):
        _singleton._anthropic_client = None
    if not hasattr(_singleton, "_ollama_client"):
        _singleton._ollama_client = None
    for attr, default in [
        ("_operation_count", 0),
        ("_total_processing_time", 0.0),
        ("_total_tokens", 0),
        ("_error_count", 0),
        ("_provider_failures", 0),
    ]:
        d = getattr(_singleton, attr, {})
        for p in ALL_PROVIDERS:
            if p not in d:
                d[p] = default

    _singleton._primary_provider = selected_provider()
    fb = selected_fallback_provider()
    if fb == _singleton._primary_provider:
        for candidate in ("gemini", "groq", "openai"):
            if candidate != _singleton._primary_provider:
                fb = candidate
                break
    _singleton._fallback_provider = fb

    _patched = True
    logger.info(
        "Asterix patched: providers=%s, primary=%s, fallback=%s",
        ALL_PROVIDERS, _singleton._primary_provider, _singleton._fallback_provider,
    )


# Auto-apply on import
apply_patches()
