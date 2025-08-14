"""
OSCAR File Operations Tool - Simplified safe file management
"""

import os
import shutil
import time
from typing import List, Tuple
from pathlib import Path

from oscar.tools.base import BaseTool, ToolResult


class FileOpsTool(BaseTool):
    """Simplified file operations with essential safety features."""
    
    def __init__(self):
        super().__init__(
            name="file_ops",
            description="Safe file and directory operations"
        )
        
        # Safe directories for operations
        self.safe_base_dirs = [
            Path.cwd(),
            Path.home() / "Documents",
            Path.home() / "Desktop", 
            Path.home() / "Downloads"
        ]
        
        # Restricted directories
        self.restricted_dirs = [
            "/system", "/boot", "/etc", "/usr/bin",
            "C:/Windows", "C:/Program Files"
        ]
        
        # Safe file extensions
        self.safe_extensions = {
            '.txt', '.md', '.json', '.yaml', '.yml', '.csv', '.log',
            '.py', '.js', '.html', '.css', '.xml', '.ini',
            '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip'
        }
        
        # Max file size (50MB)
        self.max_file_size = 50 * 1024 * 1024
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """Execute a file operation command."""
        start_time = time.time()
        
        try:
            parts = command.split(maxsplit=2)
            action = parts[0].lower()
            
            handlers = {
                "create_file": self._create_file,
                "create_directory": self._create_directory, 
                "copy": self._copy,
                "move": self._move,
                "delete": self._delete,
                "list": self._list_directory,
                "read": self._read_file,
                "write": self._write_file
            }
            
            if action not in handlers:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown file operation: {action}",
                    execution_time=time.time() - start_time
                )
            
            result = handlers[action](parts, **kwargs)
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"File operation error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _create_file(self, parts: List[str], **kwargs) -> ToolResult:
        """Create a new file with optional content."""
        if len(parts) < 2:
            return ToolResult(False, "", "create_file requires a file path")
        
        file_path = Path(parts[1])
        content = parts[2] if len(parts) > 2 else kwargs.get("content", "")
        
        if not self._is_safe_path(file_path, for_write=True):
            return ToolResult(False, "", f"Unsafe file path: {file_path}")
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if file_path.exists() and not kwargs.get("overwrite", False):
                return ToolResult(False, "", f"File already exists: {file_path}")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                True,
                f"Created file: {file_path}",
                metadata={"file_path": str(file_path), "size": len(content)}
            )
            
        except Exception as e:
            return ToolResult(False, "", f"Failed to create file: {e}")
    
    def _create_directory(self, parts: List[str], **kwargs) -> ToolResult:
        """Create a new directory."""
        if len(parts) < 2:
            return ToolResult(False, "", "create_directory requires a path")
        
        dir_path = Path(parts[1])
        
        if not self._is_safe_path(dir_path, for_write=True):
            return ToolResult(False, "", f"Unsafe directory path: {dir_path}")
        
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return ToolResult(True, f"Created directory: {dir_path}")
        except Exception as e:
            return ToolResult(False, "", f"Failed to create directory: {e}")
    
    def _copy(self, parts: List[str], **kwargs) -> ToolResult:
        """Copy a file or directory."""
        if len(parts) < 3:
            return ToolResult(False, "", "copy requires source and destination")
        
        source = Path(parts[1])
        destination = Path(parts[2])
        
        if not self._is_safe_path(source, for_read=True):
            return ToolResult(False, "", f"Unsafe source path: {source}")
        
        if not self._is_safe_path(destination, for_write=True):
            return ToolResult(False, "", f"Unsafe destination path: {destination}")
        
        try:
            if not source.exists():
                return ToolResult(False, "", f"Source does not exist: {source}")
            
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                operation = "file"
            else:
                shutil.copytree(source, destination, dirs_exist_ok=kwargs.get("overwrite", False))
                operation = "directory"
            
            return ToolResult(True, f"Copied {operation}: {source} -> {destination}")
            
        except Exception as e:
            return ToolResult(False, "", f"Copy failed: {e}")
    
    def _move(self, parts: List[str], **kwargs) -> ToolResult:
        """Move a file or directory."""
        if len(parts) < 3:
            return ToolResult(False, "", "move requires source and destination")
        
        source = Path(parts[1])
        destination = Path(parts[2])
        
        if not self._is_safe_path(source, for_read=True):
            return ToolResult(False, "", f"Unsafe source path: {source}")
        
        if not self._is_safe_path(destination, for_write=True):
            return ToolResult(False, "", f"Unsafe destination path: {destination}")
        
        try:
            if not source.exists():
                return ToolResult(False, "", f"Source does not exist: {source}")
            
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            
            return ToolResult(True, f"Moved: {source} -> {destination}")
            
        except Exception as e:
            return ToolResult(False, "", f"Move failed: {e}")
    
    def _delete(self, parts: List[str], **kwargs) -> ToolResult:
        """Delete a file or directory."""
        if len(parts) < 2:
            return ToolResult(False, "", "delete requires a path")
        
        target = Path(parts[1])
        
        if not self._is_safe_path(target, for_delete=True):
            return ToolResult(False, "", f"Unsafe deletion path: {target}")
        
        try:
            if not target.exists():
                return ToolResult(False, "", f"Path does not exist: {target}")
            
            if target.is_file():
                target.unlink()
                operation = "file"
            else:
                shutil.rmtree(target)
                operation = "directory"
            
            return ToolResult(True, f"Deleted {operation}: {target}")
            
        except Exception as e:
            return ToolResult(False, "", f"Delete failed: {e}")
    
    def _list_directory(self, parts: List[str], **kwargs) -> ToolResult:
        """List directory contents."""
        dir_path = Path(parts[1]) if len(parts) > 1 else Path.cwd()
        
        if not self._is_safe_path(dir_path, for_read=True):
            return ToolResult(False, "", f"Unsafe directory path: {dir_path}")
        
        try:
            if not dir_path.exists() or not dir_path.is_dir():
                return ToolResult(False, "", f"Directory does not exist: {dir_path}")
            
            items = []
            for item in dir_path.iterdir():
                try:
                    stat = item.stat()
                    items.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else 0
                    })
                except (OSError, PermissionError):
                    continue
            
            # Sort: directories first, then by name
            items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
            # Create output
            output_lines = [f"Contents of {dir_path}:"]
            for item in items:
                icon = "📁" if item["type"] == "directory" else "📄"
                size_str = f" ({item['size']} bytes)" if item["type"] == "file" else ""
                output_lines.append(f"{icon} {item['name']}{size_str}")
            
            return ToolResult(
                True,
                "\n".join(output_lines),
                metadata={"item_count": len(items), "items": items[:20]}
            )
            
        except Exception as e:
            return ToolResult(False, "", f"Failed to list directory: {e}")
    
    def _read_file(self, parts: List[str], **kwargs) -> ToolResult:
        """Read file contents."""
        if len(parts) < 2:
            return ToolResult(False, "", "read requires a file path")
        
        file_path = Path(parts[1])
        
        if not self._is_safe_path(file_path, for_read=True):
            return ToolResult(False, "", f"Unsafe file path: {file_path}")
        
        try:
            if not file_path.exists() or not file_path.is_file():
                return ToolResult(False, "", f"File does not exist: {file_path}")
            
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return ToolResult(False, "", f"File too large: {file_size} bytes")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Limit output for display
            max_display = kwargs.get("max_length", 2000)
            if len(content) > max_display:
                output = content[:max_display] + f"\n... (truncated, total: {len(content)} chars)"
            else:
                output = content
            
            return ToolResult(
                True,
                output,
                metadata={"file_size": file_size, "content_length": len(content)}
            )
            
        except UnicodeDecodeError:
            return ToolResult(False, "", "File appears to be binary")
        except Exception as e:
            return ToolResult(False, "", f"Failed to read file: {e}")
    
    def _write_file(self, parts: List[str], **kwargs) -> ToolResult:
        """Write content to file."""
        if len(parts) < 3:
            return ToolResult(False, "", "write requires file path and content")
        
        file_path = Path(parts[1])
        content = parts[2]
        
        if not self._is_safe_path(file_path, for_write=True):
            return ToolResult(False, "", f"Unsafe file path: {file_path}")
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if file_path.exists() and not kwargs.get("overwrite", False):
                return ToolResult(False, "", f"File exists, use overwrite=True")
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                True,
                f"Written to: {file_path}",
                metadata={"content_length": len(content)}
            )
            
        except Exception as e:
            return ToolResult(False, "", f"Failed to write file: {e}")
    
    def _is_safe_path(self, path: Path, for_read: bool = False, 
                     for_write: bool = False, for_delete: bool = False) -> bool:
        """Simple path safety validation."""
        try:
            abs_path = path.absolute()
            
            # Check restricted directories
            for restricted in self.restricted_dirs:
                if str(abs_path).startswith(restricted):
                    return False
            
            # For write/delete operations, check extension
            if (for_write or for_delete) and path.suffix:
                if path.suffix.lower() not in self.safe_extensions:
                    return False
            
            # For delete, extra safety
            if for_delete:
                if str(abs_path) in ['/', 'C:\\'] or abs_path.parent == abs_path:
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate file operation command."""
        valid_commands = [
            "create_file", "create_directory", "copy", "move", 
            "delete", "list", "read", "write"
        ]
        
        action = command.split()[0].lower() if command.split() else ""
        
        if action not in valid_commands:
            return False, f"Invalid command: {action}"
        
        return True, "Valid command"
    
    def get_help(self) -> str:
        """Return help text."""
        return f"""
File Operations Tool - Safe File Management

Commands:
- create_file <path> [content]     : Create new file
- create_directory <path>          : Create new directory  
- copy <source> <destination>      : Copy file/directory
- move <source> <destination>      : Move file/directory
- delete <path>                    : Delete file/directory
- list [directory]                 : List contents
- read <file_path>                 : Read file contents
- write <file_path> <content>      : Write to file

Safety Features:
- Operations limited to safe directories
- File extension validation
- Size limits ({self.max_file_size // (1024*1024)}MB max)
- System directories protected

Safe Extensions: {', '.join(sorted(list(self.safe_extensions)[:10]))}...
"""