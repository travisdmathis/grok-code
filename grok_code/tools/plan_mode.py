"""Plan mode tools for structured planning workflow"""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
import os

from .base import Tool


@dataclass
class PlanModeState:
    """Global plan mode state"""

    _instance: ClassVar["PlanModeState | None"] = None
    active: bool = False
    plan_file: str = ""
    plan_content: str = ""

    @classmethod
    def get_instance(cls) -> "PlanModeState":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def enter(self, plan_file: str = "") -> None:
        self.active = True
        if not plan_file:
            # Store plans in project's .grok/plans/ directory
            plan_dir = Path(os.getcwd()) / ".grok" / "plans"
            plan_dir.mkdir(parents=True, exist_ok=True)
            import uuid

            plan_file = str(plan_dir / f"plan-{uuid.uuid4().hex[:8]}.md")
        self.plan_file = plan_file
        self.plan_content = ""

    def exit(self) -> None:
        self.active = False

    def set_plan(self, content: str) -> None:
        self.plan_content = content
        if self.plan_file:
            Path(self.plan_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.plan_file, "w") as f:
                f.write(content)


class EnterPlanModeTool(Tool):
    """Tool to enter plan mode"""

    @property
    def name(self) -> str:
        return "enter_plan_mode"

    @property
    def description(self) -> str:
        return """Enter plan mode for complex implementation tasks. Use this when:
- Adding new features that need architectural decisions
- Multiple valid approaches exist
- Changes affect multiple files
- Requirements need clarification

In plan mode, explore the codebase, design an approach, and get user approval before implementing."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> str:
        state = PlanModeState.get_instance()
        state.enter()
        return f"""Entered plan mode.

In plan mode:
1. Use read_file, glob, grep to explore the codebase
2. Use task agent to explore complex areas
3. Design your implementation approach
4. Write your plan using write_plan tool
5. Call exit_plan_mode when ready for user approval

Plan will be saved to: {state.plan_file}

DO NOT make any edits to code files while in plan mode."""


class WritePlanTool(Tool):
    """Tool to write the plan content"""

    @property
    def name(self) -> str:
        return "write_plan"

    @property
    def description(self) -> str:
        return (
            "Write or update the implementation plan. Call this to document your planned approach."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The plan content in markdown format",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str) -> str:
        state = PlanModeState.get_instance()
        if not state.active:
            return "Error: Not in plan mode. Call enter_plan_mode first."

        state.set_plan(content)
        return f"Plan saved to {state.plan_file}"


class ExitPlanModeTool(Tool):
    """Tool to exit plan mode and request approval"""

    @property
    def name(self) -> str:
        return "exit_plan_mode"

    @property
    def description(self) -> str:
        return "Exit plan mode and request user approval for your plan. The user will review your plan before you can proceed with implementation."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> str:
        state = PlanModeState.get_instance()
        if not state.active:
            return "Error: Not in plan mode."

        plan_content = state.plan_content
        state.exit()

        if not plan_content:
            return "Warning: No plan was written. Exiting plan mode anyway."

        return f"""Exiting plan mode.

[PLAN FOR USER APPROVAL]
{plan_content}
[END PLAN]

Waiting for user approval. The user should respond with:
- 'approve' or 'yes' to proceed with implementation
- 'reject' or 'no' to cancel
- Feedback/changes to request modifications"""


class AskUserTool(Tool):
    """Tool to ask user questions"""

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return "Ask the user a question to clarify requirements or get their preference between options."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of choices for the user",
                },
            },
            "required": ["question"],
        }

    async def execute(self, question: str, options: list[str] | None = None) -> str:
        output = f"[QUESTION FOR USER]\n{question}"
        if options:
            output += "\n\nOptions:"
            for i, opt in enumerate(options, 1):
                output += f"\n  {i}. {opt}"
        output += "\n[END QUESTION]"
        return output
