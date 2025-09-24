"""
OSCAR Shell Tool - Simplified cross-platform command execution

- Executes system commands (like ls, mkdir, pip install)
- Cross-platform (translates commands between Windows/Linux/Mac)
- Safety-validated before execution
"""

import subprocess
import shlex
import time
import re
from typing import Tuple
from pathlib import Path
import platform

from oscar.tools.base import BaseTool, ToolResult
from oscar.config.settings import SAFETY_PATTERNS


class ShellTool(BaseTool):
    """Cross-platform shell command execution with safety features."""
    
    def __init__(self):
        super().__init__(
            name="shell",
            description="Execute system commands safely across platforms"
        )
        
        self.is_windows = platform.system() == "Windows"
        
        # Essential command translations
        self.command_translations = {
            "ls": "dir" if self.is_windows else "ls",
            "pwd": "cd" if self.is_windows else "pwd", 
            "cat": "type" if self.is_windows else "cat",
            "which": "where" if self.is_windows else "which"
        }
        
        # Safe commands that are always allowed
        self.safe_commands = {
            "ls", "dir", "pwd", "cd", "mkdir", "echo", "cat", "type",
            "python", "pip", "git", "node", "npm", "curl", "wget",
            "tree", "whoami", "date", "which", "where"
        }
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute a shell command with safety checks."""
        start_time = time.time()
        
        # Validate command safety
        is_valid, reason = self.validate_command(command)
        if not is_valid:
            return ToolResult(
                success=False,
                output="",
                error=f"Command blocked for safety: {reason}",
                execution_time=time.time() - start_time
            )
        
        # Translate command for current platform
        translated_command = self._translate_command(command)
        
        try:
            timeout = kwargs.get("timeout", 30)
            cwd = kwargs.get("cwd", None)
            
            # Execute command
            if self.is_windows:
                result = subprocess.run(
                    translated_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd
                )
            else:
                args = shlex.split(translated_command)
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd
                )
            
            execution_time = time.time() - start_time
            
            return ToolResult(
                success=result.returncode == 0,
                output=result.stdout.strip() if result.stdout else "Command executed successfully",
                error=result.stderr.strip() if result.stderr else None,
                metadata={
                    "return_code": result.returncode,
                    "command": translated_command,
                    "platform": self.platform,
                    "cwd": str(cwd) if cwd else str(Path.cwd())
                },
                execution_time=execution_time
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds",
                execution_time=time.time() - start_time
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate if a command is safe to execute."""
        command_lower = command.lower().strip()
        
        # Check for dangerous patterns
        for pattern in SAFETY_PATTERNS["dangerous_commands"]:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous pattern detected"
        
        # Extract base command
        base_command = command_lower.split()[0] if command_lower.split() else ""
        
        # Check if base command is safe
        if base_command in self.safe_commands:
            return True, "Safe command"
        
        # Check for high-risk keywords
        for keyword in SAFETY_PATTERNS["high_risk_keywords"]:
            if keyword in command_lower:
                return False, f"High-risk operation detected: {keyword}"
        
        # Allow if not explicitly dangerous
        return True, "Command appears safe"
    
    def _translate_command(self, command: str) -> str:
        """Translate command for current platform."""
        command_parts = command.split()
        if not command_parts:
            return command
        
        base_command = command_parts[0].lower()
        
        if base_command in self.command_translations:
            translated_base = self.command_translations[base_command]
            return command.replace(command_parts[0], translated_base, 1)
        
        return command
    
    def get_help(self) -> str:
        """Return help text for shell tool."""
        return f"""
Shell Tool - Cross-Platform Command Execution

Platform: {self.platform}
Available: {self.is_available}

Safe Commands:
{', '.join(sorted(self.safe_commands))}

Example Usage:
- List files: ls (Unix) or dir (Windows)
- Create directory: mkdir my_folder
- Show current directory: pwd (Unix) or cd (Windows) 
- Install package: pip install requests

Safety Features:
- Dangerous commands are blocked
- System paths are protected
- Cross-platform command translation
- Timeout protection

All commands are validated before execution.
"""