"""Display - Polished terminal UI for grokCode"""

import sys
import os
import time
from typing import Optional, Callable

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.panel import Panel
from rich.style import Style

from .console import console
from .diff import show_diff, show_edit_preview, show_file_write
from .agents import show_agent_start, show_agent_tool, show_agent_complete, get_agent_display


class StreamingText:
    """Accumulates streamed text and renders it smoothly"""

    def __init__(self):
        self.content = ""
        self.live: Optional[Live] = None

    def start(self):
        """Start live display for streaming"""
        self.content = ""
        self.live = Live(
            Text(""),
            console=console,
            refresh_per_second=30,  # Smooth updates
            transient=False,
        )
        self.live.start()

    def update(self, chunk: str):
        """Add chunk and update display"""
        self.content += chunk
        if self.live:
            # Render as markdown for nice formatting
            try:
                self.live.update(Markdown(self.content))
            except Exception:
                self.live.update(Text(self.content))

    def stop(self):
        """Stop live display"""
        if self.live:
            self.live.stop()
            self.live = None


class ToolSpinner:
    """Elegant tool execution spinner"""

    def __init__(self, console: Console, label: str):
        self.console = console
        self.label = label
        self.live: Optional[Live] = None
        self.start_time = 0

    def __enter__(self):
        self.start_time = time.time()
        text = Text()
        text.append("  ")
        text.append(self.label, style="dim")
        self.spinner = Spinner("dots", text=text, style="cyan")
        self.live = Live(
            self.spinner,
            console=self.console,
            refresh_per_second=12,
            transient=True,  # Disappears when done
        )
        self.live.start()
        return self

    def __exit__(self, *args):
        if self.live:
            self.live.stop()


