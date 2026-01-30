"""Code diff display - shows changes elegantly like Cursor"""

import difflib
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax

from .console import console


def show_diff(
    old_content: str,
    new_content: str,
    filename: str,
    context_lines: int = 3,
):
    """Display a beautiful code diff"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )

    if not diff:
        console.print(f"  [dim]No changes to {filename}[/dim]")
        return

    # Build styled diff output
    output = Text()

    for line in diff:
        line = line.rstrip("\n")

        if line.startswith("+++") or line.startswith("---"):
            output.append(line + "\n", style="bold")
        elif line.startswith("@@"):
            output.append(line + "\n", style="cyan")
        elif line.startswith("+"):
            output.append(line + "\n", style="green")
        elif line.startswith("-"):
            output.append(line + "\n", style="red")
        else:
            output.append(line + "\n", style="dim")

    console.print(
        Panel(
            output,
            title=f"[bold]{filename}[/bold]",
            border_style="dim",
            padding=(0, 1),
        )
    )


def show_edit_preview(
    filename: str,
    old_string: str,
    new_string: str,
):
    """Show a preview of an edit operation"""
    console.print()
    console.print(f"  [bold]Edit:[/bold] {filename}")
    console.print()

    # Show what's being replaced
    console.print("  [red]- Remove:[/red]")
    for line in old_string.split("\n")[:5]:
        console.print(f"    [red]{line}[/red]")
    if old_string.count("\n") > 5:
        console.print(f"    [dim]... +{old_string.count(chr(10)) - 5} lines[/dim]")

    console.print()
    console.print("  [green]+ Add:[/green]")
    for line in new_string.split("\n")[:5]:
        console.print(f"    [green]{line}[/green]")
    if new_string.count("\n") > 5:
        console.print(f"    [dim]... +{new_string.count(chr(10)) - 5} lines[/dim]")

    console.print()


def show_file_write(filename: str, content: str, is_new: bool = False):
    """Show file write with syntax highlighting preview"""
    action = "Create" if is_new else "Write"
    console.print()
    console.print(f"  [bold]{action}:[/bold] {filename}")

    # Detect language from extension
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    lang_map = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "jsx": "jsx",
        "json": "json",
        "md": "markdown",
        "yaml": "yaml",
        "yml": "yaml",
        "sh": "bash",
        "bash": "bash",
        "rs": "rust",
        "go": "go",
        "rb": "ruby",
        "html": "html",
        "css": "css",
    }
    lang = lang_map.get(ext, "text")

    # Show preview of content
    lines = content.split("\n")
    preview = "\n".join(lines[:10])
    if len(lines) > 10:
        preview += f"\n... +{len(lines) - 10} more lines"

    syntax = Syntax(preview, lang, theme="monokai", line_numbers=True)
    console.print(Panel(syntax, border_style="green", padding=(0, 1)))
