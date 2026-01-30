"""Rich console configuration"""

from rich.console import Console
from rich.theme import Theme

# Custom theme for grokCode - clean and minimal
GROK_THEME = Theme(
    {
        # Primary colors
        "grok": "bold bright_cyan",
        "grok.dim": "cyan",
        "user": "bold bright_green",

        # Tool colors
        "tool": "yellow",
        "tool.name": "bold yellow",
        "tool.arg": "dim yellow",
        "tool.result": "dim",

        # Status colors
        "error": "bold red",
        "warning": "yellow",
        "success": "bold green",
        "info": "dim white",

        # UI elements
        "border": "dim cyan",
        "muted": "dim",
        "highlight": "bold white",

        # Code
        "code": "bright_cyan",
        "path": "underline cyan",

        # Spinners
        "spinner": "cyan",
    }
)

# Global console instance
console = Console(theme=GROK_THEME, highlight=True, soft_wrap=True)
