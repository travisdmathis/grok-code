"""Base agent class and types"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import uuid


# Base rules that apply to ALL agents
BASE_AGENT_RULES = """## Base Rules (Always Follow)
1. USE TOOLS TO DO WORK - You MUST use Edit/Write tools to make changes. Never just describe what you would do - actually do it with tools.
2. Read before modify - Always read a file before editing or writing to it.
3. Work autonomously - Don't ask for permission. Just do the work.
4. Be thorough - Complete the entire task. No placeholders or TODOs.
5. Mark tasks complete - ONLY mark a task complete AFTER you have used Edit/Write tools to implement it.
6. NO FAKE COMPLETIONS - If you didn't use Edit/Write to change files, you didn't complete the task.
7. FIX SYNTAX ERRORS - Your modified files will be checked for syntax errors. You cannot finish until all errors are fixed.

## CRITICAL: How to Edit Files Correctly
The edit_file tool requires EXACT string matching including all whitespace and indentation.

When you read a file, you see output like:
```
  42│    def my_function(self):
  43│        if condition:
  44│            do_something()
```

The format is: `[line_number]│[actual_file_content]`
Everything AFTER the │ is the actual file content including indentation.

To edit lines 43-44, your old_string must include the EXACT indentation:
- Line 43 has 8 spaces before "if"
- Line 44 has 12 spaces before "do_something"

CORRECT old_string:
```
        if condition:
            do_something()
```

WRONG old_string (missing proper indentation):
```
if condition:
    do_something()
```

**Rules for editing:**
- Copy the EXACT whitespace you see after the │ in read_file output
- Include enough context (2-3 lines) to make the match unique
- If edit fails, re-read the file and check your indentation carefully
- Count the spaces - Python files typically use 4-space indentation per level
"""


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
