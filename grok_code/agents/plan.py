"""Plan agent for designing implementation approaches"""

import os
import re
from datetime import datetime
from pathlib import Path
from .base import Agent, AgentType, AgentResult


class PlanAgent(Agent):
    """Agent specialized for planning implementations"""

    def __init__(self, client, registry, agent_id: str | None = None, on_status=None):
        super().__init__(agent_id)
        self.client = client
        self.registry = registry
        self._on_status = on_status
        self._plan_file = None
        self._tasks = []

    def _update_status(self, status: str):
        """Update status via callback if available"""
        if self._on_status:
            self._on_status(status)

    @property
    def agent_type(self) -> AgentType:
        return AgentType.PLAN

    @property
    def description(self) -> str:
        return "Software architect agent for designing implementation plans"

    @property
    def allowed_tools(self) -> list[str]:
        return ["read_file", "glob", "grep", "write_file"]

    def _generate_plan_filename(self, prompt: str) -> str:
        """Generate a descriptive filename for the plan"""
        # Extract key words from prompt
        words = re.sub(r'[^\w\s]', '', prompt.lower()).split()
        # Take first few meaningful words
        keywords = [w for w in words if len(w) > 2 and w not in ('the', 'and', 'for', 'with', 'this', 'that')][:3]
        slug = '-'.join(keywords) if keywords else 'plan'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{slug}_{timestamp}.md"

    async def run(self, prompt: str, context: dict | None = None) -> AgentResult:
        """Run planning with the given prompt"""
        from ..client import Message
        from ..tools.tasks import TaskStore

        # Ensure plans directory exists
        plans_dir = Path.cwd() / ".grok" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        plan_filename = self._generate_plan_filename(prompt)
        self._plan_file = str(plans_dir / plan_filename)

        system_content = f"""You are a software architect planning agent. Your job is to create detailed implementation plans.

## Process
1. First, explore the codebase to understand existing patterns and architecture
2. Design a clear implementation approach
3. Create a structured plan with specific tasks

## Output Requirements
You MUST create a plan file at: {self._plan_file}

The plan file should follow this EXACT format:

```markdown
# [Plan Title]

## Overview
[1-2 paragraph summary of the approach]

## Files to Modify
- `path/to/file1.py` - [what changes]
- `path/to/file2.py` - [what changes]

## Implementation Tasks

- [ ] Task 1: [Clear, actionable task description]
- [ ] Task 2: [Clear, actionable task description]
- [ ] Task 3: [Clear, actionable task description]
...

## Testing Plan
[How to verify the implementation]

## Notes
[Any important considerations, edge cases, or warnings]
```

IMPORTANT:
- Use `- [ ]` for uncompleted tasks (checkbox format)
- Each task should be specific and actionable
- Tasks should be in logical order of execution
- After creating the plan file, output the task list so it appears in chat

Current working directory: {os.getcwd()}
"""

        messages = [
            Message(role="system", content=system_content),
            Message(role="user", content=prompt),
        ]

        # Get only allowed tools
        all_schemas = self.registry.get_schemas()
        tools = [t for t in all_schemas if t["function"]["name"] in self.allowed_tools]

        max_turns = 15
        full_output = []
        task_store = TaskStore.get_instance()

        for turn in range(max_turns):
            if self.is_cancelled:
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    success=False,
                    output="\n".join(full_output),
                    error="Agent cancelled",
                )

            self._update_status(f"Planning: thinking...")
            response = await self.client.chat(messages=messages, tools=tools)
            messages.append(response)

            if response.content:
                full_output.append(response.content)
                # Parse tasks from content if it contains checkbox format
                self._extract_and_create_tasks(response.content, task_store)

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
                elif tool_call.name == "write_file":
                    path = tool_call.arguments.get('file_path', '')
                    short_path = path.split('/')[-1] if '/' in path else path
                    tool_info = f"write({short_path})"
                    # Extract tasks from the file being written
                    content = tool_call.arguments.get('content', '')
                    self._extract_and_create_tasks(content, task_store)
                else:
                    tool_info = tool_call.name

                self._update_status(f"Planning: {tool_info}")

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

        # Format final output with task list
        final_output = "\n".join(full_output) if full_output else ""

        # Add task summary to output if tasks were created
        if self._tasks:
            final_output += "\n\n## Plan Tasks\n"
            # Get task IDs from store
            all_tasks = task_store.list_all()
            plan_tasks = [t for t in all_tasks if t.subject in self._tasks]
            for task in plan_tasks:
                final_output += f"@@PLAN_TASK@@ {task.id}|{task.status.value}|{task.subject}\n"

        if self._plan_file and Path(self._plan_file).exists():
            final_output += f"\n\n📋 Plan saved to: `{self._plan_file}`"

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            success=True,
            output=final_output if final_output else "Planning complete.",
        )

    def _extract_and_create_tasks(self, content: str, task_store) -> None:
        """Extract checkbox tasks from content and create them in task store"""
        # Match markdown checkbox format: - [ ] Task description
        task_pattern = r'- \[ \] (.+?)(?:\n|$)'
        matches = re.findall(task_pattern, content)

        for task_subject in matches:
            task_subject = task_subject.strip()
            if task_subject and task_subject not in self._tasks:
                # Create task in store
                task = task_store.create(
                    subject=task_subject,
                    description=f"Plan task: {task_subject}",
                    active_form=f"Working on: {task_subject[:40]}..."
                )
                self._tasks.append(task_subject)
