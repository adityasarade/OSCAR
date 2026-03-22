"""
Asterix v0.2.0 Runtime Patch — Gemini via Vertex AI

Monkey-patches Asterix to support "gemini" as an LLM provider using the
Google GenAI SDK with Vertex AI authentication. Import this module before
creating any Asterix Agent.

This patch is temporary — once Asterix natively supports Vertex AI, this
file can be deleted.
"""

import json
import time
import logging
from typing import List, Optional, Any, Dict, Union

from google.genai import Client, types

from asterix.core.config import LLMConfig
from asterix.core.llm_manager import (
    LLMProviderManager,
    LLMResponse,
    LLMMessage,
    LLMError,
)

logger = logging.getLogger(__name__)

_patched = False

# Vertex AI project config
_VERTEX_PROJECT = "oscar-490517"
_VERTEX_LOCATION = "us-central1"
_GEMINI_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Message translation helpers
# ---------------------------------------------------------------------------

def _translate_messages(messages):
    """Translate OpenAI-format messages to Gemini Contents + system_instruction.

    Returns (system_instruction: str | None, contents: list[types.Content])
    """
    system_instruction = None
    contents = []

    for msg in messages:
        # Normalize to dict
        if not isinstance(msg, dict):
            msg = {"role": msg.role, "content": msg.content}

        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            # Gemini uses system_instruction, not a system role in contents
            system_instruction = content
            continue

        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=content)],
                )
            )
            continue

        if role == "assistant":
            parts = []
            if content:
                parts.append(types.Part.from_text(text=content))
            # Translate tool calls if present
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, TypeError):
                    args = {}
                parts.append(types.Part.from_function_call(name=name, args=args))
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue

        if role == "tool":
            # Gemini expects function responses as user role.
            # Merge consecutive tool messages into one Content.
            fn_name = msg.get("name", "unknown")
            part = types.Part.from_function_response(
                name=fn_name, response={"result": content}
            )
            # If the last content is already a user message with function_response parts,
            # merge into it (consecutive tool results).
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
                contents.append(types.Content(role="user", parts=[part]))
            continue

    return system_instruction, contents


def _translate_tools(tools):
    """Translate OpenAI tool schemas to a Gemini Tool object.

    Returns types.Tool or None if no tools.
    """
    if not tools:
        return None

    declarations = []
    for tool_def in tools:
        fn = tool_def.get("function", {})
        name = fn.get("name", "")
        description = fn.get("description", "")
        parameters = fn.get("parameters")

        decl = types.FunctionDeclaration(
            name=name,
            description=description,
            parameters=parameters,
        )
        declarations.append(decl)

    if not declarations:
        return None

    return types.Tool(function_declarations=declarations)


