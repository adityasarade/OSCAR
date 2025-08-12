"""
OSCAR Base Tool - Foundation for all execution tools
Provides common interface and functionality for all OSCAR tools.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
import platform


class ToolResult(BaseModel):
    """Standardized result format for all tools."""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    execution_time: float = 0.0
    timestamp: str = ""
    
    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class ToolCapability(Enum):
    """Tool capability categories."""
    SYSTEM = "system"           # System commands, file operations
    NETWORK = "network"         # Web browsing, downloads, API calls
    ANALYSIS = "analysis"       # Data analysis, content understanding
    AUTOMATION = "automation"   # UI automation, workflows
    COMMUNICATION = "communication"  # Email, messaging, notifications


class BaseTool(ABC):
    """
    Abstract base class for all OSCAR tools.
    Provides common functionality and enforces standard interface.
    """
    
    def __init__(self, name: str, description: str, capabilities: List[ToolCapability]):
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.platform = platform.system()
        self.is_available = self._check_availability()
        
    @abstractmethod
    def execute(self, command: str, **kwargs) -> ToolResult:
        """
        Execute a command using this tool.
        
        Args:
            command: The command/action to execute
            **kwargs: Additional parameters specific to the tool
            
        Returns:
            ToolResult: Standardized result with success, output, metadata
        """
        pass
    
    @abstractmethod
    def validate_command(self, command: str) -> tuple[bool, str]:
        """
        Validate if a command is safe and executable by this tool.
        
        Args:
            command: Command to validate
            
        Returns:
            Tuple of (is_valid, reason)
        """
        pass
    
    @abstractmethod
    def get_help(self) -> str:
        """Return help text describing tool usage and capabilities."""
        pass
    
    def _check_availability(self) -> bool:
        """Check if this tool is available on the current system."""
        return True  # Override in subclasses for specific requirements
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get tool metadata and status information."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [cap.value for cap in self.capabilities],
            "platform": self.platform,
            "available": self.is_available,
            "tool_type": self.__class__.__name__
        }
    
    def supports_capability(self, capability: ToolCapability) -> bool:
        """Check if tool supports a specific capability."""
        return capability in self.capabilities
    
    def log_execution(self, command: str, result: ToolResult) -> None:
        """Log tool execution for audit purposes."""
        # This could be extended to write to specific tool logs
        pass


class AgenticTool(BaseTool):
    """
    Extended base class for agentic tools that can make autonomous decisions.
    These tools can analyze content, understand context, and take intelligent actions.
    """
    
    def __init__(self, name: str, description: str, capabilities: List[ToolCapability],
                 llm_client=None):
        super().__init__(name, description, capabilities)
        self.llm_client = llm_client
        self.context_memory: List[Dict[str, Any]] = []
        
    @abstractmethod
    def analyze_content(self, content: str, context: str = "") -> Dict[str, Any]:
        """
        Analyze content using LLM and return structured insights.
        
        Args:
            content: Content to analyze (text, HTML, JSON, etc.)
            context: Additional context for analysis
            
        Returns:
            Dict containing analysis results, insights, and recommended actions
        """
        pass
    
    @abstractmethod
    def make_autonomous_decision(self, situation: str, options: List[str]) -> str:
        """
        Make an autonomous decision based on current situation and available options.
        
        Args:
            situation: Description of current situation
            options: List of possible actions/choices
            
        Returns:
            Selected option with reasoning
        """
        pass
    
    def add_to_context(self, interaction: Dict[str, Any]) -> None:
        """Add interaction to context memory for future decision-making."""
        self.context_memory.append({
            "timestamp": datetime.now().isoformat(),
            **interaction
        })
        
        # Keep only recent context (last 10 interactions)
        if len(self.context_memory) > 10:
            self.context_memory = self.context_memory[-10:]
    
    def get_context_summary(self) -> str:
        """Get a summary of recent context for LLM prompting."""
        if not self.context_memory:
            return "No previous context"
        
        recent_actions = []
        for ctx in self.context_memory[-5:]:  # Last 5 interactions
            action = ctx.get("action", "unknown")
            result = ctx.get("result", "unknown")
            recent_actions.append(f"- {action}: {result}")
        
        return "Recent context:\n" + "\n".join(recent_actions)
    
    def call_llm_for_analysis(self, prompt: str, content: str) -> str:
        """
        Call LLM for content analysis or decision-making.
        
        Args:
            prompt: Analysis prompt
            content: Content to analyze
            
        Returns:
            LLM response
        """
        if not self.llm_client:
            return "LLM not available for analysis"
        
        try:
            full_prompt = f"""
Context: You are helping OSCAR (an AI agent) analyze content and make decisions.

Current Context:
{self.get_context_summary()}

Task: {prompt}

Content to analyze:
{content}

Provide a clear, structured response with actionable insights.
"""
            
            response = self.llm_client.chat.completions.create(
                model="openai/gpt-oss-120b",  # Use reasoning model
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=1000,
                temperature=0.1,
                reasoning_effort="medium"
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"LLM analysis failed: {str(e)}"


class ToolRegistry:
    """Registry for managing all available tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.tool_categories: Dict[ToolCapability, List[str]] = {}
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self.tools[tool.name] = tool
        
        # Categorize by capabilities
        for capability in tool.capabilities:
            if capability not in self.tool_categories:
                self.tool_categories[capability] = []
            self.tool_categories[capability].append(tool.name)
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def get_tools_by_capability(self, capability: ToolCapability) -> List[BaseTool]:
        """Get all tools that support a specific capability."""
        tool_names = self.tool_categories.get(capability, [])
        return [self.tools[name] for name in tool_names if name in self.tools]
    
    def get_available_tools(self) -> List[BaseTool]:
        """Get all available tools on current system."""
        return [tool for tool in self.tools.values() if tool.is_available]
    
    def suggest_tool_for_command(self, command: str) -> Optional[BaseTool]:
        """Suggest the best tool for executing a command."""
        command_lower = command.lower()
        
        # Simple command-to-tool mapping
        if any(keyword in command_lower for keyword in ["mkdir", "ls", "dir", "cd", "cp", "mv", "rm"]):
            return self.get_tool("shell")
        elif any(keyword in command_lower for keyword in ["browse", "search", "download", "web", "http"]):
            return self.get_tool("browser")
        elif any(keyword in command_lower for keyword in ["create file", "copy file", "move file"]):
            return self.get_tool("file_ops")
        
        return None
    
    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """List all registered tools with their metadata."""
        return {name: tool.get_metadata() for name, tool in self.tools.items()}


# Global tool registry instance
tool_registry = ToolRegistry()