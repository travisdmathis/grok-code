"""Task tracking tools for managing work items"""

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar
import uuid

from .base import Tool


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELETED = "deleted"


@dataclass
class TaskItem:
    """A task/todo item"""
    id: str
    subject: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    active_form: str = ""
    owner: str = ""
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class TaskStore:
    """Global task storage"""
    _instance: ClassVar["TaskStore | None"] = None
    _tasks: ClassVar[dict[str, TaskItem]] = {}
    _counter: ClassVar[int] = 0

    @classmethod
    def get_instance(cls) -> "TaskStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create(self, subject: str, description: str, active_form: str = "") -> TaskItem:
        TaskStore._counter += 1
        task_id = str(TaskStore._counter)
        task = TaskItem(
            id=task_id,
            subject=subject,
            description=description,
            active_form=active_form or f"Working on: {subject}",
        )
        TaskStore._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> TaskItem | None:
        return TaskStore._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> TaskItem | None:
        task = TaskStore._tasks.get(task_id)
        if not task:
            return None

        if "status" in kwargs:
            status = kwargs["status"]
            if isinstance(status, str):
                if status == "deleted":
                    del TaskStore._tasks[task_id]
                    return task
                status = TaskStatus(status)
            task.status = status

        if "subject" in kwargs:
            task.subject = kwargs["subject"]
        if "description" in kwargs:
            task.description = kwargs["description"]
        if "active_form" in kwargs:
            task.active_form = kwargs["active_form"]
        if "owner" in kwargs:
            task.owner = kwargs["owner"]
        if "add_blocked_by" in kwargs:
            task.blocked_by.extend(kwargs["add_blocked_by"])
        if "add_blocks" in kwargs:
            task.blocks.extend(kwargs["add_blocks"])
        if "metadata" in kwargs:
            task.metadata.update(kwargs["metadata"])

        return task

    def list_all(self) -> list[TaskItem]:
        return [t for t in TaskStore._tasks.values() if t.status != TaskStatus.DELETED]

    def clear(self):
        TaskStore._tasks.clear()
        TaskStore._counter = 0


class TaskCreateTool(Tool):
    """Tool for creating tasks"""

    @property
    def name(self) -> str:
        return "task_create"

    @property
    def description(self) -> str:
        return "Create a new task to track work. Use for complex multi-step tasks."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief title for the task (imperative form, e.g., 'Fix login bug')",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what needs to be done",
                },
                "active_form": {
                    "type": "string",
                    "description": "Present continuous form for spinner (e.g., 'Fixing login bug')",
                },
            },
            "required": ["subject", "description"],
        }

    async def execute(self, subject: str, description: str, active_form: str = "") -> str:
        store = TaskStore.get_instance()
        task = store.create(subject, description, active_form)
        return f"Task #{task.id} created: {task.subject}"


class TaskUpdateTool(Tool):
    """Tool for updating tasks"""

    @property
    def name(self) -> str:
        return "task_update"

    @property
    def description(self) -> str:
        return "Update a task's status or details. Set status to 'in_progress' when starting, 'completed' when done."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to update",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "deleted"],
                    "description": "New status for the task",
                },
                "subject": {
                    "type": "string",
                    "description": "New subject for the task",
                },
                "description": {
                    "type": "string",
                    "description": "New description",
                },
                "add_blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that block this task",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str, **kwargs) -> str:
        store = TaskStore.get_instance()
        task = store.update(task_id, **kwargs)
        if not task:
            return f"Error: Task #{task_id} not found"

        if kwargs.get("status") == "deleted":
            return f"Task #{task_id} deleted"

        return f"Task #{task_id} updated: {task.subject} [{task.status.value}]"


class TaskListTool(Tool):
    """Tool for listing tasks"""

    @property
    def name(self) -> str:
        return "task_list"

    @property
    def description(self) -> str:
        return "List all current tasks with their status"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> str:
        store = TaskStore.get_instance()
        tasks = store.list_all()

        if not tasks:
            return "No tasks found"

        lines = []
        for task in tasks:
            status_icon = {
                TaskStatus.PENDING: "○",
                TaskStatus.IN_PROGRESS: "◐",
                TaskStatus.COMPLETED: "●",
            }.get(task.status, "?")

            blocked = f" (blocked by: {', '.join(task.blocked_by)})" if task.blocked_by else ""
            lines.append(f"#{task.id} {status_icon} [{task.status.value}] {task.subject}{blocked}")

        return "\n".join(lines)


class TaskGetTool(Tool):
    """Tool for getting task details"""

    @property
    def name(self) -> str:
        return "task_get"

    @property
    def description(self) -> str:
        return "Get full details of a specific task"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to retrieve",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str) -> str:
        store = TaskStore.get_instance()
        task = store.get(task_id)

        if not task:
            return f"Error: Task #{task_id} not found"

        lines = [
            f"Task #{task.id}: {task.subject}",
            f"Status: {task.status.value}",
            f"Description: {task.description}",
        ]

        if task.blocked_by:
            lines.append(f"Blocked by: {', '.join(task.blocked_by)}")
        if task.blocks:
            lines.append(f"Blocks: {', '.join(task.blocks)}")
        if task.owner:
            lines.append(f"Owner: {task.owner}")

        return "\n".join(lines)
