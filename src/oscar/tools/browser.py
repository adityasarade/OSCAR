"""
OSCAR Agentic Browser Tool - Intelligent Web Automation
Autonomous web browsing with content understanding and decision-making capabilities.
"""

import time
import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from urllib.parse import urljoin, urlparse
import re

try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from bs4 import BeautifulSoup
import requests

from oscar.tools.base import AgenticTool, ToolResult, ToolCapability
from oscar.config.settings import settings


class BrowserTool(AgenticTool):
    """
    Intelligent browser automation tool that can:
    - Browse and understand web content
    - Make autonomous decisions about navigation
    - Extract and analyze information
    - Perform complex web workflows
    """
    
    def __init__(self, llm_client=None):
        super().__init__(
            name="browser",
            description="Intelligent web browsing with autonomous content understanding and decision-making",
            capabilities=[ToolCapability.NETWORK, ToolCapability.ANALYSIS, ToolCapability.AUTOMATION],
            llm_client=llm_client
        )
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.current_url = ""
        self.page_history: List[Dict[str, Any]] = []
        
        # Download settings
        self.download_dir = settings.data_dir / "downloads"
        self.download_dir.mkdir(exist_ok=True)
        
        # Content analysis settings
        self.max_content_length = 10000  # Max chars to send to LLM
        self.search_strategies = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q="
        }
    
    def _check_availability(self) -> bool:
        """Check if Playwright is available."""
        return PLAYWRIGHT_AVAILABLE
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """
        Execute a browser command with autonomous decision-making.
        
        Commands:
        - navigate <url>
        - search <query>
        - analyze_page
        - find_and_click <text>
        - extract_info <query>
        - download <url_or_link_text>
        - intelligent_search <goal>
        """
        start_time = time.time()
        
        if not self.is_available:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not available. Install with: playwright install",
                execution_time=time.time() - start_time
            )
        
        try:
            command_parts = command.split(maxsplit=1)
            action = command_parts[0].lower()
            params = command_parts[1] if len(command_parts) > 1 else ""
            
            # Initialize browser if needed
            if not self.browser:
                self._start_browser()
            
            # Route to appropriate handler
            if action == "navigate":
                result = self._navigate(params, **kwargs)
            elif action == "search":
                result = self._search(params, **kwargs)
            elif action == "analyze_page":
                result = self._analyze_current_page(**kwargs)
            elif action == "find_and_click":
                result = self._find_and_click(params, **kwargs)
            elif action == "extract_info":
                result = self._extract_info(params, **kwargs)
            elif action == "download":
                result = self._download(params, **kwargs)
            elif action == "intelligent_search":
                result = self._intelligent_search(params, **kwargs)
            elif action == "close":
                result = self._close_browser()
            else:
                result = ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown browser command: {action}"
                )
            
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Browser execution error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _start_browser(self) -> None:
        """Start the browser with appropriate settings."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=not settings.debug_mode,  # Show browser in debug mode
            downloads_path=str(self.download_dir)
        )
        self.page = self.browser.new_page()
        
        # Set realistic user agent
        self.page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
    
    def _navigate(self, url: str, **kwargs) -> ToolResult:
        """Navigate to a URL and analyze the page."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            self.page.goto(url, timeout=30000)
            self.current_url = url
            
            # Wait for page to load
            self.page.wait_for_load_state('networkidle')
            
            # Get page info
            title = self.page.title()
            content_summary = self._get_page_summary()
            
            # Add to history
            self.page_history.append({
                "url": url,
                "title": title,
                "timestamp": time.time(),
                "action": "navigate"
            })
            
            # Analyze page if requested
            analysis = {}
            if kwargs.get("analyze", True):
                analysis = self._analyze_page_content()
            
            return ToolResult(
                success=True,
                output=f"Navigated to: {title}",
                metadata={
                    "url": url,
                    "title": title,
                    "content_summary": content_summary,
                    "analysis": analysis
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Navigation failed: {str(e)}"
            )
    
    def _search(self, query: str, **kwargs) -> ToolResult:
        """Perform a web search and analyze results."""
        search_engine = kwargs.get("engine", "google")
        search_url = self.search_strategies.get(search_engine, self.search_strategies["google"])
        
        search_url += query.replace(" ", "+")
        
        # Navigate to search results
        nav_result = self._navigate(search_url)
        if not nav_result.success:
            return nav_result
        
        # Extract search results
        results = self._extract_search_results()
        
        # Analyze results using LLM if available
        if self.llm_client and results:
            analysis = self._analyze_search_results(query, results)
        else:
            analysis = "Search completed but no LLM analysis available"
        
        return ToolResult(
            success=True,
            output=f"Search completed for: {query}",
            metadata={
                "query": query,
                "search_engine": search_engine,
                "results_count": len(results),
                "results": results[:5],  # Top 5 results
                "analysis": analysis
            }
        )
    
    def _intelligent_search(self, goal: str, **kwargs) -> ToolResult:
        """
        Perform an intelligent search with autonomous navigation and decision-making.
        This is the core agentic capability.
        """
        if not self.llm_client:
            return ToolResult(
                success=False,
                output="",
                error="LLM client required for intelligent search"
            )
        
        # Step 1: Plan the search strategy
        search_plan = self._plan_search_strategy(goal)
        
        # Step 2: Execute search
        search_result = self._search(search_plan["query"])
        if not search_result.success:
            return search_result
        
        # Step 3: Analyze results and decide on next action
        results = search_result.metadata.get("results", [])
        decision = self._make_navigation_decision(goal, results)
        
        # Step 4: Navigate to best result and extract information
        if decision["action"] == "navigate" and decision.get("url"):
            nav_result = self._navigate(decision["url"])
            if nav_result.success:
                # Step 5: Extract relevant information
                extraction_result = self._extract_goal_relevant_info(goal)
                
                return ToolResult(
                    success=True,
                    output=f"Intelligent search completed for: {goal}",
                    metadata={
                        "goal": goal,
                        "search_plan": search_plan,
                        "decision": decision,
                        "extracted_info": extraction_result,
                        "pages_visited": len(self.page_history),
                        "final_url": self.current_url
                    }
                )
        
        return ToolResult(
            success=False,
            output="",
            error="Could not complete intelligent search - no suitable pages found"
        )
    
    def _plan_search_strategy(self, goal: str) -> Dict[str, Any]:
        """Use LLM to plan the search strategy."""
        prompt = f"""
Goal: {goal}

Plan an effective web search strategy. Consider:
1. What search terms would be most effective?
2. What type of websites would have this information?
3. What specific information should I look for?

Respond with JSON:
{{
    "query": "optimized search query",
    "target_sites": ["list", "of", "likely", "useful", "sites"],
    "info_to_extract": ["specific", "information", "to", "find"],
    "strategy": "brief strategy description"
}}
"""
        
        response = self.call_llm_for_analysis(prompt, "")
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        # Fallback to simple strategy
        return {
            "query": goal,
            "target_sites": [],
            "info_to_extract": ["relevant information"],
            "strategy": "Basic search strategy"
        }
    
    def _make_navigation_decision(self, goal: str, results: List[Dict]) -> Dict[str, Any]:
        """Use LLM to decide which search result to visit."""
        if not results:
            return {"action": "none", "reason": "No results available"}
        
        results_text = "\n".join([
            f"{i+1}. {r.get('title', 'No title')} - {r.get('url', 'No URL')}\n   {r.get('snippet', 'No snippet')}"
            for i, r in enumerate(results[:5])
        ])
        
        prompt = f"""
Goal: {goal}

Available search results:
{results_text}

Which result would be most likely to contain the information needed for this goal?

Respond with JSON:
{{
    "action": "navigate",
    "url": "selected_url",
    "reason": "why this result was chosen",
    "confidence": "high|medium|low"
}}
"""
        
        response = self.call_llm_for_analysis(prompt, "")
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group())
                # Validate URL exists in results
                selected_url = decision.get("url", "")
                if any(selected_url in r.get("url", "") for r in results):
                    return decision
        except:
            pass
        
        # Fallback to first result
        if results:
            return {
                "action": "navigate",
                "url": results[0].get("url", ""),
                "reason": "Fallback to first result",
                "confidence": "low"
            }
        
        return {"action": "none", "reason": "No suitable results"}
    
    def _extract_goal_relevant_info(self, goal: str) -> Dict[str, Any]:
        """Extract information relevant to the goal from current page."""
        page_content = self._get_page_content()
        
        prompt = f"""
Goal: {goal}

Extract all information from this page that is relevant to achieving this goal.
Focus on specific facts, URLs, instructions, or data that would help accomplish the goal.

Page content:
{page_content[:self.max_content_length]}

Provide a structured summary of relevant information.
"""
        
        analysis = self.call_llm_for_analysis(prompt, page_content)
        
        return {
            "analysis": analysis,
            "page_title": self.page.title(),
            "page_url": self.current_url,
            "content_length": len(page_content)
        }
    
    def _analyze_current_page(self, **kwargs) -> ToolResult:
        """Analyze the current page content."""
        if not self.current_url:
            return ToolResult(
                success=False,
                output="",
                error="No page currently loaded"
            )
        
        analysis = self._analyze_page_content()
        
        return ToolResult(
            success=True,
            output="Page analysis completed",
            metadata={
                "url": self.current_url,
                "title": self.page.title(),
                "analysis": analysis
            }
        )
    
    def _analyze_page_content(self) -> Dict[str, Any]:
        """Analyze current page content using LLM."""
        if not self.llm_client:
            return {"error": "LLM not available for analysis"}
        
        content = self._get_page_content()
        
        prompt = """
Analyze this web page content and provide:
1. Main topic/purpose of the page
2. Key information or data present
3. Available actions (links, forms, buttons)
4. Overall usefulness and credibility
5. Any notable features or concerns

Provide a structured analysis.
"""
        
        analysis = self.call_llm_for_analysis(prompt, content[:self.max_content_length])
        
        return {
            "content_analysis": analysis,
            "page_stats": {
                "content_length": len(content),
                "links_count": len(self.page.locator("a").all()),
                "forms_count": len(self.page.locator("form").all()),
                "images_count": len(self.page.locator("img").all())
            }
        }
    
    def _get_page_content(self) -> str:
        """Extract clean text content from current page."""
        try:
            # Get page HTML
            html = self.page.content()
            
            # Parse with BeautifulSoup for clean text extraction
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            return f"Error extracting content: {str(e)}"
    
    def _get_page_summary(self) -> str:
        """Get a brief summary of current page."""
        try:
            title = self.page.title()
            url = self.current_url
            content = self._get_page_content()
            
            return f"Page: {title}\nURL: {url}\nContent length: {len(content)} characters"
            
        except Exception as e:
            return f"Error getting page summary: {str(e)}"
    
    def _extract_search_results(self) -> List[Dict[str, Any]]:
        """Extract search results from current page."""
        results = []
        
        try:
            # Google search results
            if "google.com" in self.current_url:
                result_elements = self.page.locator("div.g").all()
                for element in result_elements[:10]:  # Top 10 results
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
            
            # Bing search results
            elif "bing.com" in self.current_url:
                result_elements = self.page.locator(".b_algo").all()
                for element in result_elements[:10]:
                    try:
                        title_elem = element.locator("h2 a").first
                        snippet_elem = element.locator(".b_caption p").first
                        
                        if title_elem:
                            results.append({
                                "title": title_elem.inner_text(),
                                "url": title_elem.get_attribute("href"),
                                "snippet": snippet_elem.inner_text() if snippet_elem else ""
                            })
                    except:
                        continue
            
        except Exception as e:
            self.add_to_context({"error": f"Failed to extract search results: {str(e)}"})
        
        return results
    
    def _analyze_search_results(self, query: str, results: List[Dict]) -> str:
        """Analyze search results using LLM."""
        results_text = "\n".join([
            f"{i+1}. {r.get('title', 'No title')}\n   URL: {r.get('url', 'No URL')}\n   {r.get('snippet', 'No snippet')}\n"
            for i, r in enumerate(results[:5])
        ])
        
        prompt = f"""
Search Query: {query}

Analyze these search results and provide:
1. Which results are most relevant to the query
2. What types of information are available
3. Which result would be best to visit first
4. Overall assessment of search success

Search Results:
{results_text}
"""
        
        return self.call_llm_for_analysis(prompt, results_text)
    
    def _find_and_click(self, text: str, **kwargs) -> ToolResult:
        """Find and click an element containing specific text."""
        try:
            # Try different selectors
            selectors = [
                f"text={text}",
                f"//a[contains(text(), '{text}')]",
                f"//button[contains(text(), '{text}')]",
                f"//*[contains(text(), '{text}')]"
            ]
            
            for selector in selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible():
                        element.click()
                        self.page.wait_for_load_state('networkidle')
                        
                        return ToolResult(
                            success=True,
                            output=f"Clicked element containing: {text}",
                            metadata={
                                "text": text,
                                "new_url": self.page.url,
                                "selector_used": selector
                            }
                        )
                except:
                    continue
            
            return ToolResult(
                success=False,
                output="",
                error=f"Could not find clickable element containing: {text}"
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Click operation failed: {str(e)}"
            )
    
    def _extract_info(self, query: str, **kwargs) -> ToolResult:
        """Extract specific information from current page."""
        content = self._get_page_content()
        
        if self.llm_client:
            prompt = f"""
Extract information about: {query}

From this page content:
{content[:self.max_content_length]}

Provide specific facts, data, or details related to the query.
"""
            
            extracted_info = self.call_llm_for_analysis(prompt, content)
        else:
            # Simple keyword extraction fallback
            lines = content.lower().split('\n')
            relevant_lines = [line for line in lines if query.lower() in line]
            extracted_info = '\n'.join(relevant_lines[:5])
        
        return ToolResult(
            success=True,
            output=f"Information extracted for: {query}",
            metadata={
                "query": query,
                "extracted_info": extracted_info,
                "source_url": self.current_url
            }
        )
    
    def _download(self, target: str, **kwargs) -> ToolResult:
        """Download a file from URL or by clicking a download link."""
        try:
            if target.startswith(('http://', 'https://')):
                # Direct URL download
                response = requests.get(target, stream=True)
                response.raise_for_status()
                
                # Get filename from URL or content-disposition
                filename = target.split('/')[-1] or "download"
                if 'content-disposition' in response.headers:
                    import re
                    cd = response.headers['content-disposition']
                    filename_match = re.search(r'filename="?([^"]+)"?', cd)
                    if filename_match:
                        filename = filename_match.group(1)
                
                filepath = self.download_dir / filename
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return ToolResult(
                    success=True,
                    output=f"Downloaded: {filename}",
                    metadata={
                        "filename": filename,
                        "filepath": str(filepath),
                        "size": filepath.stat().st_size,
                        "source_url": target
                    }
                )
            else:
                # Find and click download link
                click_result = self._find_and_click(target)
                if click_result.success:
                    # Wait for potential download
                    time.sleep(2)
                    return ToolResult(
                        success=True,
                        output=f"Initiated download by clicking: {target}",
                        metadata={"download_trigger": target}
                    )
                else:
                    return click_result
                
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Download failed: {str(e)}"
            )
    
    def _close_browser(self) -> ToolResult:
        """Close the browser and clean up."""
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
            
            return ToolResult(
                success=True,
                output="Browser closed successfully",
                metadata={"pages_visited": len(self.page_history)}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error closing browser: {str(e)}"
            )
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate browser command."""
        valid_commands = [
            "navigate", "search", "analyze_page", "find_and_click",
            "extract_info", "download", "intelligent_search", "close"
        ]
        
        command_parts = command.split(maxsplit=1)
        action = command_parts[0].lower()
        
        if action not in valid_commands:
            return False, f"Invalid command: {action}"
        
        # Additional validation for specific commands
        if action in ["navigate", "download"] and len(command_parts) < 2:
            return False, f"Command {action} requires a URL or target"
        
        return True, "Valid command"
    
    def get_help(self) -> str:
        """Return help text for browser tool."""
        return """
