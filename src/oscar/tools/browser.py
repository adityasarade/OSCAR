"""
OSCAR Browser Tool - Simplified intelligent web automation
"""

import time
import json
import re
from typing import Dict, Any, List, Tuple
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from bs4 import BeautifulSoup
import requests

from oscar.tools.base import BaseTool, ToolResult
from oscar.config.settings import settings


class BrowserTool(BaseTool):
    """Simplified intelligent browser with autonomous capabilities."""
    
    def __init__(self, llm_client=None):
        super().__init__(
            name="browser",
            description="Intelligent web browsing with content understanding"
        )
        
        self.llm_client = llm_client
        self.browser: Browser = None
        self.page: Page = None
        self.current_url = ""
        
        # Download settings
        self.download_dir = settings.data_dir / "downloads"
        self.download_dir.mkdir(exist_ok=True)
        
        # Content analysis settings
        self.max_content_length = 5000
    
    def _check_availability(self) -> bool:
        """Check if Playwright is available."""
        return PLAYWRIGHT_AVAILABLE
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute a browser command."""
        start_time = time.time()
        
        if not self.is_available:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not available. Install with: playwright install",
                execution_time=time.time() - start_time
            )
        
        try:
            parts = command.split(maxsplit=1)
            action = parts[0].lower()
            params = parts[1] if len(parts) > 1 else ""
            
            # Initialize browser if needed
            if not self.browser:
                self._start_browser()
            
            # Route to handlers
            handlers = {
                "navigate": self._navigate,
                "search": self._search,
                "analyze": self._analyze_page,
                "find_click": self._find_and_click,
                "extract": self._extract_info,
                "download": self._download,
                "intelligent_search": self._intelligent_search,
                "close": self._close_browser
            }
            
            if action not in handlers:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown browser command: {action}"
                )
            
            result = handlers[action](params, **kwargs)
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Browser error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _start_browser(self) -> None:
        """Start browser with settings."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=not settings.debug_mode,
            downloads_path=str(self.download_dir)
        )
        self.page = self.browser.new_page()
        
        # Set user agent
        self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    def _navigate(self, url: str, **kwargs) -> ToolResult:
        """Navigate to a URL."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            self.page.goto(url, timeout=30000)
            self.page.wait_for_load_state('networkidle')
            self.current_url = url
            
            title = self.page.title()
            
            # Basic analysis if requested
            analysis = {}
            if kwargs.get("analyze", True) and self.llm_client:
                content = self._get_page_content()
                analysis = self._analyze_content_with_llm(content, "Analyze this webpage")
            
            return ToolResult(
                success=True,
                output=f"Navigated to: {title}",
                metadata={
                    "url": url,
                    "title": title,
                    "analysis": analysis
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Navigation failed: {e}")
    
    def _search(self, query: str, **kwargs) -> ToolResult:
        """Perform web search."""
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        
        # Navigate to search
        nav_result = self._navigate(search_url)
        if not nav_result.success:
            return nav_result
        
        # Extract results
        results = self._extract_search_results()
        
        # Analyze with LLM if available
        analysis = ""
        if self.llm_client and results:
            results_text = "\n".join([f"{r.get('title', '')}: {r.get('snippet', '')}" for r in results[:3]])
            analysis = self._analyze_content_with_llm(results_text, f"Analyze these search results for: {query}")
        
        return ToolResult(
            success=True,
            output=f"Search completed for: {query}",
            metadata={
                "query": query,
                "results_count": len(results),
                "results": results[:5],
                "analysis": analysis
            }
        )
    
    def _intelligent_search(self, goal: str, **kwargs) -> ToolResult:
        """Perform intelligent search with autonomous decision-making."""
        if not self.llm_client:
            return ToolResult(False, "", "LLM client required for intelligent search")
        
        try:
            # Step 1: Plan search strategy
            search_query = self._plan_search_query(goal)
            
            # Step 2: Execute search
            search_result = self._search(search_query)
            if not search_result.success:
                return search_result
            
            # Step 3: Decide which result to visit
            results = search_result.metadata.get("results", [])
            if not results:
                return ToolResult(False, "", "No search results found")
            
            best_url = self._choose_best_result(goal, results)
            
            # Step 4: Navigate and extract info
            if best_url:
                nav_result = self._navigate(best_url)
                if nav_result.success:
                    extracted_info = self._extract_goal_info(goal)
                    
                    return ToolResult(
                        success=True,
                        output=f"Intelligent search completed for: {goal}",
                        metadata={
                            "goal": goal,
                            "search_query": search_query,
                            "chosen_url": best_url,
                            "extracted_info": extracted_info
                        }
                    )
            
            return ToolResult(False, "", "Could not find suitable information")
            
        except Exception as e:
            return ToolResult(False, "", f"Intelligent search failed: {e}")
    
    def _plan_search_query(self, goal: str) -> str:
        """Use LLM to plan optimal search query."""
        prompt = f"Create an optimal Google search query for this goal: {goal}\nRespond with just the search query, no explanation."
        
        try:
            response = self._call_llm(prompt, "")
            # Extract just the query from response
            query = response.strip().strip('"').strip("'")
            return query if query else goal
        except:
            return goal
    
    def _choose_best_result(self, goal: str, results: List[Dict]) -> str:
        """Use LLM to choose the best search result."""
        if not results:
            return ""
        
        results_text = "\n".join([
            f"{i+1}. {r.get('title', '')}\n   URL: {r.get('url', '')}\n   {r.get('snippet', '')}"
            for i, r in enumerate(results[:3])
        ])
        
        prompt = f"""Goal: {goal}

