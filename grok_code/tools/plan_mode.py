"""Plan mode tools for structured planning workflow"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, List
import os

from .base import Tool


@dataclass
class PlanModeState:
    """Global plan mode state"""

    _instance: ClassVar["PlanModeState | None"] = None
    active: bool = False
    plan_file: str = ""
    plan_content: str = ""
    created_tasks: List[str] = field(default_factory=list)

    @classmethod
    def get_instance(cls) -> "PlanModeState":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def enter(self, plan_file: str = "") -> None:
        self.active = True
        self.created_tasks = []
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
        self.created_tasks = []

    def set_plan(self, content: str) -> int:
        """Set plan content and extract/create tasks. Returns number of tasks created."""
        self.plan_content = content
        if self.plan_file:
            Path(self.plan_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.plan_file, "w") as f:
                f.write(content)

        # Extract and create tasks from plan content
        return self._extract_and_create_tasks(content)

    def _extract_and_create_tasks(self, content: str) -> int:
        """Extract checkbox tasks from content and create them in task store"""
        from .tasks import TaskStore

        task_store = TaskStore.get_instance()

        # Match markdown checkbox format: - [ ] Task description
        task_pattern = r"- \[ \] (.+?)(?:\n|$)"
        matches = re.findall(task_pattern, content)

        created_count = 0
        for task_subject in matches:
            task_subject = task_subject.strip()
            if task_subject and task_subject not in self.created_tasks:
                # Create task in store
                task_store.create(
                    subject=task_subject,
                    description=f"Plan task: {task_subject}",
                    active_form=f"Working on: {task_subject[:40]}...",
                )
                self.created_tasks.append(task_subject)
                created_count += 1

        return created_count


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
4. Write your plan using write_plan tool (MUST include tasks)
5. Call exit_plan_mode when ready for user approval

## Plan Requirements:
Your plan MUST include a ## Tasks section with checkbox items:
```
## Tasks
- [ ] Task 1: Specific actionable task
- [ ] Task 2: Specific actionable task
- [ ] Task 3: Specific actionable task
```

Tasks will be automatically created for tracking when you write the plan.

Plan will be saved to: {state.plan_file}

DO NOT make any edits to code files while in plan mode."""


class WritePlanTool(Tool):
    """Tool to write the plan content"""

    @property
    def name(self) -> str:
        return "write_plan"

    @property
    def description(self) -> str:
        return """Write or update the implementation plan. Your plan MUST include:

## Required Format:
# [Plan Title]

## Overview
[1-2 paragraph summary]

## Files to Modify
- `path/to/file.py` - [what changes]

## Tasks
- [ ] Task 1: [Specific, actionable task]
- [ ] Task 2: [Specific, actionable task]
- [ ] Task 3: [Specific, actionable task]

Tasks are MANDATORY. Each task must be in `- [ ]` checkbox format.
Tasks will be automatically created for tracking."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The plan content in markdown format. MUST include ## Tasks section with - [ ] checkboxes.",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str) -> str:
        state = PlanModeState.get_instance()
        if not state.active:
            return "Error: Not in plan mode. Call enter_plan_mode first."

        # Check for tasks before saving
        task_pattern = r"- \[ \] .+"
        if not re.search(task_pattern, content):
            return """Error: Plan must include tasks in checkbox format.

Add a ## Tasks section with tasks like:
## Tasks
- [ ] Task 1: Description
- [ ] Task 2: Description
- [ ] Task 3: Description

Each task should be specific and actionable."""

        tasks_created = state.set_plan(content)
        return f"Plan saved to {state.plan_file}\n\nCreated {tasks_created} task(s) for tracking."


class ExitPlanModeTool(Tool):
    """Tool to exit plan mode and request approval"""

    @property
    def name(self) -> str:
        return "exit_plan_mode"

    @property
    def description(self) -> str:
        return "Exit plan mode and request user approval for your plan. The user will review your plan before you can proceed with implementation. Plan must have tasks before exiting."

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

        if not plan_content:
            return "Error: No plan was written. Use write_plan to create your plan first."

        if not state.created_tasks:
            return """Error: Plan has no tasks. Cannot exit plan mode without tasks.

Your plan must include a ## Tasks section with checkbox items:
## Tasks
- [ ] Task 1: Description
- [ ] Task 2: Description

Use write_plan again with proper task format."""

        # Get task info for display
        from .tasks import TaskStore
        task_store = TaskStore.get_instance()
        all_tasks = task_store.list_all()

        tasks_info = []
        for task_subject in state.created_tasks:
            matching = [t for t in all_tasks if t.subject == task_subject]
            if matching:
                tasks_info.append(f"  - #{matching[0].id}: {task_subject}")

        state.exit()

        return f"""Exiting plan mode.

[PLAN FOR USER APPROVAL]
{plan_content}
[END PLAN]

## Created Tasks:
{chr(10).join(tasks_info)}

📋 Plan saved to: {state.plan_file}

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
