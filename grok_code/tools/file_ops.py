"""File operation tools: Read, Write, Edit"""

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
        return "Read the contents of a file. Returns file contents as [line_num]│[content]. The content after │ is exact - use it directly for edit_file old_string."

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
        # Use │ as separator to make it clearer where content starts
        result = []
        for i, line in enumerate(selected_lines, start=start_idx + 1):
            result.append(f"{i:4}│{line.rstrip()}")

        if not result:
            return "(empty file)"

        # Detect indentation style
        indent_counts = {}
        for line in selected_lines:
            stripped = line.lstrip()
            if stripped and not stripped.startswith('#'):
                indent = len(line) - len(stripped)
                if indent > 0:
                    indent_counts[indent] = indent_counts.get(indent, 0) + 1

        output = "\n".join(result)

        # Add indentation hint for files with meaningful indentation
        if indent_counts:
            common_indents = sorted(indent_counts.keys())[:4]
            output += f"\n\n[Indentation: spaces before content shown exactly. Common indents: {common_indents}]"

        return output


class WriteTool(Tool):
    """Tool for writing/creating files"""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."
        )

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
        return """Edit a file by replacing a specific string with another.

CRITICAL: old_string must match EXACTLY including all indentation/whitespace.
When you read a file, output is: [line_num]│[content]. Copy the content AFTER the │ exactly.

Example - if read_file shows:
  42│    def foo(self):
  43│        return True

To edit line 43, old_string must be "        return True" (8 spaces before "return").
Include 2-3 lines of context to ensure unique match."""

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
                    "description": "The EXACT string to find, including all leading whitespace/indentation. Copy directly from read_file output (after the │ separator).",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement string. Must have correct indentation to match the file's style.",
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
            # Try to find similar content to help debug
            old_stripped = old_string.strip()
            hint = ""
            if old_stripped and old_stripped in content:
                # Found without leading/trailing whitespace - indentation issue
                # Find the actual line to show correct indentation
                for i, line in enumerate(content.split('\n')):
                    if old_stripped.split('\n')[0].strip() in line:
                        indent = len(line) - len(line.lstrip())
                        hint = f"\n\nHint: Found similar content but indentation doesn't match. Line {i+1} has {indent} spaces of indentation. Your old_string may have wrong indentation."
                        break
            elif len(old_string) > 20:
                # Try to find first line
                first_line = old_string.split('\n')[0].strip()
                if first_line in content:
                    for i, line in enumerate(content.split('\n')):
                        if first_line in line:
                            indent = len(line) - len(line.lstrip())
                            hint = f"\n\nHint: Found '{first_line[:40]}...' on line {i+1} with {indent} spaces indentation. Re-read the file and copy the exact whitespace."
                            break
            return f"Error: Could not find the specified string in {path}.{hint}"

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
