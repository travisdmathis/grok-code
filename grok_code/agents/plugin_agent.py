"""Plugin-based agent - loads agent definition from plugin markdown files"""

import subprocess
from pathlib import Path
from typing import Callable, Optional, Set, List, Tuple

from .base import Agent, AgentType, AgentResult, BASE_AGENT_RULES
from ..plugins.loader import Agent as AgentDefinition
from ..ui.agents import show_agent_status


def check_file_syntax(file_path: str) -> Tuple[bool, str]:
    """
    Check a file for syntax errors.
    Returns (is_valid, error_message).
    """
    path = Path(file_path)
    if not path.exists():
        return True, ""  # File doesn't exist, skip

    suffix = path.suffix.lower()

    if suffix == ".py":
        # Python syntax check
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip()
                return False, f"Python syntax error in {path.name}:\n{error}"
        except subprocess.TimeoutExpired:
            return True, ""  # Timeout, assume OK
        except Exception:
            return True, ""  # Can't check, assume OK

    elif suffix in (".js", ".ts", ".jsx", ".tsx"):
        # JavaScript/TypeScript - try node syntax check
        try:
            if suffix == ".ts" or suffix == ".tsx":
                # TypeScript - check with tsc if available
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit", "--skipLibCheck", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                # JavaScript - use node --check
                result = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip()
                # Only return first few lines of error
                error_lines = error.split('\n')[:5]
                return False, f"Syntax error in {path.name}:\n" + '\n'.join(error_lines)
        except Exception:
            return True, ""  # Can't check, assume OK

    elif suffix == ".json":
        # JSON syntax check
        try:
            import json
            with open(path, 'r') as f:
                json.load(f)
        except json.JSONDecodeError as e:
            return False, f"JSON syntax error in {path.name}: {e}"
        except Exception:
            return True, ""

    return True, ""


def validate_modified_files(files: Set[str]) -> Tuple[bool, List[str]]:
    """
    Validate all modified files for syntax errors.
    Returns (all_valid, list_of_errors).
    """
    errors = []
    for file_path in files:
        is_valid, error = check_file_syntax(file_path)
        if not is_valid:
            errors.append(error)
    return len(errors) == 0, errors


