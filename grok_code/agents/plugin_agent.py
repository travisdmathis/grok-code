"""Plugin-based agent - loads agent definition from plugin markdown files"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .base import Agent, AgentType, AgentResult, BASE_AGENT_RULES
from ..plugins.loader import Agent as AgentDefinition
from ..ui.agents import show_agent_status


class PluginAgent(Agent):
    """Agent that runs based on a plugin definition"""

    def __init__(self, definition: AgentDefinition, client, registry, agent_id: str = None,
                 on_status: Optional[Callable[[str], None]] = None):
        super().__init__(agent_id)
        self.definition = definition
        self.client = client
        self.registry = registry
        self._on_status = on_status

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
        tools = []
        if self.allowed_tools:
            all_schemas = self.registry.get_schemas()
            tool_names = [t.lower() for t in self.allowed_tools]
            tools = [s for s in all_schemas if s["function"]["name"].lower() in tool_names]

        # Run conversation loop
        full_output = ""
        max_turns = 20
        tool_count = 0

        for _ in range(max_turns):
            if self.is_cancelled:
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
                    for tool_call in response.tool_calls:
                        tool_count += 1
                        # Update status with current tool
                        tool_label = self._format_tool_label(tool_call.name, tool_call.arguments)
                        show_agent_status(self.agent_id, tool_label, tool_count)
                        if self._on_status:
                            self._on_status(tool_label)

                        result = await self.registry.execute(
                            tool_call.name, tool_call.arguments
                        )
                        messages.append(
                            Message(
                                role="tool",
                                content=result,
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                            )
                        )
                else:
                    # No tool calls, agent is done
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