Agentic Browser Tool - Intelligent Web Automation

Commands:
- navigate <url>           : Navigate to a webpage
- search <query>           : Search the web for information
- analyze_page            : Analyze current page content
- find_and_click <text>   : Find and click element containing text
- extract_info <query>    : Extract specific information from page
- download <url_or_text>  : Download file from URL or click download link
- intelligent_search <goal> : Autonomous search with decision-making
- close                   : Close browser

Agentic Features:
- Autonomous content understanding using LLM
- Intelligent navigation decision-making
- Context-aware information extraction
- Goal-oriented web workflows

Example Usage:
- intelligent_search "find Python 3.11 download link"
- navigate https://python.org
- extract_info "latest Python version"
- download "Python 3.11 installer"

The browser can understand page content, make decisions about which links to follow,
and extract relevant information to accomplish complex goals autonomously.
"""
    
    def analyze_content(self, content: str, context: str = "") -> Dict[str, Any]:
        """Analyze web content using LLM."""
        prompt = f"""
Context: {context}

Analyze this web content and provide structured insights:
1. Main topics and themes
2. Key information and data points
3. Available actions (links, forms, downloads)
4. Relevance to any stated goals
5. Next recommended actions

Content:
{content[:self.max_content_length]}
"""
        
        analysis = self.call_llm_for_analysis(prompt, content)
        
        return {
            "analysis": analysis,
            "content_length": len(content),
            "timestamp": time.time()
        }
    
    def make_autonomous_decision(self, situation: str, options: List[str]) -> str:
        """Make autonomous navigation/action decisions."""
        options_text = "\n".join(f"{i+1}. {option}" for i, option in enumerate(options))
        
        prompt = f"""
Situation: {situation}

Available options:
{options_text}

Choose the best option and explain why. Consider:
- Likelihood of success
- Relevance to goals
- Potential risks
- Information quality

Respond with the option number and reasoning.
"""
        
        decision = self.call_llm_for_analysis(prompt, "")
        return decision