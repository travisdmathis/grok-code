"""Base tool class for grokCode tools"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """Abstract base class for all tools"""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for the tool's parameters"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with the given arguments"""
        pass

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI-compatible tool schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
