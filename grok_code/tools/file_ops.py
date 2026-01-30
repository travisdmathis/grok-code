"""File operation tools: Read, Write, Edit"""

import os
from pathlib import Path
from typing import Set

from .base import Tool


# Track files that have been read in this session
# This prevents blind edits/writes without first reading the file
_read_files: Set[str] = set()


def mark_file_read(file_path: str) -> None:
    """Mark a file as having been read"""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    _read_files.add(str(path.resolve()))


def has_file_been_read(file_path: str) -> bool:
    """Check if a file has been read in this session"""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve()) in _read_files


def clear_read_files() -> None:
    """Clear the list of read files (e.g., on session reset)"""
    _read_files.clear()


def unmark_file_read(file_path: str) -> None:
    """Remove a file from the read list (e.g., after modification)"""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = str(path.resolve())
    if resolved in _read_files:
        _read_files.discard(resolved)


class ReadTool(Tool):
    """Tool for reading file contents"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file. Returns the file contents with line numbers."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to read (absolute or relative to cwd)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-indexed). Optional.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read. Optional.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self, file_path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Mark file as read for edit/write safety checks
            mark_file_read(str(path))
        except Exception as e:
            return f"Error reading file: {e}"

        # Apply offset and limit
        start_idx = (offset - 1) if offset and offset > 0 else 0
        end_idx = (start_idx + limit) if limit else len(lines)
        selected_lines = lines[start_idx:end_idx]

        # Format with line numbers
        result = []
        for i, line in enumerate(selected_lines, start=start_idx + 1):
            result.append(f"{i:6}\t{line.rstrip()}")

        return "\n".join(result) if result else "(empty file)"


class WriteTool(Tool):
    """Tool for writing/creating files"""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> str:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path

        # If file exists, it must have been read first before overwriting
        if path.exists() and not has_file_been_read(str(path)):
            return f"Error: Cannot write to {path} - file exists but has not been read first. Read the file before modifying it."

        try:
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            # Unmark file - must be read again before next modification
            unmark_file_read(str(path))
            return f"Successfully wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing file: {e}"


class EditTool(Tool):
    """Tool for editing files via string replacement"""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing a specific string with another. The old_string must match exactly (including whitespace)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to replace it with",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "If true, replace all occurrences. Default is false (replace first only).",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path

        if not path.exists():
            return f"Error: File not found: {path}"

        # File must have been read before editing
        if not has_file_been_read(str(path)):
            return f"Error: Cannot edit {path} - file has not been read first. Read the file before modifying it."

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return f"Error reading file: {e}"

        if old_string not in content:
            return f"Error: Could not find the specified string in {path}"

        # Count occurrences
        count = content.count(old_string)
        if count > 1 and not replace_all:
            return f"Error: Found {count} occurrences of the string. Use replace_all=true to replace all, or provide more context to make the match unique."

        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced_count = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced_count = 1

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            # Unmark file - must be read again before next modification
            unmark_file_read(str(path))
            return f"Successfully replaced {replaced_count} occurrence(s) in {path}"
        except Exception as e:
            return f"Error writing file: {e}"
