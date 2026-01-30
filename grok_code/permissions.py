"""Permission system for dangerous operations"""

import re
from dataclasses import dataclass, field
from typing import Callable, ClassVar


@dataclass
class PermissionRule:
    """A rule for requiring permission"""
    pattern: str
    description: str
    tool: str  # Tool this applies to, or "*" for all


class PermissionManager:
    """Manages permissions for dangerous operations"""

    _instance: ClassVar["PermissionManager | None"] = None

    def __init__(self):
        self._rules: list[PermissionRule] = []
        self._pending_approval: dict[str, tuple[str, str, dict]] = {}  # id -> (tool, description, args)
        self._approved_patterns: set[str] = set()
        self._confirmation_callback: Callable[[str, str], bool] | None = None
        self._init_default_rules()

    @classmethod
    def get_instance(cls) -> "PermissionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_default_rules(self):
        """Initialize default permission rules"""
        # Bash rules
        self.add_rule(PermissionRule(
            pattern=r"rm\s+-rf?\s+[/~]",
            description="Recursive delete in root or home directory",
            tool="bash",
        ))
        self.add_rule(PermissionRule(
            pattern=r"rm\s+-rf?\s+\*",
            description="Recursive delete with wildcard",
            tool="bash",
        ))
        self.add_rule(PermissionRule(
            pattern=r"chmod\s+-R\s+777",
            description="Recursive chmod 777",
            tool="bash",
        ))
        self.add_rule(PermissionRule(
            pattern=r"git\s+push\s+.*--force",
            description="Force push to git remote",
            tool="bash",
        ))
        self.add_rule(PermissionRule(
            pattern=r"git\s+reset\s+--hard",
            description="Hard reset git repository",
            tool="bash",
        ))
        self.add_rule(PermissionRule(
            pattern=r"DROP\s+(TABLE|DATABASE)",
            description="SQL DROP statement",
            tool="bash",
        ))

        # File rules
        self.add_rule(PermissionRule(
            pattern=r"\.env$|credentials|secret|password|api.?key",
            description="Writing to sensitive file",
            tool="write_file",
        ))

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a permission rule"""
        self._rules.append(rule)

    def set_confirmation_callback(self, callback: Callable[[str, str], bool]) -> None:
        """Set the callback for getting user confirmation"""
        self._confirmation_callback = callback

    def check_permission(self, tool: str, args: dict) -> tuple[bool, str | None]:
        """
        Check if operation requires permission.
        Returns (allowed, message).
        - (True, None) = allowed without confirmation
        - (False, message) = needs confirmation, message describes why
        """
        # Get the relevant string to check based on tool
        check_string = ""
        if tool == "bash":
            check_string = args.get("command", "")
        elif tool == "write_file":
            check_string = args.get("file_path", "")
        elif tool == "edit_file":
            check_string = args.get("file_path", "")

        if not check_string:
            return True, None

        # Check against rules
        for rule in self._rules:
            if rule.tool != "*" and rule.tool != tool:
                continue

            if re.search(rule.pattern, check_string, re.IGNORECASE):
                # Check if already approved
                approval_key = f"{tool}:{rule.pattern}"
                if approval_key in self._approved_patterns:
                    return True, None

                return False, f"⚠️  {rule.description}\n   Pattern: {check_string[:100]}"

        return True, None

    def approve_pattern(self, tool: str, pattern: str) -> None:
        """Mark a pattern as approved for this session"""
        self._approved_patterns.add(f"{tool}:{pattern}")

    def approve_all_for_tool(self, tool: str) -> None:
        """Approve all patterns for a tool (dangerous!)"""
        for rule in self._rules:
            if rule.tool == tool or rule.tool == "*":
                self._approved_patterns.add(f"{tool}:{rule.pattern}")

    def clear_approvals(self) -> None:
        """Clear all session approvals"""
        self._approved_patterns.clear()

    async def request_permission(self, tool: str, args: dict, description: str) -> bool:
        """
        Request permission for an operation.
        Returns True if approved, False if denied.
        """
        if self._confirmation_callback:
            return self._confirmation_callback(description, f"{tool}: {args}")

        # Default: require explicit approval via tool
        return False


def check_requires_permission(tool: str, args: dict) -> tuple[bool, str | None]:
    """Convenience function to check if operation requires permission"""
    manager = PermissionManager.get_instance()
    return manager.check_permission(tool, args)
