"""Permission system for tool approvals"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Set, Tuple
from enum import Enum


class ApprovalMode(Enum):
    AUTO = "auto"      # Auto-accept all (except dangerous)
    APPROVE = "approve"  # Require approval for writes
    MANUAL = "manual"    # Require approval for everything


@dataclass
class PermissionRule:
    """A rule for requiring permission"""
    pattern: str
    description: str
    tool: str  # Tool this applies to, or "*" for all
    always_dangerous: bool = True  # If True, always requires approval regardless of mode


# Dangerous commands that ALWAYS require approval
DANGEROUS_BASH_PATTERNS = [
    (r"rm\s+-rf?\s+[/~]", "Recursive delete in root or home directory"),
    (r"rm\s+-rf?\s+\*", "Recursive delete with wildcard"),
    (r"rm\s+-rf?\s+\.\.", "Recursive delete of parent directory"),
    (r"sudo\s+rm\b", "Sudo remove command"),
    (r":\(\)\s*\{", "Fork bomb pattern"),
    (r"mkfs\.", "Filesystem formatting command"),
    (r"dd\s+if=/dev/", "Raw disk write"),
    (r"chmod\s+-R\s+777", "Recursive chmod 777"),
    (r"chown\s+-R\s+root", "Recursive chown to root"),
    (r"git\s+push\s+.*--force", "Force push to git"),
    (r"git\s+reset\s+--hard", "Hard reset git"),
    (r"git\s+clean\s+-fd", "Clean untracked files"),
    (r"drop\s+database", "Drop database"),
    (r"drop\s+table", "Drop table"),
    (r"truncate\s+table", "Truncate table"),
    (r">\s*/dev/sd[a-z]", "Write to block device"),
]

DANGEROUS_FILE_PATTERNS = [
    (r"^/(etc|sys|proc|dev|boot)/", "Write to system directory"),
    (r"\.ssh/", "Write to SSH directory"),
    (r"\.aws/", "Write to AWS credentials"),
    (r"\.env$", "Write to environment file"),
    (r"credentials", "Write to credentials file"),
    (r"\.pem$", "Write to PEM key file"),
]


class PermissionManager:
    """Manages permissions for tool operations"""

    _instance: ClassVar[Optional["PermissionManager"]] = None
    PERMS_PATH = Path(".grok/permissions.json")

    def __init__(self):
        self.mode: ApprovalMode = ApprovalMode.APPROVE  # Default to approve mode
        self.session_approvals: Dict[str, Set[str]] = {}  # tool -> set of approved patterns
        self.persistent_approvals: Dict[str, Set[str]] = {}  # Saved to file
        self._load()

    @classmethod
    def get_instance(cls) -> "PermissionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton for testing"""
        cls._instance = None

    def set_mode(self, mode: ApprovalMode):
        """Set the approval mode"""
        self.mode = mode

    def _is_dangerous_bash(self, command: str) -> Optional[str]:
        """Check if bash command is dangerous. Returns description if dangerous."""
        for pattern, desc in DANGEROUS_BASH_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return desc
        return None

    def _is_dangerous_file(self, path: str) -> Optional[str]:
        """Check if file path is dangerous. Returns description if dangerous."""
        for pattern, desc in DANGEROUS_FILE_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                return desc
        return None

    def _get_approval_key(self, tool: str, args: dict) -> str:
        """Generate a key for approval lookup"""
        if tool == "bash":
            cmd = args.get("command", "")
            # Use first word as key for session/persistent approval
            parts = cmd.strip().split()
            return parts[0] if parts else "bash"
        elif tool in ("write_file", "edit_file"):
            path = args.get("file_path", "")
            # Use directory pattern for approval
            if "/" in path:
                parts = path.rsplit("/", 1)
                return parts[0] + "/*"
            return path
        return tool

    def check_permission(self, tool: str, args: dict) -> Tuple[bool, Optional[str], str]:
        """
        Check if tool call needs approval.
        Returns: (allowed, danger_reason, approval_key)
        - allowed: True if can proceed without approval
        - danger_reason: If not None, this is a dangerous operation (always needs approval)
        - approval_key: Key to use for "always" approval
        """
        approval_key = self._get_approval_key(tool, args)

        # Check for dangerous operations (always need approval)
        danger_reason = None
        if tool == "bash":
            danger_reason = self._is_dangerous_bash(args.get("command", ""))
        elif tool in ("write_file", "edit_file"):
            danger_reason = self._is_dangerous_file(args.get("file_path", ""))

        if danger_reason:
            # Dangerous operations always need approval, check if already approved
            if self._is_approved(tool, approval_key):
                return True, None, approval_key
            return False, danger_reason, approval_key

        # Auto mode: allow everything except dangerous
        if self.mode == ApprovalMode.AUTO:
            return True, None, approval_key

        # Check if already approved (session or persistent)
        if self._is_approved(tool, approval_key):
            return True, None, approval_key

        # Approve mode: only writes need approval
        if self.mode == ApprovalMode.APPROVE:
            if tool in ("write_file", "edit_file", "bash"):
                return False, None, approval_key
            return True, None, approval_key

        # Manual mode: everything needs approval
        return False, None, approval_key

    def _is_approved(self, tool: str, key: str) -> bool:
        """Check if a tool/key combo is approved"""
        # Check session approvals
        if tool in self.session_approvals and key in self.session_approvals[tool]:
            return True
        # Check persistent approvals
        if tool in self.persistent_approvals and key in self.persistent_approvals[tool]:
            return True
        return False

    def approve(self, tool: str, key: str, persistent: bool = False):
        """Approve a tool/key combo"""
        # Session approval
        if tool not in self.session_approvals:
            self.session_approvals[tool] = set()
        self.session_approvals[tool].add(key)

        # Persistent approval (save to file)
        if persistent:
            if tool not in self.persistent_approvals:
                self.persistent_approvals[tool] = set()
            self.persistent_approvals[tool].add(key)
            self._save()

    def deny(self, tool: str, key: str):
        """Deny a tool/key combo (remove from approvals)"""
        if tool in self.session_approvals:
            self.session_approvals[tool].discard(key)
        if tool in self.persistent_approvals:
            self.persistent_approvals[tool].discard(key)
            self._save()

    def _load(self):
        """Load persistent approvals from file"""
        if self.PERMS_PATH.exists():
            try:
                data = json.loads(self.PERMS_PATH.read_text())
                mode_str = data.get("mode", "approve")
                try:
                    self.mode = ApprovalMode(mode_str)
                except ValueError:
                    self.mode = ApprovalMode.APPROVE
                self.persistent_approvals = {
                    k: set(v) for k, v in data.get("approvals", {}).items()
                }
            except Exception:
                pass  # Use defaults

    def _save(self):
        """Save persistent approvals to file"""
        self.PERMS_PATH.parent.mkdir(exist_ok=True, parents=True)
        data = {
            "mode": self.mode.value,
            "approvals": {k: list(v) for k, v in self.persistent_approvals.items()}
        }
        self.PERMS_PATH.write_text(json.dumps(data, indent=2))

    def save_mode(self):
        """Save current mode to file"""
        self._save()


def format_tool_for_approval(tool: str, args: dict) -> str:
    """Format a tool call for approval display"""
    if tool == "bash":
        cmd = args.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        return f"bash: {cmd}"
    elif tool == "write_file":
        path = args.get("file_path", "")
        content = args.get("content", "")
        lines = len(content.split("\n"))
        return f"write: {path} ({lines} lines)"
    elif tool == "edit_file":
        path = args.get("file_path", "")
        old = args.get("old_string", "")
        if len(old) > 30:
            old = old[:27] + "..."
        return f"edit: {path}"
    else:
        return f"{tool}: {str(args)[:60]}"
