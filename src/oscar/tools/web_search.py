"""
OSCAR Web Search Tool - Tavily-based web search with dual-key fallback

Provides AI-optimized web search capabilities:
- Automatic fallback between API keys on rate limits
- Returns structured results with content extraction
- Designed for LLM consumption (clean, relevant content)
"""

import time
from typing import Dict, Any, List, Tuple, Optional

from oscar.tools.base import BaseTool, ToolResult
from oscar.config.settings import settings


class WebSearchTool(BaseTool):
    """Web search tool using Tavily API with dual-key fallback."""
    
    def __init__(self):
        # Initialize clients BEFORE super().__init__ because it calls _check_availability
        self.clients = self._init_clients_internal()
        self.current_key_index = 0
        
        super().__init__(
            name="web_search",
            description="Search the web for current information using AI-optimized search"
        )
    
    def _init_clients_internal(self) -> List:
        """Initialize Tavily clients with available API keys."""
        clients = []
        try:
            from tavily import TavilyClient
            
            tavily_keys = settings.get_tavily_keys()
            for key in tavily_keys:
                try:
                    clients.append(TavilyClient(api_key=key))
                except Exception:
                    continue
        except ImportError:
            pass
        
        return clients
    
    def _check_availability(self) -> bool:
        """Check if Tavily is available."""
        return len(self.clients) > 0
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute a web search command."""
        start_time = time.time()
        
        if not self.is_available:
            return ToolResult(
                success=False,
                output="",
                error="Tavily not available. Please set TAVILY_API_KEY1 in your .env file and install tavily-python",
                execution_time=time.time() - start_time
            )
        
        try:
            # Parse command - support "search <query>" format
            query = command.strip()
            if query.lower().startswith("search "):
                query = query[7:].strip()
            
            if not query:
                return ToolResult(
                    success=False,
                    output="",
                    error="No search query provided",
                    execution_time=time.time() - start_time
                )
            
            # Execute search with fallback
            result = self._search_with_fallback(query)
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Web search error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _search_with_fallback(self, query: str) -> ToolResult:
        """Execute search with automatic key fallback on rate limits."""
        last_error = None
        
        for i, client in enumerate(self.clients):
            try:
                # Use advanced search for better results
                result = client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5,
                    include_answer=True
                )
                
                # Format results for LLM consumption
                formatted_output = self._format_results(result)
                
                return ToolResult(
                    success=True,
                    output=formatted_output,
                    metadata={
                        "query": query,
                        "source": f"tavily_key_{i+1}",
                        "results_count": len(result.get("results", [])),
                        "answer": result.get("answer", ""),
                        "raw_results": result.get("results", [])[:3]  # Keep top 3 for context
                    }
                )
                
            except Exception as e:
                last_error = str(e)
                
                # Check if it's a rate limit error
                if "rate" in last_error.lower() or "limit" in last_error.lower() or "429" in last_error:
                    # Try next key
                    continue
                else:
                    # Non-rate-limit error, return immediately
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Search failed: {last_error}"
                    )
        
        # All keys exhausted
        return ToolResult(
            success=False,
            output="",
            error=f"All Tavily API keys exhausted or rate limited. Last error: {last_error}"
        )
    
    def _format_results(self, result: Dict[str, Any]) -> str:
        """Format search results for clean LLM consumption."""
        output_parts = []
        
        # Include AI-generated answer if available
        if result.get("answer"):
            output_parts.append(f"**Answer:** {result['answer']}")
            output_parts.append("")
        
        # Include top results
        results = result.get("results", [])
        if results:
            output_parts.append("**Sources:**")
            for i, r in enumerate(results[:5], 1):
                title = r.get("title", "No title")
                url = r.get("url", "")
                content = r.get("content", "")[:200]  # Truncate content
                output_parts.append(f"{i}. **{title}**")
                output_parts.append(f"   URL: {url}")
                if content:
                    output_parts.append(f"   {content}...")
                output_parts.append("")
        
        return "\n".join(output_parts)
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate web search command."""
        query = command.strip()
        if query.lower().startswith("search "):
            query = query[7:].strip()
        
        if not query:
            return False, "Empty search query"
        
        if len(query) > 500:
            return False, "Search query too long (max 500 characters)"
        
        return True, "Valid search query"
    
    def get_help(self) -> str:
        """Return help text for web search tool."""
        return """
Web Search Tool - AI-Optimized Web Search

Commands:
  search <query>    : Search the web for information
  <query>          : Direct query (search prefix optional)

Features:
  - AI-optimized search results with content extraction
  - Automatic answer generation when possible
  - Dual API key fallback for rate limit handling
  - Returns structured, LLM-friendly content

Examples:
  search current weather in Pune
  search Python 3.12 new features
  latest news about AI
"""