class PluginAgent(Agent):
    """Agent that runs based on a plugin definition"""

    def __init__(
        self,
        definition: AgentDefinition,
        client,
        registry,
        agent_id: str = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(agent_id)
        self.definition = definition
        self.client = client
        self.registry = registry
        self._on_status = on_status
        self._cancel_check = None

    def set_cancel_check(self, callback):
        """Set callback to check if cancellation is requested"""
        self._cancel_check = callback

    @property
    def agent_type(self) -> AgentType:
        # Map plugin agents to closest type
        name = self.definition.name.lower()
        if "explore" in name:
            return AgentType.EXPLORE
        elif "plan" in name or "architect" in name:
            return AgentType.PLAN
        else:
            return AgentType.GENERAL

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def allowed_tools(self) -> list[str]:
        return self.definition.tools

    def _get_system_prompt(self) -> str:
        """Build the system prompt from the definition with base rules"""
        return BASE_AGENT_RULES + "\n---\n\n" + self.definition.prompt

    def _format_tool_label(self, tool_name: str, args: dict) -> str:
        """Format a tool call for display"""
        if tool_name == "read_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Read({short})"
        elif tool_name == "write_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Write({short})"
        elif tool_name == "edit_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Edit({short})"
        elif tool_name == "bash":
            cmd = args.get("command", "")[:40]
            return f"Bash({cmd}{'...' if len(args.get('command', '')) > 40 else ''})"
        elif tool_name == "glob":
            return f"Glob({args.get('pattern', '')})"
        elif tool_name == "grep":
            return f"Grep({args.get('pattern', '')[:30]})"
        else:
            return tool_name.replace("_", " ").title()

    async def run(self, prompt: str, context: dict | None = None) -> AgentResult:
        """Run the agent with the given prompt"""
        from ..client import Message

        # Build messages
        messages = [
            Message(role="system", content=self._get_system_prompt()),
            Message(role="user", content=prompt),
        ]

        # Add context if provided
        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            messages.insert(1, Message(role="user", content=f"Context:\n{context_str}"))

        # Get available tools for this agent
        # Empty/missing tools list means ALL tools available (easier for users)
        all_schemas = self.registry.get_schemas()
        if self.allowed_tools:
            # Filter to only specified tools
            tool_names = [t.lower() for t in self.allowed_tools]
            tools = [s for s in all_schemas if s["function"]["name"].lower() in tool_names]
        else:
            # No restriction - agent gets all tools
            tools = all_schemas

        # Run conversation loop
        full_output = ""
        max_turns = 50  # Increased for complex tasks
        tool_count = 0
        consecutive_no_tools = 0
        files_modified = set()  # Track files actually modified

        for turn in range(max_turns):
            # Check for cancellation
            if self.is_cancelled or (self._cancel_check and self._cancel_check()):
                self._cancelled = True
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    success=False,
                    output=full_output,
                    error="Agent was cancelled",
                )

            try:
                response = await self.client.chat(
                    messages=messages,
                    tools=tools if tools else None,
                )

                if response.content:
                    full_output += response.content + "\n"

                # Add assistant message
                messages.append(response)

                # Handle tool calls
                if response.tool_calls:
                    consecutive_no_tools = 0
                    for tool_call in response.tool_calls:
                        tool_count += 1
                        # Update status with current tool
                        tool_label = self._format_tool_label(tool_call.name, tool_call.arguments)
                        show_agent_status(self.agent_id, tool_label, tool_count)
                        if self._on_status:
                            self._on_status(tool_label)

                        # Track file modifications
                        if tool_call.name in ("edit_file", "write_file"):
                            file_path = tool_call.arguments.get("file_path", "")
                            if file_path:
                                files_modified.add(file_path)

                        # Intercept task_update to validate completion
                        if (
                            tool_call.name == "task_update"
                            and tool_call.arguments.get("status") == "completed"
                        ):
                            if not files_modified:
                                # Can't complete task without modifying files
                                result = "Error: Cannot mark task complete - no files have been modified. Use Edit or Write tools to make changes first."
                                messages.append(
                                    Message(
                                        role="tool",
                                        content=result,
                                        tool_call_id=tool_call.id,
                                        name=tool_call.name,
                                    )
                                )
                                continue

                            # Validate modified files have no syntax errors
                            all_valid, errors = validate_modified_files(files_modified)
                            if not all_valid:
                                error_msg = "Error: Cannot mark task complete - files have syntax errors that must be fixed first:\n\n"
                                error_msg += "\n\n".join(errors)
                                error_msg += "\n\nFix the errors and try again."
                                messages.append(
                                    Message(
                                        role="tool",
                                        content=error_msg,
                                        tool_call_id=tool_call.id,
                                        name=tool_call.name,
                                    )
                                )
                                continue

                        result = await self.registry.execute(tool_call.name, tool_call.arguments)
                        messages.append(
                            Message(
                                role="tool",
                                content=result,
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                            )
                        )
                else:
                    consecutive_no_tools += 1

                    # Before finishing, validate all modified files for syntax errors
                    if files_modified:
                        all_valid, errors = validate_modified_files(files_modified)
                        if not all_valid and consecutive_no_tools < 5:
                            # There are syntax errors - tell agent to fix them
                            error_msg = "STOP - You have syntax errors in your modified files that must be fixed:\n\n"
                            error_msg += "\n\n".join(errors)
                            error_msg += "\n\nFix these errors before finishing."
                            messages.append(Message(role="user", content=error_msg))
                            continue  # Continue the loop to let agent fix errors

                    # Check if there are still pending tasks
                    if "task_list" in [t.lower() for t in self.allowed_tools] or "task_update" in [
                        t.lower() for t in self.allowed_tools
                    ]:
                        try:
                            from ..tools.tasks import TaskStore, TaskStatus

                            store = TaskStore.get_instance()
                            pending = [
                                t
                                for t in store.list_all()
                                if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
                            ]
                            if pending and consecutive_no_tools < 3:
                                # Remind agent to continue working
                                task_names = ", ".join(
                                    [f"#{t.id}: {t.subject[:30]}" for t in pending[:3]]
                                )
                                messages.append(
                                    Message(
                                        role="user",
                                        content=f"You still have pending tasks: {task_names}. Continue implementing and mark them complete when done.",
                                    )
                                )
                                continue
                        except Exception:
                            pass
                    # No pending tasks or can't check - agent is done
                    break

            except Exception as e:
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    success=False,
                    output=full_output,
                    error=str(e),
                )

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            output=full_output.strip(),
        )
