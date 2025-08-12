"""
OSCAR File Operations Tool - Safe File and Directory Management
Handles file operations with safety checks and cross-platform compatibility.
"""

import os
import shutil
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import mimetypes
import hashlib

from oscar.tools.base import BaseTool, ToolResult, ToolCapability


class FileOpsTool(BaseTool):
    """
    Safe file operations tool with cross-platform support and safety features.
    """
    
    def __init__(self):
        super().__init__(
            name="file_ops",
            description="Safe file and directory operations with cross-platform support",
            capabilities=[ToolCapability.SYSTEM, ToolCapability.AUTOMATION]
        )
        
        # Safe directories (relative to current working directory)
        self.safe_base_dirs = [
            Path.cwd(),
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
            Path("/tmp") if os.name != 'nt' else Path(os.environ.get('TEMP', 'C:/temp'))
        ]
        
        # Restricted directories (never allow operations here)
        self.restricted_dirs = [
            "/system", "/boot", "/etc", "/usr/bin", "/usr/sbin",
            "C:/Windows", "C:/Program Files", "C:/Program Files (x86)",
            "/Applications", "/System", "/Library"
        ]
        
        # Allowed file extensions for creation/modification
        self.safe_extensions = {
            '.txt', '.md', '.json', '.yaml', '.yml', '.csv', '.log',
            '.py', '.js', '.html', '.css', '.xml', '.ini', '.cfg',
            '.sh', '.bat', '.ps1', '.dockerfile', '.gitignore',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.tar', '.gz', '.mp3', '.mp4', '.avi'
        }
        
        # Maximum file size for operations (100MB)
        self.max_file_size = 100 * 1024 * 1024
    
    def execute(self, command: str, **kwargs) -> ToolResult:
        """
        Execute a file operation command.
        
        Commands:
        - create_file <path> [content]
        - create_directory <path>
        - copy <source> <destination>
        - move <source> <destination>
        - delete <path>
        - list <directory>
        - read <file_path>
        - write <file_path> <content>
        - get_info <path>
        - search <directory> <pattern>
        """
        start_time = time.time()
        
        try:
            command_parts = command.split(maxsplit=2)
            action = command_parts[0].lower()
            
            # Route to appropriate handler
            if action == "create_file":
                result = self._create_file(command_parts, **kwargs)
            elif action == "create_directory":
                result = self._create_directory(command_parts, **kwargs)
            elif action == "copy":
                result = self._copy(command_parts, **kwargs)
            elif action == "move":
                result = self._move(command_parts, **kwargs)
            elif action == "delete":
                result = self._delete(command_parts, **kwargs)
            elif action == "list":
                result = self._list_directory(command_parts, **kwargs)
            elif action == "read":
                result = self._read_file(command_parts, **kwargs)
            elif action == "write":
                result = self._write_file(command_parts, **kwargs)
            elif action == "get_info":
                result = self._get_info(command_parts, **kwargs)
            elif action == "search":
                result = self._search(command_parts, **kwargs)
            else:
                result = ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown file operation: {action}"
                )
            
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"File operation error: {str(e)}",
                execution_time=time.time() - start_time
            )
    
    def _create_file(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Create a new file with optional content."""
        if len(command_parts) < 2:
            return ToolResult(
                success=False,
                output="",
                error="create_file requires a file path"
            )
        
        file_path = Path(command_parts[1])
        content = command_parts[2] if len(command_parts) > 2 else kwargs.get("content", "")
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(file_path, for_write=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe file path: {reason}"
            )
        
        try:
            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file already exists
            if file_path.exists() and not kwargs.get("overwrite", False):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File already exists: {file_path}"
                )
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"Created file: {file_path}",
                metadata={
                    "file_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "content_length": len(content)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to create file: {str(e)}"
            )
    
    def _create_directory(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Create a new directory."""
        if len(command_parts) < 2:
            return ToolResult(
                success=False,
                output="",
                error="create_directory requires a directory path"
            )
        
        dir_path = Path(command_parts[1])
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(dir_path, for_write=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe directory path: {reason}"
            )
        
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            
            return ToolResult(
                success=True,
                output=f"Created directory: {dir_path}",
                metadata={
                    "directory_path": str(dir_path),
                    "absolute_path": str(dir_path.absolute())
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to create directory: {str(e)}"
            )
    
    def _copy(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Copy a file or directory."""
        if len(command_parts) < 3:
            return ToolResult(
                success=False,
                output="",
                error="copy requires source and destination paths"
            )
        
        source = Path(command_parts[1])
        destination = Path(command_parts[2])
        
        # Validate both paths
        is_safe, reason = self._validate_path_safety(source, for_read=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe source path: {reason}"
            )
        
        is_safe, reason = self._validate_path_safety(destination, for_write=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe destination path: {reason}"
            )
        
        try:
            if not source.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Source does not exist: {source}"
                )
            
            if source.is_file():
                # Copy file
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                operation = "file"
            else:
                # Copy directory
                shutil.copytree(source, destination, dirs_exist_ok=kwargs.get("overwrite", False))
                operation = "directory"
            
            return ToolResult(
                success=True,
                output=f"Copied {operation}: {source} -> {destination}",
                metadata={
                    "source": str(source),
                    "destination": str(destination),
                    "operation_type": operation
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Copy operation failed: {str(e)}"
            )
    
    def _move(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Move a file or directory."""
        if len(command_parts) < 3:
            return ToolResult(
                success=False,
                output="",
                error="move requires source and destination paths"
            )
        
        source = Path(command_parts[1])
        destination = Path(command_parts[2])
        
        # Validate both paths
        is_safe, reason = self._validate_path_safety(source, for_read=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe source path: {reason}"
            )
        
        is_safe, reason = self._validate_path_safety(destination, for_write=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe destination path: {reason}"
            )
        
        try:
            if not source.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Source does not exist: {source}"
                )
            
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            
            return ToolResult(
                success=True,
                output=f"Moved: {source} -> {destination}",
                metadata={
                    "source": str(source),
                    "destination": str(destination)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Move operation failed: {str(e)}"
            )
    
    def _delete(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Delete a file or directory."""
        if len(command_parts) < 2:
            return ToolResult(
                success=False,
                output="",
                error="delete requires a path"
            )
        
        target_path = Path(command_parts[1])
        
        # Extra safety check for deletion
        is_safe, reason = self._validate_path_safety(target_path, for_delete=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe deletion path: {reason}"
            )
        
        try:
            if not target_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path does not exist: {target_path}"
                )
            
            if target_path.is_file():
                target_path.unlink()
                operation = "file"
            else:
                shutil.rmtree(target_path)
                operation = "directory"
            
            return ToolResult(
                success=True,
                output=f"Deleted {operation}: {target_path}",
                metadata={
                    "deleted_path": str(target_path),
                    "operation_type": operation
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Delete operation failed: {str(e)}"
            )
    
    def _list_directory(self, command_parts: List[str], **kwargs) -> ToolResult:
        """List contents of a directory."""
        dir_path = Path(command_parts[1]) if len(command_parts) > 1 else Path.cwd()
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(dir_path, for_read=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe directory path: {reason}"
            )
        
        try:
            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Directory does not exist: {dir_path}"
                )
            
            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a directory: {dir_path}"
                )
            
            # Get directory contents
            items = []
            total_size = 0
            
            for item in dir_path.iterdir():
                try:
                    stat = item.stat()
                    item_info = {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": time.ctime(stat.st_mtime),
                        "permissions": oct(stat.st_mode)[-3:]
                    }
                    
                    if item.is_file():
                        item_info["extension"] = item.suffix
                        total_size += stat.st_size
                    
                    items.append(item_info)
                    
                except (OSError, PermissionError):
                    # Skip items we can't access
                    continue
            
            # Sort items (directories first, then by name)
            items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
            # Create readable output
            output_lines = [f"Contents of {dir_path}:"]
            for item in items:
                type_indicator = "📁" if item["type"] == "directory" else "📄"
                size_str = f" ({item['size']} bytes)" if item["type"] == "file" else ""
                output_lines.append(f"{type_indicator} {item['name']}{size_str}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "directory": str(dir_path),
                    "item_count": len(items),
                    "total_size": total_size,
                    "items": items[:20]  # Limit metadata to first 20 items
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list directory: {str(e)}"
            )
    
    def _read_file(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Read contents of a file."""
        if len(command_parts) < 2:
            return ToolResult(
                success=False,
                output="",
                error="read requires a file path"
            )
        
        file_path = Path(command_parts[1])
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(file_path, for_read=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe file path: {reason}"
            )
        
        try:
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File does not exist: {file_path}"
                )
            
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path is not a file: {file_path}"
                )
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File too large to read: {file_size} bytes (max: {self.max_file_size})"
                )
            
            # Try to read as text
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Limit output for very long files
                max_output_length = kwargs.get("max_length", 5000)
                if len(content) > max_output_length:
                    output = content[:max_output_length] + f"\n... (truncated, total length: {len(content)} characters)"
                else:
                    output = content
                
                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "file_path": str(file_path),
                        "file_size": file_size,
                        "content_length": len(content),
                        "encoding": "utf-8",
                        "mime_type": mimetypes.guess_type(str(file_path))[0]
                    }
                )
                
            except UnicodeDecodeError:
                # File is likely binary
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File appears to be binary and cannot be read as text: {file_path}"
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read file: {str(e)}"
            )
    
    def _write_file(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Write content to a file."""
        if len(command_parts) < 3:
            return ToolResult(
                success=False,
                output="",
                error="write requires file path and content"
            )
        
        file_path = Path(command_parts[1])
        content = command_parts[2]
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(file_path, for_write=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe file path: {reason}"
            )
        
        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists and handle overwrite
            if file_path.exists() and not kwargs.get("overwrite", False):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"File exists and overwrite not specified: {file_path}"
                )
            
            # Write content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"Written to file: {file_path}",
                metadata={
                    "file_path": str(file_path),
                    "content_length": len(content),
                    "file_size": file_path.stat().st_size
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write file: {str(e)}"
            )
    
    def _get_info(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Get detailed information about a file or directory."""
        if len(command_parts) < 2:
            return ToolResult(
                success=False,
                output="",
                error="get_info requires a path"
            )
        
        target_path = Path(command_parts[1])
        
        try:
            if not target_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Path does not exist: {target_path}"
                )
            
            stat = target_path.stat()
            
            info = {
                "path": str(target_path),
                "absolute_path": str(target_path.absolute()),
                "name": target_path.name,
                "type": "directory" if target_path.is_dir() else "file",
                "size": stat.st_size,
                "created": time.ctime(stat.st_ctime),
                "modified": time.ctime(stat.st_mtime),
                "accessed": time.ctime(stat.st_atime),
                "permissions": oct(stat.st_mode)[-3:],
                "owner_readable": os.access(target_path, os.R_OK),
                "owner_writable": os.access(target_path, os.W_OK),
                "owner_executable": os.access(target_path, os.X_OK)
            }
            
            if target_path.is_file():
                info["extension"] = target_path.suffix
                info["mime_type"] = mimetypes.guess_type(str(target_path))[0]
                
                # Calculate file hash for integrity checking
                if stat.st_size < self.max_file_size:
                    try:
                        with open(target_path, 'rb') as f:
                            info["md5_hash"] = hashlib.md5(f.read()).hexdigest()
                    except:
                        info["md5_hash"] = "Unable to calculate"
            
            # Format output
            output_lines = [f"Information for: {target_path}"]
            for key, value in info.items():
                if key not in ["path", "absolute_path"]:  # Don't repeat in output
                    output_lines.append(f"{key.replace('_', ' ').title()}: {value}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata=info
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get info: {str(e)}"
            )
    
    def _search(self, command_parts: List[str], **kwargs) -> ToolResult:
        """Search for files matching a pattern in a directory."""
        if len(command_parts) < 3:
            return ToolResult(
                success=False,
                output="",
                error="search requires directory and pattern"
            )
        
        search_dir = Path(command_parts[1])
        pattern = command_parts[2]
        
        # Validate path safety
        is_safe, reason = self._validate_path_safety(search_dir, for_read=True)
        if not is_safe:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsafe search directory: {reason}"
            )
        
        try:
            if not search_dir.exists() or not search_dir.is_dir():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Search directory does not exist or is not a directory: {search_dir}"
                )
            
            matches = []
            
            # Search recursively
            for item in search_dir.rglob(pattern):
                try:
                    if self._validate_path_safety(item, for_read=True)[0]:
                        stat = item.stat()
                        matches.append({
                            "path": str(item.relative_to(search_dir)),
                            "absolute_path": str(item.absolute()),
                            "type": "directory" if item.is_dir() else "file",
                            "size": stat.st_size if item.is_file() else 0,
                            "modified": time.ctime(stat.st_mtime)
                        })
                except (OSError, PermissionError):
                    continue
            
            # Limit results
            max_results = kwargs.get("max_results", 50)
            if len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True
            else:
                truncated = False
            
            # Format output
            if matches:
                output_lines = [f"Found {len(matches)} matches for '{pattern}' in {search_dir}:"]
                for match in matches:
                    type_indicator = "📁" if match["type"] == "directory" else "📄"
                    size_str = f" ({match['size']} bytes)" if match["type"] == "file" else ""
                    output_lines.append(f"{type_indicator} {match['path']}{size_str}")
                
                if truncated:
                    output_lines.append(f"... (results truncated at {max_results})")
            else:
                output_lines = [f"No matches found for '{pattern}' in {search_dir}"]
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "search_directory": str(search_dir),
                    "pattern": pattern,
                    "matches_found": len(matches),
                    "truncated": truncated,
                    "matches": matches
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Search failed: {str(e)}"
            )
    
    def _validate_path_safety(self, path: Path, for_read: bool = False, 
                             for_write: bool = False, for_delete: bool = False) -> Tuple[bool, str]:
        """Validate if a path is safe for the requested operation."""
        try:
            # Convert to absolute path for checking
            abs_path = path.absolute()
            
            # Check for restricted directories
            for restricted in self.restricted_dirs:
                restricted_path = Path(restricted).absolute()
                try:
                    abs_path.relative_to(restricted_path)
                    return False, f"Path is in restricted directory: {restricted}"
                except ValueError:
                    continue  # Not in this restricted directory
            
            # For write operations, check if extension is safe
            if (for_write or for_delete) and path.suffix:
                if path.suffix.lower() not in self.safe_extensions:
                    return False, f"File extension not allowed: {path.suffix}"
            
            # For delete operations, extra safety checks
            if for_delete:
                # Don't allow deleting entire drives or root directories
                if str(abs_path) in ['/', 'C:\\', 'D:\\'] or abs_path.parent == abs_path:
                    return False, "Cannot delete root directory or drive"
                
                # Don't allow deleting system-critical files
                critical_files = ['.bashrc', '.profile', '.bash_profile', 'autoexec.bat', 'config.sys']
                if path.name.lower() in critical_files:
                    return False, f"Cannot delete critical system file: {path.name}"
            
            # Check if path is within safe base directories for write operations
            if for_write and not for_read:
                is_in_safe_dir = False
                for safe_dir in self.safe_base_dirs:
                    try:
                        safe_abs = safe_dir.absolute()
                        abs_path.relative_to(safe_abs)
                        is_in_safe_dir = True
                        break
                    except ValueError:
                        continue
                
                if not is_in_safe_dir:
                    return False, "Write operations only allowed in safe directories"
            
            return True, "Path is safe"
            
        except Exception as e:
            return False, f"Path validation error: {str(e)}"
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """Validate file operation command."""
        valid_commands = [
            "create_file", "create_directory", "copy", "move", "delete",
            "list", "read", "write", "get_info", "search"
        ]
        
        command_parts = command.split(maxsplit=1)
        action = command_parts[0].lower()
        
        if action not in valid_commands:
            return False, f"Invalid command: {action}"
        
        # Additional validation for specific commands
        if action in ["delete"] and len(command_parts) < 2:
            return False, f"Command {action} requires a path"
        
        if action in ["copy", "move"] and len(command.split()) < 3:
            return False, f"Command {action} requires source and destination paths"
        
        return True, "Valid command"
    
    def get_help(self) -> str:
        """Return help text for file operations tool."""
        return f"""
File Operations Tool - Safe File and Directory Management

Commands:
- create_file <path> [content]     : Create a new file with optional content
- create_directory <path>          : Create a new directory
- copy <source> <destination>      : Copy file or directory
- move <source> <destination>      : Move file or directory  
- delete <path>                    : Delete file or directory
- list [directory]                 : List directory contents (current dir if not specified)
- read <file_path>                 : Read file contents
- write <file_path> <content>      : Write content to file
- get_info <path>                  : Get detailed information about file/directory
- search <directory> <pattern>     : Search for files matching pattern

Safety Features:
- Operations restricted to safe directories
- System directories are protected
- File extension validation for write operations
- Size limits for file operations ({self.max_file_size // (1024*1024)}MB max)
- Critical system files are protected from deletion

Safe Extensions:
{', '.join(sorted(self.safe_extensions))}

Example Usage:
- create_file "my_script.py" "print('Hello World')"
- create_directory "new_project"
- copy "file.txt" "backup/file.txt"
- list "/home/user/documents"
- search "." "*.py"
"""
    
    def get_safe_directories(self) -> List[str]:
        """Get list of safe directories for operations."""
        return [str(d) for d in self.safe_base_dirs if d.exists()]