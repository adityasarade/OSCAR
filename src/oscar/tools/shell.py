"""
OSCAR Shell Tool - Cross-Platform Command Execution
Handles system commands with safety checks and cross-platform compatibility.
"""

import subprocess
import shlex
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import platform
import os

from oscar.tools.base import BaseTool, ToolResult, ToolCapability


class ShellTool(BaseTool):
    """
    Cross-platform shell command execution tool with safety features.
    """
    
    def __init__(self):
        super().__init__(
            name="shell",
            description="Execute system commands safely across Windows, Linux, and macOS",
            capabilities=[ToolCapability.SYSTEM, ToolCapability.AUTOMATION]
        )
        
        # Platform-specific settings
        self.is_windows = platform.system() == "Windows"
        self.shell_cmd = "cmd" if self.is_windows else "bash"
        
        # Command mappings for cross-platform compatibility
        self.command_mappings = self._build_command_mappings()
        
        # Safety patterns (inherited from config but tool-specific)
        self.dangerous_patterns = [
            r"rm\s+-rf\s+/",
            r"del\s+/s\s+/q",
            r"format\s+c:",
            r"dd\s+if=",
            r":(){ :|:& };:",  # Fork bomb
            r"sudo\s+rm\s+-rf",
            r"rmdir\s+/s\s+/q",
            r"diskpart",
            r"fdisk",
        ]
        
        # Allowed safe commands
        self.safe_commands = [
            "ls", "dir", "pwd", "cd", "mkdir", "echo", "cat", "type",
            "find", "grep", "which", "where", "python", "pip", "git",
            "node", "npm", "curl", "wget", "ping", "tree", "cp", "copy",
            "mv", "move", "touch", "whoami", "date", "history"
        ]
    
    def _build_command_mappings(self) -> Dict[str, Dict[str, str]]:
        """Build cross-platform command mappings."""
        return {
            "list_files": {
                "Windows": "dir",
                "Linux": "ls -la",
                "Darwin": "ls -la"
            },
            "current_directory": {
                "Windows": "cd",
                "Linux": "pwd", 
                "Darwin": "pwd"
            },
            "create_directory": {
                "Windows": "mkdir",
                "Linux": "mkdir -p",
                "Darwin": "mkdir -p"
            },
            "copy_file": {
                "Windows": "copy",
                "Linux": "cp",
                "Darwin": "cp"
            },
            "move_file": {
                "Windows": "move",
                "Linux": "mv",
                "Darwin": "mv"
            },
            "remove_file": {
                "Windows": "del",
                "Linux": "rm",
                "Darwin": "rm"
            },
            "show_processes": {
                "Windows": "tasklist",
                "Linux": "ps aux",
                "Darwin": "ps aux"
            }
        }
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """
        Execute a shell command with safety checks.
        
        Args:
            command: Shell command to execute
            **kwargs: Additional options like timeout, cwd, capture_output
            
        Returns:
            ToolResult with execution results
        """
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
        
        # Translate command for current platform if needed
        translated_command = self._translate_command(command)
        
        try:
            # Prepare execution parameters
            timeout = kwargs.get("timeout", 30)
            cwd = kwargs.get("cwd", None)
            capture_output = kwargs.get("capture_output", True)
            
            # Execute command
            if self.is_windows:
                result = subprocess.run(
                    translated_command,
                    shell=True,
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                    cwd=cwd
                )
            else:
                # Use shlex for safer parsing on Unix systems
                args = shlex.split(translated_command)
                result = subprocess.run(
                    args,
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                    cwd=cwd
                )
            
            execution_time = time.time() - start_time
            
            # Process results
            if result.returncode == 0:
                return ToolResult(
                    success=True,
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
            else:
                return ToolResult(
                    success=False,
                    output=result.stdout.strip() if result.stdout else "",
                    error=result.stderr.strip() if result.stderr else f"Command failed with exit code {result.returncode}",
                    metadata={
                        "return_code": result.returncode,
                        "command": translated_command,
                        "platform": self.platform
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
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Command not found: {str(e)}",
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
        """
        Validate if a command is safe to execute.
        
        Args:
            command: Command to validate
            
        Returns:
            Tuple of (is_valid, reason)
        """
        command_lower = command.lower().strip()
        
        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Dangerous pattern detected: {pattern}"
        
        # Extract base command
        base_command = command_lower.split()[0] if command_lower.split() else ""
        
        # Check if base command is in safe list
        if base_command in self.safe_commands:
            return True, "Safe command"
        
        # Check for potentially dangerous operations
        danger_indicators = [
            "format", "fdisk", "diskpart", "dd", "mkfs",
            "parted", "gparted", "cfdisk", "sfdisk"
        ]
        
        for indicator in danger_indicators:
            if indicator in command_lower:
                return False, f"Potentially dangerous operation: {indicator}"
        
        # Check for system modification attempts
        system_paths = [
            "/system", "/boot", "c:\\windows\\system32", 
            "/etc/passwd", "/etc/shadow", "registry"
        ]
        
        for path in system_paths:
            if path.lower() in command_lower:
                return False, f"Attempt to access system path: {path}"
        
        # Allow if not explicitly dangerous
        return True, "Command appears safe"
    
    def _translate_command(self, command: str) -> str:
        """Translate command for current platform if needed."""
        command_parts = command.split()
        if not command_parts:
            return command
        
        base_command = command_parts[0].lower()
        
        # Check for direct command mappings
        for mapping_name, platforms in self.command_mappings.items():
            if self.platform in platforms:
                platform_command = platforms[self.platform]
                # Simple replacement for basic commands
                if base_command in platform_command.lower():
                    return command  # Already correct for platform
        
        # Handle specific translations
        if base_command == "ls" and self.is_windows:
            return command.replace("ls", "dir", 1)
        elif base_command == "pwd" and self.is_windows:
            return command.replace("pwd", "cd", 1)
        elif base_command == "cat" and self.is_windows:
            return command.replace("cat", "type", 1)
        elif base_command == "which" and self.is_windows:
            return command.replace("which", "where", 1)
        
        return command
    
    def get_help(self) -> str:
        """Return help text for shell tool."""
        return f"""
Shell Tool - Cross-Platform Command Execution

Platform: {self.platform}
Available: {self.is_available}

Safe Commands:
{', '.join(self.safe_commands)}

Example Usage:
- List files: ls (Linux/Mac) or dir (Windows)
- Create directory: mkdir my_folder
- Show current directory: pwd (Linux/Mac) or cd (Windows)
- Copy file: cp source dest (Linux/Mac) or copy source dest (Windows)

Safety Features:
- Dangerous commands are blocked
- System paths are protected
- Commands are validated before execution
- Cross-platform command translation

Note: All commands are subject to safety validation.
Some dangerous operations require explicit confirmation.
"""
    
    def get_platform_info(self) -> Dict[str, Any]:
        """Get detailed platform information."""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.architecture(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "current_user": os.getenv("USER") or os.getenv("USERNAME", "unknown"),
            "current_directory": str(Path.cwd()),
            "home_directory": str(Path.home()),
            "shell_command": self.shell_cmd
        }
    
    def execute_safe_command(self, command_type: str, **params) -> ToolResult:
        """
        Execute a predefined safe command by type.
        
        Args:
            command_type: Type of command (list_files, current_directory, etc.)
            **params: Parameters for the command
            
        Returns:
            ToolResult
        """
        if command_type not in self.command_mappings:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown command type: {command_type}"
            )
        
        platform_commands = self.command_mappings[command_type]
        if self.platform not in platform_commands:
            return ToolResult(
                success=False,
                output="",
                error=f"Command type {command_type} not supported on {self.platform}"
            )
        
        command = platform_commands[self.platform]
        
        # Add parameters if provided
        if params:
            param_str = " ".join(f"{k} {v}" for k, v in params.items())
            command = f"{command} {param_str}"
        
        return self.execute(command)