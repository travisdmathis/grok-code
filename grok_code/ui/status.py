"""Status bar - real-time status above input"""

import time
from typing import Optional
from dataclasses import dataclass

from rich.live import Live
from rich.text import Text

from .console import console


@dataclass
class SessionStats:
    """Track session statistics"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    requests: int = 0


class StatusBar:
    """Real-time status bar displayed above input"""

    # Spinner frames for different states
    SPINNERS = {
        "thinking": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "working": ["◐", "◓", "◑", "◒"],
        "searching": ["◜", "◠", "◝", "◞", "◡", "◟"],
    }

    def __init__(self):
        self.model: str = "grok-3"
        self.status: str = "idle"  # idle, thinking, working, searching
        self.current_action: str = ""
        self.start_time: Optional[float] = None
        self.stats = SessionStats()
        self._live: Optional[Live] = None
        self._spinner_idx = 0
        self._last_update = 0

    def set_model(self, model: str):
        """Set current model"""
        self.model = model

    def start_thinking(self):
        """Start thinking state"""
        self.status = "thinking"
        self.current_action = "Thinking"
        self.start_time = time.time()
        self._start_live()

    def start_working(self, action: str):
        """Start working on something"""
        self.status = "working"
        self.current_action = action
        if not self.start_time:
            self.start_time = time.time()
        self._refresh()

    def start_searching(self, query: str = ""):
        """Start searching"""
        self.status = "searching"
        self.current_action = f"Searching{': ' + query[:20] if query else ''}"
        if not self.start_time:
            self.start_time = time.time()
        self._refresh()

    def set_idle(self):
        """Return to idle state"""
        self.status = "idle"
        self.current_action = ""
        self.start_time = None
        self._stop_live()

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0):
        """Add token usage"""
        self.stats.input_tokens += input_tokens
        self.stats.output_tokens += output_tokens
        self.stats.requests += 1
        # Rough cost estimate (adjust for actual pricing)
        self.stats.total_cost += (input_tokens * 0.000003) + (output_tokens * 0.000015)
        self._refresh()

    def _get_spinner(self) -> str:
        """Get current spinner frame"""
        frames = self.SPINNERS.get(self.status, self.SPINNERS["thinking"])
        self._spinner_idx = (self._spinner_idx + 1) % len(frames)
        return frames[self._spinner_idx]

    def _format_time(self, seconds: float) -> str:
        """Format elapsed time"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"

    def _format_tokens(self, count: int) -> str:
        """Format token count"""
        if count < 1000:
            return str(count)
        elif count < 1000000:
            return f"{count/1000:.1f}k"
        else:
            return f"{count/1000000:.1f}M"

    def _render(self) -> Text:
        """Render the status bar"""
        text = Text()

        # Left side: status
        if self.status != "idle":
            spinner = self._get_spinner()
            elapsed = time.time() - self.start_time if self.start_time else 0

            # Spinner and action
            if self.status == "thinking":
                text.append(f" {spinner} ", style="cyan")
                text.append(self.current_action, style="cyan")
            elif self.status == "working":
                text.append(f" {spinner} ", style="yellow")
                text.append(self.current_action, style="yellow")
            elif self.status == "searching":
                text.append(f" {spinner} ", style="green")
                text.append(self.current_action, style="green")

            # Elapsed time
            text.append(f"  {self._format_time(elapsed)}", style="dim")

        else:
            text.append(" ● ", style="green")
            text.append("Ready", style="dim")

        # Spacer
        text.append("  │  ", style="dim")

        # Right side: model and tokens
        text.append(self.model, style="cyan")

        if self.stats.input_tokens > 0 or self.stats.output_tokens > 0:
            text.append("  ", style="dim")
            text.append("↑", style="dim cyan")
            text.append(self._format_tokens(self.stats.input_tokens), style="dim")
            text.append(" ↓", style="dim green")
            text.append(self._format_tokens(self.stats.output_tokens), style="dim")

        if self.stats.total_cost > 0.001:
            text.append(f"  ${self.stats.total_cost:.3f}", style="dim yellow")

        return text

    def _start_live(self):
        """Start live display"""
        if not self._live:
            self._live = Live(
                self._render(),
                console=console,
                refresh_per_second=8,
                transient=True,
            )
            self._live.start()

    def _stop_live(self):
        """Stop live display"""
        if self._live:
            self._live.stop()
            self._live = None

    def _refresh(self):
        """Refresh the display"""
        if self._live:
            self._live.update(self._render())

    def print_static(self):
        """Print static status (for when not live)"""
        console.print(self._render())


# Global instance
_status_bar: Optional[StatusBar] = None


def get_status_bar() -> StatusBar:
    """Get the global status bar"""
    global _status_bar
    if _status_bar is None:
        _status_bar = StatusBar()
    return _status_bar
