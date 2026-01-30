"""Conversation management for grokCode"""

import os
from pathlib import Path

from .client import Message, ToolCall


SYSTEM_PROMPT = """You are grokCode, an AI coding assistant that orchestrates work through specialized agents.

## CRITICAL: You are a COORDINATOR, not an implementer
You do NOT have write access to files. You MUST delegate all coding work to agents using the `task` tool.
NEVER attempt to use write_file or edit_file yourself - they will fail.

## Built-in Agents (use via `task` tool)
- `explore` - Read-only codebase exploration (glob, grep, read_file)
- `plan` - Creates implementation plans with task lists
- `general` - FULL tool access, implements features and fixes

## How to Spawn Agents
Use the `task` tool to spawn agents. Include relevant context from the conversation in the prompt:

Example: task(agent_type="general", prompt="Implement the login feature. Context: We discussed using JWT tokens stored in httpOnly cookies. The auth module is in src/auth/...")

## IMPORTANT: @agent: Mentions
When the user mentions `@agent:name` in their message, DO NOT immediately spawn the agent.
Instead:
1. First respond to the user - acknowledge their request
2. If context is unclear, ASK what they want the agent to do
3. Only spawn the agent AFTER you understand the full task

The @agent: syntax is a HINT about which agent to use, not a command to immediately execute.
You should still have a conversation with the user to understand the task before delegating.

## Standard Workflow
1. User describes what they want
2. Clarify requirements if needed
3. Use `explore` agent to understand the codebase (if needed)
4. Use `plan` agent to create a plan with tasks
5. Present plan, ask for approval
6. After approval, spawn `general` (or user-specified agent) to implement

## Response Style
- Be direct and concise
- Reference file paths: `path/file.py:42`
- When spawning agents, briefly explain what you're doing
- ALWAYS respond to the user first before spawning agents

## Your Tools
- `task`: Spawn agents (explore, plan, general, or custom project agents)
- `task_output`: Get background agent results
- `read_file`, `glob`, `grep`: Basic exploration
- `bash`: Read-only commands (git status, ls, etc.)
- `task_list`, `task_get`: Check task status

Working directory: {cwd}
"""


def _read_project_file(filename: str) -> str | None:
    """Read a project configuration file if it exists"""
    filepath = Path.cwd() / ".grok" / filename
    if filepath.exists() and filepath.is_file():
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _get_active_plan_tasks() -> str | None:
    """Get active plan tasks for context injection"""
    try:
        from .tools.tasks import TaskStore, TaskStatus

        store = TaskStore.get_instance()
        tasks = store.list_all()

        # Filter to pending/in_progress tasks
        active_tasks = [
            t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]

        if not active_tasks:
            return None

        lines = [
            "## Active Plan Tasks",
            "Mark these complete with `task_update` as you implement them:",
            "",
        ]
        for task in active_tasks:
            status_icon = "◐" if task.status == TaskStatus.IN_PROGRESS else "☐"
            lines.append(f"- {status_icon} Task #{task.id}: {task.subject}")

        return "\n".join(lines)
    except Exception:
        return None


def _get_available_agents() -> str | None:
    """Get available project agents for the system prompt"""
    try:
        from .plugins.registry import PluginRegistry

        registry = PluginRegistry.get_instance()
        agents = registry.list_agents()

        if not agents:
            return None

        lines = ["## Project Agents (in addition to built-in agents)"]
        for agent in agents:
            lines.append(f"- `@agent:{agent.name}` - {agent.description}")

        return "\n".join(lines)
    except Exception:
        return None


def _build_system_prompt(include_tasks: bool = False) -> str:
    """Build the full system prompt including project-specific files"""
    prompt = SYSTEM_PROMPT.format(cwd=os.getcwd())

    # Include available project agents
    agents_context = _get_available_agents()
    if agents_context:
        prompt += f"\n\n{agents_context}\n"

    # Read project-specific configuration files
    grok_md = _read_project_file("GROK.md")
    workflow_md = _read_project_file("WORKFLOW.md")

    if grok_md or workflow_md:
        prompt += "\n\n---\n\n## Project Configuration\n"

    if grok_md:
        prompt += f"\n### Project Context (.grok/GROK.md)\n{grok_md}\n"

    if workflow_md:
        prompt += f"\n### Workflow Instructions (.grok/WORKFLOW.md)\n{workflow_md}\n"

    # Include active plan tasks if requested
    if include_tasks:
        tasks_context = _get_active_plan_tasks()
        if tasks_context:
            prompt += f"\n\n---\n\n{tasks_context}\n"

    return prompt


class Conversation:
    """Manages conversation history and messages"""

    def __init__(self):
        self._messages: list[Message] = []
        self._project_files_loaded: list[str] = []
        self._init_system_prompt()

    def _init_system_prompt(self) -> None:
        """Initialize with system prompt including project files"""
        system_content = _build_system_prompt(include_tasks=True)

        # Track which project files were loaded
        self._project_files_loaded = []
        if _read_project_file("GROK.md"):
            self._project_files_loaded.append(".grok/GROK.md")
        if _read_project_file("WORKFLOW.md"):
            self._project_files_loaded.append(".grok/WORKFLOW.md")

        self._messages.append(Message(role="system", content=system_content))

    def refresh_task_context(self) -> None:
        """Refresh the system prompt with current task state"""
        if self._messages and self._messages[0].role == "system":
            self._messages[0] = Message(
                role="system", content=_build_system_prompt(include_tasks=True)
            )

    @property
    def loaded_project_files(self) -> list[str]:
        """Return list of project files that were loaded"""
        return self._project_files_loaded.copy()

    def add_user_message(self, content: str) -> None:
        """Add a user message"""
        self._messages.append(Message(role="user", content=content))

    def add_assistant_message(
        self, content: str | None = None, tool_calls: list[ToolCall] | None = None
    ) -> None:
        """Add an assistant message"""
        self._messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_result(self, tool_call_id: str, name: str, result: str) -> None:
        """Add a tool result message"""
        self._messages.append(
            Message(role="tool", content=result, tool_call_id=tool_call_id, name=name)
        )

    def get_messages(self) -> list[Message]:
        """Get all messages"""
        return self._messages.copy()

    def clear(self) -> None:
        """Clear conversation history (keeps system prompt)"""
        self._messages = []
        self._init_system_prompt()

    def __len__(self) -> int:
        return len(self._messages)
