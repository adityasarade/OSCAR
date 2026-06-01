"""
OSCAR LLM Provider Catalog

Single source of truth for which providers and models OSCAR supports. The
agent, CLI, FastAPI server, and VS Code extension all read from here so a
new model only needs to be registered in one place.

Provider/model selection is driven by environment variables:

- ``OSCAR_LLM_PROVIDER``  — primary provider id (see ``PROVIDERS``)
- ``OSCAR_LLM_MODEL``     — primary model id (must belong to the provider)
- ``OSCAR_LLM_FALLBACK_PROVIDER``  — fallback provider id (optional)
- ``OSCAR_LLM_FALLBACK_MODEL``     — fallback model id (optional)

Defaults preserve OSCAR's historical behavior: ``gemini`` / ``gemini-2.5-flash``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelInfo:
    """A single LLM model exposed by a provider."""
    id: str
    label: str
    description: str
    recommended: bool = False


@dataclass(frozen=True)
class ProviderInfo:
    """A single LLM provider OSCAR can route through."""
    id: str
    label: str
    description: str
    api_key_env: Optional[str]  # env var that supplies credentials (None for keyless providers)
    models: List[ModelInfo] = field(default_factory=list)
    default_model: str = ""
    requires_local_server: bool = False  # True for Ollama and similar local servers


PROVIDERS: Dict[str, ProviderInfo] = {
    "gemini": ProviderInfo(
        id="gemini",
        label="Google Gemini",
        description="Gemini 3.5 / 2.5 family via Vertex AI (ADC) or the Gemini Developer API",
        api_key_env="GEMINI_API_KEY",  # optional — Vertex AI uses ADC
        models=[
            # Default stays on gemini-2.5-flash: it's available on both Vertex
            # AI and the Gemini Developer API in every region. The 3.x family
            # launched on the developer API on 2026-05-19 but Vertex AI rollout
            # is still region-gated as of 2026-05-27 (verified 404 from
            # us-central1 for gemini-3.5-flash).
            ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", "Balanced quality and speed (recommended)", recommended=True),
            ModelInfo("gemini-3.5-flash", "Gemini 3.5 Flash", "Latest Flash — Gemini Developer API; Vertex AI rollout in progress"),
            ModelInfo("gemini-3.1-pro-preview", "Gemini 3.1 Pro (preview)", "Preview Pro-tier model from the Gemini 3 family"),
            ModelInfo("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Cheapest 3.x option, stable on Developer API"),
            ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro", "High quality, available on Vertex AI"),
            ModelInfo("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "Fastest and cheapest stable option"),
        ],
        default_model="gemini-2.5-flash",
    ),
    "openai": ProviderInfo(
        id="openai",
        label="OpenAI",
        description="GPT-5.5 / 5.4 family and o-series reasoning models via the OpenAI API",
        api_key_env="OPENAI_API_KEY",
        models=[
            # gpt-5.4-mini is the safest balanced default — it's in the openai
            # SDK ChatModel literal (no runtime warnings) and OpenAI markets it
            # as the strongest mini model for coding/computer-use.
            ModelInfo("gpt-5.4-mini", "GPT-5.4 mini", "Strongest mini model for coding (recommended)", recommended=True),
            ModelInfo("gpt-5.5", "GPT-5.5", "Latest flagship (released 2026-04-24, 1M context, function calling)"),
            ModelInfo("gpt-5.5-2026-04-23", "GPT-5.5 (snapshot)", "Pinned GPT-5.5 snapshot for reproducibility"),
            ModelInfo("gpt-5.4", "GPT-5.4", "Affordable flagship for coding and professional work"),
            ModelInfo("gpt-5.4-nano", "GPT-5.4 nano", "Lowest-cost GPT-5.4 variant"),
            ModelInfo("o4-mini", "o4-mini", "Small reasoning model"),
            ModelInfo("o3", "o3", "Reasoning model for harder problems"),
            ModelInfo("gpt-4.1", "GPT-4.1", "Long-context legacy model"),
            ModelInfo("gpt-4o", "GPT-4o", "Older multimodal model, still supported"),
        ],
        default_model="gpt-5.4-mini",
    ),
    "anthropic": ProviderInfo(
        id="anthropic",
        label="Anthropic Claude",
        description="Claude 4.x family via the Anthropic API (latest: Opus 4.8 — 2026-05-28)",
        api_key_env="ANTHROPIC_API_KEY",
        models=[
            # claude-sonnet-4-6 stays the recommended default per Anthropic's
            # docs: "best combination of speed and intelligence" for general use.
            ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", "Best balance of speed and intelligence (recommended)", recommended=True),
            ModelInfo("claude-opus-4-8", "Claude Opus 4.8", "Latest flagship — most capable for complex reasoning and agentic coding"),
            ModelInfo("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "Fastest model with near-frontier intelligence"),
            ModelInfo("claude-opus-4-7", "Claude Opus 4.7", "Previous-gen Opus (legacy but supported)"),
        ],
        default_model="claude-sonnet-4-6",
    ),
    "groq": ProviderInfo(
        id="groq",
        label="Groq",
        description="Open-source models served on Groq LPU hardware (very fast inference)",
        api_key_env="GROQ_API_KEY",
        models=[
            ModelInfo("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", "General purpose (recommended)", recommended=True),
            ModelInfo("llama-3.1-8b-instant", "Llama 3.1 8B Instant", "Smallest and fastest"),
        ],
        default_model="llama-3.3-70b-versatile",
    ),
    "ollama": ProviderInfo(
        id="ollama",
        label="Ollama (local)",
        description="Open-source models running locally via Ollama (no API key)",
        api_key_env=None,
        requires_local_server=True,
        models=[
            ModelInfo("llama3.3", "Llama 3.3", "Meta's latest general-purpose model (recommended)", recommended=True),
            ModelInfo("llama3.1", "Llama 3.1", "Well-tested with tool calling"),
            ModelInfo("qwen2.5-coder", "Qwen 2.5 Coder", "Coding-focused open model"),
            ModelInfo("deepseek-coder-v2", "DeepSeek Coder v2", "Strong coding open model"),
            ModelInfo("mistral-nemo", "Mistral Nemo", "Mistral model with good tool-calling support"),
        ],
        default_model="llama3.3",
    ),
}


DEFAULT_PROVIDER_ID = "gemini"
DEFAULT_FALLBACK_PROVIDER_ID = "gemini"


def _read_env_provider(env_var: str, default: str) -> str:
    val = (os.getenv(env_var) or "").strip().lower()
    if val and val in PROVIDERS:
        return val
    return default


def _read_env_model(env_var: str, provider_id: str) -> str:
    val = (os.getenv(env_var) or "").strip()
    if not val:
        return PROVIDERS[provider_id].default_model
    info = PROVIDERS[provider_id]
    if any(m.id == val for m in info.models):
        return val
    # Unknown model id — accept it anyway (advanced users may pull non-cataloged
    # Ollama models or pin a specific Anthropic snapshot); just log via stderr.
    import sys
    print(
        f"[oscar] Warning: model '{val}' is not in the catalog for provider "
        f"'{provider_id}'. Using it anyway; behaviour is your responsibility.",
        file=sys.stderr,
    )
    return val


def selected_provider() -> str:
    return _read_env_provider("OSCAR_LLM_PROVIDER", DEFAULT_PROVIDER_ID)


def selected_model() -> str:
    return _read_env_model("OSCAR_LLM_MODEL", selected_provider())


def selected_fallback_provider() -> str:
    return _read_env_provider("OSCAR_LLM_FALLBACK_PROVIDER", DEFAULT_FALLBACK_PROVIDER_ID)


def selected_fallback_model() -> str:
    return _read_env_model("OSCAR_LLM_FALLBACK_MODEL", selected_fallback_provider())


def asterix_model_string(provider_id: str, model_id: str) -> str:
    """Return the ``<provider>/<model>`` string Asterix expects for Agent(model=...)."""
    return f"{provider_id}/{model_id}"


def list_supported_providers() -> List[Dict]:
    """Serialize the catalog for API/CLI/extension consumption."""
    result = []
    for info in PROVIDERS.values():
        result.append({
            "id": info.id,
            "label": info.label,
            "description": info.description,
            "requires_api_key": info.api_key_env is not None,
            "api_key_env": info.api_key_env,
            "requires_local_server": info.requires_local_server,
            "default_model": info.default_model,
            "models": [
                {
                    "id": m.id,
                    "label": m.label,
                    "description": m.description,
                    "recommended": m.recommended,
                }
                for m in info.models
            ],
        })
    return result


__all__ = [
    "ModelInfo",
    "ProviderInfo",
    "PROVIDERS",
    "DEFAULT_PROVIDER_ID",
    "DEFAULT_FALLBACK_PROVIDER_ID",
    "selected_provider",
    "selected_model",
    "selected_fallback_provider",
    "selected_fallback_model",
    "asterix_model_string",
    "list_supported_providers",
]
