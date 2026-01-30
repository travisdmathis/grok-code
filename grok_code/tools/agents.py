"""Agent-related tools"""

from .base import Tool
from ..ui.agents import show_agent_start, show_agent_complete


class TaskTool(Tool):
    """Tool for spawning sub-agents"""

    def __init__(self, agent_runner=None):
        self._agent_runner = agent_runner

    def set_runner(self, runner):
        """Set the agent runner (called after initialization)"""
        self._agent_runner = runner

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return """Launch a sub-agent to handle tasks. Built-in agents:
- explore: Fast read-only codebase exploration
- plan: Creates implementation plans with task lists
- general: Full tool access for implementing features

Also supports custom project agents defined in .grok/agents/ (e.g., "engineer", "code-reviewer")."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "Agent to spawn: 'explore', 'plan', 'general', or custom agent name",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task/prompt for the agent, including any relevant context from the conversation",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "If true, run in background and return immediately with agent ID",
                },
            },
            "required": ["agent_type", "prompt"],
        }

    async def execute(
        self,
        agent_type: str,
        prompt: str,
        run_in_background: bool = False,
        subagent_type: str = None,  # Alias for agent_type
        description: str = None,
    ) -> str:
        if not self._agent_runner:
            return "Error: Agent runner not configured"

        # Handle alias
        agent_type = subagent_type or agent_type
        desc = description or prompt[:50]

        try:
            if run_in_background:
                agent_id = await self._agent_runner.run_agent_background(agent_type, prompt)
                show_agent_start(agent_id, agent_type, desc)
                return f"Agent started in background with ID: {agent_id}"
            else:
                # Show agent starting
                show_agent_start("sync", agent_type, desc)

                result = await self._agent_runner.run_agent(agent_type, prompt)

                # Show completion
                show_agent_complete("sync", result.success)

                if result.success:
                    return result.output
                else:
                    return f"Agent failed: {result.error}\n\nPartial output:\n{result.output}"
        except Exception as e:
            show_agent_complete("sync", False)
            return f"Error spawning agent: {e}"


class TaskOutputTool(Tool):
    """Tool for getting output from background agents"""

    def __init__(self, agent_runner=None):
        self._agent_runner = agent_runner

    def set_runner(self, runner):
        """Set the agent runner"""
        self._agent_runner = runner

    @property
    def name(self) -> str:
        return "task_output"

    @property
    def description(self) -> str:
        return "Get the output from a background agent by its ID"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "The agent ID returned from task tool",
                },
                "wait": {
                    "type": "boolean",
                    "description": "If true, wait for agent to complete. Default true.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds when waiting. Default 60.",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(
        self,
        agent_id: str,
        wait: bool = True,
        timeout: float = 60.0,
    ) -> str:
        if not self._agent_runner:
            return "Error: Agent runner not configured"

        # Check if already completed
        result = self._agent_runner.get_result(agent_id)
        if result:
            return f"Agent completed.\n\n{result.output}"

        # Check if running
        if agent_id not in self._agent_runner.get_running_agents():
            return f"Error: No agent found with ID {agent_id}"

        if not wait:
            return f"Agent {agent_id} is still running"

        # Wait for completion
        result = await self._agent_runner.wait_for_agent(agent_id, timeout=timeout)
        if result:
            return f"Agent completed.\n\n{result.output}"
        else:
            return f"Agent {agent_id} did not complete within {timeout} seconds"