def _translate_response(response, processing_time):
    """Translate Gemini response to OpenAI-compatible LLMResponse."""
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

    # Build OpenAI-compatible tool_calls list
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

    # Build raw_response matching OpenAI structure (read by agent.py)
    message_dict = {"content": content}
    if tool_calls:
        message_dict["tool_calls"] = tool_calls

    raw_response = {
        "choices": [
            {
                "message": message_dict,
                "finish_reason": finish_reason,
            }
        ]
    }

    # Extract usage
    usage_meta = getattr(response, "usage_metadata", None)
    usage = {
        "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0) or 0,
        "completion_tokens": getattr(usage_meta, "candidates_token_count", 0) or 0,
        "total_tokens": getattr(usage_meta, "total_token_count", 0) or 0,
    }

    return LLMResponse(
        content=content,
        model=_GEMINI_MODEL,
        provider="gemini",
        usage=usage,
        processing_time=processing_time,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def apply_patches():
    """Apply all Gemini/Vertex AI patches to Asterix v0.2.0. Idempotent."""
    global _patched
    if _patched:
        return

    # ------------------------------------------------------------------
    # 1. Patch LLMConfig.__post_init__ to allow "gemini" provider
    # ------------------------------------------------------------------
    def patched_post_init(self):
        if self.provider not in ["groq", "openai", "gemini"]:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("Max tokens must be positive")

    LLMConfig.__post_init__ = patched_post_init

    # ------------------------------------------------------------------
    # 2. Patch LLMProviderManager.__init__ to add gemini tracking
    # ------------------------------------------------------------------
    _original_init = LLMProviderManager.__init__

    def patched_init(self):
        _original_init(self)
        self._gemini_client = None
        # Add gemini to all tracking dicts
        self._operation_count["gemini"] = 0
        self._total_processing_time["gemini"] = 0.0
        self._total_tokens["gemini"] = 0
        self._error_count["gemini"] = 0
        self._provider_failures["gemini"] = 0

    LLMProviderManager.__init__ = patched_init

    # ------------------------------------------------------------------
    # 3. Patch _ensure_clients_initialized to lazy-init Gemini client
    # ------------------------------------------------------------------
    _original_ensure = LLMProviderManager._ensure_clients_initialized

    async def patched_ensure_clients_initialized(self):
        await _original_ensure(self)
        if self._gemini_client is None:
            self._gemini_client = Client(
                vertexai=True,
                project=_VERTEX_PROJECT,
                location=_VERTEX_LOCATION,
            )

    LLMProviderManager._ensure_clients_initialized = patched_ensure_clients_initialized

    # ------------------------------------------------------------------
    # 4. Add _call_gemini method
    # ------------------------------------------------------------------
    async def _call_gemini(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
    ) -> LLMResponse:
        """Call Gemini via Vertex AI."""
        if not self._gemini_client:
            raise LLMError("Gemini client not initialized")

        start_time = time.time()

        try:
            # Translate messages
            system_instruction, gemini_contents = _translate_messages(messages)

            # Translate tools
            gemini_tool = _translate_tools(tools)

            # Build config
            config = types.GenerateContentConfig(
                temperature=temperature or 0.1,
                max_output_tokens=max_tokens or 1000,
            )
            if system_instruction:
                config.system_instruction = system_instruction
            if gemini_tool:
                config.tools = [gemini_tool]

            # Call Gemini API
            response = self._gemini_client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=gemini_contents,
                config=config,
            )

            processing_time = time.time() - start_time

            # Translate response
            result = _translate_response(response, processing_time)

            # Update metrics
            self._operation_count["gemini"] += 1
            self._total_processing_time["gemini"] += processing_time
            self._total_tokens["gemini"] += result.usage["total_tokens"]
            self._provider_failures["gemini"] = 0

            logger.info(
                f"Gemini completion: {result.usage['total_tokens']} tokens "
                f"in {processing_time:.3f}s"
            )
            return result

        except Exception as e:
            self._error_count["gemini"] += 1
            self._provider_failures["gemini"] += 1
            logger.error(f"Gemini API error: {e}")
            raise LLMError(f"Gemini error: {e}")

    LLMProviderManager._call_gemini = _call_gemini

    # ------------------------------------------------------------------
    # 5. Patch complete() to route "gemini" provider
    # ------------------------------------------------------------------
    _original_complete = LLMProviderManager.complete

    async def patched_complete(
        self,
        messages: Union[str, List[LLMMessage]],
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        retry_on_failure: bool = True,
    ) -> LLMResponse:
        # Normalize input
        if isinstance(messages, str):
            messages = [LLMMessage(role="user", content=messages)]
        if not messages:
            raise LLMError("No messages provided for completion")

        await self._ensure_clients_initialized()
        selected_provider = await self._select_provider(provider)

        try:
            if selected_provider == "gemini":
                return await self._call_gemini(
                    messages, temperature, max_tokens, tools, tool_choice
                )
            elif selected_provider == "groq":
                return await self._call_groq(
                    messages, temperature, max_tokens, tools, tool_choice
                )
            elif selected_provider == "openai":
                return await self._call_openai(
                    messages, temperature, max_tokens, tools, tool_choice
                )
            else:
                raise LLMError(f"Unknown provider: {selected_provider}")
        except LLMError:
            if (
                retry_on_failure
                and not provider
                and selected_provider != self._fallback_provider
            ):
                logger.warning(
                    f"Provider {selected_provider} failed, "
                    f"trying fallback {self._fallback_provider}"
                )
                return await patched_complete(
                    self,
                    messages,
                    provider=self._fallback_provider,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                    retry_on_failure=False,
                )
            raise

    LLMProviderManager.complete = patched_complete

    # ------------------------------------------------------------------
    # 6. Patch _select_provider to include gemini in failure reset
    # ------------------------------------------------------------------
    _original_select = LLMProviderManager._select_provider

    async def patched_select_provider(self, force_provider=None):
        if force_provider:
            return force_provider
        if self._provider_failures[self._primary_provider] < self._max_failures:
            return self._primary_provider
        if self._provider_failures[self._fallback_provider] < self._max_failures:
            logger.warning(
                f"Primary provider {self._primary_provider} has failed "
                f"too many times, using fallback"
            )
            return self._fallback_provider
        logger.warning(
            "Both providers have failed multiple times, resetting failure counts"
        )
        self._provider_failures = {"groq": 0, "openai": 0, "gemini": 0}
        return self._primary_provider

    LLMProviderManager._select_provider = patched_select_provider

    # ------------------------------------------------------------------
    # 7. Patch get_performance_metrics to include gemini
    # ------------------------------------------------------------------
    def patched_get_performance_metrics(self):
        metrics = {
            "primary_provider": self._primary_provider,
            "fallback_provider": self._fallback_provider,
            "provider_health": getattr(self, "_provider_health", {}),
            "provider_failures": self._provider_failures,
            "providers": {},
        }
        for provider in ["groq", "openai", "gemini"]:
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

    _patched = True
    logger.info("Asterix patched for Gemini/Vertex AI support (project: %s)", _VERTEX_PROJECT)


# Auto-apply on import
apply_patches()
