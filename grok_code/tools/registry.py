"""Tool registry for managing and executing tools"""


from .base import Tool


class ToolRegistry:
    """Registry for managing tools"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools"""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """Get OpenAI-compatible schemas for all tools"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name with arguments"""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"
        try:
            return await tool.execute(**arguments)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"


def create_default_registry(include_agent_tools: bool = True) -> ToolRegistry:
    """Create a registry with all default tools"""
    from .file_ops import ReadTool, WriteTool, EditTool, PyEditTool
    from .bash import BashTool, BashOutputTool
    from .glob_grep import GlobTool, GrepTool

    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(BashOutputTool())
    registry.register(GlobTool())
    registry.register(GrepTool())

    if include_agent_tools:
        from .agents import TaskTool, TaskOutputTool
        from .tasks import TaskCreateTool, TaskUpdateTool, TaskListTool, TaskGetTool
        from .plan_mode import EnterPlanModeTool, WritePlanTool, ExitPlanModeTool, AskUserTool
        from .web import WebFetchTool, WebSearchTool
        from .approve import ApproveOperationTool

        registry.register(TaskTool())
        registry.register(TaskOutputTool())
        registry.register(TaskCreateTool())
        registry.register(TaskUpdateTool())
        registry.register(TaskListTool())
        registry.register(TaskGetTool())
        registry.register(EnterPlanModeTool())
        registry.register(WritePlanTool())
        registry.register(ExitPlanModeTool())
        registry.register(AskUserTool())
        registry.register(WebFetchTool())
        registry.register(WebSearchTool())
        registry.register(ApproveOperationTool())

    return registry


def setup_agent_runner(registry: ToolRegistry, client) -> "AgentRunner":
    """Set up the agent runner and connect it to task tools"""
    from ..agents.runner import AgentRunner

    runner = AgentRunner(client, registry)

    # Connect runner to task tools
    task_tool = registry.get("task")
    if task_tool:
        task_tool.set_runner(runner)

    task_output_tool = registry.get("task_output")
    if task_output_tool:
        task_output_tool.set_runner(runner)

    return runner
