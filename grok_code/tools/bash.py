"""Bash command execution tool"""

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import ClassVar

from .base import Tool


@dataclass
class BackgroundTask:
    """A background bash task"""

    id: str
    command: str
    task: asyncio.Task
    output: str = ""
    completed: bool = False
    exit_code: int | None = None


class BackgroundTaskManager:
    """Manages background bash tasks"""

    _instance: ClassVar["BackgroundTaskManager | None"] = None
    _tasks: ClassVar[dict[str, BackgroundTask]] = {}

    @classmethod
    def get_instance(cls) -> "BackgroundTaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_task(self, task: BackgroundTask) -> None:
        BackgroundTaskManager._tasks[task.id] = task

    def get_task(self, task_id: str) -> BackgroundTask | None:
        return BackgroundTaskManager._tasks.get(task_id)

    def list_tasks(self) -> list[BackgroundTask]:
        return list(BackgroundTaskManager._tasks.values())


class BashTool(Tool):
    """Tool for executing bash commands"""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Execute a bash command and return its output. Use for running scripts, git commands, package managers, etc."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default is 120.",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run command in background and return task ID immediately",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self, command: str, timeout: int = 120, run_in_background: bool = False
    ) -> str:
        # Safety check for obviously dangerous commands
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf /*",
            ":(){:|:&};:",
            "mkfs.",
            "dd if=/dev/zero",
            "> /dev/sda",
        ]
        cmd_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return "Error: Refusing to execute potentially dangerous command"

        # Check permission system
        from ..permissions import check_requires_permission

        allowed, message = check_requires_permission("bash", {"command": command})
        if not allowed:
            return f"⚠️  Permission required:\n{message}\n\nUse approve_operation tool to approve, or modify the command."

        # Background execution
        if run_in_background:
            return await self._run_background(command, timeout)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
                env=os.environ.copy(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: Command timed out after {timeout} seconds"

            output_parts = []

            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace")
                if stdout_text.strip():
                    output_parts.append(stdout_text)

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if proc.returncode != 0:
                output_parts.append(f"\nExit code: {proc.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            # Truncate if too long
            max_length = 50000
            if len(result) > max_length:
                result = (
                    result[:max_length] + f"\n\n... (truncated, {len(result)} total characters)"
                )

            return result

        except Exception as e:
            return f"Error executing command: {e}"

    async def _run_background(self, command: str, timeout: int) -> str:
        """Run a command in the background"""
        task_id = f"bg-{uuid.uuid4().hex[:8]}"
        manager = BackgroundTaskManager.get_instance()

        async def run_command():
            bg_task = manager.get_task(task_id)
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.getcwd(),
                    env=os.environ.copy(),
                )

                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

                output_parts = []
                if stdout:
                    output_parts.append(stdout.decode("utf-8", errors="replace"))
                if stderr:
                    output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

                if bg_task:
                    bg_task.output = "\n".join(output_parts) if output_parts else "(no output)"
                    bg_task.exit_code = proc.returncode
                    bg_task.completed = True

            except asyncio.TimeoutError:
                if bg_task:
                    bg_task.output = f"Error: Command timed out after {timeout} seconds"
                    bg_task.completed = True
            except Exception as e:
                if bg_task:
                    bg_task.output = f"Error: {e}"
                    bg_task.completed = True

        task = asyncio.create_task(run_command())
        bg_task = BackgroundTask(id=task_id, command=command, task=task)
        manager.add_task(bg_task)

        return f"Background task started with ID: {task_id}\nUse bash_output tool to check status."


class BashOutputTool(Tool):
    """Tool for getting output from background bash commands"""

    @property
    def name(self) -> str:
        return "bash_output"

    @property
    def description(self) -> str:
        return "Get output from a background bash command by its task ID"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID from run_in_background",
                },
                "wait": {
                    "type": "boolean",
                    "description": "Wait for completion if not done. Default true.",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str, wait: bool = True) -> str:
        manager = BackgroundTaskManager.get_instance()
        bg_task = manager.get_task(task_id)

        if not bg_task:
            return f"Error: No background task found with ID {task_id}"

        if not bg_task.completed and wait:
            try:
                await asyncio.wait_for(bg_task.task, timeout=300)
            except asyncio.TimeoutError:
                return f"Task {task_id} is still running after 5 minutes"

        if bg_task.completed:
            status = (
                f"Exit code: {bg_task.exit_code}" if bg_task.exit_code is not None else "Completed"
            )
            return f"Task {task_id} - {status}\n\n{bg_task.output}"
        else:
            return f"Task {task_id} is still running..."
