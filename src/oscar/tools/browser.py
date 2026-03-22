"""
OSCAR Browser Tool — Playwright-based web automation as standalone functions.

Functions:
- browser_navigate(url) — navigate to a URL, return page content
- browser_search(query) — Google search, return formatted results
- browser_extract(query) — extract current page content
- browser_download(url) — download a file from a URL
"""

from pathlib import Path
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from oscar.config.settings import settings

try:
    from playwright.sync_api import sync_playwright, Browser, Page

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Module-level browser state (lazy singleton)
# ---------------------------------------------------------------------------

_playwright_ctx = None
_browser: "Browser | None" = None
_page: "Page | None" = None
_current_url: str = ""

_download_dir: Path = settings.data_dir / "downloads"
_download_dir.mkdir(exist_ok=True)

_MAX_CONTENT_LENGTH = 5000


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _ensure_browser() -> "Page":
    """Lazily start Playwright + Chromium and return the Page."""
    global _playwright_ctx, _browser, _page

    if _page is not None:
        return _page

    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "Playwright not available. Install with: pip install playwright && playwright install chromium"
        )

    _playwright_ctx = sync_playwright().start()
    _browser = _playwright_ctx.chromium.launch(
        headless=True,
        downloads_path=str(_download_dir),
    )
    _page = _browser.new_page()
    _page.set_extra_http_headers(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )
    return _page


def _get_page_content() -> str:
    """Extract clean text from the current page using BeautifulSoup."""
    if _page is None:
        return ""
    try:
        html = _page.content()
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style"]):
            tag.decompose()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return " ".join(chunk for chunk in chunks if chunk)
    except Exception:
        return ""


def _extract_search_results() -> List[Dict[str, str]]:
    """Extract Google search results from the current page."""
    results: List[Dict[str, str]] = []
    if _page is None:
        return results
    try:
        result_elements = _page.locator("div.g").all()
        for element in result_elements[:5]:
            try:
                title_elem = element.locator("h3").first
                link_elem = element.locator("a").first
                snippet_elem = element.locator(".VwiC3b").first

                if title_elem and link_elem:
                    results.append(
                        {
                            "title": title_elem.inner_text(),
                            "url": link_elem.get_attribute("href") or "",
                            "snippet": (
                                snippet_elem.inner_text() if snippet_elem else ""
                            ),
                        }
                    )
            except Exception:
                continue
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


def browser_navigate(url: str) -> str:
    """Navigate to a URL and return the page title and content.

    Args:
        url: The URL to navigate to (https:// is prepended if missing).

    Returns:
        Page title and truncated text content, or an error message.
    """
    global _current_url

    if not url or not url.strip():
        return "Error: Empty URL."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        page = _ensure_browser()
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        _current_url = url

        title = page.title()
        content = _get_page_content()

        return (
            f"Navigated to: {title}\n"
            f"URL: {url}\n\n"
            f"Content:\n{content[:_MAX_CONTENT_LENGTH]}"
        )
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: Navigation failed — {e}"


def browser_search(query: str) -> str:
    """Perform a Google search and return formatted results.

    Args:
        query: The search query string.

    Returns:
        Numbered list of search results, or an error message.
    """
    if not query or not query.strip():
        return "Error: Empty search query."

    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

    try:
        page = _ensure_browser()
        page.goto(search_url, timeout=30000)
        page.wait_for_load_state("networkidle")

        results = _extract_search_results()

        if not results:
            return f"Search for '{query}' returned no results."

        parts = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            parts.append(f"{i}. **{title}**")
            parts.append(f"   URL: {url}")
            if snippet:
                parts.append(f"   {snippet}")
            parts.append("")

        return "\n".join(parts)
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: Search failed — {e}"


def browser_extract(query: str) -> str:
    """Extract content from the currently loaded page.

    The query describes what information you are looking for. The full page
    content is returned for the agent to analyse.

    Args:
        query: Description of the information to extract.

    Returns:
        Page content prefixed with URL context, or an error message.
    """
    if not _current_url:
        return "Error: No page currently loaded. Use browser_navigate first."

    content = _get_page_content()
    if not content:
        return f"Error: Could not extract content from {_current_url}."

    return (
        f"Content from {_current_url} (query: {query}):\n\n"
        f"{content[:_MAX_CONTENT_LENGTH]}"
    )


def browser_download(url: str) -> str:
    """Download a file from a URL to the local downloads directory.

    Args:
        url: Direct URL of the file to download.

    Returns:
        Confirmation with filename, path, and size, or an error message.
    """
    if not url or not url.strip():
        return "Error: Empty URL."

    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        filename = url.split("/")[-1].split("?")[0] or "download"
        filepath = _download_dir / filename

        size = 0
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                size += len(chunk)

        return f"Downloaded: {filename} to {filepath} ({size} bytes)"
    except Exception as e:
        return f"Error: Download failed — {e}"
