"""Permission system for dangerous operations"

import re
from dataclasses import dataclass
from typing import Callable, ClassVar
import json
from pathlib import Path


@dataclass
class PermissionRule:
    \"\"\"A rule for requiring permission\"\"\"

    pattern: str
    description: str
    tool: str  # Tool this applies to, or "*" for all


class PermissionManager:
    \"\"\"Manages permissions for dangerous operations\"\"\"

    _instance: ClassVar[\"PermissionManager | None\"] = None

    def __init__(self):
        self._rules: list[PermissionRule] = []
        self._pending_approval: dict[str, tuple[str, str, dict]] = (
            {}
        )  # id -> (tool, description, args)
        self._approved_patterns: set[str] = set()
        self._confirmation_callback: Callable[[str, str], bool] | None = None
        self._init_default_rules()
        self._load()

    @classmethod
    def get_instance(cls) -> \"PermissionManager\":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_default_rules(self):
        \"\"\"Initialize default permission rules\"\"\"
        # Bash rules
        self.add_rule(
            PermissionRule(
                pattern=r\"rm\\\\s+-rf?\\\\s+[/~]\",
                description=\"Recursive delete in root or home directory\",
                tool=\"bash\",
            )
        )
        self.add_rule(
            PermissionRule(
                pattern=r\"rm\\\\s+-rf?\\\\s+\\\\*\",