Which search result would be most helpful for this goal?

{results_text}

Respond with just the URL of the best result."""
        
        try:
            response = self._call_llm(prompt, "")
            # Extract URL from response
            for result in results:
                if result.get("url", "") in response:
                    return result["url"]
            # Fallback to first result
            return results[0].get("url", "") if results else ""
        except:
            return results[0].get("url", "") if results else ""
    
    def _extract_goal_info(self, goal: str) -> str:
        """Extract information relevant to the goal."""
        content = self._get_page_content()
        prompt = f"""Goal: {goal}

Extract information from this page that helps achieve this goal:

{content[:self.max_content_length]}

Provide specific, relevant information only."""
        
        return self._call_llm(prompt, content)
    
    def _analyze_page(self, params: str = "", **kwargs) -> ToolResult:
        """Analyze current page content."""
        if not self.current_url:
            return ToolResult(False, "", "No page currently loaded")
        
        content = self._get_page_content()
        
        if self.llm_client:
            analysis = self._analyze_content_with_llm(content, "Analyze this webpage content")
        else:
            analysis = f"Page content ({len(content)} characters): {content[:200]}..."
        
        return ToolResult(
            success=True,
            output="Page analysis completed",
            metadata={
                "url": self.current_url,
                "title": self.page.title(),
                "analysis": analysis
            }
        )
    
    def _analyze_content_with_llm(self, content: str, task: str) -> str:
        """Analyze content using LLM."""
        prompt = f"""Task: {task}

Content:
{content[:self.max_content_length]}

