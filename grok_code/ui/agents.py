"""Agent status display - shows background agents like Cursor"""

import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from .console import console


@dataclass
class AgentActivity:
    """Tracks an agent's current activity"""
    agent_id: str
    agent_type: str
    description: str
    status: str = "running"  # running, completed, error
    current_tool: Optional[str] = None
    tool_args: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    messages: list[str] = field(default_factory=list)
    tools_used: int = 0


class AgentStatusDisplay:
    """Displays real-time status of background agents"""

    def __init__(self):
        self._agents: Dict[str, AgentActivity] = {}
        self._live: Optional[Live] = None

    def add_agent(self, agent_id: str, agent_type: str, description: str):
        """Register a new background agent"""
        self._agents[agent_id] = AgentActivity(
            agent_id=agent_id,
            agent_type=agent_type,
            description=description[:50],
        )
        self._refresh()

    def update_agent(
        self,
        agent_id: str,
        current_tool: Optional[str] = None,
        tool_args: Optional[str] = None,
        message: Optional[str] = None,
    ):
        """Update agent's current activity"""
        if agent_id not in self._agents:
            return

        agent = self._agents[agent_id]
        if current_tool:
            agent.current_tool = current_tool
            agent.tool_args = tool_args
            agent.tools_used += 1
        if message:
            agent.messages.append(message)
            # Keep only last 3 messages
            agent.messages = agent.messages[-3:]

        self._refresh()

    def complete_agent(self, agent_id: str, success: bool = True):
        """Mark agent as completed"""
        if agent_id in self._agents:
            self._agents[agent_id].status = "completed" if success else "error"
            self._agents[agent_id].current_tool = None
            self._refresh()

    def remove_agent(self, agent_id: str):
        """Remove agent from display"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._refresh()

    def _render(self) -> Panel:
        """Render the agent status panel"""
        if not self._agents:
            return Panel(
                Text("No background agents", style="dim"),
                title="[bold cyan]Agents[/bold cyan]",
                border_style="dim",
            )

        rows = []
        for agent in self._agents.values():
            # Status indicator
            if agent.status == "running":
                status = Text("● ", style="yellow")
                if agent.current_tool:
                    status.append(f"{agent.agent_type}", style="cyan")
                    status.append(f" → {agent.current_tool}", style="dim")
                    if agent.tool_args:
                        status.append(f" {agent.tool_args[:30]}", style="dim italic")
                else:
                    status.append(f"{agent.agent_type}", style="cyan")
                    status.append(" thinking...", style="dim italic")
            elif agent.status == "completed":
                status = Text("✓ ", style="green")
                status.append(f"{agent.agent_type}", style="green")
                status.append(" done", style="dim")
            else:
                status = Text("✗ ", style="red")
                status.append(f"{agent.agent_type}", style="red")
                status.append(" error", style="dim")

            rows.append(status)

            # Show description
            rows.append(Text(f"  {agent.description}", style="dim"))

            # Show recent messages if any
            for msg in agent.messages[-2:]:
                rows.append(Text(f"  │ {msg[:60]}", style="dim italic"))

        content = Text()
        for i, row in enumerate(rows):
            content.append_text(row)
            if i < len(rows) - 1:
                content.append("\n")

        return Panel(
            content,
            title="[bold cyan]Background Agents[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    def _refresh(self):
        """Refresh the live display"""
        if self._live:
            self._live.update(self._render())

    def start(self):
        """Start the live display"""
        if self._agents:
            self._live = Live(
                self._render(),
                console=console,
                refresh_per_second=4,
                transient=False,
            )
            self._live.start()

    def stop(self):
        """Stop the live display"""
        if self._live:
            self._live.stop()
            self._live = None

    def show_once(self):
        """Show current status without live updates"""
        if self._agents:
            console.print(self._render())


# Global instance
_agent_display: Optional[AgentStatusDisplay] = None
_layout_callback = None  # Callback to the chat layout


def get_agent_display() -> AgentStatusDisplay:
    """Get the global agent status display"""
    global _agent_display
    if _agent_display is None:
        _agent_display = AgentStatusDisplay()
    return _agent_display


def set_layout_callback(callback):
    """Set the callback to the chat layout for agent UI updates"""
    global _layout_callback
    _layout_callback = callback


# Agent type to color mapping
AGENT_COLORS = {
    "explore": "#56b6c2",    # Cyan
    "plan": "#c678dd",       # Purple
    "general": "#61afef",    # Blue
    "code-reviewer": "#e06c75",  # Red
    "default": "#5f9ea0",    # Teal
}


def show_agent_start(agent_id: str, agent_type: str, description: str, color: str = None):
    """Show that an agent has started"""
    if _layout_callback and hasattr(_layout_callback, 'set_agent'):
        # Use provided color, or look up by agent type, or fall back to default
        resolved_color = color or AGENT_COLORS.get(agent_type, AGENT_COLORS["default"])
        _layout_callback.set_agent(agent_type, description, resolved_color)


def show_agent_status(agent_id: str, status: str, tool_count: int = 0):
    """Update the agent's current status text"""
    if _layout_callback and hasattr(_layout_callback, 'update_agent_status'):
        _layout_callback.update_agent_status(status, tool_count)


def show_agent_tool(agent_id: str, tool_name: str, tool_args: str = ""):
    """Show agent tool usage"""
    # Tool calls are handled by add_tool_call in the layout
    pass


def show_agent_complete(agent_id: str, success: bool = True):
    """Show agent completion"""
    if _layout_callback and hasattr(_layout_callback, 'clear_agent'):
        _layout_callback.clear_agent()
