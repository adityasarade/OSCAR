"""
OSCAR Tool Base - Simplified tool interface
Provides common interface for all OSCAR tools.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
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
    
    def __init__(self, **data):
        if "timestamp" not in data.get("metadata", {}):
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class BaseTool(ABC):
    """Abstract base class for all OSCAR tools."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.platform = platform.system()
        self.is_available = self._check_availability()
    
    @abstractmethod
    def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute a command using this tool."""
        pass
    
    @abstractmethod
    def validate_command(self, command: str) -> tuple[bool, str]:
        """Validate if a command is safe and executable by this tool."""
        pass
    
    @abstractmethod
    def get_help(self) -> str:
        """Return help text describing tool usage."""
        pass
    
    def _check_availability(self) -> bool:
        """Check if this tool is available on the current system."""
        return True
    
    def get_info(self) -> Dict[str, Any]:
        """Get basic tool information."""
        return {
            "name": self.name,
            "description": self.description,
            "platform": self.platform,
            "available": self.is_available
        }


class ToolRegistry:
    """Simple registry for managing tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def get_available_tools(self) -> List[BaseTool]:
        """Get all available tools."""
        return [tool for tool in self.tools.values() if tool.is_available]
    
    def suggest_tool_for_command(self, command: str) -> Optional[BaseTool]:
        """Suggest the best tool for executing a command."""
        command_lower = command.lower()
        
        # Simple keyword-based tool suggestion
        if any(keyword in command_lower for keyword in ["mkdir", "ls", "dir", "cd", "pip", "python"]):
            return self.get_tool("shell")
        elif any(keyword in command_lower for keyword in ["browse", "search", "download", "web"]):
            return self.get_tool("browser")
        elif any(keyword in command_lower for keyword in ["create file", "copy", "move", "read file"]):
            return self.get_tool("file_ops")
        
        return None
    
    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """List all registered tools."""
        return {name: tool.get_info() for name, tool in self.tools.items()}


# Global tool registry
tool_registry = ToolRegistry()


def create_llm_client():
    """Create LLM client for tools that need it."""
    try:
        from groq import Groq
        from oscar.config.settings import settings
        
        api_key = settings.get_api_key(settings.llm_config.active_provider)
        return Groq(api_key=api_key)
    except Exception:
        return None