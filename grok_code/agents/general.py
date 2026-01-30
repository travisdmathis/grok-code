"""General agent - full-featured agent with access to all tools"""

import os
from .base import Agent, AgentType, AgentResult, BASE_AGENT_RULES
from .plugin_agent import validate_modified_files


class GeneralAgent(Agent):
    """General-purpose agent with access to all tools"""

    def __init__(self, client, registry, agent_id: str | None = None, on_status=None):
        super().__init__(agent_id)
        self.client = client
        self.registry = registry
        self._on_status = on_status
        self._cancel_check = None

    def set_cancel_check(self, callback):
        """Set callback to check if cancellation is requested"""
        self._cancel_check = callback

    def _update_status(self, status: str):
        """Update status via callback if available"""
        if self._on_status:
            self._on_status(status)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.GENERAL

    @property
    def description(self) -> str:
        return "General-purpose agent with full tool access for implementing features and fixes"

    @property
    def allowed_tools(self) -> list[str]:
        # All tools - no restrictions
        return []

    async def run(self, prompt: str, context: dict | None = None) -> AgentResult:
        """Run the agent with full tool access"""
        from ..client import Message

        system_content = f"""{BASE_AGENT_RULES}

You are a general-purpose coding agent with full access to all tools.

Your job is to implement features, fix bugs, and complete coding tasks autonomously.

## Workflow
1. Read and understand existing code before making changes
2. Make edits using edit_file or write_file
3. Test your changes with bash if appropriate
4. Complete the task fully - no placeholders or TODOs

## Tools Available
- read_file, write_file, edit_file: File operations
- glob, grep: Search and find files
- bash: Run commands
- task_create, task_update, task_list, task_get: Track work

Current working directory: {os.getcwd()}
"""

        messages = [
            Message(role="system", content=system_content),
            Message(role="user", content=prompt),
        ]

        # Add context if provided
        if context:
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            messages.insert(1, Message(role="user", content=f"Context:\n{context_str}"))

        # Get ALL tools (no filtering)
        tools = self.registry.get_schemas()

        max_turns = 30
        full_output = []
        tool_count = 0
        files_modified = set()

        for turn in range(max_turns):
            if self.is_cancelled or (self._cancel_check and self._cancel_check()):
                self._cancelled = True
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    success=False,
                    output="\n".join(full_output),
                    error="Agent cancelled",
                )

            self._update_status("Thinking...")
            response = await self.client.chat(messages=messages, tools=tools)
            messages.append(response)

            if response.content:
                full_output.append(response.content)

            if not response.tool_calls:
                # Before finishing, validate all modified files
                if files_modified:
                    all_valid, errors = validate_modified_files(files_modified)
                    if not all_valid:
                        # There are syntax errors - tell agent to fix them
                        error_msg = "STOP - You have syntax errors in your modified files that must be fixed:\n\n"
                        error_msg += "\n\n".join(errors)
                        error_msg += "\n\nFix these errors before finishing."
                        messages.append(Message(role="user", content=error_msg))
                        continue  # Continue the loop to let agent fix errors
                break

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_count += 1
                # Format tool info for status
                tool_info = self._format_tool_status(tool_call.name, tool_call.arguments)
                self._update_status(tool_info)

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

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            output="\n".join(full_output) if full_output else "Task complete.",
        )

    def _format_tool_status(self, name: str, args: dict) -> str:
        """Format tool call for status display"""
        if name == "read_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Read({short})"
        elif name == "write_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Write({short})"
        elif name == "edit_file":
            path = args.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            return f"Edit({short})"
        elif name == "bash":
            cmd = args.get("command", "")[:30]
            return f"Bash({cmd}{'...' if len(args.get('command', '')) > 30 else ''})"
        elif name == "glob":
            return f"Glob({args.get('pattern', '')})"
        elif name == "grep":
            return f"Grep({args.get('pattern', '')[:20]})"
        else:
            return name.replace("_", " ").title()
