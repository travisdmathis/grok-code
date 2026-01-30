"""Agent runner for managing and executing agents"""

import asyncio
from dataclasses import dataclass
from typing import Callable

from .base import Agent, AgentType, AgentResult
from .explore import ExploreAgent
from .plan import PlanAgent
from .plugin_agent import PluginAgent


@dataclass
class RunningAgent:
    """Represents a running agent"""

    agent: Agent
    task: asyncio.Task
    prompt: str


class AgentRunner:
    """Manages agent lifecycle and execution"""

    def __init__(self, client, registry):
        self.client = client
        self.registry = registry
        self._running_agents: dict[str, RunningAgent] = {}
        self._completed_results: dict[str, AgentResult] = {}
        self._plugin_registry = None
        self._on_status = None  # Status callback
        self._current_agent: Agent | None = None  # Currently running agent for cancellation
        self._cancel_check = None  # Callback to check if cancellation requested

    def set_plugin_registry(self, plugin_registry):
        """Set the plugin registry for loading plugin agents"""
        self._plugin_registry = plugin_registry

    def set_status_callback(self, callback):
        """Set callback for status updates from agents"""
        self._on_status = callback

    def set_cancel_check(self, callback):
        """Set callback to check if cancellation is requested"""
        self._cancel_check = callback

    def cancel_current(self):
        """Cancel the currently running agent"""
        if self._current_agent:
            self._current_agent.cancel()

    def create_agent(self, agent_type: AgentType | str) -> Agent:
        """Create an agent of the specified type or name"""
        # First check if it's a plugin agent name
        if isinstance(agent_type, str) and self._plugin_registry:
            plugin_agent_def = self._plugin_registry.get_agent(agent_type)
            if plugin_agent_def:
                return PluginAgent(
                    plugin_agent_def, self.client, self.registry, on_status=self._on_status
                )

        # Handle built-in agent types
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type)
            except ValueError:
                # Unknown type, default to explore
                agent_type = AgentType.EXPLORE

        if agent_type == AgentType.EXPLORE:
            return ExploreAgent(self.client, self.registry, on_status=self._on_status)
        elif agent_type == AgentType.PLAN:
            return PlanAgent(self.client, self.registry, on_status=self._on_status)
        else:
            # Default to explore for general purpose
            return ExploreAgent(self.client, self.registry, on_status=self._on_status)

    async def run_agent(
        self,
        agent_type: AgentType | str,
        prompt: str,
        context: dict | None = None,
        on_complete: Callable[[AgentResult], None] | None = None,
    ) -> AgentResult:
        """Run an agent synchronously and return the result"""
        agent = self.create_agent(agent_type)
        self._current_agent = agent

        # Pass cancel check to agent if it supports it
        if self._cancel_check and hasattr(agent, "set_cancel_check"):
            agent.set_cancel_check(self._cancel_check)

        try:
            result = await agent.run(prompt, context)
        finally:
            self._current_agent = None

        self._completed_results[agent.agent_id] = result

        if on_complete:
            on_complete(result)

        return result

    async def run_agent_background(
        self,
        agent_type: AgentType | str,
        prompt: str,
        context: dict | None = None,
    ) -> str:
        """Run an agent in the background, return agent ID immediately"""
        agent = self.create_agent(agent_type)

        async def run_and_store():
            result = await agent.run(prompt, context)
            self._completed_results[agent.agent_id] = result
            if agent.agent_id in self._running_agents:
                del self._running_agents[agent.agent_id]
            return result

        task = asyncio.create_task(run_and_store())
        self._running_agents[agent.agent_id] = RunningAgent(agent=agent, task=task, prompt=prompt)

        return agent.agent_id

    async def run_agents_parallel(
        self,
        tasks: list[tuple[AgentType | str, str]],
    ) -> list[AgentResult]:
        """Run multiple agents in parallel"""

        async def run_one(agent_type: AgentType | str, prompt: str) -> AgentResult:
            return await self.run_agent(agent_type, prompt)

        results = await asyncio.gather(
            *[run_one(agent_type, prompt) for agent_type, prompt in tasks]
        )
        return list(results)

    def get_running_agents(self) -> list[str]:
        """Get IDs of currently running agents"""
        return list(self._running_agents.keys())

    def get_result(self, agent_id: str) -> AgentResult | None:
        """Get result for a completed agent"""
        return self._completed_results.get(agent_id)

    async def wait_for_agent(
        self, agent_id: str, timeout: float | None = None
    ) -> AgentResult | None:
        """Wait for a background agent to complete"""
        if agent_id in self._completed_results:
            return self._completed_results[agent_id]

        running = self._running_agents.get(agent_id)
        if not running:
            return None

        try:
            if timeout:
                result = await asyncio.wait_for(running.task, timeout=timeout)
            else:
                result = await running.task
            return result
        except asyncio.TimeoutError:
            return None

    def cancel_agent(self, agent_id: str) -> bool:
        """Cancel a running agent"""
        running = self._running_agents.get(agent_id)
        if not running:
            return False

        running.agent.cancel()
        running.task.cancel()
        del self._running_agents[agent_id]
        return True
