"""Explore agent for codebase exploration"""

import os
from .base import Agent, AgentType, AgentResult


class ExploreAgent(Agent):
    """Agent specialized for exploring codebases"""

    def __init__(self, client, registry, agent_id: str | None = None, on_status=None):
        super().__init__(agent_id)
        self.client = client
        self.registry = registry
        self._on_status = on_status  # Callback for status updates

    def _update_status(self, status: str):
        """Update status via callback if available"""
        if self._on_status:
            self._on_status(status)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.EXPLORE

    @property
    def description(self) -> str:
        return "Fast agent for exploring codebases - finding files, searching code, understanding structure"

    @property
    def allowed_tools(self) -> list[str]:
        return ["read_file", "glob", "grep"]

    async def run(self, prompt: str, context: dict | None = None) -> AgentResult:
        """Run exploration with the given prompt"""
        from ..client import Message
        from ..conversation import SYSTEM_PROMPT

        system_content = f"""You are an exploration agent. Your job is to explore codebases and find information.

You have access to these tools:
- read_file: Read file contents
- glob: Find files by pattern
- grep: Search file contents

Be thorough but efficient. Search multiple patterns if needed. Summarize your findings clearly.

Current working directory: {os.getcwd()}
"""

        messages = [
            Message(role="system", content=system_content),
            Message(role="user", content=prompt),
        ]

        # Get only allowed tools
        all_schemas = self.registry.get_schemas()
        tools = [t for t in all_schemas if t["function"]["name"] in self.allowed_tools]

        max_turns = 10
        full_output = []

        for turn in range(max_turns):
            if self.is_cancelled:
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    success=False,
                    output="\n".join(full_output),
                    error="Agent cancelled",
                )

            self._update_status(f"Agent explore: thinking...")
            response = await self.client.chat(messages=messages, tools=tools)
            messages.append(response)

            if response.content:
                full_output.append(response.content)

            if not response.tool_calls:
                break

            # Execute tool calls
            for tool_call in response.tool_calls:
                # Format tool info for status
                if tool_call.name == "glob":
                    tool_info = f"glob({tool_call.arguments.get('pattern', '')})"
                elif tool_call.name == "grep":
                    tool_info = f"grep({tool_call.arguments.get('pattern', '')[:30]})"
                elif tool_call.name == "read_file":
                    path = tool_call.arguments.get('file_path', '')
                    short_path = path.split('/')[-1] if '/' in path else path
                    tool_info = f"read({short_path})"
                else:
                    tool_info = tool_call.name

                self._update_status(f"Agent explore: {tool_info}")

                if tool_call.name not in self.allowed_tools:
                    result = f"Error: Tool {tool_call.name} not allowed for this agent"
                else:
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
            output="\n".join(full_output) if full_output else "Exploration complete.",
        )
