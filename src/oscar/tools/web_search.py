"""
OSCAR Web Search Tool — Tavily-based web search with dual-key fallback.

Standalone function that preserves the dual-key rotation and result formatting
from the original WebSearchTool class.
"""

from typing import Any, Dict, List

from oscar.config.settings import settings


def _init_clients() -> List:
    """Initialize Tavily clients with available API keys."""
    clients = []
    try:
        from tavily import TavilyClient

        for key in settings.get_tavily_keys():
            try:
                clients.append(TavilyClient(api_key=key))
            except Exception:
                continue
    except ImportError:
        pass
    return clients


_clients: List = _init_clients()


def _format_results(result: Dict[str, Any]) -> str:
    """Format Tavily search results for LLM consumption."""
    parts: List[str] = []

    if result.get("answer"):
        parts.append(f"**Answer:** {result['answer']}")
        parts.append("")

    results = result.get("results", [])
    if results:
        parts.append("**Sources:**")
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")[:200]
            parts.append(f"{i}. **{title}**")
            parts.append(f"   URL: {url}")
            if content:
                parts.append(f"   {content}...")
            parts.append("")

    return "\n".join(parts)


def web_search(query: str) -> str:
    """Search the web using Tavily with automatic API-key fallback on rate limits.

    Args:
        query: The search query string.

    Returns:
        Formatted search results, or an error message on failure.
    """
    if not _clients:
        return "Error: Tavily not available. Set TAVILY_API_KEY1 in .env and install tavily-python."

    if not query or not query.strip():
        return "Error: Empty search query."

    last_error = None

    for client in _clients:
        try:
            result = client.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True,
            )
            return _format_results(result)

        except Exception as e:
            last_error = str(e)
            if "rate" in last_error.lower() or "limit" in last_error.lower() or "429" in last_error:
                continue
            return f"Error: Search failed — {last_error}"

    return f"Error: All Tavily API keys exhausted or rate limited. Last error: {last_error}"
