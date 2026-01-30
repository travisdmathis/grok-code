"""File search tools: Glob and Grep"""

import fnmatch
import os
import re
from pathlib import Path

from .base import Tool


class GlobTool(Tool):
    """Tool for finding files by pattern"""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return 'Find files matching a glob pattern (e.g., "**/*.py" for all Python files)'

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": 'The glob pattern to match (e.g., "**/*.py", "src/**/*.ts")',
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in. Defaults to current directory.",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str | None = None) -> str:
        search_path = Path(path).expanduser() if path else Path.cwd()
        if not search_path.is_absolute():
            search_path = Path.cwd() / search_path

        if not search_path.exists():
            return f"Error: Directory not found: {search_path}"

        try:
            matches = list(search_path.glob(pattern))
            # Sort by modification time, most recent first
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Limit results
            max_results = 100
            if len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True
            else:
                truncated = False

            if not matches:
                return f"No files found matching pattern: {pattern}"

            # Format output with relative paths
            results = []
            for match in matches:
                try:
                    rel_path = match.relative_to(search_path)
                except ValueError:
                    rel_path = match
                results.append(str(rel_path))

            output = "\n".join(results)
            if truncated:
                output += f"\n\n... (showing first {max_results} of {len(list(search_path.glob(pattern)))} matches)"

            return output

        except Exception as e:
            return f"Error searching: {e}"


class GrepTool(Tool):
    """Tool for searching file contents"""

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search for a pattern in file contents. Returns matching lines with file paths and line numbers."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in. Defaults to current directory.",
                },
                "glob": {
                    "type": "string",
                    "description": 'File pattern to filter (e.g., "*.py"). Defaults to all files.',
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Case-insensitive search. Default is false.",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        ignore_case: bool = False,
    ) -> str:
        search_path = Path(path).expanduser() if path else Path.cwd()
        if not search_path.is_absolute():
            search_path = Path.cwd() / search_path

        if not search_path.exists():
            return f"Error: Path not found: {search_path}"

        try:
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results = []
        max_matches = 100
        files_searched = 0
        binary_extensions = {".png", ".jpg", ".gif", ".pdf", ".zip", ".tar", ".gz", ".exe", ".bin"}

        def search_file(file_path: Path) -> list[str]:
            matches = []
            if file_path.suffix.lower() in binary_extensions:
                return matches
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            try:
                                rel_path = file_path.relative_to(search_path)
                            except ValueError:
                                rel_path = file_path
                            matches.append(f"{rel_path}:{line_num}: {line.rstrip()}")
            except (OSError, IOError):
                pass
            return matches

        if search_path.is_file():
            results.extend(search_file(search_path))
        else:
            # Search directory
            glob_pattern = glob or "**/*"
            for file_path in search_path.glob(glob_pattern):
                if file_path.is_file():
                    files_searched += 1
                    results.extend(search_file(file_path))
                    if len(results) >= max_matches:
                        break

        if not results:
            return f"No matches found for pattern: {pattern}"

        output = "\n".join(results[:max_matches])
        if len(results) > max_matches:
            output += f"\n\n... (showing first {max_matches} of {len(results)} matches)"

        return output
