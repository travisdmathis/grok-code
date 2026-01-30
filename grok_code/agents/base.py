"""Base agent class and types"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class AgentType(Enum):
    """Types of agents available"""
    EXPLORE = "explore"
    PLAN = "plan"
    GENERAL = "general"
    BASH = "bash"


@dataclass
class AgentResult:
    """Result from an agent execution"""
    agent_id: str
    agent_type: AgentType
    success: bool
    output: str
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class Agent(ABC):
    """Base class for all agents"""

    def __init__(self, agent_id: str | None = None):
        self.agent_id = agent_id or str(uuid.uuid4())[:8]
        self._cancelled = False

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """The type of this agent"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this agent does"""
        pass

    @property
    @abstractmethod
    def allowed_tools(self) -> list[str]:
        """List of tool names this agent can use"""
        pass

    @abstractmethod
    async def run(self, prompt: str, context: dict | None = None) -> AgentResult:
        """Run the agent with the given prompt"""
        pass

    def cancel(self) -> None:
        """Cancel the agent's execution"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if the agent has been cancelled"""
        return self._cancelled