Provide a clear, concise analysis."""
        
        return self._call_llm(prompt, content)
    
    def _call_llm(self, prompt: str, content: str) -> str:
        """Call LLM for analysis."""
        if not self.llm_client:
            return "LLM not available"
        
        try:
            response = self.llm_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"LLM analysis failed: {str(e)}"
    
    def _get_page_content(self) -> str:
        """Extract clean text from current page."""
        try:
            html = self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get clean text
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            return ' '.join(chunk for chunk in chunks if chunk)
        except:
            return ""
    
    def _extract_search_results(self) -> List[Dict[str, str]]:
        """Extract Google search results."""
        results = []
        try:
            # Google search results
            result_elements = self.page.locator("div.g").all()
            for element in result_elements[:5]:
                try:
                    title_elem = element.locator("h3").first
                    link_elem = element.locator("a").first
                    snippet_elem = element.locator(".VwiC3b").first
                    
                    if title_elem and link_elem:
                        results.append({
                            "title": title_elem.inner_text(),
                            "url": link_elem.get_attribute("href"),
                            "snippet": snippet_elem.inner_text() if snippet_elem else ""
                        })
                except:
                    continue
        except:
            pass
        
        return results
    
    def _find_and_click(self, text: str, **kwargs) -> ToolResult:
        """Find and click element containing text."""
        try:
            selectors = [
                f"text={text}",
                f"//a[contains(text(), '{text}')]",
                f"//button[contains(text(), '{text}')]"
            ]
            
            for selector in selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible():
                        element.click()
                        self.page.wait_for_load_state('networkidle')
                        
                        return ToolResult(
                            success=True,
                            output=f"Clicked: {text}",
                            metadata={"new_url": self.page.url}
                        )
                except:
                    continue
            
            return ToolResult(False, "", f"Could not find clickable element: {text}")
        except Exception as e:
            return ToolResult(False, "", f"Click failed: {e}")
    
    def _extract_info(self, query: str, **kwargs) -> ToolResult:
        """Extract specific information from current page."""
        content = self._get_page_content()
        
        if self.llm_client:
            extracted = self._analyze_content_with_llm(content, f"Extract information about: {query}")
        else:
            # Simple keyword search fallback
            lines = content.lower().split('\n')
            relevant = [line for line in lines if query.lower() in line]
            extracted = '\n'.join(relevant[:3])
        
        return ToolResult(
            success=True,
            output=f"Information extracted for: {query}",
            metadata={
                "query": query,
                "extracted_info": extracted,
                "source_url": self.current_url
            }
        )
    
    def _download(self, target: str, **kwargs) -> ToolResult:
        """Download file from URL or by clicking link."""
        try:
            if target.startswith(('http://', 'https://')):
                # Direct URL download
                response = requests.get(target, stream=True)
                response.raise_for_status()
                
                filename = target.split('/')[-1] or "download"
                filepath = self.download_dir / filename
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return ToolResult(
                    success=True,
                    output=f"Downloaded: {filename}",
                    metadata={"filename": filename, "filepath": str(filepath)}
                )
            else:
                # Find and click download link
                return self._find_and_click(target)
        except Exception as e:
            return ToolResult(False, "", f"Download failed: {e}")
    
    def _close_browser(self, params: str = "", **kwargs) -> ToolResult:
        """Close browser and cleanup."""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            
            self.browser = None
            self.page = None
            self.current_url = ""
            
            return ToolResult(success=True, output="Browser closed")
        except Exception as e:
            return ToolResult(False, "", f"Error closing browser: {e}")
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate browser command."""
        valid_commands = [
            "navigate", "search", "analyze", "find_click", 
            "extract", "download", "intelligent_search", "close"
        ]
        
        action = command.split()[0].lower() if command.split() else ""
        return action in valid_commands, f"Valid: {action in valid_commands}"
    
    def get_help(self) -> str:
        """Return help text."""
        return """
Browser Tool - Intelligent Web Automation

Commands:
- navigate <url>               : Navigate to webpage
- search <query>               : Search the web
- analyze                      : Analyze current page
- find_click <text>           : Find and click element
- extract <query>             : Extract specific info
- download <url_or_text>      : Download file
- intelligent_search <goal>   : Autonomous goal-driven search
- close                       : Close browser

Intelligent Features:
- Content understanding with LLM
- Autonomous navigation decisions  
- Goal-oriented information extraction
- Smart search result selection

Example: intelligent_search "find Python 3.11 download link"
"""