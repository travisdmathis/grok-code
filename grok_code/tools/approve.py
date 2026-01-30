"""Permission approval tool"""

from .base import Tool


class ApproveOperationTool(Tool):
    """Tool to approve dangerous operations"""

    @property
    def name(self) -> str:
        return "approve_operation"

    @property
    def description(self) -> str:
        return """Approve a dangerous operation that requires permission.
Use this when a tool returns a permission required message.
The user must explicitly confirm they want to proceed."""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "string",
                    "description": "The tool name (e.g., 'bash', 'write_file')",
                },
                "pattern": {
                    "type": "string",
                    "description": "The pattern to approve (from the permission message)",
                },
                "approve_all": {
                    "type": "boolean",
                    "description": "Approve all similar operations for this session",
                },
            },
            "required": ["tool"],
        }

    async def execute(self, tool: str, pattern: str = "", approve_all: bool = False) -> str:
        from ..permissions import PermissionManager

        manager = PermissionManager.get_instance()

        if approve_all:
            manager.approve_all_for_tool(tool)
            return f"✓ Approved all permission-requiring operations for '{tool}' tool this session"

        if pattern:
            manager.approve_pattern(tool, pattern)
            return f"✓ Approved pattern for '{tool}' tool: {pattern}"

        return """[APPROVAL REQUEST]
The assistant is requesting permission for a potentially dangerous operation.

Please respond with:
- 'yes' or 'approve' to allow this operation
- 'no' or 'deny' to block it
- 'always' to approve all similar operations this session

[END APPROVAL REQUEST]"""