class Display:
    """Polished display for grokCode terminal UI"""

    def __init__(self):
        self.console = console
        self._streaming = StreamingText()
        self._tool_count = 0

    def welcome(self, project_files: list[str] = None, cwd: str = None):
        """Clean, minimal welcome"""
        cwd = cwd or os.getcwd()

        print()
        # App name and version - bold and clean
        console.print("[bold cyan]grokCode[/bold cyan] [dim]v0.1.0[/dim]")
        print()

        # Show loaded project files
        if project_files:
            for f in project_files:
                console.print(f"  [dim cyan]▸[/dim cyan] [dim]{f}[/dim]")
            print()

        # Working directory
        console.print(f"[dim]cwd: {cwd}[/dim]")
        print()

        # Subtle tip
        console.print("[dim]Tip: [cyan]/help[/cyan] for commands · [cyan]@[/cyan] to mention files · [cyan]![/cyan] for bash[/dim]")
        print()

    def prompt(self) -> str:
        """Return the prompt string"""
        return "[bold cyan]>[/bold cyan] "

    def user_message(self, text: str):
        """Display user message (for non-interactive mode)"""
        console.print(f"\n[bold]You:[/bold] {text}\n")

    def assistant_start(self):
        """Start assistant response"""
        self._streaming.start()

    def stream_content(self, text: str):
        """Stream content chunk - smooth rendering"""
        self._streaming.update(text)

    def assistant_end(self):
        """End assistant response"""
        self._streaming.stop()
        print()

    def thinking(self):
        """Return a thinking spinner context manager"""
        return ToolSpinner(self.console, "Thinking...")

    def tool_start(self, name: str, args: dict):
        """Start tool execution - returns context manager"""
        label = self._format_tool(name, args)
        return ToolSpinner(self.console, label)

    def tool_done(self, name: str, args: dict):
        """Show completed tool"""
        label = self._format_tool(name, args)
        console.print(f"  [green]✓[/green] [dim]{label}[/dim]")

    def tool_error(self, name: str, error: str):
        """Show tool error"""
        console.print(f"  [red]✗[/red] [dim]{name}:[/dim] [red]{error}[/red]")

    def tool_result(self, result: str, max_lines: int = 3):
        """Show brief tool result"""
        if not result or not result.strip():
            return

        lines = result.strip().split("\n")

        # For very short results, show inline
        if len(lines) == 1 and len(lines[0]) < 60:
            console.print(f"    [dim]→ {lines[0]}[/dim]")
        elif len(lines) > max_lines:
            # Just show count for long results
            console.print(f"    [dim]({len(lines)} lines)[/dim]")

    def _format_tool(self, name: str, args: dict) -> str:
        """Format tool name and args for display"""
        # Map tool names to clean labels
        formatters = {
            "read_file": lambda a: f"Read {self._short_path(a.get('file_path', ''))}",
            "write_file": lambda a: f"Write {self._short_path(a.get('file_path', ''))}",
            "edit_file": lambda a: f"Edit {self._short_path(a.get('file_path', ''))}",
            "bash": lambda a: f"$ {self._truncate(a.get('command', ''), 50)}",
            "glob": lambda a: f"Glob {a.get('pattern', '')}",
            "grep": lambda a: f"Grep {self._truncate(a.get('pattern', ''), 30)}",
            "web_search": lambda a: f"Search: {self._truncate(a.get('query', ''), 40)}",
            "web_fetch": lambda a: f"Fetch: {self._truncate(a.get('url', ''), 40)}",
            "task": lambda a: f"{a.get('agent_type', a.get('subagent_type', 'agent'))}: {self._truncate(a.get('prompt', a.get('description', '')), 30)}",
            "task_create": lambda a: f"Task: {self._truncate(a.get('subject', ''), 40)}",
            "task_update": lambda a: f"Update task #{a.get('taskId', '')}",
            "task_list": lambda a: "List tasks",
        }

        formatter = formatters.get(name)
        if formatter:
            return formatter(args)
        return name

    def _short_path(self, path: str) -> str:
        """Shorten path for display"""
        if not path:
            return ""
        parts = path.split("/")
        if len(parts) > 2:
            return f".../{'/'.join(parts[-2:])}"
        return path

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def summary(self, stats: dict):
        """Show session summary"""
        parts = []
        if stats.get("read"):
            n = stats["read"]
            parts.append(f"Read {n} file{'s' if n > 1 else ''}")
        if stats.get("edit"):
            n = stats["edit"]
            parts.append(f"Edited {n} file{'s' if n > 1 else ''}")
        if stats.get("write"):
            n = stats["write"]
            parts.append(f"Wrote {n} file{'s' if n > 1 else ''}")
        if stats.get("bash"):
            n = stats["bash"]
            parts.append(f"Ran {n} command{'s' if n > 1 else ''}")

        if parts:
            console.print(f"\n[dim]{' · '.join(parts)}[/dim]")

    def error(self, msg: str):
        """Display error"""
        console.print(f"[red]Error:[/red] {msg}")

    def warning(self, msg: str):
        """Display warning"""
        console.print(f"[yellow]Warning:[/yellow] {msg}")

    def success(self, msg: str):
        """Display success"""
        console.print(f"[green]✓[/green] {msg}")

    def info(self, msg: str):
        """Display info"""
        console.print(f"[dim]{msg}[/dim]")

    def code(self, code: str, language: str = "python"):
        """Display syntax-highlighted code"""
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        console.print(syntax)

    def divider(self):
        """Print a subtle divider"""
        console.print("[dim]─" * 40 + "[/dim]")

    def show_edit(self, filename: str, old_string: str, new_string: str):
        """Show edit preview with diff"""
        show_edit_preview(filename, old_string, new_string)

    def show_file_diff(self, old_content: str, new_content: str, filename: str):
        """Show full file diff"""
        show_diff(old_content, new_content, filename)

    def show_write(self, filename: str, content: str, is_new: bool = False):
        """Show file write with preview"""
        show_file_write(filename, content, is_new)

    def agent_start(self, agent_id: str, agent_type: str, description: str):
        """Show agent starting"""
        show_agent_start(agent_id, agent_type, description)

    def agent_tool(self, agent_id: str, tool_name: str, args: str = ""):
        """Show agent tool usage"""
        show_agent_tool(agent_id, tool_name, args)

    def agent_complete(self, agent_id: str, success: bool = True):
        """Show agent completion"""
        show_agent_complete(agent_id, success)
