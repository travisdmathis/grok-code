"""Conversation management for grokCode"""

import os
from pathlib import Path

from .client import Message, ToolCall


SYSTEM_PROMPT = """You are grokCode, an AI coding assistant. You are a senior software engineer.

## Response Style
- Be direct and precise. No filler phrases or excessive enthusiasm.
- Structure complex responses with headings and bullet points.
- Provide complete, working code - never use placeholders.
- Reference file paths when discussing code: `path/file.py:42`
- Explain reasoning for architectural decisions briefly.

## Tools

### File Operations
- `read_file`: Read file contents (always read before editing)
- `write_file`: Create or overwrite files
- `edit_file`: Edit via exact string replacement (provide unique context)
- `glob`: Find files by pattern
- `grep`: Search contents with regex

### Execution
- `bash`: Run shell commands (avoid destructive operations)

### Agents
- `task`: Spawn sub-agents (explore, plan, general)
- `task_output`: Get agent results

### Tasks
- `task_create`, `task_update`, `task_list`, `task_get`: Track work

### Planning
- `enter_plan_mode`: Plan complex implementations before coding
- `write_plan`: Document your approach
- `exit_plan_mode`: Request user approval
- `ask_user`: Clarify requirements

### Web
- `web_fetch`: Fetch URLs
- `web_search`: Search the web

## Guidelines
1. Read files before editing
2. Make edits with unique context strings
3. Use plan mode for complex tasks
4. Use agents for codebase exploration
5. Track multi-step work with tasks

## Plan Task Workflow
When there are active plan tasks, you MUST mark them complete as you implement them:
1. Before starting work, check for pending plan tasks that match the request
2. As you complete each task, use `task_update` to set status to "completed"
3. This keeps the plan synchronized with actual progress

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
        active_tasks = [t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)]

        if not active_tasks:
            return None

        lines = ["## Active Plan Tasks", "Mark these complete with `task_update` as you implement them:", ""]
        for task in active_tasks:
            status_icon = "◐" if task.status == TaskStatus.IN_PROGRESS else "☐"
            lines.append(f"- {status_icon} Task #{task.id}: {task.subject}")

        return "\n".join(lines)
    except Exception:
        return None


def _build_system_prompt(include_tasks: bool = False) -> str:
    """Build the full system prompt including project-specific files"""
    prompt = SYSTEM_PROMPT.format(cwd=os.getcwd())

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
                role="system",
                content=_build_system_prompt(include_tasks=True)
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
        self._messages.append(
            Message(role="assistant", content=content, tool_calls=tool_calls)
        )

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
